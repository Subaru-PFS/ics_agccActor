"""``estimated_magnitude`` from the flux in a fixed aperture.

Synthetic Gaussian stars of known flux go through `centroid.getCentroidsSep`; no camera data
and no ``pfs_instdata`` are needed.
"""

import logging

import numpy as np
import pytest
from agccActor import centroid, photometry

EXPTIME = 3.0
SIGMA = 2.5
NOISE = 3.0
SKY = 60.0
RIGHT_HALF_BRIGHTER = 3.0
# Two regions of 300 x 300 pixels side by side, as the two halves of a detector.
REGION = [0, 300, 0, 300, 300, 600, 0, 300]
# (x, y) within a half, and the star's total flux (counts) on the left half: a factor 80 from
# first to last. The right half holds the same stars `RIGHT_HALF_BRIGHTER` times as bright.
STARS = [(60.3, 70.6, 2.0e5), (220.7, 80.2, 5.0e4), (80.4, 230.5, 1.2e4), (230.6, 220.3, 2.5e3)]


@pytest.fixture
def iParms():
    params = {"magFit": [0.928, 27.389]}
    for n in range(1, 7):
        params[str(n)] = {"reg": list(REGION), "badCols": [], "satVal1": 65535, "satVal2": 65535}
    return params


@pytest.fixture
def cParms():
    return {"thresh": 10, "minarea": 15, "deblend": 0.01, "ellip": 0.6, "nmin": 10, "expTime": EXPTIME}


@pytest.fixture
def image():
    """Stars on a sky that the overscan columns (the first and last four) do not see."""
    rng = np.random.default_rng(3115)
    data = 100.0 + rng.normal(0.0, NOISE, (300, 600))
    data[:, 4:-4] += SKY
    y, x = np.mgrid[0:300, 0:600].astype(float)
    for offset, brighter in ((0, 1.0), (300, RIGHT_HALF_BRIGHTER)):
        for xc, yc, flux in STARS:
            r2 = (x - xc - offset) ** 2 + (y - yc) ** 2
            data += brighter * flux / (2 * np.pi * SIGMA**2) * np.exp(-r2 / (2 * SIGMA**2))
    return data


#: The stars' flux in the order `measured` returns them: the left half, then the right.
FLUX = np.array([star[2] for star in STARS] + [RIGHT_HALF_BRIGHTER * star[2] for star in STARS])
EXPECTED = -2.5 * np.log10(FLUX / EXPTIME) + centroid.APERTURE_ZERO_POINT


def measured(result) -> np.ndarray:
    """The rows of ``result`` for `STARS` on the left half then on the right half."""
    rows = []
    for offset in (0, 300):
        for xc, yc, _ in STARS:
            distance = np.hypot(result["centroid_x_pix"] - xc - offset, result["centroid_y_pix"] - yc)
            assert distance.min() < 1.0, "a star was not detected"
            rows.append(int(np.argmin(distance)))
    return result[rows]


def test_magnitude_is_linear_in_the_stars_light(image, iParms, cParms):
    result = measured(centroid.getCentroidsSep(image, iParms, cParms, photometry.spotDtype, 0))

    # The 12-pixel aperture holds all of these stars' light; the faintest has 3% of noise in it.
    np.testing.assert_allclose(result["estimated_magnitude"], EXPECTED, atol=0.06)
    bright = [0, 1, 4, 5, 6]
    np.testing.assert_allclose(result["estimated_magnitude"][bright], EXPECTED[bright], atol=0.01)

    # The aperture is summed on the image with the sky taken out: 12 pixels of this sky hold
    # 27,000 counts, more than six of the eight stars.
    np.testing.assert_allclose(result["background"], SKY, atol=2.0)
    skyInAperture = np.pi * centroid.APERTURE_RADIUS_PIX**2 * SKY
    withSky = centroid.calculateApertureMagnitude(FLUX + skyInAperture, EXPTIME, centroid.APERTURE_ZERO_POINT)
    assert not np.allclose(result["estimated_magnitude"], withSky, atol=0.06)

    # Negative control: the isophotal flux, which the magnitude came from before, holds less of
    # a fainter star's light. On the same scale the faintest star reads more than 0.1 mag faint.
    isophotal = centroid.calculateApertureMagnitude(
        result["image_moment_00_pix"], EXPTIME, centroid.APERTURE_ZERO_POINT
    )
    assert (isophotal - EXPECTED)[3] > 0.1
    assert not np.allclose(isophotal, EXPECTED, atol=0.06)
    # The flux column itself is still the isophotal one.
    assert result["image_moment_00_pix"][3] < 0.9 * STARS[3][2]


def test_each_half_is_measured_on_its_own_region_in_row_order(image, iParms, cParms):
    """The right half's stars are three times as bright: each row has its own half's flux."""
    result = measured(centroid.getCentroidsSep(image, iParms, cParms, photometry.spotDtype, 0))

    left, right = result["estimated_magnitude"][:4], result["estimated_magnitude"][4:]
    np.testing.assert_allclose(right - left, -2.5 * np.log10(RIGHT_HALF_BRIGHTER), atol=0.06)
    assert (result["flags"][4:] & 1 == 1).all() and (result["flags"][:4] & 1 == 0).all()
    # Negative control: measured on the other half's region, or with the halves in the other
    # order, each star would have the other half's magnitude, 1.19 mag away.
    swapped = np.concatenate([EXPECTED[4:], EXPECTED[:4]])
    assert not np.allclose(result["estimated_magnitude"], swapped, atol=0.5)


