from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from urllib.parse import urlparse

import httpx

from offline_gis_app.config.settings import settings
from offline_gis_app.server_backend.routes.health import API_BUILD


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
        ready, _ = self._health_state()
        return ready

    def _health_state(self) -> tuple[bool, bool]:
        """Return (ready, stale_build_detected)."""
        try:
            response = httpx.get(self._health_url, timeout=2.0)
            if not response.is_success:
                return False, False
            payload = (
                response.json()
                if "application/json" in (response.headers.get("content-type") or "")
                else {}
            )
            api_build = payload.get("api_build") if isinstance(payload, dict) else None
            stale = api_build not in {None, API_BUILD}
            # Treat unknown/missing build as stale so old API processes are replaced.
            if api_build is None:
                stale = True
            return (not stale), stale
        except httpx.HTTPError:
            return False, False
        except Exception:  # noqa: BLE001
            return False, False

    def ensure_running(self) -> bool:
        ready, stale = self._health_state()
        if ready:
            return True
        if stale and self._can_autostart:
            self._logger.warning(
                "Detected stale API build on %s; replacing local server", self._base_url
            )
            self._terminate_local_server_on_port()
        if not self._can_autostart:
            self._logger.info(
                "Skipping API auto-start for non-local base URL: %s", self._base_url
            )
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
        command = (
            sys.executable,
            "-m",
            "uvicorn",
            "offline_gis_app.server_backend.app:app",
            "--host",
            settings.api_host,
            "--port",
            str(settings.api_port),
        )
        env = os.environ.copy()
        self._process = subprocess.Popen(command, env=env)
        self._logger.warning("Auto-started API process pid=%s", self._process.pid)

    def _terminate_local_server_on_port(self) -> None:
        """Best-effort terminate any local process bound to configured API port."""
        port = str(settings.api_port)
        try:
            result = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}"],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Failed to inspect port %s listeners: %s", port, exc)
            return

        pids = [
            line.strip()
            for line in (result.stdout or "").splitlines()
            if line.strip().isdigit()
        ]
        for raw_pid in pids:
            pid = int(raw_pid)
            try:
                os.kill(pid, signal.SIGTERM)
                self._logger.warning(
                    "Terminated stale API process pid=%s on port=%s", pid, port
                )
            except ProcessLookupError:
                continue
            except Exception as exc:  # noqa: BLE001
                self._logger.warning(
                    "Failed to terminate pid=%s on port=%s: %s", pid, port, exc
                )

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
