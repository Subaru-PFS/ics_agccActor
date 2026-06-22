import logging
import os

import numpy as np
import sep
import yaml
from pfs.utils.datamodel.ag import SourceDetectionFlag

logger = logging.getLogger("agcc")
logger.setLevel(logging.INFO)


def getConfig() -> dict:
    """Read the actor configuration file.

    Returns
    -------
    dict
        The full configuration dictionary from ``$PFS_INSTDATA_DIR/config/actors/agcc.yaml``.
    """
    configPath = os.path.join(os.environ["PFS_INSTDATA_DIR"], "config/actors", "agcc.yaml")
    with open(configPath, "r") as configFile:
        return yaml.safe_load(configFile)


def getParams(cmd=None) -> tuple[dict, dict]:
    """Read both centroiding and instrumental parameters from the configuration file.

    Centroiding defaults are optionally overridden by keywords in ``cmd``.

    Parameters
    ----------
    cmd : object, optional
        A tron command object whose keywords (nmin, thresh, deblend) may
        override centroiding defaults.

    Returns
    -------
    centroidParams : dict
        Centroiding parameters.
    cameraParams : dict
        Per-camera instrumental parameters.
    """
    config = getConfig()
    centroidParams = config["agcc"]["centroidParams"]
    cameraParams = config["agcc"]["cameraParams"]

    try:
        commandKeywords = cmd.cmd.keywords
    except AttributeError:
        commandKeywords = []

    if "nmin" in commandKeywords:
        centroidParams["nmin"] = int(cmd.cmd.keywords["nmin"].values[0])
    if "thresh" in commandKeywords:
        centroidParams["thresh"] = float(cmd.cmd.keywords["thresh"].values[0])
    if "deblend" in commandKeywords:
        centroidParams["deblend"] = float(cmd.cmd.keywords["deblend"].values[0])

    # add optional box sizes for edge flagging and windowed FWHM
    centroidParams.setdefault("halfBoxX", 5)
    centroidParams.setdefault("halfBoxY", 5)
    centroidParams.setdefault("boxSize", 20)

    return centroidParams, cameraParams


def interpBadCol(data, badCols):
    """Interpolate over known bad columns by averaging neighbours.

    Parameters
    ----------
    data : numpy.ndarray
        2-D image array (modified in place and returned).
    badCols : sequence of int
        Column indices to interpolate over.

    Returns
    -------
    numpy.ndarray
        The input ``data`` array with bad columns replaced.
    """

    for i in badCols:
        data[:, i] = (data[:, i - 1] + data[:, i + 1]) / 2
    return data


