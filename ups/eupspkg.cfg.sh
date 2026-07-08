# ups/eupspkg.cfg.sh
# shellcheck shell=bash

# Skip the default config phase 
config() { :; }

# Phase 1: Compile the underlying C library dependency
build() {
    echo "==> [EUPS] Building vendored libfli C library..."
    make -C "c/libfli-1.999.1-180223" libfli.a
}

# Phase 2: Compile the Cython code and install to the EUPS tree
install() {
    echo "==> [EUPS] Building and installing fli_camera Cython extension via pip..."
    
    # We bypass default_install entirely and use modern pip.
    # --no-deps prevents pulling GitHub packages (EUPS handles them).
    # --no-build-isolation forces the use of the EUPS-loaded Cython/numpy.
    pip install . \
        --prefix="$PREFIX" \
        --no-deps \
        --no-build-isolation
}
