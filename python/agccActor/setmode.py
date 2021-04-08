import threading

class SetMode(threading.Thread):
    def __init__(self, cams, mode, cmd=None):
        """ Run exposure command

        Args:
           cams        - list of active cameras
           mode        - readout mode
           cmd         - a Command object to report to. Ignored if None.

        Returns:
           - NULL

        Keys:
           stat_cam[1-6]
        """
        threading.Thread.__init__(self, daemon=False)
        self.cams = cams
        self.mode = mode
        self.cmd = cmd

    def run(self):
        # check if any camera is available
        if len(self.cams) <= 0:
            if self.cmd:
                self.cmd.warn('text="No available cameras"')
                self.cmd.finish()
            return

        thrs = []
        for cam in self.cams:
            thr = threading.Thread(target=cam.setMode, args=(self.mode,))
            thr.start()
            thrs.append(thr)
            if self.cmd:
                self.cmd.inform('text="Send setmode(%d) command to AGC[%d]"' % (self.mode, cam.agcid + 1))

        for thr in thrs:
            thr.join()
        if self.cmd:
            self.cmd.inform('text="Camera setmode command done"')
            self.cmd.finish()
