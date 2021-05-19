import multiprocessing
import threading
import writeFits
import photometry
import os

class Exposure(threading.Thread):
    exp_lock = threading.Lock()
    n_busy = 0

    def __init__(self, cams, expTime_ms, dflag, cmd=None, combined=False, centroid=False, seq_id=-1):
        """ Run exposure command

        Args:
           cams        - list of active cameras
           expTime_ms  - the exposure time in ms
           dflag       - true for dark exposure
           cmd         - a Command object to report to. Ignored if None.
           combined    - Multiple FITS files/Single FITS file
           centroid    - True if do centroid else don't
           seq_id      - Sequence id

        Returns:
           - NULL

        Keys:
           stat_cam[1-6]
        """
        threading.Thread.__init__(self, daemon=False)
        self.cams = cams
        self.expTime_ms = expTime_ms
        self.dflag = dflag
        self.cmd = cmd
        self.combined = combined
        self.centroid = centroid
        self.seq_id = seq_id

        # get nframe keyword, unique for each exposure
        path = os.path.join("$ICS_MHS_DATA_ROOT", 'agcc')
        path = os.path.expandvars(os.path.expanduser(path))
        if not os.path.isdir(path):
            os.makedirs(path, 0o755)
        filename = os.path.join(path, 'nframe.txt')

        with Exposure.exp_lock:
            if os.path.isfile(filename):
                with open(filename, 'r') as f:
                    self.nframe = int(f.read()) + 1
            else:
                self.nframe = 1
            with open(filename, 'w') as f:
                f.write(str(self.nframe))

    def run(self):
        # check if any camera is available
        if len(self.cams) <= 0:
            if self.cmd:
                self.cmd.warn('text="No available cameras"')
                self.cmd.finish()
            return

        with Exposure.exp_lock:
            Exposure.n_busy += len(self.cams)
            if self.cmd:
                self.cmd.inform('agc_exposing=%d' % Exposure.n_busy)

        thrs = []
        for cam in self.cams:
            thr = threading.Thread(target=self.expose_thr, args=(cam,))
            thr.start()
            thrs.append(thr)

        for thr in thrs:
            thr.join()

        with Exposure.exp_lock:
            Exposure.n_busy -= len(self.cams)
            if self.cmd:
                self.cmd.inform('agc_exposing=%d' % Exposure.n_busy)
                self.cmd.inform('agc_frameid=%d' % self.nframe)

        if self.combined and self.cams[0].getTotalTime() > 0:
            writeFits.wfits_combined(self.cmd, self.cams, self.nframe, self.seq_id)
        if self.cmd and self.seq_id < 0:
            self.cmd.finish()

    def expose_thr(self, cam, multiproc=True):
        """ Concurrent exposure thread for camera readouts """
        n = cam.agcid
        if self.cmd:
            self.cmd.inform('agc%d_stat=1' % (n + 1))

        cam.setExpTime(self.expTime_ms)
        cam.expose(dark=self.dflag)

        tread = cam.getTotalTime()
        if self.cmd:
            if tread > 0:
                self.cmd.inform('text="AGC[%d]: Retrieve camera data in %.2fs"' % (n + 1, tread))
            else:
                self.cmd.inform('text="AGC[%d]: Exposure aborted"' % (n + 1))
            self.cmd.inform('agc%d_stat=0' % (n + 1))

        if tread > 0:
            if self.centroid:
                if multiproc:
                    cam.queue[0].put(cam.data)
                    spots = cam.queue[1].get()
                else:
                    spots = photometry.measure(cam.data)
                cam.spots = spots
                if self.cmd:
                    self.cmd.inform('text="AGC[%d]: find %d objects"' % (n + 1, len(spots)))
            else:
                cam.spots = None
            if not self.combined:
                writeFits.wfits(self.cmd, cam, self.nframe)
