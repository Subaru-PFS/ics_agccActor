# Changelog

All notable changes to `ics_agccActor` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased] — tickets/INSTRM-2928-02

### Added

- **Automated test suite** — 100 pytest tests across six new files covering the full
  actor pipeline: `test_camera.py` (fake camera + `Camera` controller), `test_centroid_replay.py`
  (record/replay against real FLI hardware FITS from visit 143362), `test_db_routines.py`
  (`database.py` OpDB writes), `test_exposure.py` (`Exposure` thread lifecycle and error
  paths), `test_photometry_worker.py` (photometry worker, timeout, synthetic-image
  detection), and `test_writeFits.py` (`wfits` / `wfits_combined`).
- **Real hardware test fixtures** (`tests/data/run28/`) — four combined FITS files and
  two OpDB CSV exports from a production AGC run (visit 143362) are committed via
  **Git LFS** and used by record/replay tests to guard against centroiding regressions.
  The `images/run28/` symlink remains supported as a local-developer fallback.
- **`pytest-cov` coverage reporting** — `pytest-cov` added to dev dependencies; coverage
  config (`[tool.coverage.run/report]`) added to `pyproject.toml`. Run with
  `uv run pytest --cov=agccActor --cov-report=term-missing` locally.
- **GitHub Actions CI** (`.github/workflows/tests.yml`) — runs on every PR and push to
  `master`/`main`: checks out with LFS, clones `Subaru-PFS/pfs_instdata`, lints with
  `ruff`, runs the full test suite with coverage, posts an updating PR comment with
  the coverage table (no third-party provider), and uploads an HTML coverage artifact.
- **`build-extension` CI job** — second GHA job that installs `libusb-1.0-0-dev`, builds
  the vendored FLI C library (`make` in `c/libfli-1.999.1-180223/`), and then builds the
  Cython `fli_camera` extension via `pip install -e . --no-build-isolation`. An explicit
  import verification step (`from agccActor.fli import fli_camera`) catches silent build
  failures caused by `optional = true` in `pyproject.toml`.
- **`PFS_INSTDATA_DIR` auto-discovery** — `tests/conftest.py` now searches for a
  `pfs_instdata` sibling checkout at `../pfs_instdata` and `../../pfs_instdata` when
  `PFS_INSTDATA_DIR` is not exported, so the `real_data` tests run without manual
  configuration in standard ICS checkout layouts.
- **Shared test fixtures** (`tests/conftest.py`) — `mock_cmd`, `mock_opdb`,
  `real_data_path`, and `pfs_instdata` fixtures; stubs for `pfs.utils.database.opdb`
  and `pfs.utils.datamodel.ag.SourceDetectionFlag` so tests run without the full PFS
  stack installed. Fork-mode multiprocessing forced on macOS for worker-process tests.

### Changed

- **`pytest.ini` removed** — pytest configuration consolidated entirely into
  `pyproject.toml` (`[tool.pytest.ini_options]`). The `real_data` marker is now
  registered there. `addopts` no longer forces `--cov` by default; pass coverage flags
  explicitly when needed.
- **`README.md`** — Testing section expanded with test file table, marker documentation,
  `PFS_INSTDATA_DIR` auto-discovery explanation, Git LFS instructions, and CI overview.
  Repository layout updated to include `tests/data/run28/` and `.github/workflows/`.

### Fixed

- **`tests/conftest.py`** — replaced empty `OpDB` stub (caused `AttributeError` on
  `set_default_connection`) with a proper class that has a no-op classmethod; added all
  six `SourceDetectionFlag` members required by `centroid.py`.
- **`tests/test_db_routines.py`** — corrected stale import (`dbRoutinesAGCC` → `database`)
  that caused the entire file to error on collection.
- **`photometry.py`** — `measure()` now returns `None` for unsupported centroid methods
  instead of raising `UnboundLocalError` (the `result` variable was only assigned inside
  the `if cMethod == "sep"` block).
