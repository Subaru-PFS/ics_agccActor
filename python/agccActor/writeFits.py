"""FITS file writing helpers for AGCC single-camera and combined exposures."""

from __future__ import annotations

import os
import time
from typing import Any

import astropy.io.fits as pyfits


def wfits(cmd: Any, visitId: int, cam: Any, nframe: int) -> None:
    """Write a single-camera image to a per-camera FITS file.

    Parameters
    ----------
    cmd : Any
        Command object for status reporting.
    visitId : int
        PFS visit identifier.
    cam : Any
        Camera object whose ``data`` and header attributes are used.
    nframe : int
        Unique AG exposure identifier used in the output filename.
    """

    path = os.path.join("/data/raw", time.strftime("%Y-%m-%d", time.gmtime()), "agcc")
    path = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isdir(path):
        try:
            os.makedirs(path, 0o755)
        except Exception as e:
            raise RuntimeError(f"failed to makedirs({path}): {e}")

    pfsFilename = os.path.join(path, f"agcc_{visitId:06d}_{nframe:08d}_cam{cam.agcid + 1}.fits")

    if cam.data.size == 0:
        cmd.warn('text="No image available for AGC[%d]"' % (cam.agcid + 1))
        return
    hdu = pyfits.PrimaryHDU(cam.data)
    hdr = hdu.header
    hdr.set("DATE", cam.timestamp, "exposure begin date")
    hdr.set("INSTRUME", cam.devname, "this instrument")
    hdr.set("SERIAL", cam.devsn, "serial number")
    hdr.set("EXPTIME", cam.exptime, "exposure time (ms)")
    hdr.set("VBIN", cam.vbin, "vertical binning")
    hdr.set("HBIN", cam.hbin, "horizontal binning")
    hdr.set("CCD-TEMP", cam.getTemperature(), "CCD temperature")
    if cam.dark != 0:
        hdr.set("SHUTTER", "CLOSE", "shutter status")
    else:
        hdr.set("SHUTTER", "OPEN", "shutter status")
    hdr.set("CCDAREA", "[%d:%d,%d:%d]" % cam.expArea, "image area")
    hdr.set("FRAMEID", nframe, "unique key for exposure")
    hdr.set("VISITID", visitId, "visit id")

    if cam.spots is not None:
        c1 = pyfits.Column(name="moment_00", format="E", array=cam.spots["image_moment_00_pix"])
        c2 = pyfits.Column(name="centroid_x", format="E", array=cam.spots["centroid_x_pix"])
        c3 = pyfits.Column(name="centroid_y", format="E", array=cam.spots["centroid_y_pix"])
        c4 = pyfits.Column(name="moment_20", format="E", array=cam.spots["central_image_moment_20_pix"])
        c5 = pyfits.Column(name="moment_11", format="E", array=cam.spots["central_image_moment_11_pix"])
        c6 = pyfits.Column(name="moment_02", format="E", array=cam.spots["central_image_moment_02_pix"])
        c7 = pyfits.Column(name="peak_x", format="I", array=cam.spots["peak_pixel_x_pix"])
        c8 = pyfits.Column(name="peak_y", format="I", array=cam.spots["peak_pixel_y_pix"])
        c9 = pyfits.Column(name="peak_intensity", format="E", array=cam.spots["peak_intensity"])
        c10 = pyfits.Column(name="background", format="E", array=cam.spots["background"])

        tbhdu = pyfits.BinTableHDU.from_columns([c1, c2, c3, c4, c5, c6, c7, c8, c9, c10])
        hdulist = pyfits.HDUList([hdu, tbhdu])
        hdulist.writeto(pfsFilename, checksum=True, overwrite=True)
    else:
        hdu.writeto(pfsFilename, overwrite=True, checksum=True)

    cam.filename = pfsFilename
    if cmd:
        cmd.inform('agc%d_fitsfile="%s",%.1f' % (cam.agcid + 1, pfsFilename, cam.tstart))


