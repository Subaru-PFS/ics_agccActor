"""Timed sequence of repeated exposures for AGCC."""

from __future__ import annotations

import threading
from typing import Any

from expose import Exposure

SEQ_IDLE = 0
SEQ_RUNNING = 1
SEQ_ABORT = 2


class Sequence(threading.Thread):
    """Execute a counted sequence of exposures on a group of cameras."""

    def __init__(
        self,
        cams: list[Any],
        expTime_ms: int,
        seq_id: int,
        count: int,
        seq_stat: list[int],
        seq_count: list[int],
        combined: bool,
        centroid: bool,
        cParms: dict[str, Any],
        iParms: dict[str, Any],
        cmd: Any | None = None,
    ) -> None:
        """Initialize a sequence thread.

        Parameters
        ----------
        cams : list[Any]
            Active camera objects.
        expTime_ms : int
            Exposure time in milliseconds.
        seq_id : int
            Sequence identifier (0-based).
        count : int
            Total number of exposures to take.
        seq_stat : list[int]
            Shared sequence-status array (one entry per slot).
        seq_count : list[int]
            Shared exposure-count array (one entry per slot).
        combined : bool
            ``True`` to write a single multi-extension FITS file per exposure.
        centroid : bool
            ``True`` to run centroiding after each readout.
        cParms : dict[str, Any]
            Centroid parameters forwarded to each ``Exposure``.
        iParms : dict[str, Any]
            Image/instrument parameters forwarded to each ``Exposure``.
        cmd : Any, optional
            Command object for status reporting.
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
        self.cParms = cParms
        self.iParms = iParms
        self.cmd = cmd

    def run(self) -> None:
        """Run exposures until the count is reached or the sequence is aborted.

        Calls ``cmd.finish()`` when the sequence ends (whether completed or
        aborted).
        """
        # check if any camera is available
        if len(self.cams) <= 0:
            if self.cmd:
                self.cmd.warn('text="No available cameras"')
                self.cmd.finish()
            return

        while self.seq_stat[self.seq_id] == SEQ_RUNNING and self.seq_count[self.seq_id] < self.count:
            exp_thr = Exposure(
                self.cams,
                self.expTime_ms,
                False,
                self.cParms,
                self.iParms,
                visitId=self.seq_id,
                cMethod="sep",
                cmd=self.cmd,
                combined=self.combined,
            )
            exp_thr.start()
            exp_thr.join()

            self.seq_count[self.seq_id] += 1
            if self.cmd:
                self.cmd.inform(
                    'text="Sequence [%d] count [%d] done"' % (self.seq_id + 1, self.seq_count[self.seq_id])
                )

        self.seq_stat[self.seq_id] = SEQ_IDLE
        if self.cmd:
            self.cmd.inform('inused_seq%d="NO"' % (self.seq_id + 1))
            if self.seq_count[self.seq_id] >= self.count:
                self.cmd.inform('text="Sequence [%d] finished"' % (self.seq_id + 1))
            else:
                self.cmd.inform('text="Sequence [%d] aborted"' % (self.seq_id + 1))
            self.cmd.finish()