def subOverscan(data):
    """Subtract overscan-level background from each half of the image.

    The image is split vertically into two halves; the median of a small
    overscan strip in each half is subtracted from that half in place.

    Parameters
    ----------
    data : numpy.ndarray
        2-D image array (modified in place and returned).

    Returns
    -------
    numpy.ndarray
        The overscan-subtracted image.
    """

    h, w = data.shape
    side0 = data[:, : w // 2]
    side1 = data[:, w // 2 :]
    bg0 = np.median(side0[:, :4]).astype(data.dtype)
    bg1 = np.median(side1[:, -4:]).astype(data.dtype)

    data[:, : w // 2] -= bg0
    data[:, w // 2 :] -= bg1

    return data


def centroidRegion(data, thresh: float, minarea: int, deblend: float):
    """Subtract the background and run SEP source extraction on a region.

    Parameters
    ----------
    data : numpy.ndarray
        2-D image region (modified in place: background subtracted).
    thresh : float
        Detection threshold (in units of the per-pixel RMS).
    minarea : int
        Minimum number of connected pixels above ``thresh``.
    deblend : float
        SEP ``deblend_cont`` parameter.

    Returns
    -------
    spots : numpy.ndarray
        Structured array of detected sources, as returned by ``sep.extract``.
    nspots : int
        Number of detected sources.
    background : numpy.ndarray
        The 2-D background image estimated by SEP.
    """

    # determine the background
    backgroundEstimation = sep.Background(data)
    background = backgroundEstimation.back()
    rms = backgroundEstimation.rms()
    backgroundEstimation.subfrom(data)

    # get spots using sourcing extractor defaults
    spots = sep.extract(data, thresh, rms, minarea=minarea, deblend_cont=deblend)

    # get windowed positions for the spots
    return spots, len(spots), background


def getCentroidsSep(data, instrumentParams: dict, centroidParams: dict, spotDtype, agcid: int):
    """Run SEP-based centroiding on an AG camera image.

    Both halves (left and right regions) defined in ``instrumentParams`` are
    processed independently. Edge, ellipticity, saturation, flat-top and
    non-convergence flags are accumulated, and final windowed second
    moments and estimated magnitudes are filled in.

    Parameters
    ----------
    data : numpy.ndarray
        2-D raw image from one AG camera.
    instrumentParams : dict
        Per-camera instrumental parameters; must contain the camera's
        ``reg``, ``badCols``, ``satVal1``/``satVal2`` (optional),
        ``flatVal`` and ``magFit`` entries.
    centroidParams : dict
        Centroiding parameters: ``thresh``, ``minarea``, ``deblend``,
        ``ellip``, ``nmin``, ``expTime``, and optional ``halfBoxX``,
        ``halfBoxY``, ``boxSize``.
    spotDtype : numpy.dtype
        Structured dtype for the output spot record array.
    agcid : int
        Zero-based AG camera identifier.

    Returns
    -------
    numpy.ndarray
        Structured array with one entry per detected spot.
    """

    thresh = centroidParams["thresh"]
    minarea = centroidParams["minarea"]
    deblend = centroidParams["deblend"]
    ellip = centroidParams["ellip"]
    nmin = centroidParams["nmin"]
    halfBoxX = centroidParams["halfBoxX"]
    halfBoxY = centroidParams["halfBoxY"]
    boxSize = centroidParams["boxSize"]

    # get region information for camera
    region = instrumentParams[str(agcid + 1)]["reg"]
    try:
        satValue1 = instrumentParams[str(agcid + 1)]["satVal1"]
        satValue2 = instrumentParams[str(agcid + 1)]["satVal2"]
    except (KeyError, IndexError):
        satValue1 = (2**16) - 1
        satValue2 = (2**16) - 1
    flatVal = instrumentParams["flatVal"]

    processedData = subOverscan(data.astype("float"))
    processedData = interpBadCol(processedData, instrumentParams[str(agcid + 1)]["badCols"])

    regionData1 = processedData[region[2] : region[3], region[0] : region[1]].astype(
        "float", copy=True, order="C"
    )
    regionData2 = processedData[region[6] : region[7], region[4] : region[5]].astype(
        "float", copy=True, order="C"
    )

    spots1, nSpots1, background1 = centroidRegion(regionData1, thresh, minarea, deblend=deblend)
    spots2, nSpots2, background2 = centroidRegion(regionData2, thresh, minarea, deblend=deblend)

    nElem = nSpots1 + nSpots2

    result = np.zeros(nElem, dtype=spotDtype)

    # define the box size for edge detection and moment calculation
    # boxSize is used for windowedFWHM, halfBox is used for edge flagging.
    # We keep them separate but defined together for clarity.

    # flag spots near edge of region

    edgeIndices1 = np.where(
        np.any(
            [
                spots1["x"] - 2 * halfBoxX < 0,
                spots1["x"] + 2 * halfBoxX > (region[1] - region[0]),
                spots1["y"] - 2 * halfBoxY < 0,
                spots1["y"] + 2 * halfBoxY > (region[3] - region[2]),
            ],
            axis=0,
        )
    )
    ellipticityIndices1 = np.where(
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
    result["flags"][0:nSpots1][edgeIndices1] += SourceDetectionFlag.EDGE
    result["flags"][0:nSpots1][ellipticityIndices1] += SourceDetectionFlag.BAD_ELLIP

    # flag spots near edge of region

    edgeIndices2 = np.where(
        np.any(
            [
                spots2["x"] - 2 * halfBoxX < 0,
                spots2["x"] + 2 * halfBoxX > (region[5] - region[4]),
                spots2["y"] - 2 * halfBoxY < 0,
                spots2["y"] + 2 * halfBoxY > (region[7] - region[6]),
            ],
            axis=0,
        )
    )
    ellipticityIndices2 = np.where(
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

    result["flags"][nSpots1:nElem][edgeIndices2] += SourceDetectionFlag.EDGE
    result["flags"][nSpots1:nElem][ellipticityIndices2] += SourceDetectionFlag.BAD_ELLIP

    # determine saturation off the unprocessed data
    satValue = np.zeros((len(result)))
    satValue[0:nSpots1] = np.repeat(satValue1, nSpots1)
    satValue[nSpots1:nElem] = np.repeat(satValue2, nSpots2)

    satFlag = data[result["peak_pixel_y_pix"], result["peak_pixel_x_pix"]] >= satValue

    result["flags"] += satFlag * SourceDetectionFlag.SATURATED

    # check for flat sources

    yPos = result["centroid_x_pix"][:].astype("int")
    xPos = result["centroid_y_pix"][:].astype("int")

    # for edges of image

    xMin = xPos.copy() - 5
    xMax = xPos.copy() + 5

    ind = np.where(xMin < 0)
    xMin[ind] = 0

    ind = np.where(xMax >= data.shape[0])
    xMax[ind] = data.shape[0] - 1

    # diagnostic for flat topped sources
    diag = np.array([data[xPos, yPos] - data[xMin, yPos], data[xPos, yPos] - data[xMax, yPos]]).min(axis=0)
    diag = diag / data[xPos, yPos]
    ind = np.where(diag < flatVal)
    result["flags"][:][ind] += SourceDetectionFlag.FLAT_TOP

    # calculate more reasonable FWHMs

    # subract the background

    tempData = processedData.copy()
    tempData[region[2] : region[3], region[0] : region[1]] -= background1
    tempData[region[6] : region[7], region[4] : region[5]] -= background2

    m20 = []
    m02 = []
    m11 = []

    flags = []
    for i in range(len(result)):
        yPos = result["centroid_x_pix"][i]
        xPos = result["centroid_y_pix"][i]

        xv, yv, xyv, conv = windowedFWHM(
            tempData, yPos, xPos, region, result["flags"][i] & 1, boxSize=boxSize
        )

        # if the moment didn't converge, revert to the unweighted second moment and set flags
        if conv == 0:
            m20.append(xv)
            m02.append(yv)
            m11.append(xyv)
        else:
            m02.append(result["central_image_moment_02_pix"][i])
            m20.append(result["central_image_moment_20_pix"][i])
            m11.append(result["central_image_moment_11_pix"][i])

        # add flag for non converged sources
        flags.append(conv)

    # and update the values
    result["central_image_moment_20_pix"] = np.array(m20)
    result["central_image_moment_02_pix"] = np.array(m02)
    result["central_image_moment_11_pix"] = np.array(m11)
    result["flags"] = result["flags"] + np.array(flags)
    logger.debug(f"Calculating Magnitude: exptime = {centroidParams['expTime']}")
    result["estimated_magnitude"] = calculateApproximateMagnitude(
        instrumentParams, result["image_moment_00_pix"], centroidParams["expTime"]
    )

    return result


def windowedFWHM(data, xPos: float, yPos: float, region, side: int, boxSize: int = 20):
    """Compute iteratively-weighted second moments around a position.

    If the point is near the edge of the region the sub-image is cropped
    accordingly; the fit is still attempted but may produce poor results.
    If the fit yields a non-positive determinant or size, or if the
    iteration does not converge, a simple non-iterative weighted moment
    is returned and a ``BAD_SHAPE`` flag is set.

    Parameters
    ----------
    data : numpy.ndarray
        2-D background-subtracted image.
    xPos, yPos : float
        Centroid (column, row) position in image coordinates.
    region : sequence of int
        Region bounds ``(x0, x1, y0, y1, x2, x3, y2, y3)`` defining the
        left (``side=0``) and right (``side=1``) halves.
    side : int
        ``0`` for the left region, ``1`` for the right region.
    boxSize : int, optional
        Half-size of the box used for the windowed fit.

    Returns
    -------
    momentX, momentY, momentXY : float
        Weighted second moments (xx, yy, xy).
    flag : int
        ``0`` on convergence, ``SourceDetectionFlag.BAD_SHAPE`` otherwise.
    """

    maxIterations = 30

    # initial values
    momentX = 6
    momentY = 6
    momentXY = 0

    w11 = -1
    w12 = -1
    w22 = -1

    # some variables for iteration
    e1Old = 1e6
    e2Old = 1e6
    momentXOld = 1e6
    momentYOld = 1e6
    tolerance1 = 0.001
    tolerance2 = 0.01

    # determine the sub-image region
    minXInitial = int(np.round(xPos - boxSize))
    maxXInitial = int(np.round(xPos + boxSize + 1))
    minYInitial = int(np.round(yPos - boxSize))
    maxYInitial = int(np.round(yPos + boxSize + 1))

    # check for edges of the region, and adjust accordingly. This includes the central
    # part of the full image
    if side == 0:
        # check for edges of image
        minX = np.max([minXInitial, region[0]])
        minY = np.max([minYInitial, region[2]])
        maxX = np.min([maxXInitial, region[1]])
        maxY = np.min([maxYInitial, region[3]])
    elif side == 1:
        # check for edges of image
        minX = np.max([minXInitial, region[4]])
        minY = np.max([minYInitial, region[6]])
        maxX = np.min([maxXInitial, region[5]])
        maxY = np.min([maxYInitial, region[7]])

    # and the sub-image
    subImage = data[minY:maxY, minX:maxX]

    # scale the coordinates by the central position, to avoid numeric overflow

    xVal = np.arange(minX, maxX) - xPos
    yVal = np.arange(minY, maxY) - yPos
    xv, yv = np.meshgrid(xVal, yVal)

    # now the iteration
    for i in range(0, maxIterations):
        # get the weighting function based on the current values
        # of the moments

        detw = momentX * momentY - momentXY**2
        w11 = momentY / detw
        w12 = -momentXY / detw
        w22 = momentX / detw

        r2 = xv * xv * w11 + yv * yv * w22 + 2 * w12 * xv * yv
        w = np.exp(-r2 / 2)

        # and calcualte the weighted moments
        momentXWeighted = (subImage * w * (xv) ** 2).sum() / (subImage * w).sum()
        momentYWeighted = (subImage * w * (yv) ** 2).sum() / (subImage * w).sum()
        momentXYWeighted = (subImage * w * xv * yv).sum() / (subImage * w).sum()
        # variables to test for convergence
        d = momentXWeighted + momentYWeighted
        e1 = (momentXWeighted - momentYWeighted) / d
        e2 = 2 * momentXYWeighted / d

        # check for convergence
        if np.all(
            [
                np.abs(e1 - e1Old) < tolerance1,
                np.abs(e2 - e2Old) < tolerance1,
                np.abs(momentX / momentXOld - 1) < tolerance2,
                np.abs(momentY / momentYOld - 1) < tolerance2,
            ]
        ):
            if np.any([momentXWeighted <= 0, momentYWeighted <= 0]):
                return weightedMoment(subImage, xv, yv, w11, w12, w22)
            else:
                return momentXWeighted, momentYWeighted, momentXYWeighted, 0

        # calculate new values
        e1Old = e1
        e2Old = e2
        momentXOld = momentX
        momentYOld = momentY

        detWeighted = momentXWeighted * momentYWeighted - momentXYWeighted**2
        ow11 = momentYWeighted / detWeighted
        ow12 = -momentXYWeighted / detWeighted
        ow22 = momentXWeighted / detWeighted
        if detWeighted <= 0:
            return weightedMoment(subImage, xv, yv, w11, w12, w22)

        n11 = ow11 - w11
        n12 = ow12 - w12
        n22 = ow22 - w22
        det_n = n11 * n22 - n12 * n12
        if det_n <= 0:
            return weightedMoment(subImage, xv, yv, w11, w12, w22)

        momentX = n22 / det_n
        momentXY = -n12 / det_n
        momentY = n11 / det_n
        if np.any([momentX <= 0, momentY <= 0]):
            return weightedMoment(subImage, xv, yv, w11, w12, w22)

    # if we haven't converged return new values
    return momentX, momentY, momentXY, SourceDetectionFlag.BAD_SHAPE


def weightedMoment(subImage, xv, yv, w11: float, w12: float, w22: float):
    """Compute a single-pass weighted moment as a fallback.

    Used by :func:`windowedFWHM` when the iterative fit fails to converge
    or yields a non-physical result.

    Parameters
    ----------
    subImage : numpy.ndarray
        2-D sub-image (background-subtracted) around the source.
    xv, yv : numpy.ndarray
        Coordinate meshgrids relative to the centroid.
    w11, w12, w22 : float
        Components of the inverse covariance matrix of the weight Gaussian.

    Returns
    -------
    momentX, momentY, momentXY : float
        Weighted second moments.
    flag : int
        Always ``SourceDetectionFlag.BAD_SHAPE``.
    """

    r2 = xv * xv * w11 + yv * yv * w22 + 2 * w12 * xv * yv
    w = np.exp(-r2 / 2)

    momentX = (subImage * w * (xv) ** 2).sum() / (subImage * w).sum()
    momentY = (subImage * w * (yv) ** 2).sum() / (subImage * w).sum()
    momentXY = (subImage * w * xv * yv).sum() / (subImage * w).sum()

    return momentX, momentY, momentXY, SourceDetectionFlag.BAD_SHAPE


def calculateApproximateMagnitude(instrumentParams: dict, instrumentFlux, expTime: float):
    """Estimate an approximate Gaia magnitude from instrumental flux.

    Uses the linear ``magFit = (slope, offset)`` coefficients stored in
    ``instrumentParams`` applied to ``-2.5 * log10(flux / expTime)``.

    Parameters
    ----------
    instrumentParams : dict
        Instrumental parameters; must contain a ``magFit`` ``(slope, offset)``
        pair.
    instrumentFlux : numpy.ndarray or float
        Instrumental flux (e.g. SEP ``flux``).
    expTime : float
        Exposure time in seconds.

    Returns
    -------
    numpy.ndarray or float
        Estimated Gaia-like magnitude.
    """

    mag = (
        -2.5 * np.log10(instrumentFlux / expTime) * instrumentParams["magFit"][0]
        + instrumentParams["magFit"][1]
    )

    return mag