- **`expose.py`** — all `self.cmd.*` calls in `Exposure.__init__` and `run()` are now
  consistently guarded with `if self.cmd:` (cmd is documented as optional but was called
  unconditionally in several places, causing `AttributeError` when `cmd=None`). Fixed
  `"Turing"` → `"Turning"` typos in TEC status messages.
- **`fli/fake_camera.py`** — FITS file opened in `Camera.__init__` is now closed via a
  context manager, preventing a file-descriptor leak in long-running simulator sessions.
- **`pyproject.toml`** — corrected `[project.urls]` that pointed at the wrong repository
  (`ics_agActor`); removed stale `per-file-ignores` entry for deleted `sequence.py`.
- **`README.md`** — removed `sequence.py` and `pytest.ini` from the repository layout
  (both deleted in this PR); removed "timed exposure sequences" from the feature list.
- **`tests/test_exposure.py`** — replaced no-op assertion (`assert not exp.is_alive() or True`)
  with a meaningful check that `cam.spots` is set after inline photometry completes.

### Changed

- **Renamed `centroidTools.py` → `centroid.py`** and **`dbRoutinesAGCC.py` →
  `database.py`** for clearer, less actor-specific module names. All imports and
  references updated accordingly.
- **Renamed `doc/` → `docs/`** to follow conventional documentation directory naming;
  the old `doc/README` is replaced by the new top-level `README.md`.
- **Simulator-friendly `fli_camera` import** — the Cython `fli_camera` extension is no
  longer imported unconditionally; when `simulator: 1` is set in actor config, the
  actor starts without requiring the compiled extension (only `fake_camera` is
  imported). This unblocks development and CI on machines without `libfli` /
  `libusb-1.0`.

### Refactored

- **`writeFits.py` cleanup and modernisation** — removed the legacy time-based
  `filename` (a leftover from the removed `sequence` command) and now use a single
  `pfsFilename` (`agcc_{visitId:06d}_{nframe:08d}[_cam{N}].fits`) throughout. Adopted
  `pathlib.Path` for all path handling, factored shared logic into `_outputDir()`,
  `_spotsTableHDU()`, and `_fillImageHeader()` helpers, dropped dead `os.symlink` /
  commented-out code, fixed `wfits()` writing the with-spots branch to the stale
  `filename` instead of `pfsFilename`, fixed the misleading "NOT written" status
  message, and made `wfits_combined()` robust to an empty `cams` list. The legacy
  `seq_id` kwarg is kept (deprecated and ignored) for backward compatibility with
  `expose.py`.
- **Numpy-style docstrings** — rewrote docstrings of every function and method across
  the `agccActor` Python module (`camera.py`, `centroid.py`, `expose.py`, `setmode.py`,
  `photometry.py`, `writeFits.py`, `main.py`, and `Commands/AgccCmd.py`) into numpy
  style for consistency, and added simple type hints to signatures where trivial.
- **Fully-qualified imports** — all bare relative imports (e.g., `import camera`,
  `from expose import Exposure`) across `camera.py`, `expose.py`, `setmode.py`,
  `photometry.py`, and `Commands/AgccCmd.py` have been replaced with fully-qualified
  package imports (e.g., `from agccActor.expose import Exposure`). This removes the
  dependency on the `sys.path` shim injected by the tron actor loader.
- **Ruff sweep** — applied `ruff format` and `ruff check` (including `--unsafe-fixes`)
  across `python/`, with subsequent manual cleanups. Includes f-string modernisation
  (legacy `%`-style and `.format()` formatting converted to f-strings where
  straightforward) and other small style/lint fixes.

### Removed

- **All sequence / `startsequence` functionality** — `python/agccActor/sequence.py`
  and the `startsequence` (and related) commands in `Commands/AgccCmd.py` have been
  removed. The sequence code was broken and unused in production; it will be easier to
  reintroduce from scratch if needed.
