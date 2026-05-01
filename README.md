# ics_agccActor

`ics_agccActor` is a tron actor for the Subaru PFS Auto Guider Camera Control (AGCC) subsystem.

## What it does

- Controls up to 6 FLI USB CCD cameras.
- Runs exposures and optional centroiding/photometry.
- Writes FITS outputs and AGCC records to OpDB.

## Requirements

- Python 3.12+
- `PFS_INSTDATA_DIR` set to an install that contains `config/actors/agcc.yaml`
- Optional: FLI hardware + built `fli_camera` extension

## Install

```bash
uv sync --extra dev
```

## Development checks

```bash
uv run ruff format python/
uv run ruff check python/
uv run pytest
```

## Running modes

- Hardware mode: set actor config `simulator: 0` and use built FLI extension.
- Simulator mode: set actor config `simulator: 1`; the actor uses `fli/fake_camera.py`.
