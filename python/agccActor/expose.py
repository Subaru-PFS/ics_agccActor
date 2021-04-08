import threading
import writeFits

class Exposure(threading.Thread):
    def __init__(self, cams, expTime_ms, dflag, cmd=None, combined=False, seq_id=-1):
        """ Run exposure command

        Args:
           cams        - list of active cameras
           expTime_ms  - the exposure time in ms
           dflag       - true for dark exposure
           cmd         - a Command object to report to. Ignored if None.
           combined    - Multiple FITS files/Single FITS file
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
        self.seq_id = seq_id

    def run(self):
        # check if any camera is available
        if len(self.cams) <= 0:
            if self.cmd:
                self.cmd.warn('text="No available cameras"')
                self.cmd.finish()
            return

        thrs = []
        for cam in self.cams:
            thr = threading.Thread(target=self.expose_thr, args=(cam,))
            thr.start()
            thrs.append(thr)

        for thr in thrs:
            thr.join()

        if self.combined and self.cams[0].tend > 0:
            writeFits.wfits_combined(self.cmd, self.cams, self.seq_id)
        if self.cmd and self.seq_id < 0:
            self.cmd.finish()

    def expose_thr(self, cam):
        """ Concurrent exposure thread for camera readouts """
        n = cam.agcid
        if self.cmd:
            self.cmd.inform('stat_cam%d="BUSY"' % (n + 1))

        cam.setExpTime(self.expTime_ms)
        cam.expose(dark=self.dflag)

        if self.cmd:
            if cam.tend > 0:
                tread = cam.tend - cam.tstart
                self.cmd.inform('text="AGC[%d]: Retrieve camera data in %.2fs"' % (n + 1, tread))
            else:
                self.cmd.inform('text="AGC[%d]: Exposure aborted"' % (n + 1))
            self.cmd.inform('stat_cam%d="READY"' % (n + 1))

        if cam.tend > 0 and not self.combined:
            writeFits.wfits(self.cmd, cam)