def wfits_combined(cmd: Any, visitId: int, cams: list[Any], nframe: int, seq_id: int = -1) -> None:
    """Write all camera images into a single multi-extension FITS file.

    Each active camera occupies one image extension (``cam1``–``cam6``);
    absent cameras produce an empty ``ImageHDU``.  When centroiding has
    run, a companion binary-table extension (``table{N}``) is appended.

    Parameters
    ----------
    cmd : Any
        Command object for status reporting.
    visitId : int
        PFS visit identifier.
    cams : list[Any]
        Camera objects that have completed an exposure.
    nframe : int
        Unique AG exposure identifier used in the output filename.
    seq_id : int, optional
        Sequence identifier; ``-1`` if not part of a sequence.
    """

    path = os.path.join("/data/raw", time.strftime("%Y-%m-%d", time.gmtime()), "agcc")
    path = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isdir(path):
        os.makedirs(path, 0o755)

    pfsFilename = os.path.join(path, f"agcc_{visitId:06d}_{nframe:08d}.fits")

    hdulist = pyfits.HDUList([pyfits.PrimaryHDU()])
    for n in range(6):
        extname = "cam%d" % (n + 1)

        for cam in cams:
            if cam.agcid == n:
                break
        else:
            hdulist.append(pyfits.ImageHDU(name=extname))
            continue

        hdu = pyfits.ImageHDU(cam.data, name=extname)
        hdr = hdu.header
        hdr.set("DATE", cam.timestamp, "exposure begin date")
        hdr.set("INSTRUME", cam.devname, "this instrument")
        hdr.set("SERIAL", cam.devsn, "serial number")
        hdr.set("EXPTIME", cam.exptime, "exposure time (ms)")
        hdr.set("VBIN", cam.vbin, "vertical binning")
        hdr.set("HBIN", cam.hbin, "horizontal binning")
        hdr.set("CCD-TEMP", cam.getTemperature(), "CCD temperature")
        if cam.dark != 0:
            hdr.set("SHUTTER", "CLOSE", "shutter status")
        else:
            hdr.set("SHUTTER", "OPEN", "shutter status")
        hdr.set("CCDAREA", "[%d:%d,%d:%d]" % cam.expArea, "image area")
        hdr.set("FRAMEID", nframe, "unique key for exposure")
        hdr.set("VISITID", visitId, "visit id")
        if seq_id >= 0:
            hdr.set("REGION1", "[%d,%d,%d]" % cam.regions[0], "region 1")
            hdr.set("REGION2", "[%d,%d,%d]" % cam.regions[1], "region 2")
        hdulist.insert(n + 1, hdu)

        if cam.spots is not None:
            c1 = pyfits.Column(name="moment_00", format="E", array=cam.spots["image_moment_00_pix"])
            c2 = pyfits.Column(name="centroid_x", format="E", array=cam.spots["centroid_x_pix"])
            c3 = pyfits.Column(name="centroid_y", format="E", array=cam.spots["centroid_y_pix"])
            c4 = pyfits.Column(name="moment_20", format="E", array=cam.spots["central_image_moment_20_pix"])
            c5 = pyfits.Column(name="moment_11", format="E", array=cam.spots["central_image_moment_11_pix"])
            c6 = pyfits.Column(name="moment_02", format="E", array=cam.spots["central_image_moment_02_pix"])
            c7 = pyfits.Column(name="peak_x", format="I", array=cam.spots["peak_pixel_x_pix"])
            c8 = pyfits.Column(name="peak_y", format="I", array=cam.spots["peak_pixel_y_pix"])
            c9 = pyfits.Column(name="peak_intensity", format="E", array=cam.spots["peak_intensity"])
            c10 = pyfits.Column(name="background", format="E", array=cam.spots["background"])

            tbhdu = pyfits.BinTableHDU.from_columns([c1, c2, c3, c4, c5, c6, c7, c8, c9, c10])
            tbhdu.name = "table%d" % (n + 1)
            hdulist.append(tbhdu)

    hdulist.writeto(pfsFilename, checksum=True, overwrite=True)

    if cmd:
        if seq_id >= 0:
            cmd.inform('agc_seq%d="%s"' % (seq_id + 1, pfsFilename))
        else:
            cmd.inform('agc_fitsfile="%s",%.1f' % (pfsFilename, cams[0].tstart))
