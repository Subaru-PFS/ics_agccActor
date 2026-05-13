# ics_agccActor

`ics_agccActor` is the **tron actor** for the Subaru Prime Focus Spectrograph (PFS) **Auto Guider Camera Control (AGCC)** subsystem. It controls up to 6 FLI USB CCD cameras used for telescope auto-guiding, manages exposures, runs source extraction / centroiding / photometry, and persists results to FITS files and the PFS operational database (OpDB).

The actor is part of the PFS Instrument Control Software (ICS) stack and is deployed at the Subaru Telescope.

---

## Features

- Controls up to 6 FLI USB CCDs concurrently (one worker thread + one photometry process per camera).
- Single exposures and timed exposure sequences with per-camera and global coordination.
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
│   ├── sequence.py            # Timed exposure sequences
│   ├── setmode.py             # Parallel mode/temperature changes
│   ├── photometry.py          # Per-camera photometry worker process
│   ├── centroid.py            # SEP-based source extraction helpers
│   ├── writeFits.py           # FITS output (combined and per-camera)
│   ├── database.py            # OpDB writes (pfs_visit, agc_exposure, agc_data)
│   ├── version.py             # Generated at build time by lsst-versions
│   └── fli/                   # FLI Cython extension + fake camera backend
├── tests/                     # (Currently empty — see Testing below)
├── ups/ics_agccActor.table    # Legacy EUPS dependency declaration
├── pyproject.toml             # Python build / lint / version config (Cython ext too)
├── pytest.ini                 # Pytest configuration
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

# Build the Cython FLI extension (real hardware only; needs libfli + libusb-1.0)
pip install -e .
```

In **simulator mode** (`simulator: 1` in the actor config) the Cython
extension is not required — `python/agccActor/fli/fake_camera.py` is
used instead.

### Hardware Setup (FLI USB cameras)

To use the FLI USB cameras you need `libusb-1.0` and the vendored FLI
library built on the host:

- **Library** — build the vendored FLI library under
  `c/libfli-1.999.1-180223/` by running `make` in that directory. The
  library talks to the cameras via `libusb-1.0` in userspace; no
  separate kernel driver is required.

When provisioning a new host, ensure the `pfs` users are in the
`plugdev` group and that a udev rule grants access to the FLI vendor /
product IDs.

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

# Tests (see note below)
uv run pytest
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

The codebase currently has **minimal automated test coverage**.
`pyproject.toml` declares a `tests/` directory but it is essentially
empty. For now, test changes manually in **simulator mode**
(`simulator: 1`) using `fli/fake_camera.py`, optionally pointing
`simulatedImagePath` at a representative FITS frame.

Contributions adding real test coverage are very welcome.

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
