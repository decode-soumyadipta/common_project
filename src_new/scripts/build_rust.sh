#!/usr/bin/env bash
# build_rust.sh — Build the Rust accelerator crate and copy the compiled
# shared library into the rust_accelerators package directory so Python can
# import it via PyO3/maturin or ctypes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUST_DIR="$SCRIPT_DIR/../services/ingestion/rust_accelerators"

echo "[build_rust.sh] Building Rust crate in: $RUST_DIR"

# Require cargo
if ! command -v cargo &>/dev/null; then
    echo "ERROR: cargo not found. Install Rust via https://rustup.rs/" >&2
    exit 1
fi

# Build in release mode
(
    cd "$RUST_DIR"
    cargo build --release
)

echo "[build_rust.sh] Build complete."

# Copy the shared library next to __init__.py so Python can load it.
# The library name depends on the platform.
LIB_NAME="rust_accelerators"
TARGET_DIR="$RUST_DIR/target/release"

if [[ "$(uname)" == "Darwin" ]]; then
    SO_SRC="$TARGET_DIR/lib${LIB_NAME}.dylib"
    SO_DST="$RUST_DIR/${LIB_NAME}.so"
elif [[ "$(uname)" == "Linux" ]]; then
    SO_SRC="$TARGET_DIR/lib${LIB_NAME}.so"
    SO_DST="$RUST_DIR/${LIB_NAME}.so"
else
    SO_SRC="$TARGET_DIR/${LIB_NAME}.dll"
    SO_DST="$RUST_DIR/${LIB_NAME}.pyd"
fi

if [[ -f "$SO_SRC" ]]; then
    cp "$SO_SRC" "$SO_DST"
    echo "[build_rust.sh] Copied $SO_SRC -> $SO_DST"
else
    echo "WARNING: Expected shared library not found at $SO_SRC" >&2
    echo "         If using maturin, run 'maturin develop' inside $RUST_DIR instead." >&2
fi
