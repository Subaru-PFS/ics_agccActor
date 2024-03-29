"""FLI USB camera module"""

from libc.stdlib cimport malloc, free
from libc.string cimport strcpy, strlen
from cython.view cimport array
from libc.stdio cimport printf
import numpy as np
import astropy.io.fits as pyfits
import time
import os
import threading

CLOSED, READY, EXPOSING, SETMODE = range(4)
Status = {CLOSED:"CLOSED", READY:"READY", EXPOSING:"EXPOSING", SETMODE:"SETMODE"}
POLL_TIME = 0.02
CCD_TEMP = -30
numCams = 0



cdef void EnumerateCameras() nogil:
    cdef char file[MAX_PATH]
    cdef char name[MAX_PATH]
    cdef long domain
    global numCams, listName, listDomain

    FLICreateList(FLIDOMAIN_USB | FLIDEVICE_CAMERA)

    numCams = 0
    if FLIListFirst(&domain, file, MAX_PATH, name, MAX_PATH) == 0:
        while True:
            listName[numCams] = <char *> malloc(strlen(file) + 1)
            strcpy(listName[numCams], file)
            listDomain[numCams] = domain
            numCams += 1
            if FLIListNext(&domain, file, MAX_PATH, name, MAX_PATH) != 0 or numCams >= MAX_DEVICES:
                break

        FLIDeleteList()

class FliError(Exception):
    """Exception for FLI camera"""
    pass

def numberOfCamera():
    """Return number of available FLI cameras"""
    return numCams

def getLibVersion():
    """Get the current library version"""
    return libver.decode('utf-8')

class CameraInit:
    def __init__(self):
        for i in range(MAX_DEVICES):
            dev[i] = FLI_INVALID_DEVICE
        FLISetDebugLevel(NULL, FLIDEBUG_NONE)
        if FLIGetLibVersion(libver, LIBVERSIZE) != 0:
            raise FliError("FLIGetLibVersion failed")

        EnumerateCameras()



