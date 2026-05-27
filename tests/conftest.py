"""Pytest configuration for the agccActor test suite.

Run from the repo root:

    uv run pytest tests

Environment
-----------
PFS_INSTDATA_DIR
    Must point to a ``pfs_instdata`` product checkout for tests that exercise
    ``centroid.py`` (which reads ``agcc.yaml`` from that directory).  Tests that
    need this env var are marked ``real_data`` and skip automatically when the
    variable or the run28 data directory is absent.

    If the variable is not exported, conftest will attempt to auto-discover it
    from a sibling ``pfs_instdata`` directory in common project layouts:
    ``<repo_root>/../pfs_instdata`` and ``<repo_root>/../../pfs_instdata``.
"""

import enum
import multiprocessing as mp
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Fork-safe multiprocessing
# macOS defaults to "spawn"; the photometry worker closure cannot be pickled
# under spawn, mirroring the Linux production environment where "fork" is
# the default.  force=True is a no-op on Linux.
# ---------------------------------------------------------------------------
try:
    mp.set_start_method("fork", force=True)
except RuntimeError:
    pass


# ---------------------------------------------------------------------------
# Auto-discover PFS_INSTDATA_DIR when not set
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent

def _autodiscover_instdata() -> None:
    """Set PFS_INSTDATA_DIR if absent but discoverable from standard project layouts."""
    if os.environ.get("PFS_INSTDATA_DIR"):
        return
    candidates = [
        _REPO_ROOT.parent / "pfs_instdata",           # sibling repo checkout
        _REPO_ROOT.parent.parent / "pfs_instdata",    # two levels up
    ]
    for candidate in candidates:
        yaml_path = candidate / "config" / "actors" / "agcc.yaml"
        if yaml_path.exists():
            os.environ["PFS_INSTDATA_DIR"] = str(candidate)
            return

_autodiscover_instdata()


# ---------------------------------------------------------------------------
# Stubs for optional PFS stack dependencies
# ---------------------------------------------------------------------------

def _ensure_stub(modname: str) -> None:
    """Insert empty module stubs for every prefix of ``modname``."""
    parts = modname.split(".")
    for i in range(1, len(parts) + 1):
        sub = ".".join(parts[:i])
        if sub not in sys.modules:
            sys.modules[sub] = types.ModuleType(sub)


# pfs.utils.database.opdb -----------------------------------------------
try:
    from pfs.utils.database import opdb as _opdb  # noqa: F401
except ModuleNotFoundError:
    _ensure_stub("pfs.utils.database")

    _opdb_stub = types.ModuleType("pfs.utils.database.opdb")

    class _StubOpDB:
        @classmethod
        def set_default_connection(cls, **kw):
            pass

    _opdb_stub.OpDB = _StubOpDB
    sys.modules["pfs.utils.database.opdb"] = _opdb_stub
    sys.modules["pfs.utils.database"].opdb = _opdb_stub  # type: ignore[attr-defined]

# pfs.utils.datamodel.ag ------------------------------------------------
try:
    from pfs.utils.datamodel import ag as _ag  # noqa: F401
except ModuleNotFoundError:
    _ensure_stub("pfs.utils.datamodel")

    _ag_stub = types.ModuleType("pfs.utils.datamodel.ag")
    _SourceDetectionFlag = enum.IntFlag(
        "SourceDetectionFlag",
        ["EDGE", "BAD_ELLIP", "RIGHT", "SATURATED", "FLAT_TOP", "BAD_SHAPE"],
    )
    _ag_stub.SourceDetectionFlag = _SourceDetectionFlag
    _ag_stub.SourceDetectionFlags = _SourceDetectionFlag  # plural alias
    sys.modules["pfs.utils.datamodel.ag"] = _ag_stub
    sys.modules["pfs.utils.datamodel"].ag = _ag_stub  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_cmd():
    """MagicMock standing in for a tron ``cmd`` object.

    All reply methods (``inform``, ``warn``, ``fail``, ``finish``,
    ``respond``, ``debug``) are individual ``MagicMock`` instances so
    that tests can use ``assert_called_*`` on each independently.
    """
    cmd = MagicMock()
    for method in ("inform", "warn", "fail", "finish", "respond", "debug"):
        setattr(cmd, method, MagicMock())
    # centroid.getCentroidParams accesses cmd.cmd.keywords
    cmd.cmd.keywords = []
    return cmd


@pytest.fixture
def mock_opdb():
    """MagicMock standing in for an ``opdb.OpDB`` instance."""
    db = MagicMock()
    db.query_scalar = MagicMock(return_value=None)
    db.query_series = MagicMock(return_value=None)
    db.insert_kw = MagicMock()
    db.insert_dataframe = MagicMock()
    return db


# ---------------------------------------------------------------------------
# Real-hardware data fixtures
# ---------------------------------------------------------------------------

# Prefer committed test data (tests/data/run28/) so CI works without the
# images/ symlink.  Fall back to the symlink for local developer machines
# that have the full data directory mounted.
_COMMITTED_RUN28 = Path(__file__).parent / "data" / "run28"
_SYMLINK_RUN28 = Path(__file__).parent.parent / "images" / "run28"
_RUN28_DIR = _COMMITTED_RUN28 if _COMMITTED_RUN28.is_dir() else _SYMLINK_RUN28

#: First combined FITS file from run28 (used in most replay tests).
RUN28_FITS = _RUN28_DIR / "agcc_143362_01043046.fits"

#: All four combined FITS files from run28 (in exposure order).
RUN28_FITS_ALL = [
    _RUN28_DIR / f"agcc_143362_0104304{i}.fits" for i in range(6, 10)
]

#: Detected-centroids CSV exported from the OpDB for this run.
RUN28_DETECTED_CSV = _RUN28_DIR / "1671605105044996096-detected.csv"

#: Exposure-info CSV exported from the OpDB for this run.
RUN28_EXPOSURE_CSV = _RUN28_DIR / "1671605105044996096-exposure_info.csv"


@pytest.fixture
def real_data_path():
    """Return the path to the run28 hardware data; skip if absent."""
    if not _RUN28_DIR.is_dir():
        pytest.skip("Real hardware data not available (tests/data/run28/ or images/run28/ missing)")
    return _RUN28_DIR


@pytest.fixture
def pfs_instdata():
    """Skip the test when ``PFS_INSTDATA_DIR`` is not set in the environment."""
    val = os.environ.get("PFS_INSTDATA_DIR", "")
    if not val:
        pytest.skip("PFS_INSTDATA_DIR is not set")
    return Path(val)

