# ics_agccActor — Agent Reference

`ics_agccActor` is a **tron actor** for the Subaru Prime Focus Spectrograph (PFS) Auto Guider Camera Control (AGCC) subsystem. It controls up to 6 FLI USB CCD cameras, manages exposures, runs centroiding/photometry, and writes results to FITS files and the PFS operational database (OpDB).

## Build, Lint, and Test

```bash
# Install dev dependencies (includes pytest-cov)
uv sync --extra dev

# Lint
uv run ruff check python/

# Format
uv run ruff format python/

# Run tests
uv run pytest

# Run tests with coverage (terminal report)
uv run pytest --cov=agccActor --cov-report=term-missing

# Run tests with HTML coverage report
uv run pytest --cov=agccActor --cov-report=html
open htmlcov/index.html

# Build the Cython FLI extension (requires libfli in c/libfli-1.999.1-180223/)
pip install -e .
```

### Cython Extension Build

The Cython extension `fli_camera` (from `python/agccActor/fli/fli_camera.pyx`) must be built against the FLI C library in `c/libfli-1.999.1-180223/`. It requires `libusb-1.0`. The extension is declared in `setup.py` (legacy sdss3tools build) and `pyproject.toml`.

When the FLI hardware is unavailable or the extension fails to build, `fli/fake_camera.py` is used instead (controlled by the `simulator: 0 | 1` key in actor config). In simulator mode, there is no need to build the extension.

### Testing

The test suite has **100 tests** across six files in `tests/`. Pytest config lives entirely in `pyproject.toml` (no `pytest.ini`).

| File | Coverage |
|---|---|
| `test_camera.py` | `fake_camera` unit tests; `Camera` controller (simulator mode) |
| `test_centroid_replay.py` | Record/replay against real hardware FITS data (`tests/data/run28/`) |
| `test_db_routines.py` | All OpDB write functions in `database.py` |
| `test_exposure.py` | `Exposure` thread lifecycle, error paths, FITS output |
| `test_photometry_worker.py` | Photometry worker process, timeout, synthetic-image detection |
| `test_writeFits.py` | `wfits` (per-camera) and `wfits_combined` FITS output |

**`real_data` marker** — replay tests are marked `@pytest.mark.real_data`. They require:
1. `tests/data/run28/` (committed via Git LFS — run `git lfs pull` after cloning), **or** the `images/run28/` symlink on developer machines with the data directory mounted.
2. `PFS_INSTDATA_DIR` pointing to a `pfs_instdata` checkout.

**`PFS_INSTDATA_DIR` auto-discovery** — if the variable is not exported, `conftest.py` searches for `pfs_instdata` at `../pfs_instdata` and `../../pfs_instdata` relative to the repo root. The first path containing `config/actors/agcc.yaml` is used automatically. Tests skip with a clear message if neither location is found.

**CI** — `.github/workflows/tests.yml` runs on every PR and push to `master`/`main`:
- Checks out with `lfs: true` to pull the FITS fixtures.
- Clones `Subaru-PFS/pfs_instdata` (public) and sets `PFS_INSTDATA_DIR`.
- Runs `ruff check` then the full test suite.
- Posts a coverage table to the job summary and as an updating PR comment (via `actions/github-script`; no third-party provider required).
- Uploads the HTML coverage report as a downloadable artifact (30-day retention).

## Architecture

### Actor Framework (tron/opscore)

`AgccActor` in `main.py` extends `actorcore.Actor` from `tron_actorcore`. The actor:
- Connects to the tron hub (MHS) at startup
- Loads the `gen2` model to call into Gen2 (Subaru telescope control) for visit IDs and telescope status updates
- Dispatches commands to `Commands/AgccCmd.py` via the `opscore` keyword/protocol system

`AgccCmd` defines the command vocabulary in `self.vocab` (list of `(cmdName, argSpec, handler)` tuples) and typed key definitions in `self.keys`. Every command handler receives a `cmd` object.

### Command → Camera → Exposure Flow

```
AgccCmd.expose()
  → Camera.expose()                    # camera.py: validates readiness, selects cameras
    → Exposure(threading.Thread)       # expose.py: runs per-camera threads concurrently
      → cam.expose()                   # fli_camera (Cython) or fake_camera
      → photometry.measure()           # via multiprocessing queue (one process per camera)
        → centroidTools.getCentroidsSep()  # SEP source extraction + windowed moments
      → database.writeCentroidsToDB()
      → writeFits.wfits_combined() / wfits()
```

Each camera has its own `multiprocessing.Queue` pair and worker process (created at init in `photometry.createProc()`).

### Threading and Multiprocessing Model

- **Main actor thread** (`main.py`): Connects to tron hub; receives and dispatches commands via `AgccCmd`.
- **Command handler threads**: `Camera.expose()`, `Camera.setmode()` return immediately and spawn worker threads:
  - `Exposure` (threading.Thread): Per-exposure work; runs per-camera threads concurrently.
  - `Sequence` (threading.Thread): Timed loop of repeated `Exposure` instances.
  - `SetMode` (threading.Thread): Parallel mode changes across cameras.
- **Photometry worker processes** (multiprocessing.Process): One per camera, created at `Camera.__init__()`, runs centroiding in `photometry.worker()`. Communicates with `Exposure` via queues.
- **Global exposure counter** (`Exposure.n_busy`, `Exposure.exp_lock`): Shared class-level state protected by a single lock across all `Exposure` instances and visits (intentional for global coordination).

