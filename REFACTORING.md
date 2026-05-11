# Refactoring Recommendations

This document catalogs bugs, code quality issues, and structural improvements identified across the `ics_agccActor` codebase. Issues are grouped by severity and category.

---

## Status Update (2026-05-08) — all S-effort fixes resolved on `fix/critical-bugs`

All Small-effort Medium and Low priority items have been resolved in a single commit on `fix/critical-bugs`:

- **#13** — `shutterOps` now uses `if/elif/else` with `cmd.fail` on unknown mode
- **#18** — `Exposure.__init__` copies `cParms` defensively with `dict(cParms)`
- **#19** — `print()` replaced with `logger.info/debug` in `centroidTools.py` and `main.py`
- **#21** — `sequence_in_use()` simplified to a single `return` expression
- **#23** — `nframe.txt` dead-code block removed from `expose.py run()`
- **#26** — `MAX_SEQUENCES = 6` constant added; `inusesequence` bounds check updated
- **#27** — module-level constants in `fake_camera.py` moved before the class definition
- **#28** — O(n²) nested loop in `wfits_combined` replaced with `{cam.agcid: cam}` dict
- **#29** — `closeShutter` log message corrected from "opening" to "closing"
- **#31** — redundant `if not expType` guard removed from `camera.expose()`
- **#33** — parentheses added to `magFit` formula for unambiguous precedence
- **#34** — `_load_agcc_config()` helper with `@functools.lru_cache` caches YAML reads
- **#37** — `return` added after each `cmd.fail()` in `startsequence` error paths
- **#38** — `else: raise ValueError` added in `windowedFWHM` for invalid `side`

**Remaining open (deferred to a separate branch):**
- **#12** (Medium/M) — `setCentroidParams` command/helper separation
- **#15** (Low/S) — unused imports (largely clean after sweep; confirm individually)
- **#20** (Medium/M) — camera-list parsing code deduplication
- **#24** (Medium/M) — class-level lock/counter documentation and consistency
- **#32** (High/L) — expand test coverage to `centroidTools`, `dbRoutinesAGCC`, `Exposure`

`ruff check python/` and `ruff format --check python/` pass clean.

---

## Status Update (2026-05-11) — bare imports fully resolved (#16)

- **Issue #16** (bare imports): fully resolved on `tickets/INSTRM-2928`.
  - `camera.py`, `AgccCmd.py`, `sequence.py`, and `main.py` converted to fully-qualified imports
    (`from agccActor import ...` / `from agccActor.X import ...`).
  - All modules now use portable imports; the `sys.path` shim in tron's actor loader is no longer
    load-bearing for inter-module references within `agccActor`.

---

## Status Update (2026-05-08) — rebase onto origin/master; upstream progress on #16 and #32

- `fix/critical-bugs` rebased onto `origin/master` (tag `1.2.22`, merged `tickets/INSTRM-2920`).
- Upstream changes absorbed during rebase:
  - `expose.py`: now uses fully-qualified `from agccActor import dbRoutinesAGCC, photometry, writeFits`; adds `import queue` and `PHOTOMETRY_TIMEOUT_S = 20` timeout for photometry worker; photometry error caught with `if self.cmd:` guard.
  - `photometry.py`: `createProc.worker()` now has try/except around `measure()` with logger; prevents silent worker crashes (INSTRM-2920).
  - `tests/conftest.py` + `tests/test_photometry_worker.py` added (99 lines); photometry worker is now tested.
- **Issue #16** (bare imports): partially resolved. `expose.py` is fixed upstream. `camera.py`, `AgccCmd.py`, and `sequence.py` still use bare imports — remaining on the High-priority queue.
- **Issue #32** (no tests): partially resolved. Photometry worker tested. `centroidTools`, `dbRoutinesAGCC`, and `Exposure` threading remain uncovered.
- `ruff check python/` passes clean after rebase conflict resolution.

---

## Status Update (2026-05-07) — branching to `fix/critical-bugs`

- Non-functional cleanup sweep is complete on `chore/nonfunctional-cleanup-sweep` (not yet merged to `master`).
- New branch `fix/critical-bugs` is based off `chore/nonfunctional-cleanup-sweep` to carry the cleanup work forward.
- `mypy` dropped from scope (see checklist note); `sdss3tools` build dep blocks it outside PFS/EUPS.
- `sdss3tools` git dep added to `pyproject.toml` build requirements — not confirmed working; document for future resolution.

### `fix/critical-bugs` work queue

Items to fix on this branch, in recommended order:

