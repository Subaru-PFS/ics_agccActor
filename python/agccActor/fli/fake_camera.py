"""Fake FLI USB camera module for simulator mode."""

from __future__ import annotations

import os
import threading
import time
from typing import Any

import astropy.io.fits as pyfits
import numpy as np


class FliError(Exception):
    """Exception raised for FLI camera errors."""

    pass


def numberOfCamera() -> int:
    """Return the number of simulated FLI cameras."""
    return numCams


def getLibVersion() -> str:
    """Return a simulated FLI library version string."""
    return "Software Development Library for Linux 1.999.1"


class Camera:
    """Simulated FLI USB CCD camera.

    Provides the same interface as the Cython ``fli_camera.Camera`` so
    that the rest of the actor can run without hardware.
    """

    def __init__(self, id: int, devsn: str, imgPath: str | None = None) -> None:
        """Instantiate a simulated camera.

        Parameters
        ----------
        id : int
            Zero-based device index (must be in ``[0, numCams)``.
        devsn : str
            Simulated serial number string.
        imgPath : str | None, optional
            Path to a FITS file used as the simulated raw image.  When
            ``None`` (or when ``id+1`` extension is empty) a zero array
            is used.
        """
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
                if hdulist[id + 1].data is None:
                    self.rawdata = np.zeros((1033, 1072), dtype=np.uint16)
                else:
                    self.rawdata = hdulist[id + 1].data.astype(np.uint16)
            else:
                self.rawdata = hdulist[0].data.astype(np.uint16)
        else:
            self.rawdata = np.zeros((1033, 1072), dtype=np.uint16)
        self.lock = threading.Lock()

    def getStatusStr(self) -> str:
        """Return the current camera status as a human-readable string."""
        with self.lock:
            status = self.status
        return Status[status]

    def isClosed(self) -> bool:
        """Return ``True`` if the camera device is closed."""
        with self.lock:
            status = self.status
        return status == CLOSED

    def isReady(self) -> bool:
        """Return ``True`` if the camera is ready to accept commands."""
        with self.lock:
            status = self.status
        return status == READY

    def isExposing(self) -> bool:
        """Return ``True`` if an exposure is in progress."""
        with self.lock:
            status = self.status
        return status == EXPOSING

    def isSetmode(self) -> bool:
        """Return ``True`` if a mode change is in progress."""
        with self.lock:
            status = self.status
        return status == SETMODE

    def open(self) -> None:
        """Open the simulated camera device and set default parameters."""
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

    def close(self) -> None:
        """Close the simulated camera device."""
        if dev[self.id] == FLI_INVALID_DEVICE:
            raise FliError("Device already closed or not initialized")
        dev[self.id] = FLI_INVALID_DEVICE
        with self.lock:
            self.status = CLOSED

    def setExpTime(self, exptime: int) -> None:
        """Set the exposure time in milliseconds."""
        with self.lock:
            self.exptime = exptime

    def setHBin(self, hbin: int) -> None:
        """Set the horizontal binning factor."""
        with self.lock:
            self.hbin = hbin

    def setVBin(self, vbin: int) -> None:
        """Set the vertical binning factor."""
        with self.lock:
            self.vbin = vbin

    def setFrame(self, x1: int, y1: int, width: int, height: int) -> None:
        """Set the imaging area origin and size."""
        with self.lock:
            self.xsize = width
            self.ysize = height
            self.expArea = (x1, y1, x1 + width, y1 + height)

    def resetFrame(self) -> None:
        """Reset the imaging area to the full-frame default."""
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

    def setTemperature(self, temp: float) -> None:
        """Set the simulated CCD temperature in degrees Celsius."""
        with self.lock:
            self.temp = temp

    def getTemperature(self) -> float:
        """Return the simulated CCD temperature in degrees Celsius."""
        with self.lock:
            temp = self.temp
        return temp

    def getCoolerPower(self) -> float:
        """Return a fixed simulated cooler power percentage."""
        return 90.0

    def getPixelSize(self) -> tuple[float, float]:
        """Return the simulated pixel size in metres (x, y)."""
        return (0.000013, 0.000013)

    def wfits(self, filename: str | None = None) -> None:
        """Write the last exposure to a FITS file.

        Parameters
        ----------
        filename : str | None, optional
            Output path.  Derived automatically when ``None``.
        """
        with self.lock:
            dark = self.dark
        if not filename:
            if dark != 0:
                filename = self.getNextFilename("dark")
            else:
                filename = self.getNextFilename("object")
        with self.lock:
            if self.data.size == 0:
                raise FliError("No image available")
            hdu = pyfits.PrimaryHDU(self.data)
        hdr = hdu.header
        with self.lock:
            hdr.set("DATE", self.timestamp, "exposure begin date")
            hdr.set("INSTRUME", self.devname, "this instrument")
            hdr.set("SERIAL", self.devsn, "serial number")
            hdr.set("EXPTIME", self.exptime, "exposure time (ms)")
            hdr.set("VBIN", self.vbin, "vertical binning")
            hdr.set("HBIN", self.hbin, "horizontal binning")
            hdr.set("CCD-TEMP", self.temp, "CCD temperature")
            if dark != 0:
                hdr.set("SHUTTER", "CLOSE", "shutter status")
            else:
                hdr.set("SHUTTER", "OPEN", "shutter status")
            hdr.set("CCDAREA", "[%d:%d,%d:%d]" % self.expArea, "image area")
        hdu.writeto(filename, overwrite=True, checksum=True)
        with self.lock:
            self.filename = filename

    def getNextFilename(self, expType: str) -> str:
        """Return the next canonical exposure filename for this camera.

        Parameters
        ----------
        expType : str
            Exposure type string used in the filename (e.g. ``'dark'``).

        Returns
        -------
        str
            Absolute path of the next output FITS file.
        """
        with self.lock:
            self.exposureID += 1
            exposureID = self.exposureID
        path = os.path.join("$ICS_MHS_DATA_ROOT", "agcc")
        path = os.path.expandvars(os.path.expanduser(path))
        if not os.path.isdir(path):
            os.makedirs(path, 0o755)
        with self.lock:
            timestamp = self.timestamp
        return os.path.join(path, "AGC%d_%s_%06d_%s.fits" % (self.agcid + 1, expType, exposureID, timestamp))

    def cancelExposure(self) -> None:
        """Set the abort flag to cancel a running exposure."""
        with self.lock:
            status = self.status
        if status == EXPOSING:
            with self.lock:
                self.abort = 1

    def expose(self, dark: bool = False, blocking: bool = True) -> None:
        """Start an exposure and optionally block until completion.

        Parameters
        ----------
        dark : bool, optional
            ``True`` for a dark (shutter-closed) exposure.
        blocking : bool, optional
            ``True`` to wait for the exposure thread to finish.
        """
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

    def exposeHandler(self) -> None:
        """Internal thread target: wait for the exposure to complete, then latch the image."""
        # Check if the exposure is done and write the image
        tstart = time.time()
        with self.lock:
            # add 350ms readout time
            exptime = (self.exptime + 350.0) / 1000.0
        while time.time() - tstart < exptime:
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
                self.data = self.rawdata[self.expArea[1] : self.expArea[3], self.expArea[0] : self.expArea[2]]
                self.tend = time.time()
            self.status = READY

    def expose_test(self) -> None:
        """Set the camera data to a flat test image without using the shutter."""
        with self.lock:
            self.dark = 1
            self.tstart = time.time()
            self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.tstart))
            imagesize = (self.expArea[3] - self.expArea[1], self.expArea[2] - self.expArea[0])
            self.data = np.ones(shape=imagesize, dtype=np.uint16)
            self.tend = time.time()

    def getModeString(self, mode: int) -> str:
        """Return the name of the given readout mode.

        Parameters
        ----------
        mode : int
            Mode index (0 or 1).

        Returns
        -------
        str
            Human-readable mode label.
        """
        if mode == 0:
            return "4 MHz"
        elif mode == 1:
            return "500 KHz"
        else:
            raise FliError("FLIGetCameraModeString failed")

    def getMode(self) -> int:
        """Return the current readout mode index."""
        with self.lock:
            mode = self.mode
        return mode

    def setMode(self, mode: int) -> None:
        """Set the readout mode.

        Parameters
        ----------
        mode : int
            Mode index; must be 0 or 1.
        """
        if mode == 0 or mode == 1:
            with self.lock:
                self.mode = mode
        else:
            raise FliError("FLISetCameraMode failed")

    def getTotalTime(self) -> float:
        """Return the total elapsed time (exposure + readout) in seconds.

        Returns
        -------
        float
            Elapsed seconds, or ``-1`` if the exposure was aborted.
        """
        with self.lock:
            if self.tend == 0:
                total = -1
            else:
                total = self.tend - self.tstart
        return total


# module initialization
CLOSED, READY, EXPOSING, SETMODE = range(4)
Status: dict[int, str] = {CLOSED: "CLOSED", READY: "READY", EXPOSING: "EXPOSING", SETMODE: "SETMODE"}
POLL_TIME = 0.02
CCD_TEMP = -30
FLI_INVALID_DEVICE, FLIDEVICE_CAMERA = 0, 1

numCams = 6
dev: Any = np.zeros(numCams, int)