**Thread-safety note**: The multiprocessing worker processes and per-camera threads are independent and do not hold a global lock during exposure. Database writes happen after image readout and centroiding complete. Caution when adding concurrent operations.

### Camera Indexing

- Cameras are **0-indexed internally** (array indices, `cam.agcid`)
- Cameras are **1-indexed in all commands and user-facing output** (e.g., `agc1_stat`, `cameras=123`)
- `nCams = 6` throughout; `self.cams` is always a fixed 6-element list with `None` for absent cameras

### `cmd` Object Protocol

All handlers use the tron `cmd` object consistently:
- `cmd.inform(...)` — informational keyword reply (not final)
- `cmd.warn(...)` — warning, not final
- `cmd.fail(...)` / `cmd.error(...)` — error, terminates command
- `cmd.finish(...)` — success, terminates command
- `cmd.respond(...)` — reply without finishing
- `cmd.debug(...)` — debug-level message

Every command handler **must** call exactly one of `finish`/`fail` to complete the command. Exposure and setmode operations do this inside their threads.

### Configuration

Runtime parameters are read from `$PFS_INSTDATA_DIR/config/actors/agcc.yaml`:
- `agcc.centroidParams` — SEP thresholds, min area, deblend, ellipticity
- `agcc.cameraParams` — per-camera regions, bad columns, saturation values, magnitude fit coefficients

The actor config (camera serial numbers, TEC temperature, simulator flag, DB connection) is loaded by `tron_actorcore` from an EUPS product config file.

### FITS Output

- **Combined** (one file, 6 extensions): `agcc_{visitId:06d}_{agc_exposure_id:08d}.fits`
- **Individual** (one file per camera): `agcc_{visitId:06d}_{agc_exposure_id:08d}_cam{N}.fits`
- Written to `/data/raw/YYYY-MM-DD/agcc/`
- Each FITS file contains image data and, when centroiding is enabled, a binary table extension with spot centroids and moments

### Database (OpDB)

`database.py` writes to the PFS OpDB via `pfs.utils.database.opdb.OpDB`:
- `pfs_visit` table — visit record
- `agc_exposure` table — per-exposure record with telescope/environmental metadata from `tel_status` and `env_condition`
- `agc_data` table — per-spot centroid results (bulk insert via pandas DataFrame)

`agc_exposure_id` is obtained by querying `MAX(agc_exposure_id) + 1` from `agc_exposure` at exposure start.

## Key Conventions

- **camelCase is intentional**: ruff rules N802/N803/N806/N815/N816 are suppressed. Methods and variables use camelCase throughout (e.g., `expTime`, `pfsVisitId`, `writeFits`, `getCentroidsSep`).
- **Line length**: 110 characters (ruff enforced).
- **Ruff rules**: E, F, I selected. Docstrings follow numpy convention (`pydocstyle`).
- **Simulator mode**: Set `simulator: 1` in actor config to use `fli/fake_camera.py` instead of the Cython FLI extension. Simulator can load a FITS file path via `simulatedImagePath`.
- **Required environment variables**:
  - `PFS_INSTDATA_DIR` — path to `pfs_instdata` product, needed to read `agcc.yaml`
  - `ICS_MHS_DATA_ROOT` — data output root (referenced in `expose.py`; `writeFits.py` currently hardcodes `/data/raw`)
- **Version**: Managed by `lsst-versions`; written to `python/agccActor/version.py` at build time via `[tool.lsst_versions]` in `pyproject.toml`.
- **EUPS/ups**: The `ups/ics_agccActor.table` file declares EUPS dependencies (`ics_actorkeys`, `tron_actorcore`, `pfs_utils`). This is the legacy EUPS build system used at Subaru alongside the modern `pyproject.toml`.

## Import Conventions and Gotchas

**Bare relative imports** are used throughout (e.g., `import camera`, `from expose import Exposure`, `import centroidTools as ct`). These work only because tron's actor loader manipulates `sys.path`. They are fragile and enable unconditional import of `fli_camera` even in simulator mode (see issue #5 in REFACTORING.md). When refactoring, prefer fully-qualified imports (e.g., `from agccActor.expose import Exposure`); see REFACTORING.md issue #16 for context.

Code uses both styles inconsistently:
- **Bare relative** (requires sys.path shim): `camera.py`, `expose.py`, `sequence.py`, `setmode.py`, `photometry.py`, `Commands/AgccCmd.py`
- **Fully qualified** (portable): `from agccActor import centroidTools as ct` (used in `photometry.py` and recommended for new code)

## Known Issues and Refactoring Notes

The codebase has a comprehensive list of known bugs, code quality issues, and refactoring recommendations documented in `REFACTORING.md`. Key categories include:

- **Critical bugs** (#1–6, #8): Runtime crashes (NameError in sequence start, cmd.inform with None guard, undefined cParms/iParms, targetTemp scoping, unconditional fli_camera import, photometry.measure() NameError).
- **High-priority issues** (#7, #9, #16, #25, #30, #32): None-dereference safety, hardcoded paths, fragile imports, thread-unsafe state, type errors, and missing tests.
- **Medium-priority improvements** (#12, #18, #20, #23, #24, #29, #34, #35, #36, #38): Refactor opportunities, correctness, and observability.

**When making changes**, consult REFACTORING.md to avoid introducing or compounding existing issues. Several issues are marked resolved as of 2026-04-30 (writeFits.py issues #10, #11, #14).