- [x] **#1** — Add `cParms`/`iParms` to `camera.startsequence()`; pass `self.cParms`/`self.iParms` from `AgccCmd.startsequence()`; removed `F821` per-file lint ignores from `pyproject.toml`. (`camera.py`, `AgccCmd.py`, `pyproject.toml`)
- [x] **#2** — `cmd.inform()` ungarded calls resolved as part of #3 (block moved to `run()` with proper `if self.cmd:` guards). (`expose.py`)
- [x] **#3** — Moved `getNextAgcExposureId()`, nframe.txt write, and `writeExposureToDB()` from `__init__` to beginning of `run()`; initialized `self.nframe = -1` in `__init__`. (`expose.py`)
- [x] **#4** — Collect `cam_target_temps: dict[cam, float]` before TEC-off loop; restore per-camera temp from dict in teardown loop. (`expose.py`)
- [x] **#8** — Added `else: raise ValueError(f"Unknown centroid method: {cMethod!r}")` in `photometry.measure()`. (`photometry.py`)
- [x] Verify `ruff check python/` still passes — confirmed clean.
- [x] ~~Run mypy~~ — dropped; `sdss3tools` build dep blocks `mypy` outside PFS/EUPS environment.

---

## Status Update (2026-05-07)

- Resolved on branch `chore/nonfunctional-cleanup-sweep`: issues **#5** and **#6** in `python/agccActor/camera.py` and `python/agccActor/checkit.py`.
- Previously resolved: issues **#10**, **#11**, and **#14** in `python/agccActor/writeFits.py`.
- `sdss3tools` confirmed to come from `https://github.com/Subaru-PFS/ics_config.git`; added as explicit build dep in `pyproject.toml`.
- Verification snapshot after recent commits:
  - `ruff check python/` (local `ruff`) passes.
  - `ruff format --check python/` reports files already formatted.
  - `mypy` dropped from scope (`sdss3tools` build dep blocks it outside PFS/EUPS).

---

## Previous Status (2026-04-30)

- Resolved on branch `chore/nonfunctional-cleanup-sweep`: issues **#10**, **#11**, and **#14** in `python/agccActor/writeFits.py`.
- Those three items are no longer part of the deferred follow-up bug-fix queue.
- Verification snapshot after cleanup commits:
  - `ruff check python/` (local `ruff`) passes.
  - `ruff format --check python/` reports files already formatted.
  - `uv run ruff check python/` passes. `mypy` dropped from scope (`sdss3tools` build dep blocks it outside PFS/EUPS).

---

## Critical Bugs

### 1. `NameError` in `sequence.py` — `cParms` and `iParms` are undefined
**File:** `python/agccActor/sequence.py`, line 49

`Sequence.__init__` never receives `cParms` or `iParms` as constructor arguments, yet `run()` passes them directly to `Exposure(...)`. These variables are simply undefined in the class scope, causing a `NameError` at runtime whenever a sequence is started.

```python
# BUG: cParms and iParms are not defined here
exp_thr = Exposure(self.cams, self.expTime_ms, False, cParms, iParms, ...)
```

`camera.py` line 470 has the same bug — it calls `Sequence(...)` without passing `cParms` or `iParms`.

**Fix:** Add `cParms` and `iParms` to `Sequence.__init__` and store them as instance attributes. Pass them from `camera.startsequence()`.

---

### 2. `cmd.inform()` called without `None` guard in `Exposure.__init__`
**File:** `python/agccActor/expose.py`, lines 66, 86

`cmd` has a default value of `None` in `Exposure.__init__`, yet it is called unconditionally on lines 66 and 86 before any `if self.cmd:` check. If `cmd=None` is passed, this raises `AttributeError`.

```python
# BUG: self.cmd may be None here
self.cmd.inform(f'text="Getting agc_exposure_id = {self.nframe} from OpDB"')
```

---

### 3. Database write happens in `__init__`, before the exposure runs
**File:** `python/agccActor/expose.py`, line 88

`dbRoutinesAGCC.writeExposureToDB(...)` is called inside `Exposure.__init__`, not in `run()`. This means the DB record is committed even if `start()` is never called, or if the exposure is immediately aborted. The exposure ID is also incremented and wasted in those cases.

**Fix:** Move the `getNextAgcExposureId()` and `writeExposureToDB()` calls to the beginning of `run()`.

---

### 4. `targetTemp` used outside its defining scope — only last camera's temp restored
**File:** `python/agccActor/expose.py`, lines 110–141

When `tecOFF=True`, `targetTemp = cam.temp` is set inside the `for cam in self.cams` loop. After the loop, the TEC-on code uses `targetTemp`, which only holds the **last** camera's temperature. All other cameras are restored to the wrong temperature.

```python
# BUG: targetTemp is overwritten each iteration; only last cam's temp survives
for cam in self.cams:
    if self.tecOFF is True:
        targetTemp = cam.temp   # lost after next iteration
        cam.setTemperature(self.tecOFFtemp)
    thr = threading.Thread(...)
    ...
# After loop, only last cam's targetTemp is in scope
for cam in self.cams:
    cam.setTemperature(targetTemp)  # wrong for all but last cam
```

**Fix:** Collect `{cam: cam.temp}` in a dict before the loop; restore per-camera on teardown.

---

