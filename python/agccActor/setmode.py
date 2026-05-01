"""Threaded helper for camera mode changes."""

from __future__ import annotations

import threading
from typing import Any


class SetMode(threading.Thread):
    """Set readout mode for a group of cameras in parallel."""

    def __init__(self, cams: list[Any], mode: int, cmd: Any | None = None) -> None:
        """Initialize a setmode worker thread.

        Parameters
        ----------
        cams : list[Any]
            Active camera objects.
        mode : int
            Readout mode to apply.
        cmd : Any, optional
            Command object for status reporting.
        """
        threading.Thread.__init__(self, daemon=False)
        self.cams = cams
        self.mode = mode
        self.cmd = cmd

    def run(self) -> None:
        """Execute mode changes for all selected cameras."""
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
