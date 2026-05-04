from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Sequence

import httpx

from core_shared.config_pkg.settings import settings

LOGGER = logging.getLogger("desktop.titiler_manager")


class TiTilerManager:
    """Manages the local TiTiler server process for on-the-fly COG rendering."""

    def __init__(self, port: int = 8081):
        self.port = port
        self._process: subprocess.Popen | None = None
        self._logger = LOGGER
        self.last_error: str | None = None

    def ensure_running(self) -> bool:
        if self.is_running():
            return True

        self._logger.info("Starting local TiTiler server on port %d...", self.port)
        self._start_process()

        # Wait for health check
        for _ in range(20):  # 10 seconds total
            if self.is_running():
                self._logger.info("TiTiler server started successfully")
                return True
            time.sleep(0.5)

        # Check for immediate failure
        if self._process:
            try:
                _lines = []

                def _drain():
                    try:
                        for line in self._process.stderr:
                            _lines.append(line.decode("utf-8", errors="replace"))
                            if len(_lines) > 20:
                                break
                    except Exception:
                        pass

                t = threading.Thread(target=_drain, daemon=True)
                t.start()
                t.join(timeout=0.5)
                if _lines:
                    stderr_text = "".join(_lines[:20])
                    self.last_error = stderr_text
                    self._logger.error("TiTiler stderr: %s", stderr_text)
            except Exception:
                pass
        self._logger.error("TiTiler failed health check after auto-start")
        if not self.last_error:
            self.last_error = "TiTiler failed health check after auto-start"
        return False

    def is_running(self) -> bool:
        if self._process and self._process.poll() is not None:
            self._process = None
            return False

        try:
            resp = httpx.get(f"http://127.0.0.1:{self.port}/health", timeout=0.5)
            return resp.status_code == 200
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

    def _start_process(self) -> None:
        if self._process and self._process.poll() is None:
            return

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
            "uvicorn.run(app, host='127.0.0.1', port=8081, log_level='info')\n"
        )

        env = os.environ.copy()

        # ── GDAL/PROJ data paths ──────────────────────────────────────────────
        _python_exe = Path(sys.executable).resolve()
        _env_root = _python_exe.parent  # conda env root on Windows (bin folder)

        # On Windows/Conda, the DLLs (GEOS for shapely, GDAL for rasterio) are in Library/bin.
        # We must ensure this is in the PATH of the subprocess.
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
        # Fix "INIT_DEST was set to NO_DATA, but a NoData value was not defined"
        # — a GDAL 3.x bug on Windows when tiling files without a nodata value.
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
        kwargs: dict = dict(env=env, stderr=subprocess.PIPE)
        if platform.system() == "Windows":
            # CREATE_NO_WINDOW (0x08000000): suppress console flash
            # CREATE_NEW_PROCESS_GROUP (0x00000200): isolate signal handling
            kwargs["creationflags"] = 0x08000000 | 0x00000200

        self._process = subprocess.Popen(command, **kwargs)

    def __del__(self):
        self.stop()
