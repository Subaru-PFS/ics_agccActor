import os
import time
from datetime import datetime

from astropy.io import fits


def wfits(cmd, visitId, cam, nframe):
    """Write the image to a FITS file"""

    path = os.path.join("/data/raw", time.strftime("%Y-%m-%d", time.gmtime()), "agcc")
    path = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isdir(path):
        try:
            os.makedirs(path, 0o755)
        except Exception as e:
            raise RuntimeError(f"failed to makedirs({path}): {e}")

    tstart = datetime.fromtimestamp(cam.tstart)
    mtimestamp = tstart.strftime("%Y%m%d_%H%M%S%f")[:-5]

    pfsFilename = os.path.join(path, f"agcc_{visitId:06d}_{nframe:08d}_cam{cam.agcid + 1}.fits")
    filename = os.path.join(path, f"agcc_c{cam.agcid + 1}_{mtimestamp}.fits")

    if cam.data.size == 0:
        cmd.warn(f'text="No image available for AGC[{cam.agcid + 1}]"')
        return

    hdu = fits.PrimaryHDU(cam.data)
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
        c1 = fits.Column(name="moment_00", format="E", array=cam.spots["image_moment_00_pix"])
        c2 = fits.Column(name="centroid_x", format="E", array=cam.spots["centroid_x_pix"])
        c3 = fits.Column(name="centroid_y", format="E", array=cam.spots["centroid_y_pix"])
        c4 = fits.Column(name="moment_20", format="E", array=cam.spots["central_image_moment_20_pix"])
        c5 = fits.Column(name="moment_11", format="E", array=cam.spots["central_image_moment_11_pix"])
        c6 = fits.Column(name="moment_02", format="E", array=cam.spots["central_image_moment_02_pix"])
        c7 = fits.Column(name="peak_x", format="I", array=cam.spots["peak_pixel_x_pix"])
        c8 = fits.Column(name="peak_y", format="I", array=cam.spots["peak_pixel_y_pix"])
        c9 = fits.Column(name="peak_intensity", format="E", array=cam.spots["peak_intensity"])
        c10 = fits.Column(name="background", format="E", array=cam.spots["background"])

        tbhdu = fits.BinTableHDU.from_columns([c1, c2, c3, c4, c5, c6, c7, c8, c9, c10])
        hdulist = fits.HDUList([hdu, tbhdu])
        hdulist.writeto(filename, checksum=True, overwrite=True)
    else:
        hdu.writeto(pfsFilename, overwrite=True, checksum=True)

    cam.filename = pfsFilename
    if cmd:
        cmd.inform(f'agc{cam.agcid + 1}_fitsfile="{pfsFilename}",{cam.tstart:.1f}')
        cmd.inform(f'text="AG images are NOT written into {pfsFilename}"')


def wfits_combined(cmd, visitId, cams, nframe, seq_id=-1):
    """Write the images to a FITS file"""

    path = os.path.join("/data/raw", time.strftime("%Y-%m-%d", time.gmtime()), "agcc")
    path = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isdir(path):
        os.makedirs(path, 0o755)

    if len(cams) > 0:
        now = datetime.fromtimestamp(cams[0].tstart)
    else:
        now = datetime.now()
    mtimestamp = now.strftime("%Y%m%d_%H%M%S%f")[:-5]

    if seq_id >= 0:
        filename = os.path.join(path, f"agcc_s{seq_id + 1}_{mtimestamp}.fits")
    else:
        filename = os.path.join(path, f"agcc_{mtimestamp}.fits")

    pfsFilename = os.path.join(path, f"agcc_{visitId:06d}_{nframe:08d}.fits")

    hdulist = fits.HDUList([fits.PrimaryHDU()])
    for n in range(6):
        extname = f"cam{n + 1}"

        for cam in cams:
            if cam.agcid == n:
                break
        else:
            hdulist.append(fits.ImageHDU(name=extname))
            continue

        hdu = fits.ImageHDU(cam.data, name=extname)
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
            c1 = fits.Column(name="moment_00", format="E", array=cam.spots["image_moment_00_pix"])
            c2 = fits.Column(name="centroid_x", format="E", array=cam.spots["centroid_x_pix"])
            c3 = fits.Column(name="centroid_y", format="E", array=cam.spots["centroid_y_pix"])
            c4 = fits.Column(name="moment_20", format="E", array=cam.spots["central_image_moment_20_pix"])
            c5 = fits.Column(name="moment_11", format="E", array=cam.spots["central_image_moment_11_pix"])
            c6 = fits.Column(name="moment_02", format="E", array=cam.spots["central_image_moment_02_pix"])
            c7 = fits.Column(name="peak_x", format="I", array=cam.spots["peak_pixel_x_pix"])
            c8 = fits.Column(name="peak_y", format="I", array=cam.spots["peak_pixel_y_pix"])
            c9 = fits.Column(name="peak_intensity", format="E", array=cam.spots["peak_intensity"])
            c10 = fits.Column(name="background", format="E", array=cam.spots["background"])

            tbhdu = fits.BinTableHDU.from_columns([c1, c2, c3, c4, c5, c6, c7, c8, c9, c10])
            tbhdu.name = f"table{n + 1}"
            hdulist.append(tbhdu)

    hdulist.writeto(pfsFilename, checksum=True, overwrite=True)

    if cmd:
        if seq_id >= 0:
            cmd.inform(f'agc_seq{seq_id + 1}="{filename}"')
        else:
            cmd.inform(f'agc_fitsfile="{pfsFilename}",{cams[0].tstart:.1f}')
        cmd.inform(f'text="AG images are NOT written into {pfsFilename}"')
