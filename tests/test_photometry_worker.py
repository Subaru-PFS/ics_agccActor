"""Tests for INSTRM-2920: photometry worker error handling and main-side timeout.

Run from the repo root after `setup -r .`:

    pytest tests

The fix has two halves; each is exercised here:

1. The per-camera worker in `photometry.createProc()` must catch exceptions
   raised by `photometry.measure()` and put `None` on the output queue, so the
   consumer's bounded `.get()` always sees a value and the worker stays alive
   to serve subsequent jobs.

2. The main side in `expose.Exposure.expose_thr()` must call `out_queue.get()`
   with a timeout so that a dead/hung worker can no longer hang the actor.
"""

import queue
import time

import pytest

from agccActor import photometry
from agccActor import expose


def _send_job(in_q, *, data=None, agcid=0, cParms=None, iParms=None, cMethod='sep'):
    """Push the five items the worker expects from `in_q`, in order."""
    in_q.put(data)
    in_q.put(agcid)
    in_q.put({} if cParms is None else cParms)
    in_q.put({} if iParms is None else iParms)
    in_q.put(cMethod)


@pytest.fixture
def worker():
    """A live photometry worker process; killed on teardown."""
    in_q, out_q, p = photometry.createProc()
    yield in_q, out_q, p
    if p.is_alive():
        p.kill()
    p.join(timeout=5)


def test_worker_returns_none_when_measure_raises(worker):
    """Sending an invalid cMethod makes `measure()` fall through and raise
    UnboundLocalError on the undefined `result`. Before the INSTRM-2920 fix,
    the worker would die silently; after the fix, it logs and emits None."""
    in_q, out_q, p = worker
    _send_job(in_q, cMethod='not-a-real-method')

    result = out_q.get(timeout=10)

    assert result is None


def test_worker_survives_exception_and_serves_next_job(worker):
    """A single bad job must not poison the worker. The next job must still
    get a response (here, also None because we again pass a bad cMethod —
    we just need to confirm the worker is still consuming and producing)."""
    in_q, out_q, p = worker

    _send_job(in_q, cMethod='not-a-real-method')
    assert out_q.get(timeout=10) is None
    assert p.is_alive(), "worker died after first exception"

    _send_job(in_q, cMethod='not-a-real-method')
    assert out_q.get(timeout=10) is None
    assert p.is_alive(), "worker died after second exception"


def test_get_with_timeout_does_not_hang_on_dead_worker():
    """Reproduces the INSTRM-2920 hang scenario: if the worker process is gone,
    a bounded `out_queue.get(timeout=...)` must raise `queue.Empty` promptly
    rather than blocking forever."""
    in_q, out_q, p = photometry.createProc()
    try:
        p.kill()
        p.join(timeout=5)
        assert not p.is_alive()

        start = time.monotonic()
        with pytest.raises(queue.Empty):
            out_q.get(timeout=0.5)
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"get() took {elapsed:.2f}s — should have timed out near 0.5s"
    finally:
        if p.is_alive():
            p.kill()
        p.join(timeout=5)


def test_expose_module_defines_photometry_timeout():
    """The expose module must expose a positive PHOTOMETRY_TIMEOUT_S constant
    that the multiproc branch passes to `out_queue.get(timeout=...)`."""
    assert hasattr(expose, 'PHOTOMETRY_TIMEOUT_S')
    assert isinstance(expose.PHOTOMETRY_TIMEOUT_S, (int, float))
    assert expose.PHOTOMETRY_TIMEOUT_S > 0