class Camera:
    """FLI usb camera"""

    def __init__(self, id=0):
        """(id) : index of the camera device"""
        if id < 0 or id >= numCams:
            raise FliError("Camera[%d] not available" % id)
        self.id = id
        self.status = CLOSED
        self.exposureID = 0
        self.agcid = -1
        self.abort = 0
        self.temp = None
        self.lock = threading.Lock()

    def debugInfo(self):
        return dev[self.id], listDomain[self.id], listName[self.id]

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
        cdef int id = self.id
        cdef char buff[BUFF_SIZE]
        cdef long ltmp, res
        cdef long x1, x2, y1, y2

        if dev[id] != FLI_INVALID_DEVICE:
            raise FliError("Device already opened")
        with nogil:
            res = FLIOpen(&dev[id], listName[id], listDomain[id])
        if res != 0:
            raise FliError("FLIOpen failed")
        with nogil:
            res = FLIControlBackgroundFlush(dev[id], FLI_BGFLUSH_START)
        if res != 0:
            raise FliError("FLIControlBackgroundFlush failed")
        with nogil:
            res = FLIGetModel(dev[id], buff, BUFF_SIZE)
        if res != 0:
            raise FliError("FLIGetModel failed")
        self.devname = buff.decode('utf-8')
        with nogil:
            res = FLIGetSerialString(dev[id], buff, BUFF_SIZE)
        if res != 0:
            raise FliError("FLIGetSerialString failed")
        self.devsn = buff.decode('utf-8')
        with nogil:
            res = FLIGetHWRevision(dev[id], &ltmp)
        if res != 0:
            raise FliError("FLIGetHWRevision failed")
        self.hwRevision = ltmp
        with nogil:
            res = FLIGetFWRevision(dev[id], &ltmp)
        if res != 0:
            raise FliError("FLIGetFWRevision failed")
        self.fwRevision = ltmp

        # set default parameters
        self.setTemperature(CCD_TEMP)
        self.setHBin(1)
        self.setVBin(1)
        with nogil:
            res = FLISetTDI(dev[id], 0, 0)
        if res != 0:
            raise FliError("FLISetTDI failed")
        self.setExpTime(0)
        with nogil:
            res = FLIGetVisibleArea(dev[id], &x1, &y1, &x2, &y2)
        if res != 0:
            raise FliError("FLIGetVisibleArea failed")
        self.visibleExpArea = (x1, y1, x2, y2)
        with nogil:
            res = FLIGetArrayArea(dev[id], &x1, &y1, &x2, &y2)
        if res != 0:
            raise FliError("FLIGetArrayArea failed")
        self.defaultExpArea = (x1, y1, x2, y2)
        self.setFrame(x1, y1, x2 - x1, y2 - y1)
        self.regions = ((0, 0, 0), (0, 0, 0))

        # allocate image buffer
        buffer[self.id] = <unsigned short *> malloc(x2 * y2 * sizeof(unsigned short))
        with self.lock:
            self.status = READY

    def close(self):
        """Close the camera device"""
        cdef int id = self.id

        if dev[id] == FLI_INVALID_DEVICE:
            raise FliError("Device already closed or not initialized")
        with nogil:
            FLIClose(dev[id])
            dev[id] = FLI_INVALID_DEVICE
            free(buffer[id])
        with self.lock:
            self.status = CLOSED

    def setExpTime(self, exptime):
        """Set the exposure time in ms"""
        cdef int id = self.id
        cdef long res, cexptime = exptime

        with nogil:
            res = FLISetExposureTime(dev[id], cexptime)
        if res != 0:
            raise FliError("FLISetExposureTime failed")
        with self.lock:
            self.exptime = exptime

    def setHBin(self, hbin):
        """Set the horizontal binning"""
        cdef int id = self.id
        cdef long res, chbin = hbin

        with nogil:
            res = FLISetHBin(dev[id], chbin)
        if res != 0:
            raise FliError("FLISetHBin failed")
        with self.lock:
            self.hbin = hbin

    def setVBin(self, vbin):
        """Set the vertical binning"""
        cdef int id = self.id
        cdef long res, cvbin = vbin

        with nogil:
            res = FLISetVBin(dev[id], cvbin)
        if res != 0:
            raise FliError("FLISetVBin failed")
        with self.lock:
            self.vbin = vbin

    def setFrame(self, x1, y1, width, height):
        """Set the image area"""
        cdef int id = self.id
        cdef long res, cx1 = x1, cy1 = y1
        cdef long cx2 = x1 + width, cy2 = y1 + height

        with nogil:
            res = FLISetImageArea(dev[id], cx1, cy1, cx2, cy2)
        if res != 0:
            raise FliError("FLISetImageArea failed")
        with self.lock:
            self.xsize = width
            self.ysize = height
            self.expArea = (cx1, cy1, cx2, cy2)

    def resetFrame(self):
        """Reset the image area"""
        cdef int id = self.id
        cdef long res
        cdef long x1, y1, x2, y2

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
        with nogil:
            res = FLISetImageArea(dev[id], x1, y1, x2, y2)
        if res != 0:
            raise FliError("FLISetImageArea failed")
        with self.lock:
            self.xsize = x2 - x1
            self.ysize = y2 - y1

    def setTemperature(self, temp):
        """Set the CCD temperature"""
        cdef int id = self.id
        cdef long res
        cdef double ctemp = temp

        with nogil:
            res = FLISetTemperature(dev[id], ctemp)
        if res != 0:
            raise FliError("FLISetTemperature failed")
        with self.lock:
            self.temp = temp

    def getTemperature(self):
        """Get the CCD temperature"""
        cdef int id = self.id
        cdef long res
        cdef double dtmp

        with nogil:
            res = FLIGetTemperature(dev[id], &dtmp)
        if res != 0:
            raise FliError("FLIGetTemperature failed")
        return dtmp

    def getCoolerPower(self):
        """Get the cooler power in percentage"""
        cdef int id = self.id
        cdef long res
        cdef double dtmp

        with nogil:
            res = FLIGetCoolerPower(dev[id], &dtmp)
        if res != 0:
            raise FliError("FLIGetCoolerPower failed")
        return dtmp

    def getPixelSize(self):
        """Get the pixel sizes in micron"""
        cdef int id = self.id
        cdef long res
        cdef double dtmp, dtmp2

        with nogil:
            res = FLIGetPixelSize(dev[id], &dtmp, &dtmp2)
        if res != 0:
            raise FliError("FLIGetPixelSize failed")
        return (dtmp, dtmp2)

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
            hdr.set('CCD-TEMP', self.getTemperature(), 'CCD temperature')
            if dark != 0:
                hdr.set('SHUTTER', 'CLOSE', 'shutter status')
            else:
                hdr.set('SHUTTER', 'OPEN', 'shutter status')
            hdr.set('CCDAREA', '[%d:%d,%d:%d]' % self.expArea, 'image area')
        hdu.writeto(filename, overwrite=True, checksum=True)
        with self.lock:
            self.filename = filename

    def getDeviceStatus(self):
        """Get the device status"""
        cdef int id = self.id
        cdef long res, status

        with nogil:
            res = FLIGetDeviceStatus(dev[id], &status)
        if res != 0:
            raise FliError("FLIGetDeviceStatus failed")
        return status

    def getExposureStatus(self):
        """Get the exposure status"""
        cdef int id = self.id
        cdef long res, tleft

        with nogil:
            res = FLIGetExposureStatus(dev[id], &tleft)
        if res != 0:
            raise FliError("FLIGetExposureStatus failed")
        return tleft

    def isDataReady(self):
        """Check if the exposure finished"""
        cdef long status, tleft

        status = self.getDeviceStatus()
        tleft = self.getExposureStatus()
        return (((status == FLI_CAMERA_STATUS_UNKNOWN) and (tleft == 0)) or
               ((status != FLI_CAMERA_STATUS_UNKNOWN) and
               (status & FLI_CAMERA_DATA_READY) != 0))

    def isCameraReady(self):
        """Check if the camera is ready"""
        cdef long status, tleft

        status = self.getDeviceStatus()
        tleft = self.getExposureStatus()
        return (((status == FLI_CAMERA_STATUS_UNKNOWN) and (tleft == 0)) or
               ((status != FLI_CAMERA_STATUS_UNKNOWN) and
               (status & FLI_CAMERA_STATUS_MASK) == FLI_CAMERA_STATUS_IDLE))

    def getNextFilename(self, expType):
        """Fetch the next image filename"""

        with self.lock:
            self.exposureID += 1
            exposureID = self.exposureID
        path = os.path.join("$ICS_MHS_DATA_ROOT", 'agcc')
        path = os.path.expandvars(os.path.expanduser(path))
        if not os.path.isdir(path):
            try:
                os.makedirs(path, 0o755)
            except Exception as e:
                raise RuntimeError(f'failed to makedirs({path}): {e}')
        with self.lock:
            timestamp = self.timestamp
        return os.path.join(path, 'AGC%d_%s_%06d_%s.fits' % \
               (self.agcid + 1, expType, exposureID, timestamp))

    def cancelExposure(self):
        """Cancel current exposure"""
        cdef long res
        cdef int id = self.id

        with self.lock:
            status = self.status
        if status == EXPOSING:
            with self.lock:
                self.abort = 1
            with nogil:
                res = FLIEndExposure(dev[id])
            if res != 0:
                raise FliError("FLIEndExposure failed")

    def expose(self, dark=False, blocking=True):
        """Do exposure and return the image"""
        cdef long ftype, res
        cdef int id = self.id

        with self.lock:
            status = self.status
        if status != READY:
            raise FliError("Camera not ready, abort expose command")
        with self.lock:
            self.dark = dark
        if dark:
            ftype = FLI_FRAME_TYPE_DARK
        else:
            ftype = FLI_FRAME_TYPE_NORMAL
        with nogil:
            res = FLISetFrameType(dev[id], ftype)
        if res != 0:
            raise FliError("FLISetFrameType failed")
        with self.lock:
            self.tstart = time.time()
            self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.tstart))

        with self.lock:
            self.status = EXPOSING
        with nogil:
            res = FLIExposeFrame(dev[id])
        if res != 0:
            raise FliError("FLIExposeFrame failed")

        thr = threading.Thread(target=self.exposeHandler)
        thr.start()
        if blocking:
            thr.join()

    def exposeHandler(self):
        # Check if the exposure is done and write the image
        cdef int i, id = self.id
        cdef long res
        cdef size_t xsize, ysize
        cdef unsigned short[:, ::1] mv

        with self.lock:
            xsize = self.xsize
            ysize = self.ysize
        while not self.isDataReady():
            time.sleep(POLL_TIME)

        with self.lock:
            abort = self.abort
        if abort != 0:
            # Exposure aborted
            with self.lock:
                self.abort = 0
                self.tend = 0
        else:
            # Read data
            res = 0
            with nogil:
                for i in range(ysize):
                    res = FLIGrabRow(dev[id], &buffer[id][i*xsize], xsize)
                    if res != 0:
                        break
            if res != 0:
                raise FliError("FLIGrabRow failed")
            mv = <unsigned short[:ysize, :xsize]> buffer[self.id]
            with self.lock:
                self.data = np.asarray(mv)
                self.tend = time.time()
