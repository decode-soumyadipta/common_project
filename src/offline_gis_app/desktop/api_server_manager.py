from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from typing import Sequence
from urllib.parse import urlparse

import httpx

from offline_gis_app.config.settings import settings


class ApiServerManager:
    def __init__(self, base_url: str):
        self._logger = logging.getLogger("desktop.api_server")
        self._process: subprocess.Popen | None = None
        self._base_url = base_url.rstrip("/")
        self._health_url = f"{self._base_url}/health"
        self._can_autostart = self._is_local_base_url(self._base_url)

    @property
    def base_url(self) -> str:
        return self._base_url

    def is_ready(self) -> bool:
        try:
            response = httpx.get(self._health_url, timeout=2.0)
            return response.is_success
        except httpx.HTTPError:
            return False

    def ensure_running(self) -> bool:
        if self.is_ready():
            return True
        if not self._can_autostart:
            self._logger.info("Skipping API auto-start for non-local base URL: %s", self._base_url)
            return False
        self._start_process()
        for _ in range(30):
            if self.is_ready():
                self._logger.info("API server is ready")
                return True
            time.sleep(0.25)
        self._logger.error("API server failed health check after auto-start")
        return False

    def _start_process(self) -> None:
        if self._process and self._process.poll() is None:
            return
        command: Sequence[str] = (
            sys.executable,
            "-m",
            "uvicorn",
            "offline_gis_app.api.app:app",
            "--host",
            settings.api_host,
            "--port",
            str(settings.api_port),
        )
        env = os.environ.copy()
        self._process = subprocess.Popen(command, env=env)
        self._logger.warning("Auto-started API process pid=%s", self._process.pid)

    @staticmethod
    def _is_local_base_url(base_url: str) -> bool:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"}:
            return False
        host = (parsed.hostname or "").lower()
        if host not in {"127.0.0.1", "localhost"}:
            return False
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return port == int(settings.api_port)
