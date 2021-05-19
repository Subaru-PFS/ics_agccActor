"""Fake FLI USB camera module"""

import numpy as np
import astropy.io.fits as pyfits
import time
import os
import threading

class FliError(Exception):
    """Exception for FLI camera"""
    pass

def numberOfCamera():
    """Return number of available FLI cameras"""
    return numCams

def getLibVersion():
    """Get the current library version"""
    return "Software Development Library for Linux 1.999.1"

class Camera:
    """FLI usb camera"""

    def __init__(self, id, devsn, imgPath=None):
        """(id) : index of the camera device"""
        if id < 0 or id >= numCams:
            raise FliError("Camera[%d] not available" % id)
        self.id = id
        self.status = CLOSED
        self.exposureID = 0
        self.agcid = -1
        self.abort = 0
        self.temp = None
        self.devname = "MicroLine ML4720"
        self.devsn = devsn
        self.hwRevision = 256
        self.fwRevision = 512
        self.mode = 0

        # read simulated image, contains single or 6 image extensions
        if imgPath is not None:
            hdulist = pyfits.open(imgPath)
            if len(hdulist) > 1:
                if hdulist[id+1].data is None:
                    self.rawdata = np.zeros((1033, 1072), dtype=np.uint16)
                else:
                    self.rawdata = hdulist[id+1].data.astype(np.uint16)
            else:
                self.rawdata = hdulist[0].data.astype(np.uint16)
        else:
            self.rawdata = np.zeros((1033, 1072), dtype=np.uint16)
        self.lock = threading.Lock()

    def getStatusStr(self):
        with self.lock:
            status = self.status
        return Status[status]

    def isClosed(self):
        with self.lock:
            status = self.status
        return status == CLOSED

    def isReady(self):
        with self.lock:
            status = self.status
        return status == READY

    def isExposing(self):
        with self.lock:
            status = self.status
        return status == EXPOSING

    def isSetmode(self):
        with self.lock:
            status = self.status
        return status == SETMODE

    def open(self):
        """Open the camera device"""
        if dev[self.id] != FLI_INVALID_DEVICE:
            raise FliError("Device already opened")
        dev[self.id] = FLIDEVICE_CAMERA

        # set default parameters
        self.setTemperature(CCD_TEMP)
        self.setHBin(1)
        self.setVBin(1)
        self.setExpTime(0)
        self.setFrame(0, 0, 1072, 1033)
        with self.lock:
            self.status = READY
            self.visibleExpArea = (24, 9, 1048, 1033)
            self.defaultExpArea = (0, 0, 1072, 1033)
            self.expArea = (0, 0, 1072, 1033)
            self.regions = ((0, 0, 0), (0, 0, 0))

    def close(self):
        """Close the camera device"""
        if dev[self.id] == FLI_INVALID_DEVICE:
            raise FliError("Device already closed or not initialized")
        dev[self.id] = FLI_INVALID_DEVICE
        with self.lock:
            self.status = CLOSED

    def setExpTime(self, exptime):
        """Set the exposure time in ms"""
        with self.lock:
            self.exptime = exptime

    def setHBin(self, hbin):
        """Set the horizontal binning"""
        with self.lock:
            self.hbin = hbin

    def setVBin(self, vbin):
        """Set the vertical binning"""
        with self.lock:
            self.vbin = vbin

    def setFrame(self, x1, y1, width, height):
        """Set the image area"""
        with self.lock:
            self.xsize = width
            self.ysize = height
            self.expArea = (x1, y1, x1+width, y1+height)

    def resetFrame(self):
        """Reset the image area"""
        with self.lock:
            hbin = self.hbin
            vbin = self.vbin
        if hbin != 1:
            self.setHBin(1)
        if vbin != 1:
            self.setVBin(1)
        with self.lock:
            self.expArea = self.defaultExpArea
            x1, y1, x2, y2 = self.expArea
            self.xsize = x2 - x1
            self.ysize = y2 - y1

    def setTemperature(self, temp):
        """Set the CCD temperature"""
        with self.lock:
            self.temp = temp

    def getTemperature(self):
        """Get the CCD temperature"""
        with self.lock:
            temp = self.temp
        return temp

    def getCoolerPower(self):
        """Get the cooler power in percentage"""
        return 90.0

    def getPixelSize(self):
        """Get the pixel sizes in micron"""
        return (0.000013, 0.000013)

    def wfits(self, filename=None):
        """Write the image to a FITS file"""
        with self.lock:
            dark = self.dark
        if not filename:
            if dark != 0:
                filename = self.getNextFilename("dark")
            else:
                filename = self.getNextFilename("object")
        with self.lock:
            if(self.data.size == 0):
                raise FliError("No image available")
            hdu = pyfits.PrimaryHDU(self.data)
        hdr = hdu.header
        with self.lock:
            hdr.set('DATE', self.timestamp, 'exposure begin date')
            hdr.set('INSTRUME', self.devname, 'this instrument')
            hdr.set('SERIAL', self.devsn, 'serial number')
            hdr.set('EXPTIME', self.exptime, 'exposure time (ms)')
            hdr.set('VBIN', self.vbin, 'vertical binning')
            hdr.set('HBIN', self.hbin, 'horizontal binning')
            hdr.set('CCD-TEMP', self.temp, 'CCD temperature')
            if dark != 0:
                hdr.set('SHUTTER', 'CLOSE', 'shutter status')
            else:
                hdr.set('SHUTTER', 'OPEN', 'shutter status')
            hdr.set('CCDAREA', '[%d:%d,%d:%d]' % self.expArea, 'image area')
        hdu.writeto(filename, overwrite=True, checksum=True)
        with self.lock:
            self.filename = filename

    def getNextFilename(self, expType):
        """Fetch the next image filename"""
        with self.lock:
            self.exposureID += 1
            exposureID = self.exposureID
        path = os.path.join("$ICS_MHS_DATA_ROOT", 'agcc')
        path = os.path.expandvars(os.path.expanduser(path))
        if not os.path.isdir(path):
            os.makedirs(path, 0o755)
        with self.lock:
            timestamp = self.timestamp
        return os.path.join(path, 'AGC%d_%s_%06d_%s.fits' % \
               (self.agcid + 1, expType, exposureID, timestamp))

    def cancelExposure(self):
        """Cancel current exposure"""
        with self.lock:
            status = self.status
        if status == EXPOSING:
            with self.lock:
                self.abort = 1

    def expose(self, dark=False, blocking=True):
        """Do exposure and return the image"""
        with self.lock:
            status = self.status
        if status != READY:
            raise FliError("Camera not ready, abort expose command")
        with self.lock:
            self.dark = dark
            self.tstart = time.time()
            self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.tstart))
            self.status = EXPOSING

        thr = threading.Thread(target=self.exposeHandler)
        thr.start()
        if blocking:
            thr.join()

    def exposeHandler(self):
        # Check if the exposure is done and write the image
        tstart = time.time();
        with self.lock:
            # add 350ms readout time
            exptime = (self.exptime + 350.0) / 1000.0
        while (time.time() - tstart < exptime):
            time.sleep(POLL_TIME)
            with self.lock:
                abort = self.abort
            if abort != 0:
                break

        with self.lock:
            if self.abort != 0:
                # Exposure aborted
                self.abort = 0
                self.tend = 0
            else:
                xsize = self.xsize
                ysize = self.ysize
                self.data = self.rawdata[self.expArea[1]:self.expArea[3], self.expArea[0]:self.expArea[2]]
                self.tend = time.time()
            self.status = READY

    def expose_test(self):
        """Return the test image"""
        with self.lock:
            self.dark = 1
            self.tstart = time.time()
            self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.tstart))
            imagesize = (self.expArea[3] - self.expArea[1],
                         self.expArea[2] - self.expArea[0])
            self.data = np.ones(shape=imagesize, dtype=np.uint16)
            self.tend = time.time()

    def getModeString(self, mode):
        """Get the camera mode string"""
        if mode == 0:
            return "4 MHz"
        elif mode == 1:
            return "500 KHz"
        else:
            raise FliError("FLIGetCameraModeString failed")

    def getMode(self):
        """Get the camera mode string"""
        with self.lock:
            mode = self.mode
        return mode

    def setMode(self, mode):
        """Get the camera mode string"""
        if mode == 0 or mode == 1:
            with self.lock:
                self.mode = mode
        else:
            raise FliError("FLISetCameraMode failed")

    def getTotalTime(self):
        """ get the total readout + exposure time in second """
        with self.lock:
            if self.tend == 0:
                total = -1
            else:
                total = self.tend - self.tstart
        return total


# module initialization
CLOSED, READY, EXPOSING, SETMODE = range(4)
Status = {CLOSED:"CLOSED", READY:"READY", EXPOSING:"EXPOSING", SETMODE:"SETMODE"}
POLL_TIME = 0.02
CCD_TEMP = -30
FLI_INVALID_DEVICE, FLIDEVICE_CAMERA = 0, 1

numCams = 6
dev = np.zeros(numCams, int)
