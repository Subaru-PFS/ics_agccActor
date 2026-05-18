"""Tests for the fake_camera simulator and the Camera controller.

These tests run entirely in simulator mode and do not require real hardware
or the FLI Cython extension.
"""

import time
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from agccActor import camera
from agccActor.fli import fake_camera
from agccActor.setmode import SetMode
from astropy.io import fits

# ---------------------------------------------------------------------------
# Shared camera config (no 'db' key → Camera skips OpDB.set_default_connection)
# ---------------------------------------------------------------------------

@pytest.fixture
def cam_config():
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
def cam_set(cam_config):
    """A fully-initialised Camera (simulator mode); torn down after each test."""
    c = camera.Camera(cam_config)
    yield c
    c.closeCamera()


# ---------------------------------------------------------------------------
# fake_camera.Camera unit tests
# ---------------------------------------------------------------------------

class TestFakeCamera:
    def test_open_sets_ready(self):
        cam = fake_camera.Camera(0, "SN001")
        cam.open()
        assert cam.isReady()
        cam.close()

    def test_close_sets_closed(self):
        cam = fake_camera.Camera(0, "SN001")
        cam.open()
        cam.close()
        assert cam.isClosed()

    def test_default_image_is_zeros(self):
        cam = fake_camera.Camera(0, "SN001")
        cam.open()
        cam.expose()
        assert cam.data.shape == (1033, 1072)
        assert cam.data.dtype == np.uint16
        assert cam.data.sum() == 0  # default rawdata is zeros
        cam.close()

    def test_expose_with_synthetic_fits(self, tmp_path):
        """Camera initialised with a FITS path should return that image data."""
        img = np.ones((1033, 1072), dtype=np.uint16) * 1500
        fits_path = tmp_path / "test_image.fits"
        hdu = fits.PrimaryHDU(img)
        hdu.writeto(str(fits_path))

        cam = fake_camera.Camera(0, "SN001", imgPath=str(fits_path))
        cam.open()
        cam.expose()
        np.testing.assert_array_equal(cam.data, img)
        cam.close()

    def test_temperature_set_and_get(self):
        cam = fake_camera.Camera(0, "SN001")
        cam.open()
        cam.setTemperature(-25.5)
        assert cam.getTemperature() == pytest.approx(-25.5)
        cam.close()

    def test_abort_during_long_exposure(self):
        cam = fake_camera.Camera(0, "SN001")
        cam.open()
        cam.setExpTime(5000)  # 5-second exposure — will be aborted

        cam.expose(blocking=False)
        assert cam.isExposing()

        cam.cancelExposure()
        # Give the exposure thread time to honour the abort.
        deadline = time.monotonic() + 2.0
        while cam.isExposing() and time.monotonic() < deadline:
            time.sleep(0.05)

        assert cam.isReady(), "Camera did not return to READY after abort"
        cam.close()

    def test_set_frame_updates_exp_area(self):
        cam = fake_camera.Camera(0, "SN001")
        cam.open()
        cam.setFrame(10, 20, 200, 100)
        assert cam.expArea == (10, 20, 210, 120)
        cam.close()

    def test_reset_frame_restores_default(self):
        cam = fake_camera.Camera(0, "SN001")
        cam.open()
        cam.setFrame(10, 20, 200, 100)
        cam.resetFrame()
        assert cam.expArea == cam.defaultExpArea
        cam.close()

    def test_mode_set_and_get(self):
        cam = fake_camera.Camera(0, "SN001")
        cam.open()
        cam.setMode(1)
        assert cam.getMode() == 1
        cam.setMode(0)
        assert cam.getMode() == 0
        cam.close()

    def test_invalid_mode_raises(self):
        cam = fake_camera.Camera(0, "SN001")
        cam.open()
        with pytest.raises(fake_camera.FliError):
            cam.setMode(99)
        cam.close()

    def test_get_total_time_after_expose(self):
        cam = fake_camera.Camera(0, "SN001")
        cam.open()
        cam.setExpTime(0)
        cam.expose()
        assert cam.getTotalTime() > 0
        cam.close()

    def test_expose_uses_cropped_region(self, tmp_path):
        """When setFrame crops the sensor, expose() returns the cropped data."""
        full_img = np.arange(1033 * 1072, dtype=np.uint16).reshape(1033, 1072)
        fits_path = tmp_path / "full.fits"
        fits.PrimaryHDU(full_img).writeto(str(fits_path))

        cam = fake_camera.Camera(0, "SN001", imgPath=str(fits_path))
        cam.open()
        cam.setFrame(100, 200, 50, 30)  # x1=100, y1=200, width=50, height=30
        cam.expose()

        expected = full_img[200:230, 100:150]
        np.testing.assert_array_equal(cam.data, expected)
        cam.close()