### 5. `fli_camera` is imported unconditionally even in simulator mode
**File:** `python/agccActor/camera.py`, line 8

**Status:** ✅ Resolved (2026-05-01, `chore/nonfunctional-cleanup-sweep`).

`import fli_camera` is a top-level import. When running in simulator mode (`simulator=1`), the Cython extension is still imported, which will fail on machines without the compiled extension or FLI hardware.

Current state: `fli_camera` import is now guarded inside the hardware mode block (`if simulator == 0:`), allowing simulator mode to run without the extension.

---

### 6. Broken `checkit.py` committed with hardcoded developer path
**File:** `python/agccActor/checkit.py`

**Status:** ✅ Resolved (2026-05-01, `chore/nonfunctional-cleanup-sweep`).

This file is clearly leftover development/debug code. It contains a hardcoded path to a developer's machine (`/Users/karr/test1.fits`), calls a non-existent function (`ct.getCentroids`; the real function is `getCentroidsSep`), and will crash on import or execution. It serves no production purpose.

Current state: File deleted entirely from the repository.

---

### 7. `camera.setcamtemperature()` dereferences potentially-`None` camera
**File:** `python/agccActor/camera.py`, line 379

`self.cams[cam].isReady()` is called without first checking if `self.cams[cam] is not None`. If the requested camera is absent, this raises `AttributeError`.

```python
def setcamtemperature(self, cmd, cam, temp):
    if self.cams[cam].isReady():   # BUG: no None guard
```

Same issue in `camera_stat()` (line 502).

---

### 8. `photometry.measure()` returns undefined variable for unknown `cMethod`
**File:** `python/agccActor/photometry.py`, lines 16–20

```python
def measure(data, agcid, cParms, iParms, cMethod, thresh=10):
    if cMethod == 'sep':
        result = ct.getCentroidsSep(...)
    return result  # BUG: NameError if cMethod != 'sep'
```

If `cMethod` is anything other than `'sep'` (e.g., `'win'`, which the command grammar allows), `result` is never assigned and a `NameError` is raised.

**Fix:** Add an `else` clause that raises a descriptive `ValueError`, or return `None`.

---

## Incorrect / Misleading Behaviour

### 9. FITS write path is hardcoded, inconsistent with `$ICS_MHS_DATA_ROOT`
**File:** `python/agccActor/writeFits.py`, lines 10, 79

Both `wfits()` and `wfits_combined()` hardcode `/data/raw` as the output root, with the correct `$ICS_MHS_DATA_ROOT`-based path commented out directly above:

```python
#path = os.path.join("$ICS_MHS_DATA_ROOT", 'agcc')
path = os.path.join('/data/raw', time.strftime('%Y-%m-%d', ...), 'agcc')
```

Meanwhile, `expose.py` (line 69) uses `$ICS_MHS_DATA_ROOT` for the `nframe.txt` file. These two paths diverge in non-standard deployments.

**Fix:** Uncomment the env-var path and remove the hardcoded one in `writeFits.py`.

---

### 10. `wfits()` writes centroided images to a different filename than non-centroided ones
**File:** `python/agccActor/writeFits.py`, lines 62–65

**Status:** ✅ Resolved (2026-04-30, `chore/nonfunctional-cleanup-sweep`).

```python
if cam.spots is not None:
    hdulist.writeto(filename, ...)        # timestamp-based name
else:
    hdu.writeto(pfsFilename, ...)         # canonical PFS name
```

When centroiding is enabled, the file is written to `agcc_c{N}_{timestamp}.fits` instead of `agcc_{visitId:06d}_{exposureId:08d}_cam{N}.fits`. The canonical `pfsFilename` is only used in the non-centroid branch. The reported filename in `cmd.inform` always references `pfsFilename` regardless, so callers are told an incorrect filename.

Current state: both branches now write to the canonical `pfsFilename`.

---

### 11. Log message says "NOT written" for a file that was just written
**File:** `python/agccActor/writeFits.py`, lines 73, 157

**Status:** ✅ Resolved (2026-04-30, `chore/nonfunctional-cleanup-sweep`).

```python
cmd.inform(f'text="AG images are NOT written into {pfsFilename}"')
```

This message immediately follows a successful `writeto()` call. The message is the opposite of the truth, which will cause confusion when diagnosing missing files.

**Fix:** Change to `"AG images written to {pfsFilename}"`.

Current state: misleading `NOT written` messages were removed from `wfits()` and `wfits_combined()`.

---

### 12. `setCentroidParams` calls `cmd.finish()` when used as a side-effect during `expose`
**File:** `python/agccActor/Commands/AgccCmd.py`, lines 455–468

`setCentroidParams` was designed as both a standalone command handler and an internal helper. When called as a handler, it must call `cmd.finish()` to close the command. But `expose()` calls `self.setImageParams(cmd)` (the same pattern), and the design relies on `cmd is not None` guards to skip `finish()` in internal calls. If called via a command, `setCentroidParams` terminates the command, making it impossible to chain further operations.

