"""Photometry worker helpers for AGCC centroid processing."""

from __future__ import annotations

import multiprocessing as mp
from typing import Any

import numpy as np

from agccActor import centroidTools as ct

# Structured dtype used by centroidTools/getCentroidsSep return values.
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


def measure(
    data: np.ndarray,
    agcid: int,
    cParms: dict[str, Any],
    iParms: dict[str, Any],
    cMethod: str,
    thresh: int = 10,
) -> np.ndarray:
    """Measure spot centroids for one camera frame.

    Parameters
    ----------
    data : numpy.ndarray
        Image array from the camera.
    agcid : int
        Zero-based AG camera identifier.
    cParms : dict[str, Any]
        Centroid parameters.
    iParms : dict[str, Any]
        Image/instrument parameters.
    cMethod : str
        Centroid algorithm selector.
    thresh : int, optional
        Compatibility argument retained by legacy callers.

    Returns
    -------
    numpy.ndarray
        Structured centroid table.
    """

    if cMethod == "sep":
        result = ct.getCentroidsSep(data, iParms, cParms, spotDtype, agcid)
    else:
        raise ValueError(f"Unsupported centroiding method: {cMethod}")

    return result


def createProc() -> tuple[mp.Queue, mp.Queue, mp.Process]:
    """Create a background process for centroiding work.

    Returns
    -------
    tuple[multiprocessing.Queue, multiprocessing.Queue, multiprocessing.Process]
        Input queue, output queue, and worker process.
    """

    def worker(in_q: mp.Queue, out_q: mp.Queue) -> None:
        """Process queue items and return photometry results."""
        while True:
            data = in_q.get()
            agcid = in_q.get()
            cParms = in_q.get()
            iParms = in_q.get()
            cMethod = in_q.get()

            result = measure(data, agcid, cParms, iParms, cMethod)

            out_q.put(result)

    in_q = mp.Queue()
    out_q = mp.Queue()

    p = mp.Process(target=worker, args=(in_q, out_q), daemon=True)
    p.start()
    return in_q, out_q, p
