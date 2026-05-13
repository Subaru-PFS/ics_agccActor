import logging
import os
from typing import TYPE_CHECKING, Optional, Union

from pfs.utils.database.opdb import OpDB

from agccActor import photometry, writeFits
from agccActor.expose import Exposure
from agccActor.setmode import SetMode

if TYPE_CHECKING:
    from agccActor.fli.fake_camera import Camera as FakeFliCamera
    from agccActor.fli.fli_camera import Camera as FliCamera

    FliCameraType = Union[FliCamera, FakeFliCamera]

nCams = 6


class Camera(object):
    """Controller for the Subaru PFI AG (Auto Guider) cameras.

    Manages up to ``nCams`` FLI USB CCD cameras (real or simulated), their
    photometry worker processes, and per-camera state.
    """

    def __init__(self, config: dict):
        """Connect to the AG cameras.

        Parameters
        ----------
        config : dict
            Actor configuration dictionary. Expected keys include
            ``simulator`` (0/1), ``temperature``, ``cam1`` ... ``cam6``
            (camera serial numbers), and optionally ``simulatedImagePath``
            and ``db.opdb`` connection parameters.
        """

        self.logger = logging.getLogger("agcc")

        try:
            db_params = config["db"]["opdb"]
            self.logger.info(f"Setting default database connection with parameters: {db_params}")
            OpDB.set_default_connection(**db_params)
        except KeyError:
            self.logger.info("No database configuration for opdb found, using defaults.")

        simulator = config["simulator"]
        self.cams: list[Optional["FliCameraType"]] = [None, None, None, None, None, None]
        temp = config["temperature"]

        self.logger.info(f"Setting TEC to {temp}.")

        self.temp = temp

        if simulator == 0:
            from agccActor.fli import fli_camera
            fli_camera.CameraInit()

            # Put available cameras in a dict by serial number.
            available_cams = {}
            self.numberOfCamera = fli_camera.numberOfCamera()
            for n in range(self.numberOfCamera):
                cam = fli_camera.Camera(n)
                cam.open()
                available_cams[cam.devsn] = cam

            # Match the available to what is in the config.
            for k in range(nCams):
                expected_serial = config.get("cam" + str(k + 1))

                if expected_serial in available_cams:
                    cam = available_cams.pop(expected_serial)

                    self.cams[k] = cam
                    cam.agcid = k
                    cam.setTemperature(temp)
                    cam.regions = ((0, 0, 0), (0, 0, 0))
                    cam.in_queue, cam.out_queue, cam.proc = photometry.createProc()
                    self.logger.info(f"Creating process ID for Cam {cam.agcid + 1}: {cam.proc.pid}.")
                else:
                    self.logger.warning(f"Configured camera {expected_serial} was not found on the bus!")

            for unassigned_serial, unused_cam in available_cams.items():
                self.logger.info(f"Closing unconfigured camera {unassigned_serial}.")
                unused_cam.close()
        else:
            from agccActor.fli import fake_camera

            self.numberOfCamera = fake_camera.numberOfCamera()
            simImagePath = config["simulatedImagePath"]
            if len(simImagePath) == 0:
                simImagePath = None
            else:
                simImagePath = os.path.expandvars(simImagePath)

            for n in range(self.numberOfCamera):
                devsn = config["cam" + str(n + 1)]
                cam = fake_camera.Camera(n, devsn, simImagePath)
                cam.open()
                self.cams[n] = cam
                cam.agcid = n
                cam.setTemperature(temp)
                cam.regions = ((0, 0, 0), (0, 0, 0))
                cam.in_queue, cam.out_queue, cam.proc = photometry.createProc()

    def closeCamera(self) -> None:
        """Stop photometry workers and close all open cameras."""
        for c_i, cam in enumerate(self.cams):
            if cam is not None:
                # close the queue as well
                self.logger.info(f"Closing process ID {cam.proc.pid}.")
                cam.proc.kill()  # Send stop signal to the input queue
                self.logger.info(f"Join the process {cam.proc.pid}.")
                cam.proc.join()

                cam.close()
                self.cams[c_i] = None

    def runningCameras(self) -> list:
        """Return the list of valid (connected) camera indices.

        Returns
        -------
        list of int
            Zero-based indices of cameras that are currently connected.
        """

        cams = []
        for n in range(nCams):
            if self.cams[n] is not None:
                cams.append(n)
        return cams

    def reportTEC(self, cmd) -> None:
        """Report the current TEC/CCD temperature of each AG camera.

        Parameters
        ----------
        cmd : object
            A tron command object used to send ``inform`` keyword replies.
        """
        cmd.inform('text="Number of AG cameras = %d"' % self.numberOfCamera)
        for n in range(nCams):
            if self.cams[n] is not None:
                tempstr = "%5.1f" % self.cams[n].getTemperature()
                cmd.inform(
                    'text="[%d] %s SN=%s status=%s temp=%s"'
                    % (n + 1, self.cams[n].devname, self.cams[n].devsn, self.cams[n].getStatusStr(), tempstr)
                )

    def sendStatusKeys(self, cmd) -> None:
        """Send the status keywords (``agcN_stat``) of every camera slot.

        Parameters
        ----------
        cmd : object
            A tron command object used to send ``inform`` keyword replies.
        """

        cmd.inform('text="Number of AG cameras = %d"' % self.numberOfCamera)
        for n in range(nCams):
            if self.cams[n] is not None:
                if self.cams[n].isReady():
                    tempstr = "%5.1f" % self.cams[n].getTemperature()
                    cmd.inform("agc%d_stat=READY" % (n + 1))
                else:
                    tempstr = "<%5.1f>" % self.cams[n].temp
                    cmd.inform("agc%d_stat=BUSY" % (n + 1))
                cmd.inform(
                    'text="[%d] %s SN=%s status=%s temp=%s regions=%s bin=(%d,%d) expArea=%s"'
                    % (
                        n + 1,
                        self.cams[n].devname,
                        self.cams[n].devsn,
                        self.cams[n].getStatusStr(),
                        tempstr,
                        self.cams[n].regions,
                        self.cams[n].hbin,
                        self.cams[n].vbin,
                        self.cams[n].expArea,
                    )
                )
            else:
                cmd.inform("agc%d_stat=ABSENT" % (n + 1))

    def expose(
        self,
        cmd,
        expTime,
        expType,
        cams,
        combined,
        centroid,
        pfsVisitId,
        cParms,
        cMethod,
        iParms,
        threadDelay=None,
        tecOFF=False,
    ) -> None:
        """Take an exposure on one or more cameras.

        Parameters
        ----------
        cmd : object or None
            A tron command object to report to. Ignored if ``None``.
        expTime : float
            Exposure time in seconds.
        expType : str
            Exposure type, one of ``"dark"``, ``"object"``, ``"test"``.
        cams : list of int
            List of zero-based camera indices to expose.
        combined : bool
            If ``True`` write one combined FITS file; otherwise write one
            FITS file per camera.
        centroid : bool
            If ``True`` run centroiding on the resulting images.
        pfsVisitId : int
            The PFS visit identifier for this exposure.
        cParms : dict
            Centroiding parameters (thresholds, min area, deblend, etc.).
        cMethod : str
            Centroiding method (e.g. ``"sep"``).
        iParms : dict
            Per-camera instrumental parameters (regions, bad columns, ...).
        threadDelay : float, optional
            Inter-camera thread start delay in milliseconds.
        tecOFF : bool, optional
            If ``True`` turn the TEC off during the exposure.

        Notes
        -----
        Updates the ``stat_cam[1-6]`` keywords on the command channel.
        """

        # check if any camera is available
        cams_available = []
        for n in cams:
            if self.cams[n] is not None:
                cams_available.append(n)
        if len(cams_available) <= 0:
            if cmd:
                cmd.warn('text="No available cameras"')
                cmd.finish()
            return

        # check if all cameras are ready
        for n in cams_available:
            if not self.cams[n].isReady():
                if cmd:
                    cmd.fail('text="camera busy, command ignored"')
                return

        if not expType:
            expType = "test"
        if cmd:
            cmd.inform('text="Receive expose command"')

        active_cams = [self.cams[n] for n in cams_available]
        self.logger.info(
            f"Exposing cameras: {[cam.agcid + 1 for cam in active_cams]} for {expTime}s as {expType}."
        )
        if expType == "test":
            for n in cams_available:
                self.cams[n].expose_test()
                self.cams[n].spots = None
                if not combined:
                    writeFits.wfits(cmd, self.cams[n])
            if combined:
                writeFits.wfits_combined(cmd, active_cams)
            for n in cams_available:
                if cmd:
                    tread = self.cams[n].getTotalTime()
                    cmd.inform('text="AGC[%d]: Retrieve camera data in %.2fs"' % (n + 1, tread))
                    cmd.finish()
        else:
            expTime_ms = int(expTime * 1000)
            if expType == "dark":
                dflag = True
            else:
                dflag = False

            exp_thr = Exposure(
                active_cams,
                expTime_ms,
                dflag,
                cParms,
                iParms,
                pfsVisitId,
                cMethod,
                cmd,
                combined,
                centroid,
                threadDelay=threadDelay,
                tecOFF=tecOFF,
            )
            exp_thr.start()

    def abort(self, cmd, cams) -> None:
        """Abort the current exposure on the given cameras.

        Parameters
        ----------
        cmd : object or None
            A tron command object to report to. Ignored if ``None``.
        cams : list of int
            List of zero-based camera indices to abort.
        """

        for n in cams:
            if self.cams[n] is not None and not self.cams[n].isReady():
                cmd.inform('text="Send abort command to AGC[%d]"' % (n + 1))
                self.cams[n].cancelExposure()

    def setframe(self, cmd, cams, bx: int, by: int, cx: int, cy: int, sx: int, sy: int) -> None:
        """Set the exposure (frame) area on the given cameras.

        Parameters
        ----------
        cmd : object or None
            A tron command object to report to. Ignored if ``None``.
        cams : list of int
            List of zero-based camera indices.
        bx, by : int
            Serial (x) and parallel (y) binning sizes. Values <= 0 are
            ignored (no change).
        cx, cy : int
            Pixel coordinates of the frame corner.
        sx, sy : int
            Frame size in pixels along x and y.
        """

        for n in cams:
            if self.cams[n] is not None and not self.cams[n].isReady():
                if cmd:
                    cmd.fail('text="camera busy, command ignored"')
                return

        for n in cams:
            if self.cams[n] is not None:
                if cmd:
                    cmd.inform('text="Send setframe command to AGC[%d]"' % (n + 1))
                if bx > 0:
                    self.cams[n].setHBin(bx)
                if by > 0:
                    self.cams[n].setVBin(by)
                self.cams[n].setFrame(cx, cy, sx, sy)
        if cmd:
            cmd.inform('text="Camera expose area set"')
            cmd.finish()

    def openShutter(self, cmd, cams) -> None:
        """Open the shutter on the given cameras.

        Parameters
        ----------
        cmd : object or None
            A tron command object to report to. Ignored if ``None``.
        cams : list of int
            List of zero-based camera indices.
        """
        for n in cams:
            if self.cams[n] is not None and not self.cams[n].isReady():
                if cmd:
                    cmd.fail('text="camera busy, command ignored"')
                return

        for n in cams:
            if self.cams[n] is not None:
                if cmd:
                    cmd.inform('text="Send shutter opening command to AGC[%d]"' % (n + 1))
                self.cams[n].openShutter()
        if cmd:
            cmd.inform('text="Camera shutter opened"')
            cmd.finish()

    def closeShutter(self, cmd, cams) -> None:
        """Close the shutter on the given cameras.

        Parameters
        ----------
        cmd : object or None
            A tron command object to report to. Ignored if ``None``.
        cams : list of int
            List of zero-based camera indices.
        """
        for n in cams:
            if self.cams[n] is not None and not self.cams[n].isReady():
                if cmd:
                    cmd.fail('text="camera busy, command ignored"')
                return

        for n in cams:
            if self.cams[n] is not None:
                if cmd:
                    cmd.inform('text="Send shutter opening command to AGC[%d]"' % (n + 1))
                self.cams[n].closeShutter()
        if cmd:
            cmd.inform('text="Camera shutter closed"')
            cmd.finish()

    def resetframe(self, cmd, cams) -> None:
        """Reset the exposure area to the full frame on the given cameras.

        Parameters
        ----------
        cmd : object or None
            A tron command object to report to. Ignored if ``None``.
        cams : list of int
            List of zero-based camera indices.
        """

        for n in cams:
            if self.cams[n] is not None and not self.cams[n].isReady():
                if cmd:
                    cmd.fail('text="camera busy, command ignored"')
                return

        for n in cams:
            if self.cams[n] is not None:
                if cmd:
                    cmd.inform('text="Send resetframe command to AGC[%d]"' % (n + 1))
                self.cams[n].resetFrame()
        if cmd:
            cmd.inform('text="Camera expose area reset"')
            cmd.finish()

    def setmode(self, cmd, mode: int, cams) -> None:
        """Set the camera readout mode on the given cameras.

        Parameters
        ----------
        cmd : object or None
            A tron command object to report to. Ignored if ``None``.
        mode : int
            Readout mode (e.g. ``0`` for 4 MHz, ``1`` for 500 kHz).
        cams : list of int
            List of zero-based camera indices.
        """

        cams_available = []
        for n in cams:
            if self.cams[n] is not None:
                if not self.cams[n].isReady():
                    if cmd:
                        cmd.fail('text="camera busy, command ignored"')
                    return
                else:
                    cams_available.append(n)

        active_cams = [self.cams[n] for n in cams_available]
        setmode_thr = SetMode(active_cams, mode, cmd)
        setmode_thr.start()

    def getmode(self, cmd, cams) -> None:
        """Get the camera readout mode of the given cameras.

        Parameters
        ----------
        cmd : object or None
            A tron command object to report to. Ignored if ``None``.
        cams : list of int
            List of zero-based camera indices.
        """

        for n in cams:
            if self.cams[n] is not None and not self.cams[n].isReady():
                if cmd:
                    cmd.fail('text="camera busy, command ignored"')
                return
        for n in cams:
            if self.cams[n] is not None:
                mode = self.cams[n].getMode()
                if cmd:
                    cmd.respond('text="AGC[%d] readout mode: %d"' % (n + 1, mode))
        cmd.inform('text="Camera getmode command done"')
        cmd.finish()

    def getmodestring(self, cmd) -> None:
        """Get the readout-mode description strings from the first ready camera.

        Parameters
        ----------
        cmd : object or None
            A tron command object to report to. Ignored if ``None``.
        """

        for n in range(nCams):
            if self.cams[n] is not None and self.cams[n].isReady():
                s0 = self.cams[n].getModeString(0)
                s1 = self.cams[n].getModeString(1)
                if cmd:
                    cmd.respond('text="mode 0: %s"' % (s0))
                    cmd.respond('text="mode 1: %s"' % (s1))
                    cmd.inform('text="Camera getmodestring command done"')
                    cmd.finish()
                return
        if cmd:
            cmd.fail('text="camera busy or none attached, command ignored"')

    def setcamtemperature(self, cmd, cam: int, temp: float) -> None:
        """Set the CCD temperature for an individual camera.

        Parameters
        ----------
        cmd : object or None
            A tron command object to report to. Ignored if ``None``.
        cam : int
            Zero-based camera index.
        temp : float
            Target CCD temperature in degrees Celsius.
        """
        if self.cams[cam].isReady():
            self.cams[cam].setTemperature(temp)
        else:
            if cmd:
                cmd.warn('text="Camera [%d] is busy"' % cam)

    def settemperature(self, cmd, temp: float) -> None:
        """Set the CCD temperature on all connected cameras.

        Parameters
        ----------
        cmd : object or None
            A tron command object to report to. Ignored if ``None``.
        temp : float
            Target CCD temperature in degrees Celsius.
        """

        busy = False
        for n in range(nCams):
            if self.cams[n] is not None:
                if self.cams[n].isReady():
                    self.cams[n].setTemperature(temp)
                else:
                    busy = True
                    if cmd:
                        cmd.warn('text="Camera [%d] is busy"' % n)
        if cmd:
            if busy:
                cmd.fail('text="Camera settemperature command abort"')
            else:
                cmd.inform('text="Camera settemperature command done"')
                cmd.finish()

    def setregions(self, cmd, camid: int, regions_str: str) -> None:
        """Set the CCD regions of interest for a single camera.

        Parameters
        ----------
        cmd : object or None
            A tron command object to report to. Ignored if ``None``.
        camid : int
            Zero-based camera index.
        regions_str : str
            Comma-separated region definition. Either 3 values (one region)
            or 6 values (two regions) of the form ``x,y,d`` each.
        """

        pars = regions_str.split(",")
        if len(pars) == 3:
            # only one region
            self.cams[camid].regions = ((pars[0], pars[1], pars[2]), (0, 0, 0))
        elif len(pars) == 6:
            # two regions
            self.cams[camid].regions = ((pars[0], pars[1], pars[2]), (pars[3], pars[4], pars[5]))
        else:
            # wrong number of parameters
            if cmd:
                cmd.fail('text="setregions command failed, invalid parameter: %s"' % regions_str)
            return

        if cmd:
            cmd.inform('text="setregions command done"')
            cmd.finish()

    def camera_stat(self, cam_id: int) -> str:
        """Return the status string of a single camera.

        Parameters
        ----------
        cam_id : int
            Zero-based camera index.

        Returns
        -------
        str
            A short string describing the camera status.
        """

        return self.cams[cam_id].getStatusStr()
