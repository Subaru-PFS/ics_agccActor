# ics_agccActor

`ics_agccActor` is the **tron actor** for the Subaru Prime Focus Spectrograph (PFS) **Auto Guider Camera Control (AGCC)** subsystem. It controls up to 6 FLI USB CCD cameras used for telescope auto-guiding, manages exposures, runs source extraction / centroiding / photometry, and persists results to FITS files and the PFS operational database (OpDB).

The actor is part of the PFS Instrument Control Software (ICS) stack and is deployed at the Subaru Telescope.

---

## Features

- Controls up to 6 FLI USB CCDs concurrently (one worker thread + one photometry process per camera).
- Single exposures with per-camera and global coordination.
- TEC (thermo-electric cooler) temperature control and status reporting.
- On-the-fly source extraction (SEP) with windowed-moment centroiding and basic photometry.
- Writes combined and per-camera FITS files with optional centroid binary table extensions.
- Inserts visit, exposure, and per-spot centroid records into the PFS OpDB.
- Talks to Subaru's Gen2 system (via the tron `gen2` model) for visit IDs and telescope status.
- Simulator mode using a fake FLI backend for development without hardware.

---

## Repository Layout

```
.
├── c/libfli-1.999.1-180223/   # Vendored FLI C library (used by the Cython extension)
├── python/agccActor/          # Actor Python package
│   ├── main.py                # Actor entry point (AgccActor)
│   ├── Commands/AgccCmd.py    # Command vocabulary and handlers
│   ├── camera.py              # Camera manager (fixed 6-slot array)
│   ├── expose.py              # Per-exposure threading
│   ├── setmode.py             # Parallel mode/temperature changes
│   ├── photometry.py          # Per-camera photometry worker process
│   ├── centroid.py            # SEP-based source extraction helpers
│   ├── writeFits.py           # FITS output (combined and per-camera)
│   ├── database.py            # OpDB writes (pfs_visit, agc_exposure, agc_data)
│   ├── version.py             # Generated at build time by lsst-versions
│   └── fli/                   # FLI Cython extension + fake camera backend
├── tests/                     # Automated test suite (pytest; see Testing below)
│   └── data/run28/            # Real hardware FITS + CSV fixtures (Git LFS)
├── .github/workflows/         # GitHub Actions CI (tests + coverage)
├── ups/ics_agccActor.table    # Legacy EUPS dependency declaration
├── pyproject.toml             # Python build / lint / version config (Cython ext too; pytest config)
├── uv.lock                    # uv lockfile
├── AGENTS.md                  # Agent / contributor reference
└── REFACTORING.md             # Known issues and refactoring notes
```

---

## Requirements

