# ics_agccActor

`ics_agccActor` is a [tron](https://github.com/Subaru-PFS/tron_actorcore) actor for the Subaru PFS Auto Guider Camera Control (AGCC) subsystem. It controls up to six FLI USB CCD cameras, runs exposures with optional centroiding and photometry, and writes FITS outputs and exposure records to OpDB.

## Project structure

```
python/agccActor/
  Commands/AgccCmd.py   # tron command handlers
  fli/
    fli_camera.pyx      # Cython wrapper around libfli
    fake_camera.py       # software simulator (no hardware needed)
  camera.py             # camera abstraction layer
  expose.py             # exposure thread and sequencing
  centroidTools.py      # centroid and FWHM routines
  photometry.py         # photometry worker (sep-based)
  writeFits.py          # FITS output
  dbRoutinesAGCC.py     # OpDB read/write helpers
  sequence.py           # automated exposure sequences
  setmode.py            # readout mode configuration
  main.py               # actor entry point
c/libfli-1.999.1-180223/  # FLI C library source
docs/                      # hardware setup notes
tests/                     # pytest suite
```

## Actor commands

| Command | Description |
|---------|-------------|
| `ping` | Check actor liveness |
| `status` | Report camera status, version, and connection state |
| `expose` | Take an exposure (`test`, `dark`, or `object`) with optional centroiding |
| `abort` | Stop an in-progress exposure |
| `reconnect` | Reconnect to camera hardware |
| `shutter` | Open or close camera shutters |
| `setframe` | Configure ROI: binning (`bx`, `by`), corner (`cx`, `cy`), size (`sx`, `sy`) |
| `resetframe` | Reset to full-frame readout |
| `getmode` | Query readout mode (0 = 4 MHz, 1 = 500 KHz) |
| `setmode` | Set readout mode |
| `getmodestring` | Get readout mode as a human-readable string |
| `settemperature` | Set CCD temperature setpoint |
| `setregions` | Define regions of interest per camera |
| `startsequence` | Begin an automated exposure sequence |
| `stopsequence` | Halt a running sequence |
| `inusesequence` | Check whether a sequence slot is active |
| `inusecamera` | Check whether a camera is busy |
| `insertVisit` | Log a visit to OpDB |
| `setCentroidParams` | Configure centroid algorithm (`thresh`, `nmin`, `deblend`, etc.) |
| `setImageParams` | Configure image processing parameters |

## Configuration

The actor reads its config from `agcc.yaml`, located via the `PFS_INSTDATA_DIR` environment variable:

```
$PFS_INSTDATA_DIR/config/actors/agcc.yaml
```

Key settings in that file:

- **interface** — network interface for camera discovery (e.g. `agcc2`)
- **cameras** — serial numbers for up to 6 FLI cameras
- **temperature** — default CCD temperature setpoint
- **simulator** — `0` for hardware, `1` for simulator mode
- **centroidParams** — threshold, minimum area, deblend contrast, ellipticity limit
- **imageParams** — per-camera saturation values, bad columns, magnitude fit coefficients

## Requirements

- Python 3.12+
- `PFS_INSTDATA_DIR` set to an install that contains `config/actors/agcc.yaml`
- Optional: FLI hardware + built `fli_camera` Cython extension

## Install

```bash
uv sync --extra dev
```

## Building the FLI Cython extension

The hardware camera interface requires the Cython extension `fli_camera`, which wraps the vendored FLI C library.

1. Build the C library:

   ```bash
   cd c/libfli-1.999.1-180223
   make
   ```

2. Build the Cython extension:

   ```bash
   cd python/agccActor/fli
   python setup.py build_ext --inplace
   ```

This step is only needed for hardware mode. Simulator mode uses `fli/fake_camera.py` and has no native dependencies.

See [docs/hardware-setup.md](docs/hardware-setup.md) for USB driver and udev configuration on new machines.

## Running modes

- **Hardware mode** (`simulator: 0` in `agcc.yaml`): uses the built `fli_camera` Cython extension to talk to real FLI cameras over USB.
- **Simulator mode** (`simulator: 1`): uses `fli/fake_camera.py`, which returns synthetic images. No hardware or Cython extension required.

## Development checks

```bash
uv run ruff format python/
uv run ruff check python/
uv run pytest
```

## Environment variables

| Variable | Purpose |
|----------|---------|
| `PFS_INSTDATA_DIR` | Path to the PFS instrument data install containing `config/actors/agcc.yaml` |
| `ICS_MHS_DATA_ROOT` | Root directory for FITS output and exposure bookkeeping |