# ---------------------------------------------------------------------------
# Camera controller (simulator mode)
# ---------------------------------------------------------------------------

class TestCameraController:
    def test_all_six_slots_initialised(self, cam_set):
        assert len(cam_set.cams) == 6
        for n, cam in enumerate(cam_set.cams):
            assert cam is not None, f"Camera slot {n} is None"

    def test_all_cameras_ready(self, cam_set):
        for n, cam in enumerate(cam_set.cams):
            assert cam.isReady(), f"Camera {n} not in READY state"

    def test_agcid_matches_slot(self, cam_set):
        for n, cam in enumerate(cam_set.cams):
            assert cam.agcid == n

    def test_temperature_applied(self, cam_set):
        for cam in cam_set.cams:
            assert cam.getTemperature() == pytest.approx(-30)

    def test_photometry_workers_started(self, cam_set):
        for cam in cam_set.cams:
            assert cam.proc.is_alive(), f"Photometry worker for cam {cam.agcid} is not alive"

    def test_running_cameras_returns_all(self, cam_set):
        running = cam_set.runningCameras()
        assert running == list(range(6))

    def test_close_camera_terminates_workers(self, cam_config):
        c = camera.Camera(cam_config)
        procs = [cam.proc for cam in c.cams]
        c.closeCamera()
        for p in procs:
            p.join(timeout=3)
            assert not p.is_alive(), "Worker process still alive after closeCamera()"

    def test_close_camera_sets_slots_to_none(self, cam_config):
        c = camera.Camera(cam_config)
        c.closeCamera()
        assert all(cam is None for cam in c.cams)

    def test_send_status_keys_calls_inform(self, cam_set, mock_cmd):
        cam_set.sendStatusKeys(mock_cmd)
        assert mock_cmd.inform.call_count >= 6  # at least one per camera

    def test_report_tec_calls_inform(self, cam_set, mock_cmd):
        cam_set.reportTEC(mock_cmd)
        mock_cmd.inform.assert_called()

    def test_simulatedImagePath_loaded_into_cameras(self, tmp_path, cam_config):
        """Cameras initialised with a combined FITS should expose non-zero images."""
        img = np.ones((1033, 1072), dtype=np.uint16) * 999
        fits_path = tmp_path / "combined.fits"
        primary = fits.PrimaryHDU()
        hdulist = fits.HDUList([primary] + [fits.ImageHDU(img, name=f"cam{n + 1}") for n in range(6)])
        hdulist.writeto(str(fits_path))

        cfg = dict(cam_config, simulatedImagePath=str(fits_path))
        c = camera.Camera(cfg)
        try:
            cam = c.cams[0]
            cam.setExpTime(0)
            cam.expose()
            assert cam.data.sum() > 0, "Expected non-zero image from simulatedImagePath"
        finally:
            c.closeCamera()

    @pytest.mark.real_data
    def test_simulatedImagePath_from_run28(self, cam_config):
        """Camera loaded from a real run28 FITS returns the recorded pixel values."""
        run28_fits = Path(__file__).parent.parent / "images" / "run28" / "agcc_143362_01043046.fits"
        if not run28_fits.exists():
            pytest.skip("images/run28/ not available")

        cfg = dict(cam_config, simulatedImagePath=str(run28_fits))
        c = camera.Camera(cfg)
        try:
            cam = c.cams[0]
            cam.setExpTime(0)
            cam.expose()
            # Real images have a bias level well above zero
            assert float(np.median(cam.data)) > 100
        finally:
            c.closeCamera()


# ---------------------------------------------------------------------------
# SetMode thread tests
# ---------------------------------------------------------------------------

class TestSetMode:
    """Tests for the SetMode threading helper."""

    def _mock_cmd(self):
        cmd = MagicMock()
        for m in ("inform", "warn", "fail", "finish", "respond", "debug"):
            setattr(cmd, m, MagicMock())
        return cmd

    def test_setmode_sets_mode_and_finishes(self):
        cmd = self._mock_cmd()
        cam = fake_camera.Camera(0, "SN001")
        cam.open()
        try:
            sm = SetMode([cam], 1, cmd)
            sm.start()
            sm.join(timeout=5)
            assert not sm.is_alive()
            assert cam.getMode() == 1
            cmd.finish.assert_called_once()
        finally:
            cam.close()

    def test_setmode_no_cameras_warns_and_finishes(self):
        cmd = self._mock_cmd()
        sm = SetMode([], 0, cmd)
        sm.start()
        sm.join(timeout=5)

        cmd.warn.assert_called_once()
        cmd.finish.assert_called_once()

    def test_setmode_no_cmd_does_not_raise(self):
        cam = fake_camera.Camera(0, "SN001")
        cam.open()
        try:
            sm = SetMode([cam], 1, None)
            sm.start()
            sm.join(timeout=5)
            assert cam.getMode() == 1
        finally:
            cam.close()

    def test_setmode_multiple_cameras(self):
        cmd = self._mock_cmd()
        cams = [fake_camera.Camera(n, f"SN00{n}") for n in range(3)]
        for cam in cams:
            cam.open()
        try:
            sm = SetMode(cams, 1, cmd)
            sm.start()
            sm.join(timeout=5)
            for cam in cams:
                assert cam.getMode() == 1
            cmd.finish.assert_called_once()
        finally:
            for cam in cams:
                cam.close()


