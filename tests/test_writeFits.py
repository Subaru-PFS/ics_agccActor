"""Tests for agccActor.writeFits — FITS output for single and combined exposures."""

import time
import types
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from agccActor import writeFits
from agccActor.photometry import spotDtype


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_fake_cam(agcid: int = 0, with_spots: bool = False, empty: bool = False):
    """Return a minimal camera-like namespace sufficient for writeFits."""
    cam = types.SimpleNamespace()
    cam.agcid = agcid
    cam.data = np.zeros((0,), dtype=np.uint16) if empty else np.ones((100, 100), dtype=np.uint16) * 1500
    cam.timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    cam.devname = "MicroLine ML4720"
    cam.devsn = f"SN{agcid + 1:03d}"
    cam.exptime = 5000.0
    cam.vbin = 1
    cam.hbin = 1
    cam.getTemperature = lambda: -29.8
    cam.dark = 0
    cam.expArea = (0, 0, 100, 100)
    cam.tstart = time.time()
    cam.filename = ""
    cam.spots = None
    if with_spots:
        spots = np.zeros(3, dtype=spotDtype)
        spots["centroid_x_pix"] = [10.0, 20.0, 30.0]
        spots["centroid_y_pix"] = [5.0, 15.0, 25.0]
        spots["image_moment_00_pix"] = [1000.0, 2000.0, 1500.0]
        spots["peak_intensity"] = [500.0, 1000.0, 750.0]
        spots["background"] = [100.0, 100.0, 100.0]
        cam.spots = spots
    return cam


