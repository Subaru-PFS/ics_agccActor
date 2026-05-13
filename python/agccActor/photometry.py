import logging
import multiprocessing as mp

import numpy as np

from agccActor import centroid

spotDtype = np.dtype(
    dict(
        names=[
            "image_moment_00_pix",
            "centroid_x_pix",
            "centroid_y_pix",
            "central_image_moment_20_pix",
            "central_image_moment_11_pix",
            "central_image_moment_02_pix",
            "peak_pixel_x_pix",
            "peak_pixel_y_pix",
            "peak_intensity",
            "background",
            "estimated_magnitude",
            "flags",
        ],
        formats=["f4", "f4", "f4", "f4", "f4", "f4", "i2", "i2", "f4", "f4", "f4", "i2"],
    )
)


def measure(data, agcid: int, cParms: dict, iParms: dict, cMethod: str, thresh: float = 10):
    """Measure centroid positions for one camera image.

    Parameters
    ----------
    data : numpy.ndarray
        2-D raw image array from the camera.
    agcid : int
        Zero-based AG camera identifier.
    cParms : dict
        Centroiding parameters.
    iParms : dict
        Per-camera instrumental parameters.
    cMethod : str
        Centroiding method; currently only ``"sep"`` is supported.
    thresh : float, optional
        Detection threshold; presently unused (taken from ``cParms``).

    Returns
    -------
    numpy.ndarray
        Structured array of detected spots, as produced by
        :func:`agccActor.centroid.getCentroidsSep`.
    """

    if cMethod == "sep":
        result = centroid.getCentroidsSep(data, iParms, cParms, spotDtype, agcid)

    return result


def createProc():
    """Create and start a photometry worker process for one camera.

    The worker pulls ``(data, agcid, cParms, iParms, cMethod)`` tuples
    from its input queue, runs :func:`measure` on each, and pushes the
    result (or ``None`` on failure) onto its output queue.

    Returns
    -------
    in_q : multiprocessing.Queue
        Queue to push exposure inputs to.
    out_q : multiprocessing.Queue
        Queue from which to retrieve centroid results.
    p : multiprocessing.Process
        The started, daemonised worker process.
    """

    def worker(in_q, out_q) -> None:
        """Worker loop: consume input queue, run :func:`measure`, post result."""
        logger = logging.getLogger("agcc")
        while True:
            data = in_q.get()
            agcid = in_q.get()
            cParms = in_q.get()
            iParms = in_q.get()
            cMethod = in_q.get()

            try:
                result = measure(data, agcid, cParms, iParms, cMethod)
            except Exception as e:
                # Never let the worker die silently: log, return None so the
                # consumer's bounded .get() always sees a value (INSTRM-2920).
                logger.exception(f"AGC[{agcid + 1}]: photometry.measure failed: {e}")
                result = None

            out_q.put(result)

    in_q = mp.Queue()
    out_q = mp.Queue()

    p = mp.Process(target=worker, args=(in_q, out_q), daemon=True)
    p.start()
    return in_q, out_q, p