- **Exposure ID written to `nframe.txt`** - No longer write the exposure id to the
  plain text file. It appears to be legacy code and is not read by anything.
- **`python/agccActor/checkit.py`** — leftover development script that called a
  non-existent function (`ct.getCentroids`), contained a hardcoded developer path, and
  had no production purpose.
- **`python/agccActor/agparms.ipynb`** — stale scratch notebook committed by mistake.
- **`fittedFWHM` / `gaussian` in `centroidTools.py` (now `centroid.py`)** — Gaussian-fit
  FWHM path that was never called in production (the call site had been commented out
  in favour of `windowedFWHM`). Removed along with the `lmfit` import it required.
- **Legacy `doc/README`** — superseded by the new top-level `README.md`.
- **Dead commented-out code** — removed stale commented-out code blocks from
  `camera.py` (leftover `cam.close()` / `os.kill()` snippets in `connectCamera`
  and `closeCamera`), `Commands/AgccCmd.py` (commented `connectCamera` call in
  `reconnect`, commented `setCentroidParams` call in `expose`), `centroid.py`
  (commented dynamic FWHM `spots['x2'].mean()` lines and the dead `fittedFWHM`
  call site), and `main.py` (orphan `# To work` placeholder comment).

---

## [1.2.22] — tickets/INSTRM-2920

### Fixed

- Catch and report errors raised by per-camera photometry worker processes instead of
  silently losing them.

---

## [1.2.21] — tickets/INSTRM-2812-hotfix

### Fixed

- Fix default OpDB connection parameters (host/port) broken by the 1.2.20 migration.

---

## [1.2.20] — tickets/INSTRM-2812

### Changed

- Migrate all database access to `pfs_utils.database.opdb.OpDB`; remove direct
  `psycopg2` usage from `dbRoutinesAGCC.py`.

---

## [1.2.19] — tickets/INSTRM-2785

### Removed

- Delete the old unused `windowedCentroid/` directory.

---

## [1.2.18]

### Fixed

- Explicit Python type cast when writing centroid data to the DB to work around a NumPy
  type-serialisation regression.

---

## [1.2.17] — tickets/INSTRM-2698

### Fixed

- Be more defensive around `expose_thr` exceptions: catch and log failures from
  per-camera exposure threads so one bad camera does not silently stall the whole
  exposure.

---

## [1.2.15] — tickets/INSTRM-2588

### Changed

- Add structured exception handling and logging around photometry measurements inside
  the threaded exposure run code.

---

## [1.2.14] — tickets/INSTRM-2585

### Added

- `pfs_utils` declared as an explicit dependency.

### Changed

- Use `SourceDetectionFlags` enumeration from `pfs_utils` for centroid flag values.

---

## [1.2.13] — tickets/INSTRM-2559

### Changed

- Updates to `centroidTools.py`: revised SEP-based centroid extraction parameters and
  moment calculations.

---

## [1.2.12] — tickets/INSTRM-2558

### Added

- Per-amplifier saturation calculation instead of a single image-wide value.

### Fixed

- Better exception handling when `pfs_instdata` centroid/camera parameter config is
  missing or malformed.

---

## [1.2.11] — tickets/INSTRM-2555

### Fixed

- Pass the current `visit` ID to `gen2.updateTelStatus` so telescope-status keywords
  are recorded against the correct visit.

---

## [1.2.10] — tickets/INSTRM-2496

### Changed

- Replace row-by-row DB inserts for centroid data with a bulk insert via pandas
  `DataFrame` for improved performance.

---

## [1.2.9] — tickets/INSTRM-2372 / INSTRM-2449

### Fixed

- Handle `NaN` values gracefully when inserting centroid rows into the database.

### Changed

- Add flag for flat-topped (saturated-core) sources in centroid output.

---

## [1.2.8] — tickets/INSTRM-2218

### Fixed

- Correct exposure-time units in `expose.py` (was off by a factor of 1000).

