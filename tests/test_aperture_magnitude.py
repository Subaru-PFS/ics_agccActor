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
# Two regions of 300 x 300 pixels side by side, as the two halves of a detector.
REGION = [0, 300, 0, 300, 300, 600, 0, 300]
# (x, y) within a half, and the star's total flux (counts): a factor 80 from first to last.
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
    rng = np.random.default_rng(3115)
    data = 100.0 + rng.normal(0.0, NOISE, (300, 600))
    y, x = np.mgrid[0:300, 0:600].astype(float)
    for offset in (0, 300):
        for xc, yc, flux in STARS:
            r2 = (x - xc - offset) ** 2 + (y - yc) ** 2
            data += flux / (2 * np.pi * SIGMA**2) * np.exp(-r2 / (2 * SIGMA**2))
    return data


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

    flux = np.array([star[2] for star in STARS] * 2)
    expected = -2.5 * np.log10(flux / EXPTIME) + centroid.APERTURE_ZERO_POINT
    # The 12-pixel aperture holds all of these stars' light; the faintest has 3% of noise in it.
    np.testing.assert_allclose(result["estimated_magnitude"], expected, atol=0.06)
    np.testing.assert_allclose(result["estimated_magnitude"][[0, 1, 4, 5]], expected[[0, 1, 4, 5]], atol=0.01)

    # Negative control: the isophotal flux, which the magnitude came from before, holds less of
    # a fainter star's light. On the same scale the faintest star reads more than 0.1 mag faint.
    isophotal = centroid.calculateApertureMagnitude(
        result["image_moment_00_pix"], EXPTIME, centroid.APERTURE_ZERO_POINT
    )
    assert (isophotal - expected)[[3, 7]].min() > 0.1
    assert not np.allclose(isophotal, expected, atol=0.06)
    # The flux column itself is still the isophotal one.
    assert (result["image_moment_00_pix"][[3, 7]] < 0.9 * STARS[3][2]).all()


def test_right_half_spots_are_measured_on_their_own_region(image, iParms, cParms):
    """Both halves hold the same stars: their magnitudes agree, each from its own image region."""
    result = measured(centroid.getCentroidsSep(image, iParms, cParms, photometry.spotDtype, 0))
    np.testing.assert_allclose(
        result["estimated_magnitude"][:4], result["estimated_magnitude"][4:], atol=0.06
    )
    assert (result["flags"][4:] & 1 == 1).all() and (result["flags"][:4] & 1 == 0).all()


def test_radius_and_zero_point_come_from_the_config(image, iParms, cParms):
    default = measured(centroid.getCentroidsSep(image, iParms, cParms, photometry.spotDtype, 0))
    iParms["aperturePhotometry"] = {"radius": 4.0, "zeroPoint": 25.0}
    small = measured(centroid.getCentroidsSep(image, iParms, cParms, photometry.spotDtype, 0))

    # A 4-pixel aperture holds 1 - exp(-4^2 / (2 sigma^2)) = 72% of a Gaussian star: 0.355 mag less.
    lost = -2.5 * np.log10(1 - np.exp(-(4.0**2) / (2 * SIGMA**2)))
    shift = small["estimated_magnitude"] - default["estimated_magnitude"]
    np.testing.assert_allclose(shift[[0, 1, 4, 5]], 25.0 - centroid.APERTURE_ZERO_POINT + lost, atol=0.02)


def test_aperture_params_default_per_value():
    assert centroid.getAperturePhotometryParams({}) == (12.0, 28.26)
    assert centroid.getAperturePhotometryParams({"aperturePhotometry": None}) == (12.0, 28.26)
    assert centroid.getAperturePhotometryParams({"aperturePhotometry": {"radius": 16}}) == (16.0, 28.26)
    assert centroid.getAperturePhotometryParams({"aperturePhotometry": {"zeroPoint": 27}}) == (12.0, 27.0)


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