**Fix:** Extract internal parameter-loading logic into a private `_loadCentroidParams()` method. The command handler calls that, then calls `cmd.finish()` itself.

---

### 13. `shutterOps` proceeds silently when shutter mode is unrecognised
**File:** `python/agccActor/Commands/AgccCmd.py`, lines 153–157

```python
if shutterMode == 'open':
    self.actor.camera.openShutter(cmd, cams)
if shutterMode == 'close':
    self.actor.camera.closeShutter(cmd, cams)
```

Two independent `if` statements are used instead of `if/elif/else`. An unrecognised mode silently does nothing and returns success. The grammar enforces `@(open|close)`, but the implementation should still be defensive.

---

### 14. `wfits_combined` uses `filename` (legacy name) in the `seq_id` reporting path
**File:** `python/agccActor/writeFits.py`, line 154

**Status:** ✅ Resolved (2026-04-30, `chore/nonfunctional-cleanup-sweep`).

```python
cmd.inform('agc_seq%d="%s"' % (seq_id + 1, filename))  # reports old timestamp name
```

`filename` is the old timestamp-based name, not `pfsFilename`. The sequence case reports a file that is no longer written (the actual write uses `pfsFilename`).

Current state: sequence reporting now uses `pfsFilename`.

---

## Code Quality & Maintainability

### 15. Unused imports throughout
Multiple files contain imports that are never used:

| File | Unused import |
|------|--------------|
| `AgccCmd.py` | `base64`, `numpy`, `astropy.io.fits` |
| `centroidTools.py` | `from scipy.integrate import dblquad`, `from lmfit import Model` (imported twice), `import lmfit` (imported twice) |
| `photometry.py` | `from importlib import reload`, `import sep` (sep is used only via `centroidTools`) |
| `main.py` | `reload` from `importlib` (only used in `connectCamera`, not `reloadCamera`) |

---

### 16. Bare relative imports will fail in Python 3
**Files:** `camera.py`, `AgccCmd.py`, `sequence.py` (`checkit.py` deleted)

**Partial fix upstream (2026-05-08):** `expose.py` was updated in `tickets/INSTRM-2920` to use `from agccActor import dbRoutinesAGCC, photometry, writeFits`. The following bare imports remain:

```python
# camera.py
from expose import Exposure     # should be: from agccActor.expose import Exposure
from setmode import SetMode
import writeFits
import photometry

# AgccCmd.py
import centroidTools as ct
import dbRoutinesAGCC as dbRoutinesAGCC

# sequence.py
from expose import Exposure
```

Implicit relative imports do not work in Python 3 and require `sys.path` manipulation (via an EUPS/tron shim) to function. This makes the code fragile and non-portable.

**Fix:** Use fully-qualified package imports (`from agccActor.expose import Exposure`, etc.).

---

### 17. `None` comparisons use `!=` and `==` instead of `is not` / `is`
**File:** `camera.py` (numerous lines including 104, 115, 152, 207, 223, 229, 249, 254, 293, 319, 360, 395, 450)

```python
if self.cams[n] != None:   # should be: if self.cams[n] is not None:
```

PEP 8 and the Python data model both require identity comparison (`is`/`is not`) for singletons like `None`.

---

### 18. `cParms` is mutated in `Exposure.__init__`, affecting the caller's copy
**File:** `python/agccActor/expose.py`, line 50

```python
self.cParms['expTime'] = expTime_ms / 1000
```

`cParms` is a dict passed in from `AgccCmd` and stored on `self`. Mutating it in-place modifies the dict held by the caller. If two concurrent exposures were ever started, they would clobber each other's `expTime`.

**Fix:** Work on a shallow copy: `self.cParms = dict(cParms); self.cParms['expTime'] = ...`.

---

### 19. `print()` used instead of logger in production code
**Files:** `centroidTools.py` line 275, `main.py` line 16

```python
print(f'Calculating Magnitude: exptime = {cParms["expTime"]}')  # centroidTools.py
print(f'   actorConfig: {self.actorConfig}')                     # main.py
```

`print()` bypasses the tron logging infrastructure and does not appear in the actor log. `main.py` also risks printing sensitive configuration (e.g., database credentials) to stdout.

**Fix:** Replace with `logger.debug(...)` or `logger.info(...)`.

---

### 20. Massively duplicated camera-list parsing code
**File:** `python/agccActor/Commands/AgccCmd.py`

The following pattern is copy-pasted verbatim across at least 8 command handlers (`expose`, `abort`, `setframe`, `resetframe`, `setmode`, `getmode`, `shutterOps`, `startsequence`):

```python
cams = []
if 'cameras' in cmdKeys:
    camList = cmdKeys['cameras'].values[0]
    for cam in camList:
        k = int(cam) - 1
        if k < 0 or k >= nCams:
            cmd.error('text="camera list error: %s"' % camList)
            cmd.fail()
            return
        cams.append(k)
else:
    for k in range(nCams):
        cams.append(k)
```

