#!/usr/bin/env bash
set -euo pipefail

export GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR
export GDAL_HTTP_MERGE_CONSECUTIVE_RANGES=YES

uvicorn titiler.application.main:app --host 127.0.0.1 --port 8081

