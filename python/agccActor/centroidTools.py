"""Centroiding and photometry utilities for AGCC source detection."""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
import sep
import yaml
from pfs.utils.datamodel.ag import SourceDetectionFlag

logger = logging.getLogger("agcc")


def getCentroidParams(cmd: Any) -> dict[str, Any]:
    """Read centroiding parameters from config and optional command overrides.

    Parameters
    ----------
    cmd : Any
        Parsed tron command object.

    Returns
    -------
    dict[str, Any]
        Centroid parameter dictionary.
    """

    try:
        cmdKeys = cmd.cmd.keywords
    except Exception:
        cmdKeys = []

    fileName = os.path.join(os.environ["PFS_INSTDATA_DIR"], "config/actors", "agcc.yaml")

    with open(fileName, "r") as inFile:
        defaultParms = yaml.safe_load(inFile)

    # returns just the values dictionary
    centParms = defaultParms["agcc"]["centroidParams"]

    if "nmin" in cmdKeys:
        centParms["nmin"] = int(cmd.cmd.keywords["nmin"].values[0])
    if "thresh" in cmdKeys:
        centParms["thresh"] = float(cmd.cmd.keywords["thresh"].values[0])
    if "deblend" in cmdKeys:
        centParms["deblend"] = float(cmd.cmd.keywords["deblend"].values[0])

    return centParms


def getImageParams(cmd: Any) -> dict[str, Any]:
    """Read instrumental image parameters from config.

    Parameters
    ----------
    cmd : Any
        Parsed tron command object (currently unused).

    Returns
    -------
    dict[str, Any]
        Camera parameter dictionary loaded from config.
    """

    fileName = os.path.join(os.environ["PFS_INSTDATA_DIR"], "config/actors", "agcc.yaml")

    with open(fileName, "r") as inFile:
        imageParms = yaml.safe_load(inFile)

    return imageParms["agcc"]["cameraParams"]


def interpBadCol(data: np.ndarray, badCols: list[int]) -> np.ndarray:
    """Interpolate over bad columns in-place by linear averaging of neighbours.

    Parameters
    ----------
    data : numpy.ndarray
        2-D image array (modified in-place).
    badCols : list[int]
        Column indices to interpolate.

    Returns
    -------
    numpy.ndarray
        The modified ``data`` array (same object).
    """

    for i in badCols:
        data[:, i] = (data[:, i - 1] + data[:, i + 1]) / 2
    return data


