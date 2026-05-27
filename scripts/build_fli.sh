#!/usr/bin/env bash
# build_fli.sh — Build the vendored FLI C library and the fli_camera Cython extension.
#
# Usage:
#   ./scripts/build_fli.sh           # native build (Linux)
#   ./scripts/build_fli.sh --test    # native build then run fli_build pytest tests
#
# Requirements (native build):
#   sudo apt-get install libusb-1.0-0-dev
#
# After a successful build you can verify independently with:
#   uv run pytest tests/test_fli_build.py -v

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIBFLI_DIR="$REPO_ROOT/c/libfli-1.999.1-180223"

echo "==> Building libfli C library..."
make -C "$LIBFLI_DIR" libfli.a

echo ""
echo "==> Building fli_camera Cython extension..."
cd "$REPO_ROOT"
uv run pip install -e . --no-build-isolation

echo ""
echo "==> Verifying import..."
uv run python -c "
from agccActor.fli import fli_camera
print(f'  fli_camera loaded OK')
print(f'  Library version: {fli_camera.getLibVersion()}')
print(f'  Cameras detected: {fli_camera.numberOfCamera()}')
"

echo ""
echo "Build successful."

if [[ "${1:-}" == "--test" ]]; then
    echo ""
    echo "==> Running fli_build tests..."
    cd "$REPO_ROOT"
    uv run pytest tests/test_fli_build.py -v
fi
