from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Sequence

import httpx

from offline_gis_app.config.settings import settings


class TiTilerManager:
    def __init__(self):
        self._logger = logging.getLogger("desktop.titiler")
        self._process: subprocess.Popen | None = None
        self._health_url = f"{settings.titiler_base_url.rstrip('/')}/healthz"

    def is_ready(self) -> bool:
        try:
            response = httpx.get(self._health_url, timeout=2.0)
            return response.is_success
        except httpx.HTTPError:
            return False

    def ensure_running(self) -> bool:
        if self.is_ready():
            return True
        self._start_process()
        for _ in range(20):
            if self.is_ready():
                self._logger.info("TiTiler is ready")
                return True
            time.sleep(0.25)
        self._logger.error("TiTiler failed health check after auto-start")
        return False

    def _start_process(self) -> None:
        if self._process and self._process.poll() is None:
            return
        command: Sequence[str] = (
            "uvicorn",
            "titiler.application.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8081",
        )
        env = os.environ.copy()
        env["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"
        env["GDAL_HTTP_MERGE_CONSECUTIVE_RANGES"] = "YES"
        self._process = subprocess.Popen(command, env=env)
        self._logger.warning("Auto-started TiTiler process pid=%s", self._process.pid)