# ---------------------------------------------------------------------------
# Camera controller method tests
# ---------------------------------------------------------------------------

class TestCameraCommands:
    """Tests for Camera controller methods (expose, abort, setframe, etc.)."""

    @pytest.fixture
    def minimal_cParms(self):
        return {"thresh": 5.0, "minarea": 5, "deblend": 0.01, "ellip": 0.5, "nmin": 5, "expTime": 0.1}

    @pytest.fixture
    def minimal_iParms(self):
        base = {"flatVal": 0.006, "magFit": [0.928, 27.389]}
        for n in range(1, 7):
            base[str(n)] = {
                "reg": [0, 80, 0, 80, 80, 160, 0, 80],
                "badCols": [],
                "satVal1": 65535,
                "satVal2": 65535,
            }
        return base

    def test_abort_is_noop_on_ready_cameras(self, cam_set, mock_cmd):
        cam_set.abort(mock_cmd, [0, 1])
        mock_cmd.inform.assert_not_called()

    def test_abort_cancels_busy_camera(self, cam_set, mock_cmd):
        cam_set.cams[0].setExpTime(5000)
        cam_set.cams[0].expose(blocking=False)
        assert cam_set.cams[0].isExposing()
        try:
            cam_set.abort(mock_cmd, [0])
            mock_cmd.inform.assert_called()
        finally:
            cam_set.cams[0].cancelExposure()
            deadline = time.monotonic() + 2.0
            while cam_set.cams[0].isExposing() and time.monotonic() < deadline:
                time.sleep(0.05)

    def test_setframe_updates_expArea(self, cam_set, mock_cmd):
        cam_set.setframe(mock_cmd, [0], bx=0, by=0, cx=10, cy=20, sx=100, sy=80)
        assert cam_set.cams[0].expArea == (10, 20, 110, 100)
        mock_cmd.finish.assert_called_once()

    def test_setframe_busy_camera_fails(self, cam_set, mock_cmd):
        cam_set.cams[0].setExpTime(5000)
        cam_set.cams[0].expose(blocking=False)
        assert cam_set.cams[0].isExposing()
        try:
            cam_set.setframe(mock_cmd, [0], bx=0, by=0, cx=10, cy=20, sx=100, sy=80)
            mock_cmd.fail.assert_called_once()
        finally:
            cam_set.cams[0].cancelExposure()
            deadline = time.monotonic() + 2.0
            while cam_set.cams[0].isExposing() and time.monotonic() < deadline:
                time.sleep(0.05)

    def test_resetframe_restores_default(self, cam_set, mock_cmd):
        cam_set.setframe(mock_cmd, [0], bx=0, by=0, cx=10, cy=20, sx=100, sy=80)
        mock_cmd.reset_mock()
        cam_set.resetframe(mock_cmd, [0])
        assert cam_set.cams[0].expArea == cam_set.cams[0].defaultExpArea
        mock_cmd.finish.assert_called_once()

    def test_setmode_changes_camera_mode(self, cam_set, mock_cmd):
        cam_set.setmode(mock_cmd, 1, [0])
        deadline = time.monotonic() + 2.0
        while not mock_cmd.finish.called and time.monotonic() < deadline:
            time.sleep(0.05)
        assert cam_set.cams[0].getMode() == 1
        mock_cmd.finish.assert_called_once()

    def test_getmode_responds_for_each_camera(self, cam_set, mock_cmd):
        cam_set.getmode(mock_cmd, [0, 1])
        mock_cmd.finish.assert_called_once()
        assert mock_cmd.respond.call_count >= 2

    def test_getmodestring_returns_mode_strings(self, cam_set, mock_cmd):
        cam_set.getmodestring(mock_cmd)
        mock_cmd.finish.assert_called_once()
        assert mock_cmd.respond.call_count >= 2

    def test_setcamtemperature_ready_camera(self, cam_set, mock_cmd):
        cam_set.setcamtemperature(mock_cmd, 0, -20.0)
        assert cam_set.cams[0].getTemperature() == pytest.approx(-20.0)

    def test_setcamtemperature_busy_camera_warns(self, cam_set, mock_cmd):
        cam_set.cams[0].setExpTime(5000)
        cam_set.cams[0].expose(blocking=False)
        assert cam_set.cams[0].isExposing()
        try:
            cam_set.setcamtemperature(mock_cmd, 0, -20.0)
            mock_cmd.warn.assert_called_once()
        finally:
            cam_set.cams[0].cancelExposure()
            deadline = time.monotonic() + 2.0
            while cam_set.cams[0].isExposing() and time.monotonic() < deadline:
                time.sleep(0.05)

    def test_settemperature_all_cameras(self, cam_set, mock_cmd):
        cam_set.settemperature(mock_cmd, -25.0)
        for cam in cam_set.cams:
            assert cam.getTemperature() == pytest.approx(-25.0)
        mock_cmd.finish.assert_called_once()

    def test_settemperature_busy_camera_fails(self, cam_set, mock_cmd):
        cam_set.cams[0].setExpTime(5000)
        cam_set.cams[0].expose(blocking=False)
        assert cam_set.cams[0].isExposing()
        try:
            cam_set.settemperature(mock_cmd, -25.0)
            mock_cmd.fail.assert_called_once()
        finally:
            cam_set.cams[0].cancelExposure()
            deadline = time.monotonic() + 2.0
            while cam_set.cams[0].isExposing() and time.monotonic() < deadline:
                time.sleep(0.05)

    def test_setregions_one_region(self, cam_set, mock_cmd):
        cam_set.setregions(mock_cmd, 0, "100,200,50")
        assert cam_set.cams[0].regions == (("100", "200", "50"), (0, 0, 0))
        mock_cmd.finish.assert_called_once()

    def test_setregions_two_regions(self, cam_set, mock_cmd):
        cam_set.setregions(mock_cmd, 0, "100,200,50,300,400,60")
        assert cam_set.cams[0].regions == (("100", "200", "50"), ("300", "400", "60"))
        mock_cmd.finish.assert_called_once()

    def test_setregions_invalid_fails(self, cam_set, mock_cmd):
        cam_set.setregions(mock_cmd, 0, "100,200")
        mock_cmd.fail.assert_called_once()

    def test_camera_stat_returns_string(self, cam_set):
        stat = cam_set.camera_stat(0)
        assert isinstance(stat, str)

    def test_sendstatuskeys_reports_absent_slot(self, cam_config, mock_cmd):
        c = camera.Camera(cam_config)
        c.cams[2].close()
        c.cams[2] = None
        try:
            c.sendStatusKeys(mock_cmd)
            calls = " ".join(str(a) for a in mock_cmd.inform.call_args_list)
            assert "ABSENT" in calls
        finally:
            c.closeCamera()

    def test_expose_test_type_calls_finish(self, cam_set, mock_cmd, minimal_cParms, minimal_iParms):
        # expType="test" calls expose_test() + wfits() (which is a no-op due to arg order bug)
        cam_set.expose(
            mock_cmd, 1.0, "test", [0],
            combined=False, centroid=False, pfsVisitId=999,
            cParms=minimal_cParms, cMethod="sep", iParms=minimal_iParms,
        )
        mock_cmd.finish.assert_called()

    def test_expose_no_cameras_available(self, cam_set, mock_cmd, minimal_cParms, minimal_iParms):
        cam_set.expose(
            mock_cmd, 1.0, "object", [],
            combined=False, centroid=False, pfsVisitId=999,
            cParms=minimal_cParms, cMethod="sep", iParms=minimal_iParms,
        )
        mock_cmd.warn.assert_called_once()
        mock_cmd.finish.assert_called_once()

    def test_expose_busy_camera_fails(self, cam_set, mock_cmd, minimal_cParms, minimal_iParms):
        cam_set.cams[0].setExpTime(5000)
        cam_set.cams[0].expose(blocking=False)
        assert cam_set.cams[0].isExposing()
        try:
            cam_set.expose(
                mock_cmd, 1.0, "object", [0],
                combined=False, centroid=False, pfsVisitId=999,
                cParms=minimal_cParms, cMethod="sep", iParms=minimal_iParms,
            )
            mock_cmd.fail.assert_called_once()
        finally:
            cam_set.cams[0].cancelExposure()
            deadline = time.monotonic() + 2.0
            while cam_set.cams[0].isExposing() and time.monotonic() < deadline:
                time.sleep(0.05)