**Fix:** Extract into a helper method, e.g.:

```python
def _parseCameraList(self, cmd, cmdKeys, default_all=True):
    ...
```

---

### 21. `sequence_in_use()` uses an if/else to return a boolean
**File:** `python/agccActor/camera.py`, lines 492–497

```python
def sequence_in_use(self, seq_id):
    if self.seq_stat[seq_id] != SEQ_IDLE:
        return True
    else:
        return False
```

**Fix:**
```python
def sequence_in_use(self, seq_id):
    return self.seq_stat[seq_id] != SEQ_IDLE
```

---

### 22. `busy` flag is set but never used in `setcamtemperature()`
**File:** `python/agccActor/camera.py`, lines 378–384

```python
def setcamtemperature(self, cmd, cam, temp):
    busy = False
    if self.cams[cam].isReady():
        self.cams[cam].setTemperature(temp)
    else:
        busy = True          # assigned but never read
        if cmd:
            cmd.warn(...)
```

The `busy` variable is set but never read, and the caller receives no indication of failure.

---

### 23. `expose.py` inconsistently uses both `$ICS_MHS_DATA_ROOT` path and the `nframe.txt` file
**File:** `python/agccActor/expose.py`, lines 69–86

The `nframe.txt` file is written (when it already exists) to record the current exposure ID, but it is never *read* — the actual value comes from the database via `getNextAgcExposureId()`. The `nframe.txt` write is therefore dead code. Worse, the file is only written if it already exists (the `if os.path.isfile` guard), so first-time runs never create it. This logic is inverted from any useful intent.

---

### 24. `Exposure` class lock (`exp_lock`) is a class-level attribute, not instance-level
**File:** `python/agccActor/expose.py`, line 11

```python
class Exposure(threading.Thread):
    exp_lock = threading.Lock()
    n_busy = 0
```

This is intentional for the global counter, but it means all `Exposure` instances (including concurrent ones from different visits) share a single lock. There is no documentation that this is deliberate, and the class-level `n_busy` counter is only protected in two specific places, while camera state is modified in per-camera threads without holding the lock at all.

---

### 25. `AgccCmd.setOrGetVisit` stores mutable state on `self`, making it non-reentrant
**File:** `python/agccActor/Commands/AgccCmd.py`, lines 108–125

```python
def setOrGetVisit(self, cmd):
    self.cmd = cmd          # overwrites any previous cmd
    self.frameSeq = 0
    self.visit = ...
```

Storing `cmd` and `visit` as instance attributes means a second concurrent command invocation would corrupt the state of the first. These should be local variables returned from the method, not stored on `self`.

---

### 26. `inusesequence` bounds-checks against `nCams` (6), but sequences are not cameras
**File:** `python/agccActor/Commands/AgccCmd.py`, line 434

```python
if seq_id < 0 or seq_id >= nCams:   # nCams = 6, but is this the sequence limit?
```

`seq_id` is bounded against `nCams` (6), which is coincidentally correct only because the number of sequences happens to equal the number of cameras. A named constant (`MAX_SEQUENCES`) would make this intent explicit and safe to change independently.

---

### 27. `fake_camera.py` module-level constants defined at the bottom, used at the top
**File:** `python/agccActor/fli/fake_camera.py`, lines 302–309

`CLOSED`, `READY`, `EXPOSING`, `SETMODE`, `numCams`, `dev`, etc. are defined at the bottom of the file, but are used by `Camera.__init__` and methods defined much earlier. This works because the constants are only referenced at call time, not at class definition time, but it is confusing and fragile.

**Fix:** Move all module-level constants to the top of the file, before the class definition.

---

### 28. `wfits_combined` inner loop uses `break`/`else` to find a camera — O(n²) search
**File:** `python/agccActor/writeFits.py`, lines 102–107

```python
for n in range(6):
    for cam in cams:
        if cam.agcid == n:
            break
    else:
        hdulist.append(pyfits.ImageHDU(name=extname))
        continue
```

Building a `{cam.agcid: cam}` dict before the outer loop would be clearer and more efficient.

---

### 29. `closeShutter` log message says "opening"
**File:** `python/agccActor/camera.py`, line 279

```python
def closeShutter(self, cmd, cams):
    ...
    cmd.inform('text="Send shutter opening command to AGC[%d]"' % (n + 1))
    #                          ^^^^^^^ should be "closing"
    self.cams[n].closeShutter()
```

Copy-paste error from `openShutter`. The log says "opening" even though the shutter is being closed.

---

### 30. `setregions` stores region coordinates as raw strings, not integers
**File:** `python/agccActor/camera.py`, lines 420–425

```python
pars = regions_str.split(',')
if len(pars) == 3:
    self.cams[camid].regions = ((pars[0], pars[1], pars[2]), (0, 0, 0))
```

