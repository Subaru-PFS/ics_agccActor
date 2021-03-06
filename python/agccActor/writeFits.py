import astropy.io.fits as pyfits
import os
from datetime import datetime

def wfits(cmd, cam, nframe):
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
    hdr.set('FRAMEID', nframe, 'unique key for exposure')

    if cam.spots is not None:
        c1 = pyfits.Column(name='moment_00', format='E', array=cam.spots['m00'])
        c2 = pyfits.Column(name='centroid_x', format='E', array=cam.spots['m10'])
        c3 = pyfits.Column(name='centroid_y', format='E', array=cam.spots['m01'])
        c4 = pyfits.Column(name='moment_20', format='E', array=cam.spots['m20'])
        c5 = pyfits.Column(name='moment_11', format='E', array=cam.spots['m11'])
        c6 = pyfits.Column(name='moment_02', format='E', array=cam.spots['m02'])
        c7 = pyfits.Column(name='peak_x', format='I', array=cam.spots['xpeak'])
        c8 = pyfits.Column(name='peak_y', format='I', array=cam.spots['ypeak'])
        c9 = pyfits.Column(name='peak_intensity', format='E', array=cam.spots['peak'])
        c10 = pyfits.Column(name='background', format='E', array=cam.spots['bg'])

        tbhdu = pyfits.BinTableHDU.from_columns([c1, c2, c3, c4, c5, c6, c7, c8, c9, c10])
        hdulist = pyfits.HDUList([hdu, tbhdu])
        hdulist.writeto(filename, checksum=True, clobber=True)
    else:
        hdu.writeto(filename, clobber=True, checksum=True)

    cam.filename = filename
    if cmd:
        cmd.inform('agc%d_fitsfile="%s",%.1f' % (cam.agcid + 1, filename, cam.tstart))

def wfits_combined(cmd, cams, nframe, seq_id=-1):
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
    if seq_id >= 0:
        filename = os.path.join(path, 'agcc_s%d_%s.fits' % (seq_id + 1, mtimestamp))
    else:
        filename = os.path.join(path, 'agcc_%s.fits' % mtimestamp)

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
        hdr.set('FRAMEID', nframe, 'unique key for exposure')
        if seq_id >= 0:
            hdr.set('REGION1', '[%d,%d,%d]' % cam.regions[0], 'region 1')
            hdr.set('REGION2', '[%d,%d,%d]' % cam.regions[1], 'region 2')
        hdulist.insert(n+1, hdu)

        if cam.spots is not None:
            c1 = pyfits.Column(name='moment_00', format='E', array=cam.spots['m00'])
            c2 = pyfits.Column(name='centroid_x', format='E', array=cam.spots['m10'])
            c3 = pyfits.Column(name='centroid_y', format='E', array=cam.spots['m01'])
            c4 = pyfits.Column(name='moment_20', format='E', array=cam.spots['m20'])
            c5 = pyfits.Column(name='moment_11', format='E', array=cam.spots['m11'])
            c6 = pyfits.Column(name='moment_02', format='E', array=cam.spots['m02'])
            c7 = pyfits.Column(name='peak_x', format='I', array=cam.spots['xpeak'])
            c8 = pyfits.Column(name='peak_y', format='I', array=cam.spots['ypeak'])
            c9 = pyfits.Column(name='peak_intensity', format='E', array=cam.spots['peak'])
            c10 = pyfits.Column(name='background', format='E', array=cam.spots['bg'])

            tbhdu = pyfits.BinTableHDU.from_columns([c1, c2, c3, c4, c5, c6, c7, c8, c9, c10])
            tbhdu.name = "table%d" % (n + 1)
            hdulist.append(tbhdu)

    hdulist.writeto(filename, checksum=True, clobber=True)
    if cmd:
        if seq_id >= 0:
            cmd.inform('agc_seq%d="%s"' % (seq_id + 1, filename))
        else:
            cmd.inform('agc_fitsfile="%s",%.1f' % (filename, cams[0].tstart))
