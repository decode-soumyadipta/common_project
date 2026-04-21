#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="$ROOT_DIR/src/offline_gis_app/client_frontend/web_assets/cesium"
VERSION="${1:-1.133.1}"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

TARBALL="$TMP_DIR/cesium.tgz"
URL="https://registry.npmjs.org/cesium/-/cesium-${VERSION}.tgz"

echo "Downloading Cesium ${VERSION}..."
curl -fsSL "$URL" -o "$TARBALL"

echo "Extracting Cesium build..."
tar -xzf "$TARBALL" -C "$TMP_DIR"

rm -rf "$TARGET_DIR"
mkdir -p "$(dirname "$TARGET_DIR")"
cp -R "$TMP_DIR/package/Build/Cesium" "$TARGET_DIR"

echo "Cesium assets installed at: $TARGET_DIR"
