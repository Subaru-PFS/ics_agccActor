import astropy.io.fits as pyfits
import os
from datetime import datetime

def wfits(cmd, cam):
    """Write the image to a FITS file"""

    path = os.path.join("$ICS_MHS_DATA_ROOT", 'agcc')
    path = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isdir(path):
        os.makedirs(path, 0o755)

    tstart = datetime.fromtimestamp(cam.tstart)
    mtimestamp = tstart.strftime("%Y%m%d_%H%M%S%f")[:-5]
    filename = os.path.join(path, 'agcc_c%d_%s.fits' % \
           (cam.agcid + 1, mtimestamp))

    if(cam.data.size == 0):
        cmd.warn('text="No image available for AGC[%d]"' % (cam.agcid + 1))
        return
    hdu = pyfits.PrimaryHDU(cam.data)
    hdr = hdu.header
    hdr.set('DATE', cam.timestamp, 'exposure begin date')
    hdr.set('INSTRUME', cam.devname, 'this instrument')
    hdr.set('SERIAL', cam.devsn, 'serial number')
    hdr.set('EXPTIME', cam.exptime, 'exposure time (ms)')
    hdr.set('VBIN', cam.vbin, 'vertical binning')
    hdr.set('HBIN', cam.hbin, 'horizontal binning')
    hdr.set('CCD-TEMP', cam.getTemperature(), 'CCD temperature')
    if(cam.dark != 0):
        hdr.set('SHUTTER', 'CLOSE', 'shutter status')
    else:
        hdr.set('SHUTTER', 'OPEN', 'shutter status')
    hdr.set('CCDAREA', '[%d:%d,%d:%d]' % cam.expArea, 'image area')
    hdu.writeto(filename, clobber=True, checksum=True)

    cam.filename = filename
    if cmd:
        cmd.inform('fits_cam%d="%s"' % (cam.agcid + 1, filename))

def wfits_combined(cmd, cams, seq_id=-1):
    """Write the images to a FITS file"""

    path = os.path.join("$ICS_MHS_DATA_ROOT", 'agcc')
    path = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isdir(path):
        os.makedirs(path, 0o755)
    if len(cams) > 0:
        now = datetime.fromtimestamp(cams[0].tstart)
    else:
        now = datetime.now()
    mtimestamp = now.strftime("%Y%m%d_%H%M%S%f")[:-5]
    filename = os.path.join(path, 'agcc_s%d_%s.fits' % (seq_id + 1, mtimestamp))

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
        hdr.set('DATE', cam.timestamp, 'exposure begin date')
        hdr.set('INSTRUME', cam.devname, 'this instrument')
        hdr.set('SERIAL', cam.devsn, 'serial number')
        hdr.set('EXPTIME', cam.exptime, 'exposure time (ms)')
        hdr.set('VBIN', cam.vbin, 'vertical binning')
        hdr.set('HBIN', cam.hbin, 'horizontal binning')
        hdr.set('CCD-TEMP', cam.getTemperature(), 'CCD temperature')
        if(cam.dark != 0):
            hdr.set('SHUTTER', 'CLOSE', 'shutter status')
        else:
            hdr.set('SHUTTER', 'OPEN', 'shutter status')
        hdr.set('CCDAREA', '[%d:%d,%d:%d]' % cam.expArea, 'image area')
        hdr.set('REGION1', '[%d,%d,%d]' % cam.regions[0], 'region 1')
        hdr.set('REGION2', '[%d,%d,%d]' % cam.regions[1], 'region 2')
        hdulist.append(hdu)

    hdulist.writeto(filename, checksum=True, clobber=True)
    if cmd:
        cmd.inform('fits_seq%d="%s"' % (seq_id + 1, filename))
