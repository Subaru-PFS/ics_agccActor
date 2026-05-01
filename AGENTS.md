# ics_agccActor — Agent Reference

`ics_agccActor` is a **tron actor** for the Subaru Prime Focus Spectrograph (PFS) Auto Guider Camera Control (AGCC) subsystem. It controls up to 6 FLI USB CCD cameras, manages exposures, runs centroiding/photometry, and writes results to FITS files and the PFS operational database (OpDB).

## Build, Lint, and Test

```bash
# Install dev dependencies
uv sync --extra dev

# Lint
uv run ruff check python/

# Format
uv run ruff format python/

# Run tests
uv run pytest

# Build the Cython FLI extension (requires libfli in c/libfli-1.999.1-180223/)
pip install -e .
```

The Cython extension `fli_camera` (from `python/agccActor/fli/fli_camera.pyx`) must be built against the FLI C library in `c/libfli-1.999.1-180223/`. It requires `libusb-1.0`. When the FLI hardware is unavailable, `fli/fake_camera.py` is used instead (controlled by the `simulator` key in actor config).

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
      → dbRoutinesAGCC.writeCentroidsToDB()
      → writeFits.wfits_combined() / wfits()
```

Each camera has its own `multiprocessing.Queue` pair and worker process (created at init in `photometry.createProc()`).

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

`dbRoutinesAGCC.py` writes to the PFS OpDB via `pfs.utils.database.opdb.OpDB`:
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