def subOverscan(data: np.ndarray) -> np.ndarray:
    """Subtract the overscan bias level from each half of the image.

    The left half uses the median of its first 4 columns as the bias level;
    the right half uses the median of its last 4 columns.

    Parameters
    ----------
    data : numpy.ndarray
        2-D image array (modified in-place).

    Returns
    -------
    numpy.ndarray
        The bias-subtracted ``data`` array (same object).
    """

    h, w = data.shape
    side0 = data[:, : w // 2]
    side1 = data[:, w // 2 :]
    bg0 = np.median(side0[:, :4]).astype(data.dtype)
    bg1 = np.median(side1[:, -4:]).astype(data.dtype)

    data[:, : w // 2] -= bg0
    data[:, w // 2 :] -= bg1

    return data


def centroidRegion(
    data: np.ndarray,
    thresh: float,
    minarea: int,
    deblend: float,
) -> tuple[np.ndarray, int, np.ndarray]:
    """Subtract the background and extract sources from a sub-image region.

    Parameters
    ----------
    data : numpy.ndarray
        2-D sub-image array (modified in-place by background subtraction).
    thresh : float
        Detection threshold in units of background RMS.
    minarea : int
        Minimum number of connected pixels for a valid source.
    deblend : float
        Deblending contrast ratio passed to ``sep.extract``.

    Returns
    -------
    tuple[numpy.ndarray, int, numpy.ndarray]
        Structured SEP source array, number of sources detected, and the
        background image array.
    """

    # determine the background
    bgClass = sep.Background(data)
    background = bgClass.back()
    rms = bgClass.rms()
    bgClass.subfrom(data)

    # get spots using sourcing extractor defaults
    spots = sep.extract(data, thresh, rms, minarea=minarea, deblend_cont=deblend)

    # get windowed positions for the spots
    return spots, len(spots), background


def getCentroidsSep(
    data: np.ndarray,
    iParms: dict[str, Any],
    cParms: dict[str, Any],
    spotDtype: np.dtype,
    agcid: int,
) -> np.ndarray:
    """Run SEP centroiding on one camera frame and return a structured result.

    Parameters
    ----------
    data : numpy.ndarray
        Raw 2-D image array from the camera.
    iParms : dict[str, Any]
        Image/instrument parameters (regions, bad columns, saturation values).
    cParms : dict[str, Any]
        Centroid parameters (threshold, min area, deblend, ellipticity).
    spotDtype : numpy.dtype
        Structured dtype for the output array.
    agcid : int
        Zero-based AG camera identifier.

    Returns
    -------
    numpy.ndarray
        Structured array of centroid results with shape ``(nSpots,)``.
    """

    thresh = cParms["thresh"]
    minarea = cParms["minarea"]
    deblend = cParms["deblend"]
    ellip = cParms["ellip"]
    nmin = cParms["nmin"]

    # get region information for camera
    region = iParms[str(agcid + 1)]["reg"]
    try:
        satValue1 = iParms[str(agcid + 1)]["satVal1"]
        satValue2 = iParms[str(agcid + 1)]["satVal2"]
    except (KeyError, IndexError):
        satValue1 = (2**16) - 1
        satValue2 = (2**16) - 1
    flatVal = iParms["flatVal"]

    dataProc = subOverscan(data.astype("float"))
    dataProc = interpBadCol(dataProc, iParms[str(agcid + 1)]["badCols"])

    _data1 = dataProc[region[2] : region[3], region[0] : region[1]].astype("float", copy=True, order="C")
    _data2 = dataProc[region[6] : region[7], region[4] : region[5]].astype("float", copy=True, order="C")

    spots1, nSpots1, background1 = centroidRegion(_data1, thresh, minarea, deblend=deblend)
    spots2, nSpots2, background2 = centroidRegion(_data2, thresh, minarea, deblend=deblend)

    nElem = nSpots1 + nSpots2

    result = np.zeros(nElem, dtype=spotDtype)

    # flag spots near edge of region

    # dynamic fwhm calculation is overenthusiastic with out of focus images
    # fx = spots1['x2'].mean()
    # fy = spots1['y2'].mean()

    fx = 5
    fy = 5

    ind1 = np.where(
        np.any(
            [
                spots1["x"] - 2 * fx < 0,
                spots1["x"] + 2 * fx > (region[1] - region[0]),
                spots1["y"] - 2 * fy < 0,
                spots1["y"] + 2 * fy > (region[3] - region[2]),
            ],
            axis=0,
        )
    )
    ind2 = np.where(
        np.all(
            [
                np.any([spots1["b"] / spots1["a"] < ellip, spots1["b"] / spots1["a"] > 1 / ellip], axis=0),
                spots1["npix"] < nmin,
            ],
            axis=0,
        )
    )

    result["image_moment_00_pix"][0:nSpots1] = spots1["flux"]
    result["centroid_x_pix"][0:nSpots1] = spots1["x"] + region[0]
    result["centroid_y_pix"][0:nSpots1] = spots1["y"] + region[2]
    result["central_image_moment_20_pix"][0:nSpots1] = spots1["x2"]
    result["central_image_moment_11_pix"][0:nSpots1] = spots1["xy"]
    result["central_image_moment_02_pix"][0:nSpots1] = spots1["y2"]
    result["peak_pixel_x_pix"][0:nSpots1] = spots1["xpeak"] + region[0]
    result["peak_pixel_y_pix"][0:nSpots1] = spots1["ypeak"] + region[2]
    result["peak_intensity"][0:nSpots1] = spots1["peak"]
    result["background"][0:nSpots1] = background1[spots1["ypeak"], spots1["xpeak"]]
    result["flags"][0:nSpots1][ind1] += SourceDetectionFlag.EDGE
    result["flags"][0:nSpots1][ind2] += SourceDetectionFlag.BAD_ELLIP

    # flag spots near edge of region

    # fx = spots2['x2'].mean()
    # fy = spots2['y2'].mean()
    fx = 5
    fy = 5

    ind1 = np.where(
        np.any(
            [
                spots2["x"] - 2 * fx < 0,
                spots2["x"] + 2 * fx > (region[5] - region[4]),
                spots2["y"] - 2 * fy < 0,
                spots2["y"] + 2 * fy > (region[7] - region[6]),
            ],
            axis=0,
        )
    )
    ind2 = np.where(
        np.all(
            [
                np.any([spots2["b"] / spots2["a"] < ellip, spots2["b"] / spots2["a"] > 1 / ellip], axis=0),
                spots2["npix"] < nmin,
            ],
            axis=0,
        )
    )

    result["image_moment_00_pix"][nSpots1:nElem] = spots2["flux"]
    result["centroid_x_pix"][nSpots1:nElem] = spots2["x"] + region[4]
    result["centroid_y_pix"][nSpots1:nElem] = spots2["y"] + region[6]
    result["central_image_moment_20_pix"][nSpots1:nElem] = spots2["x2"]
    result["central_image_moment_11_pix"][nSpots1:nElem] = spots2["xy"]
    result["central_image_moment_02_pix"][nSpots1:nElem] = spots2["y2"]
    result["peak_pixel_x_pix"][nSpots1:nElem] = spots2["xpeak"] + region[4]
    result["peak_pixel_y_pix"][nSpots1:nElem] = spots2["ypeak"] + region[6]
    result["peak_intensity"][nSpots1:nElem] = spots2["peak"]
    result["background"][nSpots1:nElem] = background2[spots2["ypeak"], spots2["xpeak"]]
    # set flag for right half of image

    result["flags"][nSpots1:nElem] += SourceDetectionFlag.RIGHT

    result["flags"][nSpots1:nElem][ind1] += SourceDetectionFlag.EDGE
    result["flags"][nSpots1:nElem][ind2] += SourceDetectionFlag.BAD_ELLIP

    # determine saturation off the unprocessed data
    satValue = np.zeros((len(result)))
    satValue[0:nSpots1] = np.repeat(satValue1, nSpots1)
    satValue[nSpots1:nElem] = np.repeat(satValue2, nSpots2)

    satFlag = data[result["peak_pixel_y_pix"], result["peak_pixel_x_pix"]] >= satValue

    result["flags"] += satFlag * SourceDetectionFlag.SATURATED

    # check for flat sources

    colIdx = result["centroid_x_pix"][:].astype("int")
    rowIdx = result["centroid_y_pix"][:].astype("int")

    # for edges of image

    xMin = rowIdx.copy() - 5
    xMax = rowIdx.copy() + 5

    ind = np.where(xMin < 0)
    xMin[ind] = 0

    ind = np.where(xMax >= data.shape[0])
    xMax[ind] = data.shape[0] - 1

    # diagnostic for flat topped sources
    diag = np.array([data[rowIdx, colIdx] - data[xMin, colIdx], data[rowIdx, colIdx] - data[xMax, colIdx]]).min(axis=0)
    diag = diag / data[rowIdx, colIdx]
    ind = np.where(diag < flatVal)
    result["flags"][:][ind] += SourceDetectionFlag.FLAT_TOP

    # calculate more reasonable FWHMs

    # subract the background

    newData = dataProc.copy()
    newData[region[2] : region[3], region[0] : region[1]] -= background1
    newData[region[6] : region[7], region[4] : region[5]] -= background2

    m20 = []
    m02 = []
    m11 = []

    flags = []
    for ii in range(len(result)):
        colIdx = result["centroid_x_pix"][ii]
        rowIdx = result["centroid_y_pix"][ii]

        xv, yv, xyv, conv = windowedFWHM(newData, colIdx, rowIdx, region, result["flags"][ii] & 1)

        # if the moment didn't converge, revert to the unweighted second moment and set flags
        if conv == 0:
            m20.append(xv)
            m02.append(yv)
            m11.append(xyv)
        else:
            m02.append(result["central_image_moment_02_pix"][ii])
            m20.append(result["central_image_moment_20_pix"][ii])
            m11.append(result["central_image_moment_11_pix"][ii])

        # add flag for non converged sources
        flags.append(conv)

    # and update the values
    result["central_image_moment_20_pix"] = np.array(m20)
    result["central_image_moment_02_pix"] = np.array(m02)
    result["central_image_moment_11_pix"] = np.array(m11)
    result["flags"] = result["flags"] + np.array(flags)
    logger.debug(f"Calculating Magnitude: exptime = {cParms['expTime']}")
    result["estimated_magnitude"] = calculateApproximateMagnitude(
        iParms, result["image_moment_00_pix"], cParms["expTime"]
    )

    return result


def windowedFWHM(
    data: np.ndarray,
    xPos: float,
    yPos: float,
    region: tuple[int, ...],
    side: int,
) -> tuple[float, float, float, int]:
    """Compute iterative windowed second moments for one source.

    Uses the KSB adaptive-weight scheme.  If the iteration fails to
    converge, or if the covariance matrix becomes non-positive-definite,
    ``weightedMoment`` is called as a fallback and a non-convergence flag
    is set.

    Parameters
    ----------
    data : numpy.ndarray
        Background-subtracted 2-D image.
    xPos : float
        Source centroid x-coordinate (column, in full-image pixels).
    yPos : float
        Source centroid y-coordinate (row, in full-image pixels).
    region : tuple[int, ...]
        8-element region tuple ``(x0, x1, y0, y1, x2, x3, y2, y3)``
        defining the two imaging sub-regions.
    side : int
        ``0`` for the left sub-region, ``1`` for the right sub-region.

    Returns
    -------
    tuple[float, float, float, int]
        Second moment in x, second moment in y, cross-moment xy, and a
        convergence flag (0 = converged, non-zero = fall-back used).
    """

    maxIt = 30
    boxSize = 20

    # initial values
    sx = 6
    sy = 6
    sxy = 0

    w11 = -1
    w12 = -1
    w22 = -1

    # some variables for iteration
    e1_old = 1e6
    e2_old = 1e6
    sx_o = 1e6
    tol1 = 0.001
    tol2 = 0.01

    # determine the sub-image region
    dMinX1 = int(np.round(xPos - boxSize))
    dMaxX1 = int(np.round(xPos + boxSize + 1))
    dMinY1 = int(np.round(yPos - boxSize))
    dMaxY1 = int(np.round(yPos + boxSize + 1))

    # check for edges of the region, and adjust accordingly. This includes the central
    # part of the full image
    if side == 0:
        # check for edges of image
        dMinX = np.max([dMinX1, region[0]])
        dMinY = np.max([dMinY1, region[2]])
        dMaxX = np.min([dMaxX1, region[1]])
        dMaxY = np.min([dMaxY1, region[3]])
    elif side == 1:
        # check for edges of image
        dMinX = np.max([dMinX1, region[4]])
        dMinY = np.max([dMinY1, region[6]])
        dMaxX = np.min([dMaxX1, region[5]])
        dMaxY = np.min([dMaxY1, region[7]])

    # and the sub-image
    winVal = data[dMinY:dMaxY, dMinX:dMaxX]

    # scale the coordinates by the central position, to avoid numeric overflow

    xVal = np.arange(dMinX, dMaxX) - xPos
    yVal = np.arange(dMinY, dMaxY) - yPos
    xv, yv = np.meshgrid(xVal, yVal)

    # now the iteration
    for i in range(0, maxIt):
        # get the weighting function based on the current values
        # of the moments

        ow11 = w11
        ow12 = w12
        ow22 = w22

        detw = sx * sy - sxy**2
        w11 = sy / detw
        w12 = -sxy / detw
        w22 = sx / detw

        r2 = xv * xv * w11 + yv * yv * w22 + 2 * w12 * xv * yv
        w = np.exp(-r2 / 2)

        # and calcualte the weighted moments
        sxow = (winVal * w * (xv) ** 2).sum() / (winVal * w).sum()
        syow = (winVal * w * (yv) ** 2).sum() / (winVal * w).sum()
        sxyow = (winVal * w * xv * yv).sum() / (winVal * w).sum()
        # variables to test for convergence
        d = sxow + syow
        e1 = (sxow - syow) / d
        e2 = 2 * sxyow / d

        # check for convergence
        if np.all([np.abs(e1 - e1_old) < tol1, np.abs(e2 - e2_old) < tol1, np.abs(sx / sx_o - 1) < tol2]):
            if np.any([sxow <= 0, syow <= 0]):
                return weightedMoment(winVal, xv, yv, w11, w12, w22)
            else:
                return sxow, syow, sxyow, 0

        # calculate new values
        e1_old = e1
        e2_old = e2
        sx_o = sx

        detow = sxow * syow - sxy**2
        ow11 = syow / detow
        ow12 = -sxyow / detow
        ow22 = sxow / detow
        if detow <= 0:
            return weightedMoment(winVal, xv, yv, w11, w12, w22)

        n11 = ow11 - w11
        n12 = ow12 - w12
        n22 = ow22 - w22
        det_n = n11 * n22 - n12 * n12
        if det_n <= 0:
            return weightedMoment(winVal, xv, yv, w11, w12, w22)

        sx = n22 / det_n
        sxy = -n12 / det_n
        sy = n11 / det_n
        if np.any([sx <= 0, sy <= 0]):
            return weightedMoment(winVal, xv, yv, w11, w12, w22)

    # if we haven't converged return new values
    return sy, sx, sxy, SourceDetectionFlag.BAD_SHAPE


def weightedMoment(
    winVal: np.ndarray,
    xv: np.ndarray,
    yv: np.ndarray,
    w11: float,
    w12: float,
    w22: float,
) -> tuple[float, float, float, int]:
    """Compute a single-pass weighted second moment as a fall-back.

    Parameters
    ----------
    winVal : numpy.ndarray
        Sub-image pixel values.
    xv : numpy.ndarray
        x coordinate grid relative to the source centre.
    yv : numpy.ndarray
        y coordinate grid relative to the source centre.
    w11 : float
        Inverse-covariance matrix element (1,1) for the weighting Gaussian.
    w12 : float
        Inverse-covariance matrix element (1,2).
    w22 : float
        Inverse-covariance matrix element (2,2).

    Returns
    -------
    tuple[float, float, float, int]
        Second moment in x, y, cross-moment xy, and convergence flag
        ``SourceDetectionFlag.BAD_SHAPE``.
    """

    r2 = xv * xv * w11 + yv * yv * w22 + 2 * w12 * xv * yv
    w = np.exp(-r2 / 2)

    sx = (winVal * w * (xv) ** 2).sum() / (winVal * w).sum()
    sy = (winVal * w * (yv) ** 2).sum() / (winVal * w).sum()
    sxy = (winVal * w * xv * yv).sum() / (winVal * w).sum()

    return sx, sy, sxy, SourceDetectionFlag.BAD_SHAPE


def calculateApproximateMagnitude(
    iParms: dict[str, Any],
    instrumentFlux: np.ndarray,
    expTime: float,
) -> np.ndarray:
    """Convert instrument flux to approximate Gaia magnitudes.

    Uses an empirical linear fit of the form
    ``mag = slope * (-2.5 * log10(flux / t)) + intercept``.

    Parameters
    ----------
    iParms : dict[str, Any]
        Instrument parameters; must contain ``magFit`` key with
        ``[slope, intercept]``.
    instrumentFlux : numpy.ndarray
        Instrument flux values (total counts).
    expTime : float
        Exposure time in seconds.

    Returns
    -------
    numpy.ndarray
        Estimated Gaia magnitudes.
    """

    mag = -2.5 * np.log10(instrumentFlux / expTime) * iParms["magFit"][0] + iParms["magFit"][1]

    return mag
