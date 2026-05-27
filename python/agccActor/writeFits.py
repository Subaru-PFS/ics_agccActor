import time
from pathlib import Path

from astropy.io import fits

# TODO: honour $ICS_MHS_DATA_ROOT instead of hardcoding /data/raw.
_DATA_ROOT = Path("/data/raw")


def _outputDir() -> Path:
    """Return (and create) the AGCC output directory for today (UTC)."""
    path = _DATA_ROOT / time.strftime("%Y-%m-%d", time.gmtime()) / "agcc"
    path.mkdir(parents=True, mode=0o755, exist_ok=True)
    return path


def _spotsTableHDU(spots, name: str | None = None) -> fits.BinTableHDU:
    """Build a binary-table HDU from a camera's measured spots."""
    columns = [
        fits.Column(name="moment_00", format="E", array=spots["image_moment_00_pix"]),
        fits.Column(name="centroid_x", format="E", array=spots["centroid_x_pix"]),
        fits.Column(name="centroid_y", format="E", array=spots["centroid_y_pix"]),
        fits.Column(name="moment_20", format="E", array=spots["central_image_moment_20_pix"]),
        fits.Column(name="moment_11", format="E", array=spots["central_image_moment_11_pix"]),
        fits.Column(name="moment_02", format="E", array=spots["central_image_moment_02_pix"]),
        fits.Column(name="peak_x", format="I", array=spots["peak_pixel_x_pix"]),
        fits.Column(name="peak_y", format="I", array=spots["peak_pixel_y_pix"]),
        fits.Column(name="peak_intensity", format="E", array=spots["peak_intensity"]),
        fits.Column(name="background", format="E", array=spots["background"]),
    ]
    tbhdu = fits.BinTableHDU.from_columns(columns)
    if name is not None:
        tbhdu.name = name
    return tbhdu


def _fillImageHeader(hdr: fits.Header, cam, visitId: int, nframe: int) -> None:
    """Populate the standard AGCC image header keywords from ``cam``."""
    hdr.set("DATE", cam.timestamp, "exposure begin date")
    hdr.set("INSTRUME", cam.devname, "this instrument")
    hdr.set("SERIAL", cam.devsn, "serial number")
    hdr.set("EXPTIME", cam.exptime, "exposure time (ms)")
    hdr.set("VBIN", cam.vbin, "vertical binning")
    hdr.set("HBIN", cam.hbin, "horizontal binning")
    hdr.set("CCD-TEMP", cam.getTemperature(), "CCD temperature")
    hdr.set("SHUTTER", "CLOSE" if cam.dark != 0 else "OPEN", "shutter status")
    hdr.set("CCDAREA", "[%d:%d,%d:%d]" % cam.expArea, "image area")
    hdr.set("FRAMEID", nframe, "unique key for exposure")
    hdr.set("VISITID", visitId, "visit id")


def wfits(cmd, visitId: int = 0, cam=None, nframe: int = 0) -> None:
    """Write a single-camera image (and optional centroids) to a FITS file.

    Output is written under ``/data/raw/YYYY-MM-DD/agcc/`` with name
    ``agcc_{visitId:06d}_{nframe:08d}_cam{N}.fits``.

    Parameters
    ----------
    cmd : object or None
        A tron command object used for status replies. Ignored if ``None``.
    visitId : int
        The PFS visit identifier.
    cam : object
        The camera object holding the image data and metadata.
    nframe : int
        The AGC exposure identifier (used as FRAMEID in the header).
    """
    if cam is None:
        return

    if cam.data.size == 0:
        if cmd:
            cmd.warn('text="No image available for AGC[%d]"' % (cam.agcid + 1))
        return

    pfsFilename = _outputDir() / f"agcc_{visitId:06d}_{nframe:08d}_cam{cam.agcid + 1}.fits"

    hdu = fits.PrimaryHDU(cam.data)
    _fillImageHeader(hdu.header, cam, visitId, nframe)

    if cam.spots is not None:
        hdulist = fits.HDUList([hdu, _spotsTableHDU(cam.spots)])
    else:
        hdulist = fits.HDUList([hdu])
    hdulist.writeto(str(pfsFilename), checksum=True, overwrite=True)

    cam.filename = str(pfsFilename)
    if cmd:
        cmd.inform('agc%d_fitsfile="%s",%.1f' % (cam.agcid + 1, pfsFilename, cam.tstart))
        cmd.inform(f'text="AG image written to {pfsFilename}"')


def wfits_combined(cmd, visitId: int = 0, cams=None, nframe: int = 0, seq_id: int = -1) -> None:
    """Write images from all cameras into a single multi-extension FITS file.

    The output FITS contains one image HDU per AG camera (``cam1`` ...
    ``cam6``) plus a binary table per camera when centroids are present.
    Output path is ``/data/raw/YYYY-MM-DD/agcc/agcc_{visitId:06d}_{nframe:08d}.fits``.

    Parameters
    ----------
    cmd : object or None
        A tron command object used for status replies. Ignored if ``None``.
    visitId : int
        The PFS visit identifier.
    cams : list
        List of camera objects participating in this exposure.
    nframe : int
        The AGC exposure identifier (FRAMEID).
    seq_id : int, optional
        Deprecated; retained for backward compatibility and ignored.
    """
    del seq_id  # legacy parameter from the removed `sequence` command path.

    if cams is None:
        cams = []

    pfsFilename = _outputDir() / f"agcc_{visitId:06d}_{nframe:08d}.fits"

    hdulist = fits.HDUList([fits.PrimaryHDU()])
    spotsHDUs: list[fits.BinTableHDU] = []
    for n in range(6):
        extname = f"cam{n + 1}"

        cam = next((c for c in cams if c.agcid == n), None)
        if cam is None:
            hdulist.append(fits.ImageHDU(name=extname))
            continue

        hdu = fits.ImageHDU(cam.data, name=extname)
        _fillImageHeader(hdu.header, cam, visitId, nframe)
        hdulist.insert(n + 1, hdu)

        if cam.spots is not None:
            spotsHDUs.append(_spotsTableHDU(cam.spots, name=f"table{n + 1}"))

    for tbhdu in spotsHDUs:
        hdulist.append(tbhdu)

    hdulist.writeto(str(pfsFilename), checksum=True, overwrite=True)

    if cmd:
        tstart = cams[0].tstart if cams else time.time()
        cmd.inform('agc_fitsfile="%s",%.1f' % (pfsFilename, tstart))
        cmd.inform(f'text="AG images written to {pfsFilename}"')
