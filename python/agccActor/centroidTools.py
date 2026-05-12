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
        command_keys = cmd.cmd.keywords
    except Exception:
        command_keys = []

    config_file = os.path.join(os.environ["PFS_INSTDATA_DIR"], "config/actors", "agcc.yaml")

    with open(config_file, "r") as in_file:
        config = yaml.safe_load(in_file)

    # returns just the values dictionary
    centroid_params = config["agcc"]["centroidParams"]

    if "nmin" in command_keys:
        centroid_params["nmin"] = int(cmd.cmd.keywords["nmin"].values[0])
    if "thresh" in command_keys:
        centroid_params["thresh"] = float(cmd.cmd.keywords["thresh"].values[0])
    if "deblend" in command_keys:
        centroid_params["deblend"] = float(cmd.cmd.keywords["deblend"].values[0])

    return centroid_params


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

    config_file = os.path.join(os.environ["PFS_INSTDATA_DIR"], "config/actors", "agcc.yaml")

    with open(config_file, "r") as in_file:
        config = yaml.safe_load(in_file)

    return config["agcc"]["cameraParams"]


def interpBadCol(data: np.ndarray, bad_columns: list[int]) -> np.ndarray:
    """Interpolate over bad columns in-place by linear averaging of neighbours.

    Parameters
    ----------
    data : numpy.ndarray
        2-D image array (modified in-place).
    bad_columns : list[int]
        Column indices to interpolate.

    Returns
    -------
    numpy.ndarray
        The modified ``data`` array (same object).
    """

    for i in bad_columns:
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

    _, width = data.shape
    left_half = data[:, : width // 2]
    right_half = data[:, width // 2 :]
    bias_level_left = np.median(left_half[:, :4]).astype(data.dtype)
    bias_level_right = np.median(right_half[:, -4:]).astype(data.dtype)

    data[:, : width // 2] -= bias_level_left
    data[:, width // 2 :] -= bias_level_right

    return data


def centroidRegion(
    data: np.ndarray,
    thresh: float,
    min_area: int,
    deblend: float,
) -> tuple[np.ndarray, int, np.ndarray]:
    """Subtract the background and extract sources from a sub-image region.

    Parameters
    ----------
    data : numpy.ndarray
        2-D sub-image array (modified in-place by background subtraction).
    thresh : float
        Detection threshold in units of background RMS.
    min_area : int
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
    background_obj = sep.Background(data)
    background = background_obj.back()
    rms = background_obj.rms()
    background_obj.subfrom(data)

    # get spots using sourcing extractor defaults
    spots = sep.extract(data, thresh, rms, minarea=min_area, deblend_cont=deblend)

    # get windowed positions for the spots
    return spots, len(spots), background


def getCentroidsSep(
    data: np.ndarray,
    instrument_params: dict[str, Any],
    centroid_params: dict[str, Any],
    spot_dtype: np.dtype,
    camera_id: int,
) -> np.ndarray:
    """Run SEP centroiding on one camera frame and return a structured result.

    Parameters
    ----------
    data : numpy.ndarray
        Raw 2-D image array from the camera.
    instrument_params : dict[str, Any]
        Image/instrument parameters (regions, bad columns, saturation values).
    centroid_params : dict[str, Any]
        Centroid parameters (threshold, min area, deblend, ellipticity).
    spot_dtype : numpy.dtype
        Structured dtype for the output array.
    camera_id : int
        Zero-based AG camera identifier.

    Returns
    -------
    numpy.ndarray
        Structured array of centroid results with shape ``(nSpots,)``.
    """

    thresh = centroid_params["thresh"]
    min_area = centroid_params["minarea"]
    deblend = centroid_params["deblend"]
    ellip = centroid_params["ellip"]
    nmin = centroid_params["nmin"]

    # get region information for camera
    region = instrument_params[str(camera_id + 1)]["reg"]
    (
        x1_start,
        x1_end,
        y1_start,
        y1_end,
        x2_start,
        x2_end,
        y2_start,
        y2_end,
    ) = region

    try:
        sat_value_left = instrument_params[str(camera_id + 1)]["satVal1"]
        sat_value_right = instrument_params[str(camera_id + 1)]["satVal2"]
    except (KeyError, IndexError):
        sat_value_left = (2**16) - 1
        sat_value_right = (2**16) - 1
    flat_top_threshold = instrument_params["flatVal"]

    processed_data = subOverscan(data.astype("float"))
    processed_data = interpBadCol(processed_data, instrument_params[str(camera_id + 1)]["badCols"])

    sub_image_left = processed_data[y1_start:y1_end, x1_start:x1_end].astype("float", copy=True, order="C")
    sub_image_right = processed_data[y2_start:y2_end, x2_start:x2_end].astype("float", copy=True, order="C")

    spots_left, num_spots_left, background_left = centroidRegion(sub_image_left, thresh, min_area, deblend=deblend)
    spots_right, num_spots_right, background_right = centroidRegion(
        sub_image_right, thresh, min_area, deblend=deblend
    )

    total_num_spots = num_spots_left + num_spots_right

    result = np.zeros(total_num_spots, dtype=spot_dtype)

    # flag spots near edge of region

    # dynamic fwhm calculation is overenthusiastic with out of focus images
    # fwhm_x = spots_left['x2'].mean()
    # fwhm_y = spots_left['y2'].mean()

    nominal_fwhm_x = 5
    nominal_fwhm_y = 5

    edge_indices = np.where(
        np.any(
            [
                spots_left["x"] - 2 * nominal_fwhm_x < 0,
                spots_left["x"] + 2 * nominal_fwhm_x > (x1_end - x1_start),
                spots_left["y"] - 2 * nominal_fwhm_y < 0,
                spots_left["y"] + 2 * nominal_fwhm_y > (y1_end - y1_start),
            ],
            axis=0,
        )
    )
    bad_shape_indices = np.where(
        np.all(
            [
                np.any(
                    [
                        spots_left["b"] / spots_left["a"] < ellip,
                        spots_left["b"] / spots_left["a"] > 1 / ellip,
                    ],
                    axis=0,
                ),
                spots_left["npix"] < nmin,
            ],
            axis=0,
        )
    )

    result["image_moment_00_pix"][0:num_spots_left] = spots_left["flux"]
    result["centroid_x_pix"][0:num_spots_left] = spots_left["x"] + x1_start
    result["centroid_y_pix"][0:num_spots_left] = spots_left["y"] + y1_start
    result["central_image_moment_20_pix"][0:num_spots_left] = spots_left["x2"]
    result["central_image_moment_11_pix"][0:num_spots_left] = spots_left["xy"]
    result["central_image_moment_02_pix"][0:num_spots_left] = spots_left["y2"]
    result["peak_pixel_x_pix"][0:num_spots_left] = spots_left["xpeak"] + x1_start
    result["peak_pixel_y_pix"][0:num_spots_left] = spots_left["ypeak"] + y1_start
    result["peak_intensity"][0:num_spots_left] = spots_left["peak"]
    result["background"][0:num_spots_left] = background_left[spots_left["ypeak"], spots_left["xpeak"]]
    result["flags"][0:num_spots_left][edge_indices] += SourceDetectionFlag.EDGE
    result["flags"][0:num_spots_left][bad_shape_indices] += SourceDetectionFlag.BAD_ELLIP

    # flag spots near edge of region

    # fwhm_x = spots_right['x2'].mean()
    # fwhm_y = spots_right['y2'].mean()
    nominal_fwhm_x = 5
    nominal_fwhm_y = 5

    edge_indices = np.where(
        np.any(
            [
                spots_right["x"] - 2 * nominal_fwhm_x < 0,
                spots_right["x"] + 2 * nominal_fwhm_x > (x2_end - x2_start),
                spots_right["y"] - 2 * nominal_fwhm_y < 0,
                spots_right["y"] + 2 * nominal_fwhm_y > (y2_end - y2_start),
            ],
            axis=0,
        )
    )
    bad_shape_indices = np.where(
        np.all(
            [
                np.any(
                    [
                        spots_right["b"] / spots_right["a"] < ellip,
                        spots_right["b"] / spots_right["a"] > 1 / ellip,
                    ],
                    axis=0,
                ),
                spots_right["npix"] < nmin,
            ],
            axis=0,
        )
    )

    result["image_moment_00_pix"][num_spots_left:total_num_spots] = spots_right["flux"]
    result["centroid_x_pix"][num_spots_left:total_num_spots] = spots_right["x"] + x2_start
    result["centroid_y_pix"][num_spots_left:total_num_spots] = spots_right["y"] + y2_start
    result["central_image_moment_20_pix"][num_spots_left:total_num_spots] = spots_right["x2"]
    result["central_image_moment_11_pix"][num_spots_left:total_num_spots] = spots_right["xy"]
    result["central_image_moment_02_pix"][num_spots_left:total_num_spots] = spots_right["y2"]
    result["peak_pixel_x_pix"][num_spots_left:total_num_spots] = spots_right["xpeak"] + x2_start
    result["peak_pixel_y_pix"][num_spots_left:total_num_spots] = spots_right["ypeak"] + y2_start
    result["peak_intensity"][num_spots_left:total_num_spots] = spots_right["peak"]
    result["background"][num_spots_left:total_num_spots] = background_right[
        spots_right["ypeak"], spots_right["xpeak"]
    ]
    # set flag for right half of image

    result["flags"][num_spots_left:total_num_spots] += SourceDetectionFlag.RIGHT

    result["flags"][num_spots_left:total_num_spots][edge_indices] += SourceDetectionFlag.EDGE
    result["flags"][num_spots_left:total_num_spots][bad_shape_indices] += SourceDetectionFlag.BAD_ELLIP

    # determine saturation off the unprocessed data
    saturation_thresholds = np.zeros((len(result)))
    saturation_thresholds[0:num_spots_left] = np.repeat(sat_value_left, num_spots_left)
    saturation_thresholds[num_spots_left:total_num_spots] = np.repeat(sat_value_right, num_spots_right)

    is_saturated = data[result["peak_pixel_y_pix"], result["peak_pixel_x_pix"]] >= saturation_thresholds

    result["flags"] += is_saturated * SourceDetectionFlag.SATURATED

    # check for flat sources

    centroid_x_coords = result["centroid_x_pix"][:].astype("int")
    centroid_y_coords = result["centroid_y_pix"][:].astype("int")

    # for edges of image

    y_min_box = centroid_y_coords.copy() - 5
    y_max_box = centroid_y_coords.copy() + 5

    edge_idx = np.where(y_min_box < 0)
    y_min_box[edge_idx] = 0

    edge_idx = np.where(y_max_box >= data.shape[0])
    y_max_box[edge_idx] = data.shape[0] - 1

    # diagnostic for flat topped sources
    flat_top_diagnostic = np.array(
        [
            data[centroid_y_coords, centroid_x_coords] - data[y_min_box, centroid_x_coords],
            data[centroid_y_coords, centroid_x_coords] - data[y_max_box, centroid_x_coords],
        ]
    ).min(axis=0)
    flat_top_diagnostic = flat_top_diagnostic / data[centroid_y_coords, centroid_x_coords]
    flat_top_idx = np.where(flat_top_diagnostic < flat_top_threshold)
    result["flags"][:][flat_top_idx] += SourceDetectionFlag.FLAT_TOP

    # calculate more reasonable FWHMs

    # subract the background

    bg_subtracted_full_data = processed_data.copy()
    bg_subtracted_full_data[y1_start:y1_end, x1_start:x1_end] -= background_left
    bg_subtracted_full_data[y2_start:y2_end, x2_start:x2_end] -= background_right

    m20 = []
    m02 = []
    m11 = []

    flags = []
    for spot_idx in range(len(result)):
        col_idx = result["centroid_x_pix"][spot_idx]
        row_idx = result["centroid_y_pix"][spot_idx]

        xv, yv, xyv, convergence_flag = windowedFWHM(
            bg_subtracted_full_data, col_idx, row_idx, region, result["flags"][spot_idx] & 1
        )

        # if the moment didn't converge, revert to the unweighted second moment and set flags
        if convergence_flag == 0:
            m20.append(xv)
            m02.append(yv)
            m11.append(xyv)
        else:
            m02.append(result["central_image_moment_02_pix"][spot_idx])
            m20.append(result["central_image_moment_20_pix"][spot_idx])
            m11.append(result["central_image_moment_11_pix"][spot_idx])

        # add flag for non converged sources
        flags.append(convergence_flag)

    # and update the values
    result["central_image_moment_20_pix"] = np.array(m20)
    result["central_image_moment_02_pix"] = np.array(m02)
    result["central_image_moment_11_pix"] = np.array(m11)
    result["flags"] = result["flags"] + np.array(flags)
    logger.debug(f"Calculating Magnitude: exptime = {centroid_params['expTime']}")
    result["estimated_magnitude"] = calculateApproximateMagnitude(
        instrument_params, result["image_moment_00_pix"], centroid_params["expTime"]
    )

    return result


def windowedFWHM(
    data: np.ndarray,
    x_centroid: float,
    y_centroid: float,
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
    x_centroid : float
        Source centroid x-coordinate (column, in full-image pixels).
    y_centroid : float
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

    max_it = 30
    box_size = 20

    # initial values
    moment_x2 = 6
    moment_y2 = 6
    moment_xy = 0

    weight_11 = -1
    weight_12 = -1
    weight_22 = -1

    # some variables for iteration
    e1_old = 1e6
    e2_old = 1e6
    sigma_x2_old = 1e6
    tol1 = 0.001
    tol2 = 0.01

    # determine the sub-image region
    init_min_x = int(np.round(x_centroid - box_size))
    init_max_x = int(np.round(x_centroid + box_size + 1))
    init_min_y = int(np.round(y_centroid - box_size))
    init_max_y = int(np.round(y_centroid + box_size + 1))

    # unpack region
    (
        x1_start,
        x1_end,
        y1_start,
        y1_end,
        x2_start,
        x2_end,
        y2_start,
        y2_end,
    ) = region

    # check for edges of the region, and adjust accordingly. This includes the central
    # part of the full image
    if side == 0:
        # check for edges of image
        min_x = np.max([init_min_x, x1_start])
        min_y = np.max([init_min_y, y1_start])
        max_x = np.min([init_max_x, x1_end])
        max_y = np.min([init_max_y, y1_end])
    elif side == 1:
        # check for edges of image
        min_x = np.max([init_min_x, x2_start])
        min_y = np.max([init_min_y, y2_start])
        max_x = np.min([init_max_x, x2_end])
        max_y = np.min([init_max_y, y2_end])

    # and the sub-image
    sub_image = data[min_y:max_y, min_x:max_x]

    # scale the coordinates by the central position, to avoid numeric overflow

    x_rel = np.arange(min_x, max_x) - x_centroid
    y_rel = np.arange(min_y, max_y) - y_centroid
    x_grid, y_grid = np.meshgrid(x_rel, y_rel)

    # now the iteration
    for _ in range(0, max_it):
        # get the weighting function based on the current values
        # of the moments

        det_weight = moment_x2 * moment_y2 - moment_xy**2
        weight_11 = moment_y2 / det_weight
        weight_12 = -moment_xy / det_weight
        weight_22 = moment_x2 / det_weight

        r2 = x_grid * x_grid * weight_11 + y_grid * y_grid * weight_22 + 2 * weight_12 * x_grid * y_grid
        weight = np.exp(-r2 / 2)

        # and calcualte the weighted moments
        weighted_moment_x2 = (sub_image * weight * (x_grid) ** 2).sum() / (sub_image * weight).sum()
        weighted_moment_y2 = (sub_image * weight * (y_grid) ** 2).sum() / (sub_image * weight).sum()
        weighted_moment_xy = (sub_image * weight * x_grid * y_grid).sum() / (sub_image * weight).sum()
        # variables to test for convergence
        trace = weighted_moment_x2 + weighted_moment_y2
        e1 = (weighted_moment_x2 - weighted_moment_y2) / trace
        e2 = 2 * weighted_moment_xy / trace

        # check for convergence
        if np.all(
            [
                np.abs(e1 - e1_old) < tol1,
                np.abs(e2 - e2_old) < tol1,
                np.abs(moment_x2 / sigma_x2_old - 1) < tol2,
            ]
        ):
            if np.any([weighted_moment_x2 <= 0, weighted_moment_y2 <= 0]):
                return weightedMoment(sub_image, x_grid, y_grid, weight_11, weight_12, weight_22)
            else:
                return weighted_moment_x2, weighted_moment_y2, weighted_moment_xy, 0

        # calculate new values
        e1_old = e1
        e2_old = e2
        sigma_x2_old = moment_x2

        det_weighted = weighted_moment_x2 * weighted_moment_y2 - moment_xy**2
        old_weight_11 = weighted_moment_y2 / det_weighted
        old_weight_12 = -weighted_moment_xy / det_weighted
        old_weight_22 = weighted_moment_x2 / det_weighted
        if det_weighted <= 0:
            return weightedMoment(sub_image, x_grid, y_grid, weight_11, weight_12, weight_22)

        n11 = old_weight_11 - weight_11
        n12 = old_weight_12 - weight_12
        n22 = old_weight_22 - weight_22
        det_n = n11 * n22 - n12 * n12
        if det_n <= 0:
            return weightedMoment(sub_image, x_grid, y_grid, weight_11, weight_12, weight_22)

        moment_x2 = n22 / det_n
        moment_xy = -n12 / det_n
        moment_y2 = n11 / det_n
        if np.any([moment_x2 <= 0, moment_y2 <= 0]):
            return weightedMoment(sub_image, x_grid, y_grid, weight_11, weight_12, weight_22)

    # if we haven't converged return new values
    return moment_y2, moment_x2, moment_xy, SourceDetectionFlag.BAD_SHAPE


def weightedMoment(
    sub_image: np.ndarray,
    x_grid: np.ndarray,
    y_grid: np.ndarray,
    weight_11: float,
    weight_12: float,
    weight_22: float,
) -> tuple[float, float, float, int]:
    """Compute a single-pass weighted second moment as a fall-back.

    Parameters
    ----------
    sub_image : numpy.ndarray
        Sub-image pixel values.
    x_grid : numpy.ndarray
        x coordinate grid relative to the source centre.
    y_grid : numpy.ndarray
        y coordinate grid relative to the source centre.
    weight_11 : float
        Inverse-covariance matrix element (1,1) for the weighting Gaussian.
    weight_12 : float
        Inverse-covariance matrix element (1,2).
    weight_22 : float
        Inverse-covariance matrix element (2,2).

    Returns
    -------
    tuple[float, float, float, int]
        Second moment in x, y, cross-moment xy, and convergence flag
        ``SourceDetectionFlag.BAD_SHAPE``.
    """

    r2 = x_grid * x_grid * weight_11 + y_grid * y_grid * weight_22 + 2 * weight_12 * x_grid * y_grid
    weight = np.exp(-r2 / 2)

    moment_x2 = (sub_image * weight * (x_grid) ** 2).sum() / (sub_image * weight).sum()
    moment_y2 = (sub_image * weight * (y_grid) ** 2).sum() / (sub_image * weight).sum()
    moment_xy = (sub_image * weight * x_grid * y_grid).sum() / (sub_image * weight).sum()

    return moment_x2, moment_y2, moment_xy, SourceDetectionFlag.BAD_SHAPE


def calculateApproximateMagnitude(
    instrument_params: dict[str, Any],
    instrument_flux: np.ndarray,
    exposure_time: float,
) -> np.ndarray:
    """Convert instrument flux to approximate Gaia magnitudes.

    Uses an empirical linear fit of the form
    ``mag = slope * (-2.5 * log10(flux / t)) + intercept``.

    Parameters
    ----------
    instrument_params : dict[str, Any]
        Instrument parameters; must contain ``magFit`` key with
        ``[slope, intercept]``.
    instrument_flux : numpy.ndarray
        Instrument flux values (total counts).
    exposure_time : float
        Exposure time in seconds.

    Returns
    -------
    numpy.ndarray
        Estimated Gaia magnitudes.
    """

    mag = (
        -2.5 * np.log10(instrument_flux / exposure_time) * instrument_params["magFit"][0]
        + instrument_params["magFit"][1]
    )

    return mag