@pytest.fixture(autouse=True)
def redirect_data_root(monkeypatch, tmp_path):
    """Redirect writeFits._DATA_ROOT to a temp directory for every test."""
    monkeypatch.setattr(writeFits, "_DATA_ROOT", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# wfits — single-camera output
# ---------------------------------------------------------------------------

class TestWfits:
    def test_creates_file(self, tmp_path):
        cam = _make_fake_cam(agcid=0)
        writeFits.wfits(None, visitId=12345, cam=cam, nframe=42)

        today = time.strftime("%Y-%m-%d", time.gmtime())
        expected = tmp_path / today / "agcc" / "agcc_012345_00000042_cam1.fits"
        assert expected.exists(), f"Expected FITS file not found: {expected}"

    def test_filename_convention(self, tmp_path):
        cam = _make_fake_cam(agcid=2)
        writeFits.wfits(None, visitId=999, cam=cam, nframe=7)

        today = time.strftime("%Y-%m-%d", time.gmtime())
        expected = tmp_path / today / "agcc" / "agcc_000999_00000007_cam3.fits"
        assert expected.exists()

    def test_required_header_keywords(self, tmp_path):
        cam = _make_fake_cam(agcid=0)
        writeFits.wfits(None, visitId=1, cam=cam, nframe=1)

        today = time.strftime("%Y-%m-%d", time.gmtime())
        path = tmp_path / today / "agcc" / "agcc_000001_00000001_cam1.fits"
        with fits.open(path) as hdul:
            hdr = hdul[0].header
        assert "DATE" in hdr
        assert "INSTRUME" in hdr
        assert "SERIAL" in hdr
        assert hdr["EXPTIME"] == pytest.approx(5000.0)
        assert hdr["VBIN"] == 1
        assert hdr["HBIN"] == 1
        assert hdr["FRAMEID"] == 1
        assert hdr["VISITID"] == 1
        assert "CCDAREA" in hdr
        assert hdr["SHUTTER"] == "OPEN"

    def test_dark_sets_shutter_close(self, tmp_path):
        cam = _make_fake_cam(agcid=0)
        cam.dark = 1
        writeFits.wfits(None, visitId=1, cam=cam, nframe=1)

        today = time.strftime("%Y-%m-%d", time.gmtime())
        path = tmp_path / today / "agcc" / "agcc_000001_00000001_cam1.fits"
        with fits.open(path) as hdul:
            assert hdul[0].header["SHUTTER"] == "CLOSE"

    def test_no_spots_no_table_extension(self, tmp_path):
        cam = _make_fake_cam(agcid=0, with_spots=False)
        writeFits.wfits(None, visitId=1, cam=cam, nframe=1)

        today = time.strftime("%Y-%m-%d", time.gmtime())
        path = tmp_path / today / "agcc" / "agcc_000001_00000001_cam1.fits"
        with fits.open(path) as hdul:
            assert len(hdul) == 1, "Expected only PrimaryHDU when no spots"

    def test_with_spots_appends_bintable(self, tmp_path):
        cam = _make_fake_cam(agcid=0, with_spots=True)
        writeFits.wfits(None, visitId=1, cam=cam, nframe=1)

        today = time.strftime("%Y-%m-%d", time.gmtime())
        path = tmp_path / today / "agcc" / "agcc_000001_00000001_cam1.fits"
        with fits.open(path) as hdul:
            assert len(hdul) == 2, "Expected PrimaryHDU + BinTableHDU"
            tbl = hdul[1]
            assert isinstance(tbl, fits.BinTableHDU)
            assert len(tbl.data) == 3
            assert "centroid_x" in tbl.columns.names
            assert "centroid_y" in tbl.columns.names
            assert "moment_00" in tbl.columns.names

    def test_empty_image_skips_write(self, tmp_path, mock_cmd):
        cam = _make_fake_cam(agcid=0, empty=True)
        writeFits.wfits(mock_cmd, visitId=1, cam=cam, nframe=1)

        mock_cmd.warn.assert_called_once()
        today = time.strftime("%Y-%m-%d", time.gmtime())
        outdir = tmp_path / today / "agcc"
        fits_files = list(outdir.glob("*.fits")) if outdir.exists() else []
        assert len(fits_files) == 0

    def test_none_cam_is_noop(self, tmp_path):
        writeFits.wfits(None, visitId=1, cam=None, nframe=1)  # must not raise

    def test_cmd_inform_called_on_success(self, mock_cmd, tmp_path):
        cam = _make_fake_cam(agcid=0)
        writeFits.wfits(mock_cmd, visitId=1, cam=cam, nframe=1)
        mock_cmd.inform.assert_called()


# ---------------------------------------------------------------------------
# wfits_combined — multi-extension combined output
# ---------------------------------------------------------------------------

class TestWfitsCombined:
    def _make_six_cams(self, with_spots: bool = False):
        return [_make_fake_cam(agcid=n, with_spots=with_spots) for n in range(6)]

    def test_creates_file(self, tmp_path):
        cams = self._make_six_cams()
        writeFits.wfits_combined(None, visitId=12345, cams=cams, nframe=99)

        today = time.strftime("%Y-%m-%d", time.gmtime())
        expected = tmp_path / today / "agcc" / "agcc_012345_00000099.fits"
        assert expected.exists()

    def test_has_six_image_extensions(self, tmp_path):
        cams = self._make_six_cams()
        writeFits.wfits_combined(None, visitId=1, cams=cams, nframe=1)

        today = time.strftime("%Y-%m-%d", time.gmtime())
        path = tmp_path / today / "agcc" / "agcc_000001_00000001.fits"
        with fits.open(path) as hdul:
            # PrimaryHDU + 6 image extensions
            image_hdus = [h for h in hdul if isinstance(h, fits.ImageHDU)]
            assert len(image_hdus) == 6

    def test_extension_names_match_cameras(self, tmp_path):
        cams = self._make_six_cams()
        writeFits.wfits_combined(None, visitId=1, cams=cams, nframe=1)

        today = time.strftime("%Y-%m-%d", time.gmtime())
        path = tmp_path / today / "agcc" / "agcc_000001_00000001.fits"
        with fits.open(path) as hdul:
            names = [h.name.upper() for h in hdul if isinstance(h, fits.ImageHDU)]
            assert names == ["CAM1", "CAM2", "CAM3", "CAM4", "CAM5", "CAM6"]

    def test_with_spots_appends_tables(self, tmp_path):
        cams = self._make_six_cams(with_spots=True)
        writeFits.wfits_combined(None, visitId=1, cams=cams, nframe=1)

        today = time.strftime("%Y-%m-%d", time.gmtime())
        path = tmp_path / today / "agcc" / "agcc_000001_00000001.fits"
        with fits.open(path) as hdul:
            tables = [h for h in hdul if isinstance(h, fits.BinTableHDU)]
            assert len(tables) == 6, "Expected one BinTableHDU per camera"

    def test_partial_cameras(self, tmp_path):
        """Only cameras 0 and 2 present — the others get empty ImageHDU slots."""
        cams = [_make_fake_cam(agcid=0), _make_fake_cam(agcid=2)]
        writeFits.wfits_combined(None, visitId=1, cams=cams, nframe=1)

        today = time.strftime("%Y-%m-%d", time.gmtime())
        path = tmp_path / today / "agcc" / "agcc_000001_00000001.fits"
        with fits.open(path) as hdul:
            image_hdus = [h for h in hdul if isinstance(h, fits.ImageHDU)]
            assert len(image_hdus) == 6

    def test_empty_cams_list(self, tmp_path):
        writeFits.wfits_combined(None, visitId=1, cams=[], nframe=1)

        today = time.strftime("%Y-%m-%d", time.gmtime())
        path = tmp_path / today / "agcc" / "agcc_000001_00000001.fits"
        assert path.exists()

    def test_each_extension_has_image_header(self, tmp_path):
        cams = self._make_six_cams()
        writeFits.wfits_combined(None, visitId=77, cams=cams, nframe=5)

        today = time.strftime("%Y-%m-%d", time.gmtime())
        path = tmp_path / today / "agcc" / "agcc_000077_00000005.fits"
        with fits.open(path) as hdul:
            for hdu in hdul:
                if isinstance(hdu, fits.ImageHDU) and hdu.data is not None and hdu.data.size > 0:
                    assert "EXPTIME" in hdu.header
                    assert "VISITID" in hdu.header
                    assert hdu.header["VISITID"] == 77
