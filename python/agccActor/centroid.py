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


def do_region_centroiding(data, thresh: float, minarea: int, deblend: float):
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

    logger.info(f"Running SEP centroiding on AGC camera {agcid + 1} (thresh={thresh}, minarea={minarea})")

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

    # Define bounds for the left and right halves of the detector
    half_regions = [
        (region[0], region[1], region[2], region[3]),  # Left half
        (region[4], region[5], region[6], region[7]),  # Right half
    ]

    spots_list = []
    nSpots_list = []
    backgrounds = []

    for side, (x0, x1, y0, y1) in enumerate(half_regions):
        regionData = processedData[y0:y1, x0:x1].astype("float", copy=True, order="C")
        spots, nSpots, background = do_region_centroiding(regionData, thresh, minarea, deblend=deblend)
        spots_list.append(spots)
        nSpots_list.append(nSpots)
        backgrounds.append(background)
        side_name = "left" if side == 0 else "right"
        logger.info(
            f"AGC camera {agcid + 1} {side_name} region: detected {nSpots} spots "
            f"(bg median={np.median(background):.1f}, std={np.std(background):.1f})"
        )

    nElem = sum(nSpots_list)
    logger.info(f"AGC camera {agcid + 1}: detected {nElem} spots in total")
    result = np.zeros(nElem, dtype=spotDtype)

    start_idx = 0
    for side, (x0, x1, y0, y1) in enumerate(half_regions):
        spots = spots_list[side]
        nSpots = nSpots_list[side]
        background = backgrounds[side]

        if nSpots == 0:
            continue

        end_idx = start_idx + nSpots
        res_slice = result[start_idx:end_idx]

        # flag spots near edge of region
        edgeIndices = np.where(
            np.any(
                [
                    spots["x"] - 2 * halfBoxX < 0,
                    spots["x"] + 2 * halfBoxX > (x1 - x0),
                    spots["y"] - 2 * halfBoxY < 0,
                    spots["y"] + 2 * halfBoxY > (y1 - y0),
                ],
                axis=0,
            )
        )
        ellipticityIndices = np.where(
            np.all(
                [
                    np.any([spots["b"] / spots["a"] < ellip, spots["b"] / spots["a"] > 1 / ellip], axis=0),
                    spots["npix"] < nmin,
                ],
                axis=0,
            )
        )

        res_slice["image_moment_00_pix"] = spots["flux"]
        res_slice["centroid_x_pix"] = spots["x"] + x0
        res_slice["centroid_y_pix"] = spots["y"] + y0
        res_slice["central_image_moment_20_pix"] = spots["x2"]
        res_slice["central_image_moment_11_pix"] = spots["xy"]
        res_slice["central_image_moment_02_pix"] = spots["y2"]
        res_slice["peak_pixel_x_pix"] = spots["xpeak"] + x0
        res_slice["peak_pixel_y_pix"] = spots["ypeak"] + y0
        res_slice["peak_intensity"] = spots["peak"]
        res_slice["background"] = background[spots["ypeak"], spots["xpeak"]]

        if side == 1:
            res_slice["flags"] += SourceDetectionFlag.RIGHT

        res_slice["flags"][edgeIndices] += SourceDetectionFlag.EDGE
        res_slice["flags"][ellipticityIndices] += SourceDetectionFlag.BAD_ELLIP

        start_idx = end_idx

    # determine saturation off the unprocessed data
    satValue = np.concatenate(
        [
            np.repeat(satValue1, nSpots_list[0]),
            np.repeat(satValue2, nSpots_list[1]),
        ]
    )

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
    for side, (x0, x1, y0, y1) in enumerate(half_regions):
        tempData[y0:y1, x0:x1] -= backgrounds[side]

    non_conv_count = 0
    for i in range(len(result)):
        yPos = result["centroid_x_pix"][i]
        xPos = result["centroid_y_pix"][i]

        xv, yv, xyv, conv = windowedFWHM(
            tempData, yPos, xPos, region, result["flags"][i] & SourceDetectionFlag.RIGHT, boxSize=boxSize
        )

        # if the moment converged, update values. otherwise keep unweighted ones and add flag.
        if conv == 0:
            result["central_image_moment_20_pix"][i] = xv
            result["central_image_moment_02_pix"][i] = yv
            result["central_image_moment_11_pix"][i] = xyv
        else:
            result["flags"][i] += conv
            non_conv_count += 1

    if non_conv_count > 0:
        logger.info(f"AGC camera {agcid + 1}: {non_conv_count} spots failed FWHM moment convergence")

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
