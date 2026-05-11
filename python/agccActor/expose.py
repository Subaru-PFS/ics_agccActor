"""Concurrent multi-camera exposure thread for AGCC."""

from __future__ import annotations

import queue
import threading
import time
from typing import Any

from agccActor import dbRoutinesAGCC, photometry, writeFits

# Bound on how long the main thread will wait for a per-camera photometry
# worker to return a result. If exceeded, we assume the worker has crashed
# or hung and proceed without spots for that camera (INSTRM-2920).
PHOTOMETRY_TIMEOUT_S = 20


class Exposure(threading.Thread):
    """Run a concurrent multi-camera exposure and optional centroiding.

    Class-level attributes ``exp_lock`` and ``n_busy`` are intentionally
    shared across all instances to provide a global exposure counter.
    """

    exp_lock = threading.Lock()
    n_busy = 0

    def __init__(
        self,
        cams: list[Any],
        expTime_ms: int,
        dflag: bool,
        cParms: dict[str, Any],
        iParms: dict[str, Any],
        visitId: int,
        cMethod: str,
        cmd: Any,
        combined: bool = False,
        centroid: bool = False,
        seq_id: int = -1,
        threadDelay: int | None = None,
        tecOFF: bool = False,
    ) -> None:
        """Initialize an exposure thread.

        Parameters
        ----------
        cams : list[Any]
            Active camera objects.
        expTime_ms : int
            Exposure time in milliseconds.
        dflag : bool
            ``True`` for a dark exposure.
        cParms : dict[str, Any]
            Centroid parameters.
        iParms : dict[str, Any]
            Image/instrument parameters.
        visitId : int
            PFS visit identifier.
        cMethod : str
            Centroid algorithm selector (e.g. ``'sep'``).
        cmd : Any
            Command object for status reporting.
        combined : bool, optional
            ``True`` to write a single multi-extension FITS file.
        centroid : bool, optional
            ``True`` to run centroiding after readout.
        seq_id : int, optional
            Sequence identifier; ``-1`` if not part of a sequence.
        threadDelay : int | None, optional
            Delay in milliseconds applied between per-camera thread launches.
        tecOFF : bool, optional
            ``True`` to disable the TEC during the exposure.
        """
        threading.Thread.__init__(self, daemon=False)
        self.cams = cams
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

        self.nframe = dbRoutinesAGCC.getNextAgcExposureId()
        self.cmd.inform(f'text="Writing agc_exposure_id = {self.nframe} from OpDB"')
        dbRoutinesAGCC.writeExposureToDB(self.visitId, self.nframe, expTime_ms / 1000.0)

    def run(self) -> None:
        """Execute exposure threads and write results.

        Starts one per-camera thread, waits for all to complete, then
        writes the combined FITS file when requested.  Calls
        ``cmd.finish()`` on completion unless running inside a sequence.
        """
        # check if any camera is available
        if len(self.cams) <= 0:
            self.cmd.warn('text="No available cameras"')
            self.cmd.finish()
            return

        with Exposure.exp_lock:
            Exposure.n_busy += len(self.cams)
            self.cmd.inform("agc_exposing=%d" % Exposure.n_busy)

        thrs = []
        for cam in self.cams:
            self.cmd.inform(f'text="Applying time delay of {self.timeDelay} second on Cam {cam.devsn}"')
            time.sleep(self.timeDelay)

            if self.tecOFF is True:
                targetTemp = cam.temp
                self.cmd.inform(f'text="AGCC sets CCD temp = {targetTemp}"')

                self.cmd.inform(f'text="Turing off TEC by setting to {self.tecOFFtemp}C on Cam {cam.devsn}"')
                cam.setTemperature(self.tecOFFtemp)

            thr = threading.Thread(target=self.expose_thr, args=(cam,))
            thr.start()
            thrs.append(thr)
        self.cmd.debug(f'text="done starting {len(thrs)} exposure threads"')

        for thr in thrs:
            thr.join()
        self.cmd.debug('text="done joining exposure threads"')

        with Exposure.exp_lock:
            Exposure.n_busy -= len(self.cams)
            self.cmd.inform("agc_exposing=%d" % Exposure.n_busy)
            self.cmd.inform("agc_frameid=%d" % self.nframe)

        if self.combined and self.cams[0].getTotalTime() > 0:
            writeFits.wfits_combined(self.cmd, self.visitId, self.cams, self.nframe, self.seq_id)

        if self.tecOFF is True:
            """
                Turning TEC on!
            """
            for cam in self.cams:
                self.cmd.inform(f'text="Turing on TEC to {targetTemp}C"')
                cam.setTemperature(targetTemp)

        if self.seq_id < 0:
            self.cmd.finish()

    def expose_thr(self, cam: Any, multiproc: bool = True) -> None:
        """Run a single-camera exposure in a dedicated thread.

        Performs exposure, optional centroiding via a multiprocessing queue
        or direct call, database centroid write, and per-camera FITS write.

        Parameters
        ----------
        cam : Any
            Camera object (``fli_camera.Camera`` or ``fake_camera.Camera``).
        multiproc : bool, optional
            ``True`` to dispatch centroiding to the pre-spawned worker
            process; ``False`` to run in the calling thread.
        """
        cam_id = cam.agcid + 1
        self.cmd.inform(f"agc{cam_id:d}_stat=BUSY")

        try:
            cam.setExpTime(self.expTime_ms)
        except Exception as e:
            self.cmd.warn(f'text="AGC[{cam_id}]: set exposure time error: {e}"')
            return

        try:
            cam.expose(dark=self.dflag)
        except Exception as e:
            self.cmd.warn(f'text="AGC[{cam_id}]: exposure error: {e}"')
            return

        try:
            tread = cam.getTotalTime()
        except Exception as e:
            self.cmd.warn(f'text="AGC[{cam_id}]: readout error in getTotalTime: {e}"')
            return

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
                        self.cmd.warn(
                            f'text="AGC[{cam_id}]: photometry worker did not respond within '
                            f'{PHOTOMETRY_TIMEOUT_S}s -- worker may have crashed"'
                        )
                        spots = None
                    except Exception as e:
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
                        self.cmd.warn(f'text="AGC[{cam_id}]: photometry error: {e}"')
                        spots = None

                cam.spots = spots

                # Writing to database when spot number is larger than zero
                if spots is not None and len(spots) > 0:
                    self.cmd.inform(f'text="AGC[{cam_id:d}]: find {len(spots):d} objects"')
                    self.cmd.inform(f'text="AGC[{cam_id:d}]: wrote centroids to database"')
                    aa = spots["estimated_magnitude"]
                    self.cmd.inform(f'text="AGC[{cam_id:d}]: estimated mags = {aa}"')
                    dbRoutinesAGCC.writeCentroidsToDB(spots, self.visitId, self.nframe, cam.agcid)
                else:
                    self.cmd.inform(f'text="AGC[{cam_id:d}]: found no objects, skipping DB writing"')
            else:
                cam.spots = spots

            if not self.combined:
                writeFits.wfits(self.cmd, self.visitId, cam, self.nframe)
