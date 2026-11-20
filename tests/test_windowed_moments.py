"""The scale of the second moments `centroid.windowedFWHM` returns.

Synthetic Gaussian spots of known covariance go through the routine; no camera data and
no ``pfs_instdata`` are needed.
"""

import numpy as np
import pytest
from agccActor import centroid

# One region covering the whole synthetic image, given for both detector halves.
SIZE = 101
REGION = (0, SIZE, 0, SIZE, 0, SIZE, 0, SIZE)


def gaussianSpot(sxx, syy, sxy, xc=50.3, yc=49.6, flux=1.0e5):
    """Return an image of a Gaussian spot with the given covariance (pix^2)."""
    y, x = np.mgrid[0:SIZE, 0:SIZE].astype(float)
    dx = x - xc
    dy = y - yc
    det = sxx * syy - sxy**2
    r2 = (syy * dx**2 - 2 * sxy * dx * dy + sxx * dy**2) / det
    return flux / (2 * np.pi * np.sqrt(det)) * np.exp(-r2 / 2), xc, yc


@pytest.mark.parametrize(
    "sxx, syy, sxy",
    [
        (4.0, 4.0, 0.0),  # round
        (9.0, 9.0, 0.0),  # round, larger
        (12.0, 5.0, 0.0),  # elongated along x
        (5.0, 12.0, 0.0),  # elongated along y
        (8.0, 6.0, 3.0),  # elongated off the pixel axes
        (8.0, 6.0, -3.0),
    ],
)
def test_converged_moments_are_the_spot_covariance(sxx, syy, sxy):
    """A converged spot's moments are its covariance, not the weighted moments of the last pass."""
    image, xc, yc = gaussianSpot(sxx, syy, sxy)

    mxx, myy, mxy, flag = centroid.windowedFWHM(image, xc, yc, REGION, 0)

    assert flag == 0
    np.testing.assert_allclose([mxx, myy, mxy], [sxx, syy, sxy], rtol=0.02, atol=0.02)

    # Negative control: a Gaussian under its matched Gaussian weight has half its variance,
    # which is what the weighted moments of the last pass are.
    assert not np.allclose([mxx, myy], [sxx / 2, syy / 2], rtol=0.2)


def test_right_half_gives_the_same_moments():
    """The detector half only selects the region the window is cut to."""
    image, xc, yc = gaussianSpot(7.0, 5.0, 1.0)

    left = centroid.windowedFWHM(image, xc, yc, REGION, 0)
    right = centroid.windowedFWHM(image, xc, yc, REGION, 1)

    assert left == right