#            self.wfits()

        with self.lock:
            self.status = READY

    def expose_test(self):
        """Return the test image"""

        with self.lock:
            self.dark = 1
            self.tstart = time.time()
            self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.tstart))
            imagesize = (self.expArea[3] - self.expArea[1],
                         self.expArea[2] - self.expArea[0])
            self.data = np.ones(shape=imagesize).astype('u2')
            self.tend = time.time()
#        filename = self.getNextFilename("test")
#        self.wfits(filename)

    def getModeString(self, mode):
        """Get the camera mode string"""
        cdef int id = self.id
        cdef long res, cmode = mode
        cdef char buff[BUFF_SIZE]

        with nogil:
            res = FLIGetCameraModeString(dev[id], cmode, buff, BUFF_SIZE)
        if res != 0:
            raise FliError("FLIGetCameraModeString failed")
        return buff.decode('utf-8')

    def getMode(self):
        """Get the camera mode string"""
        cdef int id = self.id
        cdef long res, cmode

        with nogil:
            res = FLIGetCameraMode(dev[id], &cmode)
        if res != 0:
            raise FliError("FLIGetCameraMode failed")
        return cmode

    def setMode(self, mode):
        """Get the camera mode string"""
        cdef int id = self.id
        cdef long res, cmode = mode

        with self.lock:
            self.status = SETMODE
        with nogil:
            res = FLISetCameraMode(dev[id], cmode)
        if res != 0:
            raise FliError("FLISetCameraMode failed")
        with self.lock:
            self.status = READY

    def getTotalTime(self):
        """ get the total readout + exposure time in second """
        with self.lock:
            if self.tend == 0:
                total = -1
            else:
                total = self.tend - self.tstart
        return total
    
    def openShutter(self):
        """ Force to close the shutter """
        cdef int id = self.id
        
        with nogil:
            res = FLIControlShutter(dev[id], FLI_SHUTTER_OPEN)
        if res != 0:
            raise FliError("FLIControlShutter failed")
    
    def closeShutter(self):
        """ Force to close the shutter """
        cdef int id = self.id
        
        with nogil:
            res = FLIControlShutter(dev[id], FLI_SHUTTER_CLOSE)
        if res != 0:
            raise FliError("FLIControlShutter failed")


# module initialization
#CLOSED, READY, EXPOSING, SETMODE = range(4)
#Status = {CLOSED:"CLOSED", READY:"READY", EXPOSING:"EXPOSING", SETMODE:"SETMODE"}
#POLL_TIME = 0.02
#CCD_TEMP = -30

#numCams = 0
#for i in range(MAX_DEVICES):
#    dev[i] = FLI_INVALID_DEVICE
#FLISetDebugLevel(NULL, FLIDEBUG_NONE)
#if FLIGetLibVersion(libver, LIBVERSIZE) != 0:
#    raise FliError("FLIGetLibVersion failed")
#EnumerateCameras()