def test_a_half_without_spots(image, iParms, cParms):
    """An empty right half leaves the left half's spots and magnitudes as they are."""
    both = measured(centroid.getCentroidsSep(image, iParms, cParms, photometry.spotDtype, 0))
    image[:, 304:-4] = (100.0 + SKY) + np.random.default_rng(1).normal(0.0, NOISE, (300, 292))
    result = centroid.getCentroidsSep(image, iParms, cParms, photometry.spotDtype, 0)

    assert len(result) == len(STARS) and (result["flags"] & 1 == 0).all()
    np.testing.assert_allclose(
        np.sort(result["estimated_magnitude"]), np.sort(both["estimated_magnitude"][:4]), atol=0.01
    )


def test_radius_and_zero_point_come_from_the_config(image, iParms, cParms):
    default = measured(centroid.getCentroidsSep(image, iParms, cParms, photometry.spotDtype, 0))
    iParms["aperturePhotometry"] = {"radius": 4.0, "zeroPoint": 25.0}
    small = measured(centroid.getCentroidsSep(image, iParms, cParms, photometry.spotDtype, 0))
    assert centroid.getAperturePhotometryParams(iParms) == (4.0, 25.0)

    # A 4-pixel aperture holds 1 - exp(-4^2 / (2 sigma^2)) = 72% of a Gaussian star: 0.355 mag less.
    lost = -2.5 * np.log10(1 - np.exp(-(4.0**2) / (2 * SIGMA**2)))
    shift = small["estimated_magnitude"] - default["estimated_magnitude"]
    np.testing.assert_allclose(shift[[0, 1, 4, 5]], 25.0 - centroid.APERTURE_ZERO_POINT + lost, atol=0.02)


def test_aperture_params_default_per_value():
    assert centroid.getAperturePhotometryParams({}) == (12.0, 28.26)
    assert centroid.getAperturePhotometryParams({"aperturePhotometry": None}) == (12.0, 28.26)
    assert centroid.getAperturePhotometryParams({"aperturePhotometry": {"radius": 16}}) == (16.0, 28.26)
    assert centroid.getAperturePhotometryParams({"aperturePhotometry": {"zeroPoint": 27}}) == (12.0, 27.0)


@pytest.mark.parametrize(
    "entry",
    [
        12.0,  # a scalar where the mapping belongs
        "radius: 12",
        [12.0, 28.26],
        {"radius": None, "zeroPoint": None},  # keys left empty
        {"radius": "twelve", "zeroPoint": "x"},
        {"radius": [12.0], "zeroPoint": {}},
        {"radius": 0, "zeroPoint": float("nan")},
        {"radius": -3.0, "zeroPoint": float("inf")},
        {"radius": float("nan")},
    ],
)
def test_a_slip_in_the_config_gives_the_defaults(entry, image, iParms, cParms, caplog):
    """agcc.yaml is read again at every exposure: a bad entry must cost neither spots nor magnitudes."""
    good = centroid.getCentroidsSep(image, iParms, cParms, photometry.spotDtype, 0)
    iParms["aperturePhotometry"] = entry
    with caplog.at_level(logging.WARNING, logger="agcc"):
        assert centroid.getAperturePhotometryParams(iParms) == (12.0, 28.26)
        result = centroid.getCentroidsSep(image, iParms, cParms, photometry.spotDtype, 0)

    assert "aperturePhotometry" in caplog.text
    np.testing.assert_array_equal(result["estimated_magnitude"], good["estimated_magnitude"])
    np.testing.assert_array_equal(result["centroid_x_pix"], good["centroid_x_pix"])


def test_valid_config_values_are_not_replaced(iParms, caplog):
    """Negative control for the test above: good values are used, without a warning."""
    iParms["aperturePhotometry"] = {"radius": "16", "zeroPoint": 0}
    with caplog.at_level(logging.WARNING, logger="agcc"):
        assert centroid.getAperturePhotometryParams(iParms) == (16.0, 0.0)
    assert caplog.text == ""


def test_failed_aperture_photometry_keeps_the_centroids(image, iParms, cParms, monkeypatch, caplog):
    """If the aperture step raises, the spots are still returned, with the isophotal magnitude."""
    good = centroid.getCentroidsSep(image, iParms, cParms, photometry.spotDtype, 0)

    def broken(data, spots, radius):
        raise RuntimeError("no aperture today")

    monkeypatch.setattr(centroid, "apertureFluxes", broken)
    with caplog.at_level(logging.WARNING, logger="agcc"):
        result = centroid.getCentroidsSep(image, iParms, cParms, photometry.spotDtype, 0)

    assert len(result) == len(good)
    for column in (
        "centroid_x_pix",
        "centroid_y_pix",
        "image_moment_00_pix",
        "central_image_moment_20_pix",
        "flags",
    ):
        np.testing.assert_array_equal(result[column], good[column])
    np.testing.assert_allclose(
        result["estimated_magnitude"],
        centroid.calculateApproximateMagnitude(iParms, result["image_moment_00_pix"], EXPTIME),
    )
    assert "aperture photometry failed" in caplog.text
    # Negative control: that is not the magnitude an exposure normally gets.
    assert not np.allclose(result["estimated_magnitude"], good["estimated_magnitude"], atol=0.05)


def test_calculateApertureMagnitude():
    magnitudes = centroid.calculateApertureMagnitude(np.array([3000.0, 300.0, 0.0, -50.0]), 3.0, 28.26)
    np.testing.assert_allclose(magnitudes[:2], [28.26 - 7.5, 28.26 - 5.0])
    # A spot with no positive flux has no magnitude.
    assert np.isnan(magnitudes[2:]).all()
    # Negative control: a brighter star has the smaller magnitude.
    assert magnitudes[0] < magnitudes[1]


def test_no_spots():
    assert (
        len(centroid.apertureFluxes(np.zeros((50, 50)), np.zeros(0, dtype=[("x", "f8"), ("y", "f8")]), 12.0))
        == 0
    )