`pars` contains string elements from `split()`. `cam.regions` is used downstream as a numeric tuple. Arithmetic on these strings will produce silent type errors.

**Fix:** `pars = [int(x) for x in regions_str.split(',')]`

---

### 31. `expose` type-guard checks in `camera.py` are redundant or incomplete
**File:** `python/agccActor/camera.py`, line 166

```python
if not expType:
    expType = 'test'
```

`expType` is always provided by the command grammar (`@(test|dark|object)`), so this can never be falsy in practice. The guard creates a false sense of safety while masking any real bugs in the calling path.

---

### 32. No unit tests exist in the repository
**Partial fix upstream (2026-05-08):** `tickets/INSTRM-2920` added `tests/conftest.py` and `tests/test_photometry_worker.py` (99 lines). The photometry worker is now tested. The following remain uncovered:

- `centroidTools` (pure functions, easily testable with mock data)
- `dbRoutinesAGCC` (mockable database)
- `Exposure` thread integration tests using the fake camera

The `conftest.py` installs a `pfs.utils.database.opdb` stub so tests can run without the full PFS stack, and forces `fork` start method for multiprocessing compatibility on macOS. This pattern can be extended for future test additions.

---

## Minor Issues

### 33. `magFit` formula in `calculateApproximateMagnitude` has ambiguous operator precedence
**File:** `python/agccActor/centroidTools.py`, line 493

```python
mag = -2.5 * np.log10(instrumentFlux / expTime) * iParms['magFit'][0] + iParms['magFit'][1]
```

The standard magnitude formula is `mag = -2.5 * log10(flux/t) * c0 + c1`. The multiplication chain is evaluated left-to-right and is correct, but parentheses would make it unambiguous:

```python
mag = (-2.5 * np.log10(instrumentFlux / expTime)) * iParms['magFit'][0] + iParms['magFit'][1]
```

---

### 34. `getCentroidParams` and `getImageParams` re-read the config file on every call
**File:** `python/agccActor/centroidTools.py`, lines 19–63

Both functions open and parse `agcc.yaml` on every invocation, including every single exposure. The file should be cached at startup (e.g., parsed once by the actor) or at least cached using `functools.lru_cache` if command-override support is not needed on every call.

---

### 37. `startsequence` error paths call `cmd.fail()` but don't `return`
**File:** `python/agccActor/Commands/AgccCmd.py`, lines 410–416

```python
if count < 0:
    cmd.error('text="parameter count invalid: %d"' % count)
    cmd.fail()
# no return here — falls through to elif
elif len(cams) <= 0:
    cmd.error('text="No usable camera"')
    cmd.fail()
# no return here either
```

While the if/elif structure prevents multiple branches from executing, `cmd.fail()` is not a `raise` — it does not interrupt execution. Omitting `return` after each failure path is confusing and creates a maintenance hazard if the structure is ever changed.

---

### 38. `windowedFWHM` has no guard for `side` values other than 0 or 1
**File:** `python/agccActor/centroidTools.py`, lines 326–337

```python
if side == 0:
    ...
elif side == 1:
    ...
# No else: if side is neither 0 nor 1, dMinX/dMinY/dMaxX/dMaxY are undefined
winVal = data[dMinY:dMaxY, dMinX:dMaxX]   # NameError if side is invalid
```

If `side` is any value other than `0` or `1`, the subsequent slice raises a `NameError`. Add an `else: raise ValueError(...)`.

---

## Build Tooling

### 39. `setup.py` uses deprecated `distutils` and depends on `sdss3tools`
**File:** `setup.py`

The project's only build entry point is a legacy `setup.py` that imports `distutils.extension` (removed in Python 3.12) and `sdss3tools` (not on PyPI — ships inside `https://github.com/Subaru-PFS/ics_config.git`). This blocks standard packaging workflows (`pip install -e .`, `uv sync`) and prevents running modern tooling (`mypy`, `pytest` via `uv run`) outside the full PFS EUPS environment.

```python
from distutils.extension import Extension   # removed in Python 3.12
from Cython.Distutils import build_ext
import sdss3tools                            # not on PyPI

sdss3tools.setup(
    name = "agcc",
    ...
)
```

A draft `pyproject.toml` was prototyped on this branch but removed — it is out of scope for the cleanup sweep and needs its own dedicated effort to validate against the EUPS build pipeline and Subaru deployment environment.

**Key blockers for a `pyproject.toml` migration:**
- `sdss3tools.setup()` wraps `setuptools.setup()` with EUPS-specific hooks (version injection, product table generation). These must be replicated or replaced.
- The Cython extension (`fli_camera.pyx`) links against the vendored `c/libfli-*` and system `libusb-1.0`. The extension build config needs to be expressed in `[tool.setuptools]` or a custom build backend.
- PFS stack dependencies (`pfs-tron-actorcore`, `pfs-utils`) are git-only and not on PyPI, requiring `direct_url` references or a private index.
- Deployment at Subaru uses EUPS, not pip/uv, so any migration must remain compatible with the existing deployment workflow.

