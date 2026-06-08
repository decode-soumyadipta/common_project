from __future__ import annotations

import contextlib
import logging
import os
import platform
import signal
import subprocess
import sys
import time
from urllib.parse import urlparse

import httpx

from src_new.shared.config import settings

# Note: server_gateway is only needed in UNIFIED/SERVER modes In CLIENT mode, we connect to external services
try:
    from server_gateway.api.routes.health import API_BUILD
except ImportError:
    API_BUILD = "unknown"  # Fallback for CLIENT mode


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
            
            # If we get a 200 OK, the server is at least alive. Try to parse JSON to detect stale builds.
            try:
                payload = response.json()
            except Exception:
                # 200 OK but not JSON yet? Might be starting up. Return ready=True to satisfy the wait loop, but stale=False.
                return True, False

            if not isinstance(payload, dict):
                return True, False

            api_build = payload.get("api_build")
            
            # If api_build is missing, it's either an old version or still initializing. We treat this as "ready" so the app can proceed, but not "stale".
            if api_build is None:
                return True, False
            
            stale = api_build != API_BUILD
            return (not stale), stale
        except httpx.HTTPError:
            return False, False
        except Exception:
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
        # Wait up to 20 seconds (80 * 0.25s) for the API to initialize DB/migrations
        for _ in range(80):
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
            "server_gateway.api.app:app",
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
        port = settings.api_port
        if platform.system() == "Windows":
            self._terminate_port_windows(port)
        else:
            self._terminate_port_unix(port)

    def _terminate_port_unix(self, port: int) -> None:
        """Terminate processes on a port using lsof (macOS/Linux)."""
        try:
            result = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}"],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:
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
            except Exception as exc:
                self._logger.warning(
                    "Failed to terminate pid=%s on port=%s: %s", pid, port, exc
                )

    def _terminate_port_windows(self, port: int) -> None:
        """Terminate processes on a port using netstat (Windows)."""
        try:
            result = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:
            self._logger.warning(
                "Failed to inspect port %s listeners on Windows: %s", port, exc
            )
            return

        pids: set[int] = set()
        for line in (result.stdout or "").splitlines():
            parts = line.split()
            # netstat -ano output: Proto  Local  Foreign  State  PID e.g. TCP  0.0.0.0:8000  0.0.0.0:0  LISTENING  1234
            if len(parts) < 5:
                continue
            local = parts[1]
            if local.endswith(f":{port}") and parts[-2].upper() in {
                "LISTENING",
                "ESTABLISHED",
            }:
                with contextlib.suppress(ValueError):
                    pids.add(int(parts[-1]))

        for pid in pids:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True,
                    check=False,
                )
                self._logger.warning(
                    "Terminated stale API process pid=%s on port=%s", pid, port
                )
            except Exception as exc:
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
