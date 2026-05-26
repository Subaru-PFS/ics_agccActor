import queue
import threading
import time
from typing import TYPE_CHECKING, Union

from agccActor import database, photometry, writeFits

if TYPE_CHECKING:
    from agccActor.fli.fake_camera import Camera as FakeFliCamera
    from agccActor.fli.fli_camera import Camera as FliCamera

    FliCameraType = Union[FliCamera, FakeFliCamera]

# Bound on how long the main thread will wait for a per-camera photometry
# worker to return a result. If exceeded, we assume the worker has crashed
# or hung and proceed without spots for that camera (INSTRM-2920).
PHOTOMETRY_TIMEOUT_S = 20


class Exposure(threading.Thread):
    """Threaded driver for a single multi-camera AGCC exposure.

    One :class:`Exposure` instance is created per ``expose`` command. It
    starts a per-camera worker thread, gathers their results, optionally
    triggers centroiding via the photometry worker processes, and writes
    FITS files plus database records.

    Attributes
    ----------
    exp_lock : threading.Lock
        Class-level lock guarding the global busy counter.
    n_busy : int
        Class-level counter of cameras currently exposing across all
        ``Exposure`` instances.
    """

    exp_lock = threading.Lock()
    n_busy = 0

    def __init__(
        self,
        cams: "list[FliCameraType]",
        expTime_ms,
        dflag,
        cParms,
        iParms,
        visitId,
        cMethod,
        cmd=None,
        combined=False,
        centroid=False,
        seq_id=-1,
        threadDelay=None,
        tecOFF=False,
    ):
        """Initialise the exposure driver.

        Parameters
        ----------
        cams : list
            Active camera objects to expose.
        expTime_ms : int
            Exposure time in milliseconds.
        dflag : bool
            ``True`` for a dark exposure (shutter closed).
        cParms : dict
            Centroiding parameters. The exposure time in seconds is
            inserted into this dict as ``cParms['expTime']``.
        iParms : dict
            Per-camera instrumental parameters.
        visitId : int
            The PFS visit identifier.
        cMethod : str
            Centroiding method (e.g. ``"sep"``).
        cmd : object, optional
            A tron command object to report to. Ignored if ``None``.
        combined : bool, optional
            If ``True`` write a single combined FITS file; otherwise one
            FITS per camera.
        centroid : bool, optional
            If ``True`` run centroiding on each image.
        seq_id : int, optional
            Sequence identifier (``-1`` if not part of a sequence).
        threadDelay : float, optional
            Inter-camera thread start delay in milliseconds.
        tecOFF : bool, optional
            If ``True`` turn the TEC off during the exposure and restore
            it afterwards.

        Notes
        -----
        Updates the ``stat_cam[1-6]`` keywords on the command channel.
        """
        threading.Thread.__init__(self, daemon=False)
        self.cams: "list[FliCameraType]" = cams
        self.expTime_ms = expTime_ms
        self.dflag = dflag
        self.cmd = cmd
        self.combined = combined
        self.centroid = centroid
        self.visitId = visitId
        self.cParms = cParms
        self.iParms = iParms
        self.seq_id = seq_id
        self.cMethod = cMethod

        # update the exposure time in cParms

        self.cParms["expTime"] = expTime_ms / 1000

        self.tecOFFtemp = 20

        if tecOFF is True:
            self.tecOFF = True
        else:
            self.tecOFF = False

        # setting defalut time delay before next exposure thread.
        if threadDelay is None:
            self.timeDelay = 0.0
        else:
            self.timeDelay = threadDelay / 1000

        self.nframe = database.getNextAgcExposureId()
        if self.cmd:
            self.cmd.inform(f'text="Getting agc_exposure_id = {self.nframe} from OpDB"')

        database.writeExposureToDB(self.visitId, self.nframe, expTime_ms / 1000.0)

    def run(self) -> None:
        """Execute the exposure: launch per-camera threads and finalise output."""
        # check if any camera is available
        if len(self.cams) <= 0:
            if self.cmd:
                self.cmd.warn('text="No available cameras"')
                self.cmd.finish()
            return

        with Exposure.exp_lock:
            Exposure.n_busy += len(self.cams)
            if self.cmd:
                self.cmd.inform("agc_exposing=%d" % Exposure.n_busy)

        thrs = []
        for cam in self.cams:
            if self.cmd:
                self.cmd.inform(f'text="Applying time delay of {self.timeDelay} second on Cam {cam.devsn}"')
            time.sleep(self.timeDelay)

            if self.tecOFF is True:
                targetTemp = cam.temp
                if self.cmd:
                    self.cmd.inform(f'text="AGCC sets CCD temp = {targetTemp}"')
                    self.cmd.inform(
                        f'text="Turning off TEC by setting to {self.tecOFFtemp}C on Cam {cam.devsn}"'
                    )
                cam.setTemperature(self.tecOFFtemp)

            thr = threading.Thread(target=self.expose_thr, args=(cam,))
            thr.start()
            thrs.append(thr)
        if self.cmd:
            self.cmd.debug(f'text="done starting {len(thrs)} exposure threads"')

        for thr in thrs:
            thr.join()
        if self.cmd:
            self.cmd.debug('text="done joining exposure threads"')

        with Exposure.exp_lock:
            Exposure.n_busy -= len(self.cams)
            if self.cmd:
                self.cmd.inform("agc_exposing=%d" % Exposure.n_busy)
                self.cmd.inform("agc_frameid=%d" % self.nframe)

        if self.combined and self.cams[0].getTotalTime() > 0:
            writeFits.wfits_combined(self.cmd, self.visitId, self.cams, self.nframe, self.seq_id)

        if self.tecOFF is True:
            for cam in self.cams:
                if self.cmd:
                    self.cmd.inform(f'text="Turning on TEC to {cam.temp}C"')
                cam.setTemperature(cam.temp)

        if self.cmd and self.seq_id < 0:
            self.cmd.finish()

    def expose_thr(self, cam: "FliCameraType", multiproc: bool = True) -> None:
        """Run the exposure and post-processing for a single camera.

        Sets the exposure time, triggers the exposure, retrieves the image,
        optionally runs centroiding (in-process or via the per-camera
        multiprocessing worker), writes a per-camera FITS file when not in
        combined mode, and writes centroids to the database.

        Parameters
        ----------
        cam : object
            The camera object to drive.
        multiproc : bool, optional
            If ``True`` dispatch centroiding to the per-camera photometry
            worker process; otherwise run it inline.
        """
        cam_id = cam.agcid + 1
        if self.cmd:
            self.cmd.inform(f"agc{cam_id:d}_stat=BUSY")

        try:
            cam.setExpTime(self.expTime_ms)
        except Exception as e:
            if self.cmd:
                self.cmd.warn(f'text="AGC[{cam_id}]: set exposure time error: {e}"')
            return

        try:
            cam.expose(dark=self.dflag)
        except Exception as e:
            if self.cmd:
                self.cmd.warn(f'text="AGC[{cam_id}]: exposure error: {e}"')
            return

        try:
            tread = cam.getTotalTime()
        except Exception as e:
            if self.cmd:
                self.cmd.warn(f'text="AGC[{cam_id}]: readout error in getTotalTime: {e}"')
            return

        if self.cmd:
            if tread > 0:
                self.cmd.inform(f'text="AGC[{cam_id:d}]: Retrieve camera data in {tread:.2f}s"')
            else:
                self.cmd.inform(f'text="AGC[{cam_id:d}]: Exposure aborted"')
            self.cmd.inform(f"agc{cam_id:d}_stat=READY")

        spots = None
        if tread > 0:
            if self.centroid:
                if multiproc:
                    cam.in_queue.put(cam.data)
                    cam.in_queue.put(cam.agcid)
                    cam.in_queue.put(self.cParms)
                    cam.in_queue.put(self.iParms)
                    cam.in_queue.put(self.cMethod)
                    try:
                        spots = cam.out_queue.get(timeout=PHOTOMETRY_TIMEOUT_S)
                    except queue.Empty:
                        if self.cmd:
                            self.cmd.warn(
                                f'text="AGC[{cam_id}]: photometry worker did not respond '
                                f'within {PHOTOMETRY_TIMEOUT_S}s -- worker may have crashed"'
                            )
                        spots = None
                    except Exception as e:
                        if self.cmd:
                            self.cmd.warn(
                                f'text="AGC[{cam_id}]: photometry multiprocessing error with photometry: {e}"'
                            )
                        spots = None
                else:
                    try:
                        spots = photometry.measure(
                            cam.data, cam.agcid, self.cParms, self.iParms, self.cMethod
                        )
                    except Exception as e:
                        if self.cmd:
                            self.cmd.warn(f'text="AGC[{cam_id}]: photometry error: {e}"')
                        spots = None

                cam.spots = spots

                # Writing to database when spot number is larger than zero
                if spots is not None and len(spots) > 0:
                    if self.cmd:
                        self.cmd.inform(f'text="AGC[{cam_id:d}]: find {len(spots):d} objects"')
                        self.cmd.inform(f'text="AGC[{cam_id:d}]: wrote centroids to database"')
                        aa = spots["estimated_magnitude"]
                        self.cmd.inform(f'text="AGC[{cam_id:d}]: estimated mags = {aa}"')

                    database.writeCentroidsToDB(spots, self.visitId, self.nframe, cam.agcid)
                else:
                    self.cmd.inform(f'text="AGC[{cam_id:d}]: found no objects, skipping DB writing"')
            else:
                cam.spots = spots

            if not self.combined:
                writeFits.wfits(self.cmd, self.visitId, cam, self.nframe)
