"""Camera management for the Subaru PFS Auto Guider CCD subsystem."""

from __future__ import annotations

import logging
import os
from typing import Any

import photometry
import writeFits
from expose import Exposure
from sequence import SEQ_ABORT, SEQ_IDLE, SEQ_RUNNING, Sequence
from setmode import SetMode

from agccActor import dbRoutinesAGCC

nCams = 6


class Camera(object):
    """Manage up to six FLI USB CCD cameras for the Subaru PFS AG subsystem."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Connect to AG cameras and initialise per-camera worker processes.

        Parameters
        ----------
        config : dict[str, Any]
            Actor configuration dictionary.  Expected keys include
            ``simulator``, ``temperature``, ``cam1``–``cam6`` (serial
            numbers), and optionally ``db.opdb`` and
            ``simulatedImagePath``.
        """

        self.logger = logging.getLogger("agcc")

        try:
            db_params = config["db"]["opdb"]
            self.logger.info(f"Setting default database connection with parameters: {db_params}")
            dbRoutinesAGCC.opdb.OpDB.set_default_connection(**db_params)
        except KeyError:
            self.logger.info("No database configuration for opdb found, using defaults.")

        simulator = config["simulator"]
        self.cams = [None, None, None, None, None, None]
        self.seq_stat = [SEQ_IDLE, SEQ_IDLE, SEQ_IDLE, SEQ_IDLE, SEQ_IDLE, SEQ_IDLE]
        self.seq_count = [0, 0, 0, 0, 0, 0]
        temp = config["temperature"]

        self.logger.info(f"Setting TEC to {temp}.")

        self.temp = temp

        if simulator == 0:
            import fli_camera

            fli_camera.CameraInit()
            self.numberOfCamera = fli_camera.numberOfCamera()
            for n in range(self.numberOfCamera):
                cam = fli_camera.Camera(n)
                cam.open()
                for k in range(nCams):
                    if cam.devsn == config["cam" + str(k + 1)]:
                        self.cams[k] = cam
                        cam.agcid = k
                        cam.setTemperature(temp)
                        cam.regions = ((0, 0, 0), (0, 0, 0))
                        cam.in_queue, cam.out_queue, cam.proc = photometry.createProc()
                        self.logger.info(f"Creating process ID for Cam {cam.agcid + 1} {cam.proc.pid}.")
                        break
        else:
            from fli import fake_camera

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
        """Terminate worker processes and close all open camera devices."""
        for c_i, cam in enumerate(self.cams):
            if cam is not None:
                # close the queue as well
                self.logger.info(f"Closing process ID {cam.proc.pid}.")
                # if cam.proc.is_alive():
                # os.kill(cam.proc.pid, signal.SIGTERM)
                cam.proc.kill()  # Send stop signal to the input queue
                self.logger.info(f"Join the process {cam.proc.pid}.")
                cam.proc.join()

                cam.close()
                self.cams[c_i] = None

    def runningCameras(self) -> list[int]:
        """Return the list of valid (non-``None``) camera indices (0-based)."""

        cams = []
        for n in range(nCams):
            if self.cams[n] is not None:
                cams.append(n)
        return cams

    def reportTEC(self, cmd: Any) -> None:
        """Report TEC temperatures for all connected cameras.

        Parameters
        ----------
        cmd : Any
            Command object for status reporting.
        """
        cmd.inform('text="Number of AG cameras = %d"' % self.numberOfCamera)
        for n in range(nCams):
            if self.cams[n] is not None:
                tempstr = "%5.1f" % self.cams[n].getTemperature()
                cmd.inform(
                    'text="[%d] %s SN=%s status=%s temp=%s"'
                    % (n + 1, self.cams[n].devname, self.cams[n].devsn, self.cams[n].getStatusStr(), tempstr)
                )

    def sendStatusKeys(self, cmd: Any) -> None:
        """Send status keywords for all cameras to the command object.

        Parameters
        ----------
        cmd : Any
            Command object for status reporting.
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
        cmd: Any,
        expTime: float,
        expType: str,
        cams: list[int],
        combined: bool,
        centroid: bool,
        pfsVisitId: int,
        cParms: dict[str, Any],
        cMethod: str,
        iParms: dict[str, Any],
        threadDelay: int | None = None,
        tecOFF: bool = False,
    ) -> None:
        """Validate camera readiness and launch an ``Exposure`` thread.

        Parameters
        ----------
        cmd : Any
            Command object for status reporting.
        expTime : float
            Exposure time in seconds.
        expType : str
            Exposure type: ``'dark'``, ``'object'``, or ``'test'``.
        cams : list[int]
            Requested camera indices (0-based).
        combined : bool
            ``True`` to write a single multi-extension FITS file.
        centroid : bool
            ``True`` to run centroiding after readout.
        pfsVisitId : int
            PFS visit identifier.
        cParms : dict[str, Any]
            Centroid parameters.
        cMethod : str
            Centroid algorithm selector.
        iParms : dict[str, Any]
            Image/instrument parameters.
        threadDelay : int | None, optional
            Millisecond delay between per-camera thread launches.
        tecOFF : bool, optional
            ``True`` to disable the TEC during the exposure.
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

    def abort(self, cmd: Any, cams: list[int]) -> None:
        """Abort current exposures on the specified cameras.

        Parameters
        ----------
        cmd : Any
            Command object for status reporting.
        cams : list[int]
            Camera indices (0-based) to abort.
        """

        for n in cams:
            if self.cams[n] is not None and not self.cams[n].isReady():
                cmd.inform('text="Send abort command to AGC[%d]"' % (n + 1))
                self.cams[n].cancelExposure()

    def setframe(  # noqa: PLR0913
        self, cmd: Any, cams: list[int], bx: int, by: int, cx: int, cy: int, sx: int, sy: int
    ) -> None:
        """Set the imaging area and binning for the specified cameras.

        Parameters
        ----------
        cmd : Any
            Command object for status reporting.
        cams : list[int]
            Camera indices (0-based).
        bx : int
            Horizontal binning factor (0 to leave unchanged).
        by : int
            Vertical binning factor (0 to leave unchanged).
        cx : int
            Left edge of the imaging area in pixels.
        cy : int
            Top edge of the imaging area in pixels.
        sx : int
            Width of the imaging area in pixels.
        sy : int
            Height of the imaging area in pixels.
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

    def openShutter(self, cmd: Any, cams: list[int]) -> None:
        """Open the mechanical shutter on the specified cameras.

        Parameters
        ----------
        cmd : Any
            Command object for status reporting.
        cams : list[int]
            Camera indices (0-based).
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

    def closeShutter(self, cmd: Any, cams: list[int]) -> None:
        """Close the mechanical shutter on the specified cameras.

        Parameters
        ----------
        cmd : Any
            Command object for status reporting.
        cams : list[int]
            Camera indices (0-based).
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

    def resetframe(self, cmd: Any, cams: list[int]) -> None:
        """Reset the imaging area to the full-frame default.

        Parameters
        ----------
        cmd : Any
            Command object for status reporting.
        cams : list[int]
            Camera indices (0-based).
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

    def setmode(self, cmd: Any, mode: int, cams: list[int]) -> None:
        """Set the readout mode for the specified cameras.

        Parameters
        ----------
        cmd : Any
            Command object for status reporting.
        mode : int
            Readout mode index.
        cams : list[int]
            Camera indices (0-based).
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

    def getmode(self, cmd: Any, cams: list[int]) -> None:
        """Query and report the readout mode for the specified cameras.

        Parameters
        ----------
        cmd : Any
            Command object for status reporting.
        cams : list[int]
            Camera indices (0-based).
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

    def getmodestring(self, cmd: Any) -> None:
        """Report the mode strings of the first available ready camera.

        Parameters
        ----------
        cmd : Any
            Command object for status reporting.
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

    def setcamtemperature(self, cmd: Any, cam: int, temp: float) -> None:
        """Set the CCD temperature for an individual camera.

        Parameters
        ----------
        cmd : Any
            Command object for status reporting.
        cam : int
            Camera index (0-based).
        temp : float
            Target CCD temperature in degrees Celsius.
        """
        if self.cams[cam].isReady():
            self.cams[cam].setTemperature(temp)
        else:
            if cmd:
                cmd.warn('text="Camera [%d] is busy"' % cam)

    def settemperature(self, cmd: Any, temp: float) -> None:
        """Set the CCD temperature for all connected cameras.

        Parameters
        ----------
        cmd : Any
            Command object for status reporting.
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

    def setregions(self, cmd: Any, camid: int, regions_str: str) -> None:
        """Set the regions of interest for a camera.

        Parameters
        ----------
        cmd : Any
            Command object for status reporting.
        camid : int
            Camera index (0-based).
        regions_str : str
            Comma-separated region coordinates: either 3 values for one
            region or 6 values for two regions.
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

    def startsequence(
        self,
        cmd: Any,
        seq_id: int,
        expTime: float,
        count: int,
        cams: list[int],
        combined: bool,
        cParms: dict[str, Any],
        iParms: dict[str, Any],
        centroid: bool = False,
    ) -> None:
        """Start a repeated exposure sequence on the specified cameras.

        Parameters
        ----------
        cmd : Any
            Command object for status reporting.
        seq_id : int
            Sequence slot identifier (0-based).
        expTime : float
            Exposure time per frame in seconds.
        count : int
            Total number of frames to acquire.
        cams : list[int]
            Camera indices (0-based).
        combined : bool
            ``True`` to write a single multi-extension FITS per frame.
        cParms : dict[str, Any]
            Centroid parameters.
        iParms : dict[str, Any]
            Image/instrument parameters.
        centroid : bool, optional
            ``True`` to run centroiding after each readout.
        """

        cams_available = []
        for n in cams:
            if self.cams[n] is not None and self.cams[n].isReady():
                cams_available.append(n)
            elif cmd:
                cmd.warn('text="Camera [%d] is not available"' % n)
        if len(cams_available) <= 0:
            if cmd:
                cmd.fail('text="No usable camera"')
            return

        if self.seq_stat[seq_id] != SEQ_IDLE:
            if cmd:
                cmd.fail('text="Sequence ID %d in used"' % (seq_id + 1))
            return
        self.seq_stat[seq_id] = SEQ_RUNNING
        self.seq_count[seq_id] = 0
        expTime_ms = int(expTime * 1000)
        if cmd:
            cmd.inform('inused_seq%d="YES"' % (seq_id + 1))

        active_cams = [self.cams[n] for n in cams_available]
        sequence_thr = Sequence(
            active_cams,
            expTime_ms,
            seq_id,
            count,
            self.seq_stat,
            self.seq_count,
            combined,
            centroid,
            cParms,
            iParms,
            cmd,
        )
        sequence_thr.start()

    def stopsequence(self, cmd: Any, seq_id: int) -> None:
        """Signal the running sequence to stop after the current exposure.

        Parameters
        ----------
        cmd : Any
            Command object for status reporting.
        seq_id : int
            Sequence slot identifier (0-based).
        """

        if self.seq_stat[seq_id] != SEQ_RUNNING:
            if cmd:
                cmd.fail('text="Sequence ID %d not in used"' % (seq_id + 1))
            return
        self.seq_stat[seq_id] = SEQ_ABORT

        if cmd:
            cmd.inform('text="Camera stopsequence [%d] command sent"' % (seq_id + 1))
            cmd.finish()

    def sequence_in_use(self, seq_id: int) -> bool:
        """Return ``True`` if the given sequence slot is active.

        Parameters
        ----------
        seq_id : int
            Sequence slot identifier (0-based).
        """

        if self.seq_stat[seq_id] != SEQ_IDLE:
            return True
        else:
            return False

    def camera_stat(self, cam_id: int) -> str:
        """Return the status string for the given camera.

        Parameters
        ----------
        cam_id : int
            Camera index (0-based).

        Returns
        -------
        str
            Status string from the camera driver.
        """

        return self.cams[cam_id].getStatusStr()
