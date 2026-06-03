from __future__ import annotations

import logging
import os
import platform
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Sequence

import httpx


LOGGER = logging.getLogger("desktop.titiler_manager")


class TiTilerManager:
    """Manages the local TiTiler server process for on-the-fly COG rendering."""

    def __init__(self, port: int = 8081):
        self.port = port
        self._process: subprocess.Popen | None = None
        self._logger = LOGGER
        self.last_error: str | None = None
        self._stderr_buffer: list[str] = []
        self._drain_threads: list[threading.Thread] = []

    def is_port_in_use(self) -> bool:
        """Check if the target port is already being used."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            return s.connect_ex(("127.0.0.1", self.port)) == 0

    def ensure_running(self) -> bool:
        """Ensures TiTiler is running, either by starting a new one or adopting an existing one."""
        if self.is_running():
            return True

        # If port is in use but it's not us (is_running failed), try to 'adopt' it if it looks like TiTiler
        if self.is_port_in_use():
            self._logger.info("Port %d is in use. Checking if it's an existing TiTiler instance...", self.port)
            # Try a few common TiTiler/FastAPI paths
            for path in ["/health", "/openapi.json", "/"]:
                try:
                    resp = httpx.get(f"http://127.0.0.1:{self.port}{path}", timeout=1.0)
                    # Even if 404, if it's a FastAPI server it's likely our TiTiler from a previous run
                    if resp.status_code in (200, 404):
                        server_header = resp.headers.get("server", "").lower()
                        if "uvicorn" in server_header or resp.status_code == 200:
                            self._logger.info("Adopted existing TiTiler server on port %d", self.port)
                            return True
                except Exception:
                    continue
            
            self._logger.warning("Port %d is occupied by an unknown process.", self.port)
            self.last_error = f"Port {self.port} is already in use by a non-responsive or unknown process."
            # We will still try to start it (it will likely fail, but uvicorn will provide the error)
        
        self._logger.info("Starting local TiTiler server on port %d...", self.port)
        self._start_process()

        # Wait for health check with more patience and better logging
        for i in range(40):  # 20 seconds total
            if self.is_running():
                self._logger.info("TiTiler server started successfully")
                return True
            
            # Check if process died during startup
            if self._process:
                poll = self._process.poll()
                if poll is not None:
                    stderr_content = "".join(self._stderr_buffer)
                    self._logger.error("TiTiler process exited with code %d. Output: %s", poll, stderr_content)
                    self.last_error = stderr_content or f"Process exited with code {poll}"
                    return False

            if i % 10 == 0 and i > 0:
                self._logger.info("Waiting for TiTiler health check... (attempt %d/40)", i)
            time.sleep(0.5)

        self._logger.error("TiTiler failed health check after auto-start. Buffer: %s", "".join(self._stderr_buffer[-10:]))
        if not self.last_error:
            self.last_error = "TiTiler failed health check after auto-start"
        return False

    def is_running(self) -> bool:
        """Check if TiTiler is responsive on the configured port."""
        if self._process and self._process.poll() is not None:
            self._process = None
            return False

        try:
            # We check /health (new) then /openapi.json (default titiler)
            for path in ["/health", "/openapi.json"]:
                try:
                    resp = httpx.get(f"http://127.0.0.1:{self.port}{path}", timeout=0.8)
                    if resp.status_code == 200:
                        return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    def stop(self) -> None:
        if self._process:
            self._logger.info("Stopping TiTiler server...")
            self._process.terminate()
            try:
                self._process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        self._drain_threads = []

    def _start_process(self) -> None:
        if self._process and self._process.poll() is None:
            return

        self._stderr_buffer = []
        bootstrap_code = (
            "import sys, platform, re, uvicorn, os\n"
            "# Windows DLL shadowing fix: load shapely (GEOS) before rasterio (GDAL)\n"
            "try: import shapely\n"
            "except: pass\n"
            "from titiler.application.main import app\n"
            "from starlette.middleware.base import BaseHTTPMiddleware\n"
            "from starlette.requests import Request\n"
            "import urllib.parse\n"
            "\n"
            "class _WinPathFix(BaseHTTPMiddleware):\n"
            "    async def dispatch(self, request, call_next):\n"
            "        if platform.system() == 'Windows':\n"
            "            raw = request.scope.get('query_string', b'').decode('utf-8', errors='replace')\n"
            "            import urllib.parse\n"
            "            params = urllib.parse.parse_qsl(raw, keep_blank_values='url' in raw)\n"
            "            new_params = []\n"
            "            target_file = None\n"
            "            for k, v in params:\n"
            "                if k == 'url':\n"
            "                    # Normalize Windows paths (/C:/... -> C:/...)\n"
            "                    v = re.sub(r'^/([A-Za-z]:)', r'\\1', v)\n"
            "                    v = re.sub(r'^file:/{2,3}([A-Za-z]:)', r'\\1', v)\n"
            "                    v = v.replace('\\\\', '/')\n"
            "                    target_file = v\n"
            "                new_params.append((k, v))\n"
            "            \n"
            "            # Pre-emptive check: If file is missing, return 404 instead of letting GDAL crash with 500\n"
            "            if target_file and not os.path.exists(target_file):\n"
            "                from starlette.responses import JSONResponse\n"
            "                return JSONResponse({'detail': f'File not found: {target_file}'}, status_code=404)\n"
            "                \n"
            "            request.scope['query_string'] = urllib.parse.urlencode(new_params, quote_via=urllib.parse.quote).encode('utf-8')\n"
            "        try:\n"
            "            return await call_next(request)\n"
            "        except Exception as e:\n"
            "            import logging\n"
            "            logging.getLogger('titiler.middleware').error(f'TiTiler request failed: {e}')\n"
            "            from starlette.responses import JSONResponse\n"
            "            return JSONResponse({'detail': str(e)}, status_code=500)\n"
            "\n"
            "app.add_middleware(_WinPathFix)\n"
            "\n"
            "@app.get('/health')\n"
            "async def health():\n"
            "    return {'status': 'ok'}\n"
            "\n"
            "print('TITILER_STARTUP: Server process initialized', flush=True)\n"
            "cpu_count = os.cpu_count() or 2\n"
            "backlog = max(128, cpu_count * 64)\n"
            "uvicorn.run(app, host='127.0.0.1', port=8081, log_level='warning', access_log=False, timeout_keep_alive=5, backlog=backlog)\n"
        )

        env = os.environ.copy()

        # ── GDAL/PROJ data paths ──────────────────────────────────────────────
        _python_exe = Path(sys.executable).resolve()
        _env_root = _python_exe.parent  # conda env root on Windows (bin folder)

        # On Windows/Conda, the DLLs (GEOS for shapely, GDAL for rasterio) are in Library/bin. We must ensure this is in the PATH of the subprocess.
        _env_lib_bin = _env_root / "Library" / "bin"
        _env_scripts = _env_root / "Scripts"
        _new_paths = [str(_env_root), str(_env_scripts), str(_env_lib_bin)]

        existing_path = env.get("PATH", "")
        if existing_path:
            env["PATH"] = os.pathsep.join(_new_paths + [existing_path])
        else:
            env["PATH"] = os.pathsep.join(_new_paths)

        # conda layout: <env>\Library\share\gdal  and  <env>\Library\share\proj
        _gdal_data_candidate = _env_root / "Library" / "share" / "gdal"
        _proj_data_candidate = _env_root / "Library" / "share" / "proj"
        # venv / non-conda layout: <env>\Lib\site-packages\pyproj\proj_dir\share\proj
        if not _proj_data_candidate.exists():
            try:
                import pyproj

                _proj_data_candidate = Path(pyproj.datadir.get_data_dir())
            except Exception:
                pass
        if not _gdal_data_candidate.exists():
            try:
                import rasterio

                _gdal_data_candidate = Path(rasterio.__file__).parent / "gdal_data"
            except Exception:
                pass

        if _gdal_data_candidate.exists():
            env.setdefault("GDAL_DATA", str(_gdal_data_candidate))
        if Path(str(_proj_data_candidate)).exists():
            env.setdefault("PROJ_DATA", str(_proj_data_candidate))
            env.setdefault("PROJ_LIB", str(_proj_data_candidate))

        env["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"
        env["GDAL_HTTP_MERGE_CONSECUTIVE_RANGES"] = "YES"
        env["GDAL_TIFF_INTERNAL_MASK"] = "NO"
        env["GDAL_NUM_THREADS"] = "ALL_CPUS"
        env["VSI_CACHE"] = "TRUE"
        env["VSI_CACHE_SIZE"] = "100000000"
        env["GDAL_CACHEMAX"] = "2048"
        env["CPL_VSIL_USE_TEMP_FILE_FOR_RANDOM_WRITE"] = "NO"
        env["GDAL_TIFF_OVR_BLOCKSIZE"] = "512"
        # Suppress numpy cast warnings that spam stderr
        warning_filter = "ignore:invalid value encountered in cast:RuntimeWarning"
        existing_filters = env.get("PYTHONWARNINGS", "").strip()
        env["PYTHONWARNINGS"] = (
            f"{existing_filters},{warning_filter}"
            if existing_filters
            else warning_filter
        )

        command: Sequence[str] = (sys.executable, "-c", bootstrap_code)

        # ── Windows-specific subprocess flags ─────────────────────────────────
        kwargs: dict = dict(env=env, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        if platform.system() == "Windows":
            # CREATE_NO_WINDOW (0x08000000): suppress console flash CREATE_NEW_PROCESS_GROUP (0x00000200): isolate signal handling
            kwargs["creationflags"] = 0x08000000 | 0x00000200

        self._process = subprocess.Popen(command, **kwargs)

        # Start drain threads to prevent pipe blocking
        def _drain_output(stream, label):
            try:
                for line in stream:
                    text = line.decode("utf-8", errors="replace")
                    self._stderr_buffer.append(f"[{label}] {text}")
                    if len(self._stderr_buffer) > 200:
                        self._stderr_buffer.pop(0)
            except Exception:
                pass

        t1 = threading.Thread(target=_drain_output, args=(self._process.stdout, "STDOUT"), daemon=True)
        t2 = threading.Thread(target=_drain_output, args=(self._process.stderr, "STDERR"), daemon=True)
        t1.start()
        t2.start()
        self._drain_threads = [t1, t2]

    def __del__(self):
        self.stop()