### Changed

- Improved hot-pixel filtering and flagging in centroid detection.

---

## [1.2.7]

### Added

- Bundle required FLI C library into the repository.

---

## [1.2.6] — tickets/INSTRM-2060

### Fixed

- Corrected Gaia magnitude scaling calculation (flux was not divided by exposure time
  before converting to magnitude).

---

## [1.2.5] — tickets/INSTRM-2098

### Added

- `shutter` command for manual shutter open/close operation, wired through Cython,
  `camera.py`, and `AgccCmd.py`.

---

## [1.2.4] — tickets/INSTRM-1978

### Changed

- Update telescope metadata fields written to `agc_exposure` (coordinates, rotator
  angle, focus position).

---

## [1.2.3] — tickets/INSTRM-2004

### Added

- `cameraInit` command and `CameraInit` thread class to (re-)initialise individual
  cameras without restarting the actor.
- `reloadCamera` command for hot-reloading a single camera connection.

### Fixed

- Correctly terminate photometry worker processes when a camera is closed.
- Fix reconnect logic in `camera.py`.

---

## [1.2.2] — tickets/INSTRM-1962

### Fixed

- Fix TEC (thermo-electric cooler) temperature reporting: keyword values were not being
  updated correctly after the camera polling loop.

---

## [1.2.1]

### Fixed

- Fix database write bug in centroid insertion.
- Handle the case where SEP detects zero sources (avoid divide-by-zero / empty insert).

---

## [1.2.0] — tickets/INSTRM-1948

### Changed

- Consolidate database writes into a single bulk-insert call per exposure.

---

## [1.1.4] — tickets/INSTRM-1892

### Added

- Empirical Gaia magnitude estimate from SEP `FLUX` (moment-0) values written to
  `agc_data.estimated_magnitude`.

---

## [1.1.3]

### Fixed

- Simulator compatibility fixes for Yoshida-san's test environment.

---

## [1.1.2]

### Fixed

- Correct YAML actor configuration file bugs that prevented startup.

---

## [1.1.1] — tickets/INSTRM-1799

### Changed

- Adjust centroid detection flag bit definitions.

---

## [1.1.0] — tickets/INSTRM-1789

### Changed

- Revised flag-setting logic in `centroidTools.py`.

---

## [1.0.7]

### Changed

- Switch edge-proximity detection from dynamic to fixed pixel-distance thresholds.

---

## [1.0.6]

### Fixed

- Enforce normal Python scalar types when sending `centroidParams` over MHS (NumPy
  scalar types caused keyword serialisation errors).

---

## [1.0.5]

### Fixed

- Miscellaneous bug fixes.

---

## [1.0.4] — tickets/INSTRM-1796

### Fixed

- Use the database-assigned `agc_exposure_id` (from `MAX(agc_exposure_id)+1`) instead
  of a local counter, ensuring uniqueness across actor restarts.

### Changed

- Improved diagnostic log messages for exposure and DB write failures.

---

## [1.0.3]

### Fixed

- Correct Cython extension compilation order in `setup.py`.

---

## [1.0.2]

### Fixed

- Correct FITS output filename (`agc_fitsfile` header keyword and on-disk path).

---

## [1.0.1] — tickets/INSTRM-1764

### Changed

- Adopt final `agcc_{visitId:06d}_{agc_exposure_id:08d}.fits` filename convention.
- Update actor configuration (connection settings).

---

## [1.0.0] — tickets/INSTRM-1717

### Added

- Initial production release.
- FLI USB CCD camera control via Cython extension; parallel readout of up to 6 cameras.
- SEP-based centroid extraction (`centroidTools.getCentroidsSep`).
- FITS output (combined 6-extension file and per-camera files).
- PFS OpDB integration: writes `pfs_visit`, `agc_exposure`, and `agc_data` tables.
- Exposure time stored in seconds in both FITS headers and the database.