- Python **3.12+** (as declared by `requires-python` in `pyproject.toml`; the repository's `.venv` uses 3.13).
- A working **tron / MHS** environment with `tron_actorcore` and `ics_actorkeys`.
- `pfs_utils` (for `pfs.utils.database.opdb`) and access to the PFS OpDB.
- For real-hardware runs:
  - `libusb-1.0` available on the system.
  - The vendored FLI C library under `c/libfli-1.999.1-180223/` builds into the `fli_camera` Cython extension.
- Optional: [`uv`](https://github.com/astral-sh/uv) for dependency management (used in the examples below).

### Environment Variables

- `PFS_INSTDATA_DIR` — path to the `pfs_instdata` product. Required to read
  `$PFS_INSTDATA_DIR/config/actors/agcc.yaml`.
- `ICS_MHS_DATA_ROOT` — data output root (referenced in `expose.py`).
  Note: `writeFits.py` currently hardcodes `/data/raw` for FITS output.

---

## Installation

```bash
# Create / sync the virtual environment with dev extras
uv sync --extra dev
```

In **simulator mode** (`simulator: 1` in the actor config) the Cython
extension is not required — `python/agccActor/fli/fake_camera.py` is
used instead and no further build steps are needed.

### Building the FLI Cython extension (real hardware only)

The `fli_camera` Cython extension links against the vendored FLI C library.
Building requires two steps:

**1. Build the FLI C library** (needs `libusb-1.0`):

```bash
sudo apt-get install libusb-1.0-0-dev

cd c/libfli-1.999.1-180223
make libfli.a   # only the library target; 'make all' also needs ncurses
```

**2. Build and install the Python extension:**

```bash
pip install -e . --no-build-isolation
```

`--no-build-isolation` is required so the build can locate the pre-built
`libfli.a`. Without it, setuptools' isolated build environment cannot find
the library.

Or use the convenience script: `./scripts/build_fli.sh [--test]`

**Verify the build succeeded:**

```bash
python -c "from agccActor.fli import fli_camera; print('OK')"
```

> **Note:** `optional = true` in `pyproject.toml` means `pip install`
> silently succeeds even if the extension fails to compile. Always run
> the import check above to confirm the build.

**Host provisioning (new machines):** ensure the `pfs` user is in the `plugdev` group and add a udev rule for the FLI USB vendor/product IDs:

In `/etc/group`:
```
plugdev:x:46:pfs,pfs-data
```

In `/etc/udev/rules.d/99-agc.rules`:
```
SUBSYSTEM=="usb", ACTION=="add", ATTRS{idVendor}=="0f18", ATTRS{idProduct}=="000a", GROUP="plugdev"
```

---

## Configuration

Two layers of configuration are involved:

1. **Actor config** (loaded by `tron_actorcore` from the EUPS product
   config): camera serial numbers, target TEC temperature, OpDB
   connection parameters, `simulator: 0 | 1` flag, and optionally
   `simulatedImagePath` to load a FITS file as the simulated frame.

2. **Runtime parameters** in `$PFS_INSTDATA_DIR/config/actors/agcc.yaml`:
   - `agcc.centroidParams` — SEP thresholds, minimum area, deblending,
     ellipticity cuts.
   - `agcc.cameraParams` — per-camera regions of interest, bad columns,
     saturation values, magnitude calibration coefficients.

---

## Architecture Overview

```
AgccCmd.expose()
  └─ Camera.expose()                  # validates readiness, selects cameras
       └─ Exposure (threading.Thread) # per-exposure, runs per-camera threads
            ├─ cam.expose()           # fli_camera (Cython) or fake_camera
            ├─ photometry.measure()   # via multiprocessing queue (1 proc / camera)
            │     └─ centroid.getCentroidsSep()
            ├─ database.writeCentroidsToDB()
            └─ writeFits.wfits_combined() / wfits()
```

Key conventions:

- Cameras are **0-indexed internally** but **1-indexed in user-facing
  commands and keywords** (e.g., `agc1_stat`, `cameras=123`).
- `nCams = 6` and `self.cams` is always a fixed-length 6-element list
  with `None` for absent cameras.
- Every command handler must terminate with exactly one
  `cmd.finish(...)` or `cmd.fail(...)` (typically from inside the
  worker thread).
- A class-level lock (`Exposure.exp_lock`) and counter
  (`Exposure.n_busy`) coordinate exposures globally across visits.

For more detail, see [`AGENTS.md`](AGENTS.md).

---

## FITS Output

- **Combined** (single file, 6 image extensions):
  `agcc_{visitId:06d}_{agc_exposure_id:08d}.fits`
- **Per-camera**:
  `agcc_{visitId:06d}_{agc_exposure_id:08d}_cam{N}.fits`
- Written under `/data/raw/YYYY-MM-DD/agcc/`.
- When centroiding is enabled, each FITS file includes a binary table
  extension with spot centroids and moments.

## Database (OpDB)

`database.py` writes to the PFS OpDB via
`pfs.utils.database.opdb.OpDB`:

- `pfs_visit` — visit record.
- `agc_exposure` — per-exposure record with telescope and environmental
  metadata (`tel_status`, `env_condition`).
- `agc_data` — per-spot centroid results (bulk-inserted from a pandas
  DataFrame).

`agc_exposure_id` is assigned as `MAX(agc_exposure_id) + 1` at the start
of each exposure.

---

## Development

```bash
# Lint
uv run ruff check python/

# Format
uv run ruff format python/

# Tests
uv run pytest

# Tests with coverage (terminal)
uv run pytest --cov=agccActor --cov-report=term-missing

# Tests with coverage (HTML — open htmlcov/index.html)
uv run pytest --cov=agccActor --cov-report=html
```

### Code Style

- **camelCase is intentional** — ruff rules `N802/N803/N806/N815/N816`
  are suppressed. Names like `expTime`, `pfsVisitId`, `writeFits`,
  `getCentroidsSep` follow Subaru / PFS conventions.
- Line length: **110**.
- Ruff rule selection: `E`, `F`, `I`. Docstrings follow the numpy
  convention (`pydocstyle`).
- New code should prefer **fully-qualified imports**
  (e.g., `from agccActor import centroid as ct`) rather than the
  bare relative imports used in older modules. See `REFACTORING.md`
  issue #16.

### Testing

The test suite lives in `tests/` and is run with:

```bash
uv run pytest
```

**131 tests** are collected across six files:

| File | What it covers |
|---|---|
| `test_camera.py` | `fake_camera` unit tests and `Camera` controller (simulator mode) |
| `test_centroid_replay.py` | Record/replay against real hardware FITS data (`images/run28/`) |
| `test_db_routines.py` | OpDB write functions in `database.py` |
| `test_exposure.py` | `Exposure` thread lifecycle, error paths, FITS output |
| `test_photometry_worker.py` | Photometry worker process, timeout handling, synthetic-image detection |
| `test_writeFits.py` | `wfits` (per-camera) and `wfits_combined` FITS output |

#### Test markers

- **`real_data`** — tests that replay real FLI camera frames from `images/run28/`.
  These require two conditions (see below) and are skipped automatically when
  either is absent.  Run them explicitly with `pytest -m real_data`.
- **`fli_build`** — tests that verify the `fli_camera` Cython extension is compiled
  and importable.  Skipped if the extension has not been built.  Run after
  `scripts/build_fli.sh`:

  ```bash
  # Build then test
  ./scripts/build_fli.sh --test

  # Or just run the tests after a manual build
  uv run pytest -m fli_build -v
  ```

#### `PFS_INSTDATA_DIR` and auto-discovery

Several tests (and the production code) need
`$PFS_INSTDATA_DIR/config/actors/agcc.yaml` to be readable.  The test suite
resolves this in the following order:

1. **Exported env var** — if `PFS_INSTDATA_DIR` is already set in your shell,
   it is used as-is.
2. **Auto-discovery** — if the variable is *not* set, `conftest.py` searches
   for a `pfs_instdata` checkout in two sibling locations relative to this
   repository root:
   - `../pfs_instdata` (e.g., both repos checked out under a common `ICS/` folder)
   - `../../pfs_instdata` (two levels up)

   The first path that contains `config/actors/agcc.yaml` is used and
   `PFS_INSTDATA_DIR` is set automatically for the test process.

   If neither location contains the file and the variable is unset, any test
   that requires it will skip with a clear message rather than failing.

#### Real hardware data (`images/run28/`)

The centroid replay tests use real FLI camera frames from visit 143362
(4 combined exposures, 6 cameras each).  These files are stored in
`tests/data/run28/` using **Git LFS** — `git clone` fetches LFS pointers
by default, but you need `git lfs pull` if you cloned before LFS was set up:

```bash
git lfs pull
```

The `real_data` tests re-run `centroid.getCentroidsSep` on those frames and
compare results to the centroid tables embedded in the FITS files by the
production actor, providing regression coverage for the centroiding pipeline.

The `images/run28/` symlink (pointing to an external data directory) is also
accepted as a fallback for local developer machines that have the full data
mounted there.  `tests/data/run28/` takes priority when present.

### Versioning

The version is managed by
[`lsst-versions`](https://pypi.org/project/lsst-versions/) and written
to `python/agccActor/version.py` at build time, configured under
`[tool.lsst_versions]` in `pyproject.toml`.

### EUPS / ups

`ups/ics_agccActor.table` declares EUPS dependencies (`ics_actorkeys`,
`tron_actorcore`, `pfs_utils`). This is the legacy EUPS build system
used at Subaru alongside the modern `pyproject.toml`.

---

## See Also

- [`AGENTS.md`](AGENTS.md) — contributor / agent reference with deeper
  architectural notes.
- Subaru PFS project: https://pfs.ipmu.jp/
