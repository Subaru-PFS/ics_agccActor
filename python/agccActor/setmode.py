import threading


class SetMode(threading.Thread):
    """Threaded driver that sets the readout mode on several cameras in parallel."""

    def __init__(self, cams, mode: int, cmd=None):
        """Initialise the parallel set-mode driver.

        Parameters
        ----------
        cams : list
            Active camera objects on which to change the readout mode.
        mode : int
            Readout mode value to set on each camera.
        cmd : object, optional
            A tron command object to report to. Ignored if ``None``.
        """
        threading.Thread.__init__(self, daemon=False)
        self.cams = cams
        self.mode = mode
        self.cmd = cmd

    def run(self) -> None:
        """Spawn one thread per camera, call ``setMode`` on each, and join."""
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
