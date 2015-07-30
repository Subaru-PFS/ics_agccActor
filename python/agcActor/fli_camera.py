"""FLI USB camera module"""

import numpy
import fli_device as fli
import astropy.io.fits as pyfits
from time import localtime, strftime
from twisted.internet import reactor
import os

def numberOfCamera():
    """Get the number of available cameras"""
    return fli.numberOfCamera()

CLOSED, READY, EXPOSING = range(3)
Status = {CLOSED:"CLOSED", READY:"READY", EXPOSING:"EXPOSING"}
POLL_TIME = 0.1
CCD_TEMP = -30

class Camera:
    """FLI USB camera"""

    def __init__(self, id=0):
        """(id) : index of the camera device"""
        self.id = id
        self.exptime = 0
        self.timestamp = ""
        self.devname = ""
        self.devsn = ""
        self.defaultExpArea = (0, 0, 0, 0)
        self.expArea = (0, 0, 0, 0)
        self.data = numpy.array([], dtype = numpy.uint16)
        self.hbin = 1
        self.vbin = 1
        self.temp = CCD_TEMP
        self.dark = 0
        self.status = CLOSED
        self.exposureID = 0
        self.filename = ""
        self.agcid = 0
        self.abort = 0

    def getStatusStr(self):
        return(Status[self.status])

    def isReady(self):
        return self.status == READY

    def open(self):
        """Open camera device"""
        fli.open(self.id)
        self.devname = fli.getModel(self.id)
        self.devsn = fli.getSerial(self.id)
        # set default parameters
        fli.setTemperature(self.id, self.temp)
        fli.setHBin(self.id, 1)
        fli.setVBin(self.id, 1)
        fli.setTDI(self.id, 0)
        fli.setExposure(self.id, 0)
        self.defaultExpArea = fli.getArrayArea(self.id)
        self.expArea = self.defaultExpArea
        fli.setImageArea(self.id, *self.expArea)
        self.status = READY

    def close(self):
        """Close camera device"""
        fli.close(self.id)
        self.status = CLOSED

    def setExpTime(self, exptime):
        """Set exposure time in ms"""
        fli.setExposure(self.id, exptime)
        self.exptime = exptime

    def setHBin(self, hbin):
        """Set horizontal binning"""
        fli.setHBin(self.id, hbin)
        self.hbin = hbin

    def setVBin(self, vbin):
        """Set vertical binning"""
        fli.setVBin(self.id, vbin)
        self.vbin = vbin

    def setFrame(self, x1, y1, width, height):
        """Set image area"""
        fli.setImageArea(self.id, x1, y1, x1 + width, y1 + height)
        self.expArea = (x1, y1, x1 + width, y1 + height)

    def resetFrame(self):
        """Reset image area"""
        self.expArea = self.defaultExpArea
        fli.setImageArea(self.id, *self.expArea)
        if self.hbin != 1:
            self.setHBin(1)
        if self.vbin != 1:
            self.setVBin(1)

    def setTemperature(self, temp):
        """Set CCD temperature"""
        fli.setTemperature(self.id, temp)
        self.temp = temp

    def getTemperature(self):
        """Get CCD temperature"""
        return fli.getTemperature(self.id)

    def expose(self, dark=0):
        """Do exposure and return the image"""
        if self.status != READY:
            print "Camera not ready, abort expose command"
            return
        self.dark = dark
        if dark != 0:
            fli.setFrameType(self.id, fli.FRAME_TYPE_DARK)
        else:
            fli.setFrameType(self.id, fli.FRAME_TYPE_NORMAL)
        self.timestamp = strftime("%Y-%m-%dT%H:%M:%S", localtime())

        self.status = EXPOSING
        fli.expose(self.id)
        reactor.callLater(POLL_TIME, self.exposeHandler)

    def exposeHandler(self):
        """Check if exposure is done and write image"""
        if self.isDataReady():
            self.data = fli.grabImage(self.id)
            self.wfits()
            self.status = READY
        elif self.abort != 0:
            reactor.callLater(0, self.abortHandler)
            self.abort = 0
        else:
            reactor.callLater(POLL_TIME, self.exposeHandler)

    def abortHandler(self):
        """Check if camera is ready after abort exposure"""
        if self.isCameraReady():
            self.status = READY
        else:
            reactor.callLater(POLL_TIME, self.abortHandler)

    def expose_test(self):
        """Return the test image"""
        self.dark = 1
        self.timestamp = strftime("%Y-%m-%dT%H:%M:%S", localtime())
        imagesize = (self.expArea[3] - self.expArea[1],
                     self.expArea[2] - self.expArea[0])
        self.data = numpy.ones(shape=imagesize).astype('u2')
        filename = self.getNextFilename("test")
        self.wfits(filename)

    def wfits(self):
        """Write image to a FITS file"""
        if self.dark != 0:
            filename = self.getNextFilename("dark")
        else:
            filename = self.getNextFilename("object")
        if(self.data.size == 0):
            print "No image available"
            return
        hdu = pyfits.PrimaryHDU(self.data)
        hdr = hdu.header
        hdr.update('DATE', self.timestamp, 'file creation date')
        hdr.update('INSTRUME', self.devname, 'this instrument')
        hdr.update('SERIAL', self.devsn, 'serial number')
        hdr.update('EXPTIME', self.exptime, 'exposure time (ms)')
        hdr.update('VBIN', self.vbin, 'vertical binning')
        hdr.update('HBIN', self.hbin, 'horizontal binning')
        hdr.update('CCD-TEMP', self.getTemperature(), 'CCD temperature')
        if(self.dark != 0):
            hdr.update('SHUTTER', 'CLOSE', 'shutter status')
        else:
            hdr.update('SHUTTER', 'OPEN', 'shutter status')
        hdr.update('CCDAREA', '[%d:%d,%d:%d]' % self.expArea, 'image area')
        hdu.writeto(filename, clobber=True, checksum=True)
        self.filename = filename

    def isDataReady(self):
        """Check if exposure finished"""
        return fli.isDataReady(self.id)

    def isCameraReady(self):
        """Check if camera is ready"""
        return fli.isCameraReady(self.id)

    def cancelExposure(self):
        """Cancel an exposure"""
        if self.status == EXPOSING:
            self.abort = 1
            fli.cancelExposure(self.id)

    def getNextFilename(self, expType):
        """Fetch next image filename"""
        self.exposureID += 1
        path = os.path.join("$ICS_MHS_DATA_ROOT", 'agc')
        path = os.path.expandvars(os.path.expanduser(path))
        if not os.path.isdir(path):
            os.makedirs(path, 0o755)
        return os.path.join(path, 'AGC%d_%s_%06d.fits' % (self.agcid + 1, expType, self.exposureID))

