"""Pytest config for the agccActor test suite.

Run from the repo root after `setup -r .` has put `agccActor` on PYTHONPATH:

    setup -r .
    pytest tests

`expose.py` transitively imports `pfs.utils.database.opdb`, which only exists
in a fully-set-up PFS development environment. The tests here only need the
photometry worker logic and the `PHOTOMETRY_TIMEOUT_S` constant from `expose`,
not any DB functionality, so we install a no-op stub for `pfs.utils.database`
when it is not available. This keeps the test runnable on dev machines
without the full PFS stack.
"""

import multiprocessing as mp
import sys
import types

# The repo's photometry worker is defined as a closure inside `createProc()`,
# which the default macOS `spawn` start method cannot pickle. Production runs
# on Linux where `fork` is the default; force `fork` here so tests exercise
# the same path. `force=True` is a no-op on Linux.
try:
    mp.set_start_method('fork', force=True)
except RuntimeError:
    pass


def _ensure_stub(modname):
    if modname in sys.modules:
        return
    parts = modname.split('.')
    for i in range(1, len(parts) + 1):
        sub = '.'.join(parts[:i])
        if sub not in sys.modules:
            sys.modules[sub] = types.ModuleType(sub)


try:
    from pfs.utils.database import opdb  # noqa: F401
except ModuleNotFoundError:
    _ensure_stub('pfs.utils.database')
    opdb_stub = types.ModuleType('pfs.utils.database.opdb')
    opdb_stub.OpDB = type('OpDB', (), {})
    sys.modules['pfs.utils.database.opdb'] = opdb_stub
    sys.modules['pfs.utils.database'].opdb = opdb_stub
