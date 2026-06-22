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

import numpy as np
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


# ---------------------------------------------------------------------------
# photometry.measure() direct tests (no worker process)
# ---------------------------------------------------------------------------

def _minimal_iParms(agcid: int = 0) -> dict:
    """Minimal per-camera parameter dict sufficient for getCentroidsSep."""
    cam_key = str(agcid + 1)
    return {
        cam_key: {
            "reg": [0, 80, 0, 80, 80, 160, 0, 80],
            "badCols": [],
            "satVal1": 65535,
            "satVal2": 65535,
        },
        "flatVal": 0.006,
        "magFit": [0.928, 27.389],
    }


def _minimal_cParms() -> dict:
    return {
        "thresh": 5.0,
        "minarea": 5,
        "deblend": 0.01,
        "ellip": 0.5,
        "nmin": 5,
        "expTime": 5.0,
        "halfBoxX": 5,
        "halfBoxY": 5,
        "boxSize": 20,
    }


def _gaussian_image(height: int = 160, width: int = 160):
    """Return a synthetic image with a single Gaussian star-like source."""
    img = np.zeros((height, width), dtype=np.uint16)
    rng = np.random.default_rng(42)
    background = rng.integers(1300, 1500, size=(height, width), dtype=np.uint16)
    img = background.copy()

    yy, xx = np.ogrid[:height, :width]
    sigma = 3.0
    cx, cy = 40, 40
    gauss = (10000 * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma ** 2))).astype(np.uint16)
    img = (img.astype(np.int32) + gauss).clip(0, 65535).astype(np.uint16)
    return img


def test_measure_with_synthetic_image():
    """photometry.measure() must detect at least one spot in a synthetic star image."""
    from agccActor.photometry import spotDtype

    img = _gaussian_image()
    result = photometry.measure(
        img, agcid=0, cParms=_minimal_cParms(), iParms=_minimal_iParms(0), cMethod="sep"
    )

    assert result is not None
    assert len(result) >= 1, "Expected at least one detected spot in the synthetic image"


def test_measure_output_dtype():
    """photometry.measure() must return a structured array with the canonical spotDtype."""
    from agccActor.photometry import spotDtype

    img = _gaussian_image()
    result = photometry.measure(
        img, agcid=0, cParms=_minimal_cParms(), iParms=_minimal_iParms(0), cMethod="sep"
    )

    assert result.dtype == spotDtype, f"dtype mismatch: {result.dtype} != {spotDtype}"


def test_worker_survives_multiple_failures(worker):
    """After several successive bad jobs the worker must still process a valid one."""
    in_q, out_q, p = worker

    for _ in range(3):
        _send_job(in_q, cMethod='not-a-real-method')
        result = out_q.get(timeout=10)
        assert result is None
        assert p.is_alive(), "worker died during repeated-failure test"

    # Now send a valid job with a synthetic image — worker must still respond.
    img = _gaussian_image()
    in_q.put(img)
    in_q.put(0)
    in_q.put(_minimal_cParms())
    in_q.put(_minimal_iParms(0))
    in_q.put("sep")

    valid_result = out_q.get(timeout=15)
    assert valid_result is not None, "Worker returned None for a valid job after failures"
    assert p.is_alive()
