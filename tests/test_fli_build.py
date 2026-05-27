"""Verify the fli_camera Cython extension is built and importable.

These tests are skipped by default. Run them explicitly after building the
FLI extension (see scripts/build_fli.sh or README Hardware Setup):

    uv run pytest -m fli_build -v

The tests do NOT require FLI hardware to be connected — they only verify
that the compiled extension module can be imported and exposes the expected
public API.
"""

import pytest

try:
    from agccActor.fli import fli_camera as _fli_camera  # noqa: F401

    _FLI_AVAILABLE = True
except ImportError:
    _FLI_AVAILABLE = False

pytestmark = pytest.mark.fli_build

skip_if_not_built = pytest.mark.skipif(
    not _FLI_AVAILABLE,
    reason="fli_camera extension not built — run scripts/build_fli.sh first",
)


@skip_if_not_built
def test_fli_camera_importable():
    """fli_camera can be imported after the extension is built."""
    from agccActor.fli import fli_camera

    assert fli_camera is not None


@skip_if_not_built
def test_fli_camera_status_constants():
    """CLOSED/READY/EXPOSING/SETMODE state constants are present."""
    from agccActor.fli import fli_camera

    assert fli_camera.CLOSED == 0
    assert fli_camera.READY == 1
    assert fli_camera.EXPOSING == 2
    assert fli_camera.SETMODE == 3


@skip_if_not_built
def test_fli_camera_status_dict():
    """Status dict maps integer states to string labels."""
    from agccActor.fli import fli_camera

    assert fli_camera.Status[fli_camera.CLOSED] == "CLOSED"
    assert fli_camera.Status[fli_camera.READY] == "READY"
    assert fli_camera.Status[fli_camera.EXPOSING] == "EXPOSING"
    assert fli_camera.Status[fli_camera.SETMODE] == "SETMODE"


@skip_if_not_built
def test_fli_camera_public_functions():
    """Public functions required by camera.py are callable."""
    from agccActor.fli import fli_camera

    for name in ("numberOfCamera", "getLibVersion", "FliError"):
        assert hasattr(fli_camera, name), f"Missing: {name}"


@skip_if_not_built
def test_fli_camera_number_of_cameras_returns_int():
    """numberOfCamera() returns an int (may be 0 with no hardware attached)."""
    from agccActor.fli import fli_camera

    result = fli_camera.numberOfCamera()
    assert isinstance(result, int)


@skip_if_not_built
def test_fli_camera_lib_version_returns_string():
    """getLibVersion() returns a string (may be empty when no hardware is attached)."""
    from agccActor.fli import fli_camera

    version = fli_camera.getLibVersion()
    assert isinstance(version, str)


@skip_if_not_built
def test_fli_error_is_exception():
    """FliError is a proper Exception subclass."""
    from agccActor.fli import fli_camera

    assert issubclass(fli_camera.FliError, Exception)
    exc = fli_camera.FliError("test error")
    assert str(exc) == "test error"