**Fix:** Create a `pyproject.toml` that replaces `setup.py`, with the Cython extension configured via `setuptools`. Validate that both `uv sync && uv run pytest` and the EUPS build pipeline work. This is a standalone effort best done on a dedicated branch.

---

## Priority & Effort Summary

**Priority** — how urgently the issue should be addressed:
- 🔴 **Critical** — crashes, data corruption, or silent wrong results
- 🟠 **High** — significant incorrect behaviour or broken functionality
- 🟡 **Medium** — potential issues under certain conditions; code correctness concerns
- 🟢 **Low** — style, clarity, or minor robustness improvements

**Effort** — rough estimate of work to fix:
- **S** (Small) — isolated change, under an hour
- **M** (Medium) — requires thought or touches multiple files, a few hours
- **L** (Large) — substantial rework, multi-session effort

| # | Issue | File(s) | Priority | Effort |
|---|-------|---------|----------|--------|
| 1 | ✅ Resolved: `cParms`/`iParms` added to `Sequence.__init__`; passed from `camera.startsequence()` | `sequence.py`, `camera.py` | — | — |
| 2 | ✅ Resolved: `cmd.inform()` guards added; block moved to `run()` | `expose.py` | — | — |
| 3 | ✅ Resolved: DB write moved to `run()` | `expose.py` | — | — |
| 4 | ✅ Resolved: per-camera temp dict; restored per-cam on teardown | `expose.py` | — | — |
| 5 | ✅ Resolved: `fli_camera` import now guarded in simulator mode | `camera.py` | — | — |
| 6 | ✅ Resolved: deleted broken `checkit.py` with hardcoded paths | `checkit.py` | — | — |
| 7 | ✅ Resolved: `None` guards added to `setcamtemperature()` and `camera_stat()` | `camera.py` | — | — |
| 8 | ✅ Resolved: `else: raise ValueError` added in `photometry.measure()` | `photometry.py` | — | — |
| 9 | ✅ Resolved: FITS output path now uses `$ICS_MHS_DATA_ROOT` | `writeFits.py` | — | — |
| 10 | ✅ Resolved: centroided images now use canonical reported filename | `writeFits.py` | — | — |
| 11 | ✅ Resolved: removed misleading "NOT written" message | `writeFits.py` | — | — |
| 12 | `setCentroidParams` calls `cmd.finish()` when used as internal helper | `AgccCmd.py` | 🟡 Medium | M |
| 13 | ✅ Resolved: `shutterOps` uses `if/elif/else` with `cmd.fail` on unknown mode | `AgccCmd.py` | — | — |
| 14 | ✅ Resolved: sequence reporting now uses canonical `pfsFilename` | `writeFits.py` | — | — |
| 15 | Unused imports largely clean after sweep; `sep`, `Model`, `reload` confirmed in use | `AgccCmd.py`, `centroidTools.py`, `photometry.py`, `main.py` | 🟢 Low | S |
| 16 | ✅ Resolved: `expose.py` fixed upstream; `camera.py`, `AgccCmd.py`, `sequence.py` fixed on `fix/critical-bugs` | `camera.py`, `AgccCmd.py`, `sequence.py` | — | — |
| 17 | ✅ Resolved: `None` comparisons fixed in cleanup sweep | `camera.py` | — | — |
| 18 | ✅ Resolved: `self.cParms = dict(cParms)` in `Exposure.__init__` | `expose.py` | — | — |
| 19 | ✅ Resolved: `print()` replaced with `logger.info/debug` | `centroidTools.py`, `main.py` | — | — |
| 20 | Camera-list parsing block copy-pasted across 8+ command handlers | `AgccCmd.py` | 🟡 Medium | M |
| 21 | ✅ Resolved: `sequence_in_use()` simplified to single `return` | `camera.py` | — | — |
| 22 | ✅ Resolved: `busy` flag removed as side-effect of #7 `None` guard | `camera.py` | — | — |
| 23 | ✅ Resolved: `nframe.txt` dead-code block removed from `expose.py` | `expose.py` | — | — |
| 24 | Class-level `exp_lock` / `n_busy` inconsistently protect shared state | `expose.py` | 🟡 Medium | M |
| 25 | ✅ Resolved: `setOrGetVisit` uses local variables, not `self` state | `AgccCmd.py` | — | — |
| 26 | ✅ Resolved: `MAX_SEQUENCES = 6` added; bounds check updated | `AgccCmd.py` | — | — |
| 27 | ✅ Resolved: module-level constants moved to top of file | `fake_camera.py` | — | — |
| 28 | ✅ Resolved: O(n²) loop replaced with `{cam.agcid: cam}` dict | `writeFits.py` | — | — |
| 29 | ✅ Resolved: `closeShutter` log message corrected to "closing" | `camera.py` | — | — |
| 30 | ✅ Resolved: `setregions` parses coordinates as integers | `camera.py` | — | — |
| 31 | ✅ Resolved: redundant `if not expType` guard removed | `camera.py` | — | — |
| 32 | Partial test coverage — photometry worker tested upstream; centroidTools, dbRoutinesAGCC, Exposure remain uncovered | `tests/` | 🟠 High | L |
| 33 | ✅ Resolved: parentheses added to `magFit` formula | `centroidTools.py` | — | — |
| 34 | ✅ Resolved: `_load_agcc_config()` with `@functools.lru_cache` caches YAML | `centroidTools.py` | — | — |
| 37 | ✅ Resolved: `return` added after each `cmd.fail()` in `startsequence` | `AgccCmd.py` | — | — |
| 38 | ✅ Resolved: `else: raise ValueError` added in `windowedFWHM` | `centroidTools.py` | — | — |
| 39 | `setup.py` uses deprecated `distutils` and `sdss3tools`; blocks modern tooling | `setup.py` | 🟠 High | L |

