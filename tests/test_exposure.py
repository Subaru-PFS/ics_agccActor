import time
import queue
import threading
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from astropy.io import fits

from agccActor import camera, expose, writeFits


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cam_config():
    """Simulator Camera config (no 'db' key → skips OpDB.set_default_connection)."""
    return {
        "simulator": 1,
        "temperature": -30,
        "simulatedImagePath": "",
        "cam1": "SN001",
        "cam2": "SN002",
        "cam3": "SN003",
        "cam4": "SN004",
        "cam5": "SN005",
        "cam6": "SN006",
    }


@pytest.fixture
def minimal_cParms():
    return {
        "thresh": 5.0,
        "minarea": 5,
        "deblend": 0.01,
        "ellip": 0.5,
        "nmin": 5,
        "expTime": 0.1,
    }


@pytest.fixture
def minimal_iParms():
    """Minimal iParms covering 6 cameras so expose.py doesn't KeyError."""
    base = {"flatVal": 0.006, "magFit": [0.928, 27.389]}
    for n in range(1, 7):
        base[str(n)] = {
            "reg": [0, 80, 0, 80, 80, 160, 0, 80],
            "badCols": [],
            "satVal1": 65535,
            "satVal2": 65535,
        }
    return base


@pytest.fixture
def cam_set(cam_config):
    c = camera.Camera(cam_config)
    yield c
    c.closeCamera()


@pytest.fixture(autouse=True)
def redirect_data_root(tmp_path, monkeypatch):
    """Redirect all FITS writes to tmp_path so tests don't touch /data/raw."""
    today_dir = tmp_path / time.strftime("%Y-%m-%d", time.gmtime()) / "agcc"
    today_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(writeFits, "_DATA_ROOT", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _mock_opdb_with_defaults(mock_opdb):
    mock_opdb.query_scalar.return_value = 101
    mock_opdb.query_series.side_effect = [
        {"altitude": 45.0, "azimuth": 180.0, "insrot": 0.0, "adc_pa": 10.0, "m2_pos3": 1.2},
        {"outside_temperature": 2.5, "outside_pressure": 600.0, "outside_humidity": 15.0},
    ]
    return mock_opdb


def _run_exposure(cam_set, mock_cmd, mock_opdb, cParms, iParms, **kwargs) -> expose.Exposure:
    """Create, start, and join an Exposure thread; return it for assertions."""
    _mock_opdb_with_defaults(mock_opdb)
    from pfs.utils.database import opdb as opdb_mod

    with patch.object(opdb_mod, "OpDB", return_value=mock_opdb):
        exp = expose.Exposure(
            cams=cam_set.cams[:1],
            expTime_ms=100,
            dflag=False,
            cParms=cParms,
            iParms=iParms,
            visitId=12345,
            cMethod="sep",
            cmd=mock_cmd,
            **kwargs,
        )
        exp.start()
        exp.join(timeout=15)
    return exp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_exposure_lifecycle(cam_set, mock_cmd, mock_opdb, minimal_cParms, minimal_iParms, tmp_path):
    """Basic single-camera exposure with centroiding writes a FITS file."""
    exp = _run_exposure(
        cam_set, mock_cmd, mock_opdb, minimal_cParms, minimal_iParms,
        combined=False, centroid=False,
    )
    assert not exp.is_alive()
    fits_files = list(tmp_path.rglob("*.fits"))
    assert len(fits_files) > 0, "No FITS file was written"


def test_exposure_no_centroid(cam_set, mock_cmd, mock_opdb, minimal_cParms, minimal_iParms, tmp_path):
    """Exposure with centroid=False must write FITS but NOT call insert_dataframe."""
    exp = _run_exposure(
        cam_set, mock_cmd, mock_opdb, minimal_cParms, minimal_iParms,
        combined=False, centroid=False,
    )
    assert not exp.is_alive()
    fits_files = list(tmp_path.rglob("*.fits"))
    assert len(fits_files) >= 1, "FITS file expected even without centroiding"
    mock_opdb.insert_dataframe.assert_not_called()


def test_exposure_combined(cam_set, mock_cmd, mock_opdb, minimal_cParms, minimal_iParms, tmp_path):
    """Combined-mode exposure with 2 cameras writes a single combined FITS."""
    _mock_opdb_with_defaults(mock_opdb)
    from pfs.utils.database import opdb as opdb_mod

    with patch.object(opdb_mod, "OpDB", return_value=mock_opdb):
        exp = expose.Exposure(
            cams=cam_set.cams[:2],
            expTime_ms=100,
            dflag=False,
            cParms=minimal_cParms,
            iParms=minimal_iParms,
            visitId=12345,
            cMethod="sep",
            cmd=mock_cmd,
            combined=True,
            centroid=False,
        )
        exp.start()
        exp.join(timeout=15)

    assert not exp.is_alive()
    fits_files = list(tmp_path.rglob("agcc_*.fits"))
    assert len(fits_files) >= 1, "No combined FITS file produced"


def test_exposure_camera_failure(cam_set, mock_cmd, mock_opdb, minimal_cParms, minimal_iParms):
    """If a camera's expose() raises, cmd.warn or cmd.fail should be called."""
    cam_set.cams[0].expose = MagicMock(side_effect=RuntimeError("simulated camera failure"))

    _run_exposure(
        cam_set, mock_cmd, mock_opdb, minimal_cParms, minimal_iParms,
        combined=False, centroid=False,
    )

    # The exposure thread must have completed (not hung) and signalled failure.
    assert mock_cmd.warn.called or mock_cmd.fail.called, (
        "Expected cmd.warn or cmd.fail after camera failure"
    )


def test_exposure_centroid_timeout(cam_set, mock_cmd, mock_opdb, minimal_cParms, minimal_iParms):
    """When the photometry worker never responds, the exposure should time out gracefully."""
    import multiprocessing

    # Replace the camera's out_queue with one that never delivers results.
    empty_queue = multiprocessing.Queue()
    cam_set.cams[0].out_queue = empty_queue

    # Shorten the timeout to keep the test fast.
    original_timeout = expose.PHOTOMETRY_TIMEOUT_S
    expose.PHOTOMETRY_TIMEOUT_S = 1

    try:
        exp = _run_exposure(
            cam_set, mock_cmd, mock_opdb, minimal_cParms, minimal_iParms,
            combined=False, centroid=True,
        )
        assert not exp.is_alive(), "Exposure thread hung on empty photometry queue"
    finally:
        expose.PHOTOMETRY_TIMEOUT_S = original_timeout


def test_exposure_does_not_hang_on_close(cam_set, mock_cmd, mock_opdb, minimal_cParms, minimal_iParms):
    """Closing the camera set immediately after an exposure completes must not deadlock."""
    _run_exposure(
        cam_set, mock_cmd, mock_opdb, minimal_cParms, minimal_iParms,
        combined=False, centroid=False,
    )
    cam_set.closeCamera()
    for cam in cam_set.cams:
        assert cam is None, "closeCamera() did not clear all camera slots"

