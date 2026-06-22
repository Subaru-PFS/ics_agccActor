"""Record/replay tests using real FLI camera FITS files from images/run28/.

These tests require:
- ``images/run28/`` symlink to be present (real hardware FITS data)
- ``PFS_INSTDATA_DIR`` to be set in the environment (for agcc.yaml config)

All tests in this module are marked ``real_data`` and skip automatically when
either condition is not met.

The run28 dataset (visit 143362) contains 4 combined FITS files, each with:
- 6 image extensions (CAM1–CAM6, 1033×1072 uint16)
- 6 binary table extensions (TABLE1–TABLE6) with centroid results written
  by the production actor at observation time.

Re-running ``centroid.getCentroidsSep`` on the same raw images with the same
configuration must reproduce the embedded centroid values, within floating-
point tolerance.  Any divergence signals a regression in the centroiding code.
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from astropy.io import fits

from agccActor import centroid, photometry
from agccActor.photometry import spotDtype

pytestmark = pytest.mark.real_data

# ---------------------------------------------------------------------------
# Module-level paths (resolved relative to the project root)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent
_RUN28_DIR = _REPO_ROOT / "images" / "run28"
_RUN28_FITS = _RUN28_DIR / "agcc_143362_01043046.fits"
_RUN28_FITS_ALL = [_RUN28_DIR / f"agcc_143362_0104304{i}.fits" for i in range(6, 10)]
_DETECTED_CSV = _RUN28_DIR / "1671605105044996096-detected.csv"


def _skip_if_missing():
    """Called at top of each test so the skip reason is specific."""
    if not _RUN28_DIR.is_dir():
        pytest.skip("images/run28/ not available")
    if not os.environ.get("PFS_INSTDATA_DIR"):
        pytest.skip("PFS_INSTDATA_DIR not set")


@pytest.fixture(scope="module")
def real_params():
    """Load centroiding and image parameters once for the whole module."""
    _skip_if_missing()
    cParms, iParms = centroid.getParams(None)
    return cParms, iParms


@pytest.fixture(scope="module")
def run28_hdul():
    """Open the first run28 FITS file (module scope — open once, close after)."""
    _skip_if_missing()
    with fits.open(_RUN28_FITS) as hdul:
        # Read everything into memory so the file handle can be closed.
        hdus = [hdu.copy() for hdu in hdul]
    return hdus


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _cam_image(hdus, cam_id: int) -> np.ndarray:
    """Return the uint16 image array for 1-based ``cam_id`` from the HDU list."""
    return hdus[cam_id].data.astype(np.uint16)


def _cam_table(hdus, cam_id: int) -> np.ndarray:
    """Return the centroid BinTable data for 1-based ``cam_id``."""
    return hdus[cam_id + 6].data  # TABLE{N} extensions start at index 7


# ---------------------------------------------------------------------------
# Overscan / bad-column utilities
# ---------------------------------------------------------------------------

class TestImagePreprocessing:
    def test_subOverscan_reduces_background(self, run28_hdul):
        """subOverscan should lower the median pixel value."""
        raw = _cam_image(run28_hdul, cam_id=1).astype(float)
        before = float(np.median(raw))
        processed = centroid.subOverscan(raw.copy())
        after = float(np.median(processed))
        assert after < before, (
            f"subOverscan did not reduce background: before={before:.1f} after={after:.1f}"
        )

    def test_subOverscan_output_shape(self, run28_hdul):
        raw = _cam_image(run28_hdul, cam_id=1).astype(float)
        out = centroid.subOverscan(raw.copy())
        assert out.shape == raw.shape

    def test_interpBadCol_smooths_spike(self, run28_hdul):
        """Injecting a hot column and interpolating it should reduce its deviation."""
        raw = _cam_image(run28_hdul, cam_id=1).astype(float)
        col = 200  # arbitrary interior column
        raw[:, col] = 60000  # inject a very high spike
        spike_before = float(np.mean(raw[:, col]))

        processed = centroid.interpBadCol(raw.copy(), [col])
        spike_after = float(np.mean(processed[:, col]))

        assert spike_after < spike_before * 0.5, (
            f"interpBadCol did not remove spike: before={spike_before:.0f} after={spike_after:.0f}"
        )

    def test_interpBadCol_no_bad_cols_is_noop(self, run28_hdul):
        raw = _cam_image(run28_hdul, cam_id=1).astype(float)
        original = raw.copy()
        result = centroid.interpBadCol(raw.copy(), [])
        np.testing.assert_array_equal(result, original)


# ---------------------------------------------------------------------------
# Centroid replay — per camera
# ---------------------------------------------------------------------------

class TestCentroidReplay:
    @pytest.mark.parametrize("cam_id", range(1, 7))
    def test_spot_count_matches_fits_table(self, run28_hdul, real_params, cam_id):
        """Re-running centroiding on a real image must yield the same spot count
        as the TABLE{N} extension written by the production actor."""
        cParms, iParms = real_params
        cParms = dict(cParms)
        cParms["expTime"] = 7.0  # from exposure_info.csv

        image = _cam_image(run28_hdul, cam_id=cam_id)
        result = centroid.getCentroidsSep(image, iParms, cParms, spotDtype, agcid=cam_id - 1)
        table = _cam_table(run28_hdul, cam_id=cam_id)

        assert len(result) == len(table), (
            f"CAM{cam_id}: expected {len(table)} spots, got {len(result)}"
        )

    @pytest.mark.parametrize("cam_id", range(1, 7))
    def test_centroid_positions_close_to_fits_table(self, run28_hdul, real_params, cam_id):
        """Centroid x/y positions must match the FITS table values within 0.1 pixel."""
        cParms, iParms = real_params
        cParms = dict(cParms)
        cParms["expTime"] = 7.0

        image = _cam_image(run28_hdul, cam_id=cam_id)
        result = centroid.getCentroidsSep(image, iParms, cParms, spotDtype, agcid=cam_id - 1)
        table = _cam_table(run28_hdul, cam_id=cam_id)

        if len(result) == 0:
            pytest.skip(f"CAM{cam_id}: no spots detected — cannot compare positions")

        # Sort both by x-position for stable comparison
        result_sorted = result[np.argsort(result["centroid_x_pix"])]
        table_sorted = table[np.argsort(table["centroid_x"])]

        np.testing.assert_allclose(
            result_sorted["centroid_x_pix"],
            table_sorted["centroid_x"],
            atol=0.1,
            err_msg=f"CAM{cam_id}: centroid_x mismatch",
        )
        np.testing.assert_allclose(
            result_sorted["centroid_y_pix"],
            table_sorted["centroid_y"],
            atol=0.1,
            err_msg=f"CAM{cam_id}: centroid_y mismatch",
        )

    @pytest.mark.parametrize("cam_id", range(1, 7))
    def test_output_dtype_matches_spotDtype(self, run28_hdul, real_params, cam_id):
        """getCentroidsSep must return a structured array with the canonical spotDtype."""
        cParms, iParms = real_params
        cParms = dict(cParms)
        cParms["expTime"] = 7.0

        image = _cam_image(run28_hdul, cam_id=cam_id)
        result = centroid.getCentroidsSep(image, iParms, cParms, spotDtype, agcid=cam_id - 1)

        assert result.dtype == spotDtype, f"CAM{cam_id}: dtype mismatch: {result.dtype} != {spotDtype}"


# ---------------------------------------------------------------------------
# CSV cross-validation
# ---------------------------------------------------------------------------

class TestCsvCrossValidation:
    def test_detected_csv_matches_fits_table_spot_counts(self, run28_hdul):
        """The spot counts from detected.csv must match the FITS TABLE{N} extensions."""
        if not _DETECTED_CSV.exists():
            pytest.skip("detected.csv not available")

        df = pd.read_csv(_DETECTED_CSV)
        # Filter to the first exposure (agc_exposure_id 1043046)
        df_exp = df[df["agc_exposure_id"] == 1043046]

        for cam_id in range(1, 7):
            table = _cam_table(run28_hdul, cam_id=cam_id)
            # agc_camera_id in CSV is 0-indexed
            csv_count = len(df_exp[df_exp["agc_camera_id"] == cam_id - 1])
            assert csv_count == len(table), (
                f"CAM{cam_id}: detected.csv has {csv_count} spots, FITS TABLE has {len(table)}"
            )

    def test_detected_csv_centroid_x_matches_fits(self, run28_hdul):
        """CSV centroid_x_pix values must match FITS TABLE centroid_x within 0.01 pix."""
        if not _DETECTED_CSV.exists():
            pytest.skip("detected.csv not available")

        df = pd.read_csv(_DETECTED_CSV)
        df_exp = df[df["agc_exposure_id"] == 1043046]

        for cam_id in range(1, 7):
            table = _cam_table(run28_hdul, cam_id=cam_id)
            csv_rows = df_exp[df_exp["agc_camera_id"] == cam_id - 1].sort_values("centroid_x_pix")
            tbl_x = np.sort(table["centroid_x"])

            np.testing.assert_allclose(
                csv_rows["centroid_x_pix"].values,
                tbl_x,
                atol=0.01,
                err_msg=f"CAM{cam_id}: centroid_x mismatch between CSV and FITS table",
            )


# ---------------------------------------------------------------------------
# photometry.measure — end-to-end through the worker interface
# ---------------------------------------------------------------------------

class TestPhotometryMeasureReplay:
    @pytest.mark.parametrize("cam_id", range(1, 7))
    def test_measure_dtype(self, run28_hdul, real_params, cam_id):
        """photometry.measure() must return a structured array with spotDtype."""
        cParms, iParms = real_params
        cParms = dict(cParms)
        cParms["expTime"] = 7.0

        image = _cam_image(run28_hdul, cam_id=cam_id)
        result = photometry.measure(image, agcid=cam_id - 1, cParms=cParms, iParms=iParms, cMethod="sep")

        assert result.dtype == spotDtype

    @pytest.mark.parametrize("cam_id", range(1, 7))
    def test_measure_spot_count_matches_fits(self, run28_hdul, real_params, cam_id):
        """photometry.measure() must find the same number of spots as the FITS table."""
        cParms, iParms = real_params
        cParms = dict(cParms)
        cParms["expTime"] = 7.0

        image = _cam_image(run28_hdul, cam_id=cam_id)
        result = photometry.measure(image, agcid=cam_id - 1, cParms=cParms, iParms=iParms, cMethod="sep")
        table = _cam_table(run28_hdul, cam_id=cam_id)

        assert len(result) == len(table), (
            f"CAM{cam_id}: photometry.measure returned {len(result)} spots, expected {len(table)}"
        )


# ---------------------------------------------------------------------------
# Stability across exposures
# ---------------------------------------------------------------------------

class TestExposureStability:
    def test_spot_counts_stable_across_exposures(self, real_params):
        """Star counts per camera should be consistent across all 4 run28 exposures."""
        missing = [p for p in _RUN28_FITS_ALL if not p.exists()]
        if missing:
            pytest.skip(f"Some run28 FITS files missing: {missing}")

        cParms, iParms = real_params
        cParms = dict(cParms)
        cParms["expTime"] = 7.0

        counts_per_cam = {cam_id: [] for cam_id in range(1, 7)}

        for fits_path in _RUN28_FITS_ALL:
            with fits.open(fits_path) as hdul:
                for cam_id in range(1, 7):
                    image = hdul[cam_id].data.astype(np.uint16)
                    result = centroid.getCentroidsSep(
                        image, iParms, cParms, spotDtype, agcid=cam_id - 1
                    )
                    counts_per_cam[cam_id].append(len(result))

        for cam_id, counts in counts_per_cam.items():
            assert max(counts) - min(counts) <= 3, (
                f"CAM{cam_id}: spot count varies too much across exposures: {counts}"
            )