### Recommended fix order

1. **Fix all remaining 🔴 Critical items** (#1–4, #8) — most are one-line or two-line changes and the system will crash or silently corrupt data without them. Issues #5 and #6 are already resolved.
2. **Address 🟠 High items** (#7, #9, #16, #25, #30, #32) — fragile imports and the absence of tests compound risk during future changes.
3. **Work through 🟡 Medium items** (#12, #18, #20, #23, #24, #29, #34, #35, #36, #38) — most are Small effort and clean up correctness and observability.
4. **Mop up 🟢 Low items** (#13, #15, #17, #19, #21, #22, #26, #27, #28, #31, #33, #37) — style and clarity; address alongside any file already being touched.

---

## Non-Functional Cleanup Sweep (No Behavior Changes)

This appendix captures a one-time hygiene pass that is intentionally limited to formatting, linting, typing,
docstrings, and baseline documentation. Runtime behavior, business logic, camera control flow, and database/FITS
semantics are out of scope for this sweep.

### Agreed decisions

- Work is done on branch `chore/nonfunctional-cleanup-sweep`.
- Docstrings remain **NumPy style**.
- Typing starts with a **permissive baseline**.
- Keep all planning in this file (no separate cleanup plan file).
- Root `README.md` should stay minimal and **must not link to** `AGENTS.md`.

### In scope

- Lint and format pass for Python sources (`ruff format`, then `ruff check`).
- Type hints added where low-risk and non-semantic (function signatures first).
- NumPy-style docstring normalization for public classes/functions/modules.
- Add/update minimal root repository documentation.
- Tooling/config changes that support the above (e.g., type-checker config).

### Out of scope

- Any bug fix listed in issues #1-#38 above.
- Behavior changes, refactors, or control-flow rewrites.
- Camera, FITS, or database logic modifications intended to change runtime outcomes.
- Test additions that require logic changes to pass.

Exception applied during cleanup commits:
- Low-risk consistency fixes in `writeFits.py` were completed for #10, #11, and #14.

### Deferred bug-fix queue (explicitly postponed)

All remaining unresolved issues in the existing table are deferred to a follow-up functional refactor/fix branch.
If a lint/type/docstring task uncovers one of those bugs, document it and defer; do not fix in this sweep.

Resolved and removed from deferred scope in this branch: #5, #6, #10, #11, #14.

Temporary lint handling in this branch:
- `F821` is ignored for `python/agccActor/camera.py` and `python/agccActor/sequence.py`
  via `pyproject.toml` (`tool.ruff.lint.per-file-ignores`) to keep this pass non-functional.
- These ignores must be removed when functional fixes for issues #1 and related sequence/camera bugs are applied.

### Execution checklist

- [x] Confirm branch is `chore/nonfunctional-cleanup-sweep`.
- [x] Add minimal root `README.md` (overview, install, lint/format/test commands, simulator note).
- [x] Add permissive type-checker baseline to project config.
- [x] Run formatter across `python/agccActor/`.
- [x] Run linter and apply style-only cleanups.
- [x] Add/normalize NumPy docstrings in public APIs (all modules: `main.py`, `Commands/AgccCmd.py`, `photometry.py`, `dbRoutinesAGCC.py`, `setmode.py`, `expose.py`, `sequence.py`, `writeFits.py`, `camera.py`, `centroidTools.py`, `fli/fake_camera.py`).
- [x] Add low-risk type hints (signatures first; all modules above completed).
- [x] Re-run lint checks and record remaining deferred items.
- [x] ~~Re-run type checks~~ — dropped; `sdss3tools` build dep prevents `uv run mypy` outside the full PFS/EUPS environment. Type hints were added for documentation value; ruff covers the lint-level checks that matter.

### Suggested command sequence

```bash
uv sync --extra dev
uv run ruff format python/
uv run ruff check python/
```

*End of REFACTORING.md*
