import threading
from expose import Exposure

SEQ_IDLE = 0
SEQ_RUNNING = 1
SEQ_ABORT = 2

class Sequence(threading.Thread):
    def __init__(self, cams, expTime_ms, seq_id, count, seq_stat, seq_count, combined, centroid, cParms, iParms, cmd=None):
        """ Run exposure command

        Args:
           cams        - list of active cameras
           expTime_ms  - exposure time
           seq_id      - Sequence ID
           count       - number of exposures
           seq_stat    - seq_stat in Camera class
           seq_count   - seq_count in Camera class
           combined    - True if Multiple FITS files else Single FITS file
           centroid    - True if do centroid else don't
           cmd         - a Command object to report to. Ignored if None.

        Returns:
           - NULL

        Keys:
           stat_cam[1-6]
        """
        threading.Thread.__init__(self, daemon=False)
        self.cams = cams
        self.expTime_ms = expTime_ms
        self.seq_id = seq_id
        self.count = count
        self.seq_stat = seq_stat
        self.seq_count = seq_count
        self.combined = combined
        self.centroid = centroid
        self.cmd = cmd

    def run(self):
        # check if any camera is available
        if len(self.cams) <= 0:
            if self.cmd:
                self.cmd.warn('text="No available cameras"')
                self.cmd.finish()
            return

        while self.seq_stat[self.seq_id] == SEQ_RUNNING and self.seq_count[self.seq_id] < self.count:
            exp_thr = Exposure(self.cams, self.expTime_ms, False, cParms, iParms, self.cmd, self.combined, self.centroid, self.seq_id)
            exp_thr.start()
            exp_thr.join()

            self.seq_count[self.seq_id] += 1
            if self.cmd:
                self.cmd.inform('text="Sequence [%d] count [%d] done"' % \
                                (self.seq_id + 1, self.seq_count[self.seq_id]))

        self.seq_stat[self.seq_id] = SEQ_IDLE
        if self.cmd:
            self.cmd.inform('inused_seq%d="NO"' % (self.seq_id + 1))
            if self.seq_count[self.seq_id] >= self.count:
                self.cmd.inform('text="Sequence [%d] finished"' % (self.seq_id + 1))
            else:
                self.cmd.inform('text="Sequence [%d] aborted"' % (self.seq_id + 1))
            self.cmd.finish()
