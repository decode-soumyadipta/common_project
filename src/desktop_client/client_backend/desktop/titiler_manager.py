from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

import httpx

from core_shared.config_pkg.settings import settings


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
        for _ in range(40):          # up to 10 s — Windows process startup is slower
            if self.is_ready():
                self._logger.info("TiTiler is ready")
                return True
            time.sleep(0.25)
        # Log stderr snippet from the subprocess to help diagnose Windows failures
        if self._process is not None and self._process.stderr is not None:
            try:
                import select as _select
                # Non-blocking read on Windows via os.read with a short timeout
                import threading
                _lines: list[str] = []
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
                    self._logger.error("TiTiler stderr: %s", "".join(_lines[:20]))
            except Exception:
                pass
        self._logger.error("TiTiler failed health check after auto-start")
        return False

    def _start_process(self) -> None:
        if self._process and self._process.poll() is None:
            return

        bootstrap_code = (
            "import sys, platform, re, uvicorn\n"
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
            "        if platform.system() == 'Windows' and 'url' in request.query_params:\n"
            "            raw = request.scope.get('query_string', b'').decode('utf-8', errors='replace')\n"
            "            fixed = re.sub(r'(?<=[?&])url=%2F([A-Za-z](?:%3A|:))', lambda m: 'url=' + m.group(1).replace('%3A', ':'), raw)\n"
            "            fixed = re.sub(r'(?<=[?&])url=/([A-Za-z]:)', r'url=\\1', fixed)\n"
            "            request.scope['query_string'] = fixed.encode('utf-8')\n"
            "        return await call_next(request)\n"
            "\n"
            "app.add_middleware(_WinPathFix)\n"
            "uvicorn.run(app, host='127.0.0.1', port=8081, log_level='warning')\n"
        )

        env = os.environ.copy()

        # ── GDAL/PROJ data paths ──────────────────────────────────────────────
        _python_exe = Path(sys.executable).resolve()
        _env_root = _python_exe.parent          # conda env root on Windows (bin folder)
        
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
            env.setdefault("PROJ_LIB",  str(_proj_data_candidate))

        env["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"
        env["GDAL_HTTP_MERGE_CONSECUTIVE_RANGES"] = "YES"
        # Fix "INIT_DEST was set to NO_DATA, but a NoData value was not defined"
        # — a GDAL 3.x bug on Windows when tiling files without a nodata value.
        env["GDAL_TIFF_INTERNAL_MASK"] = "NO"
        env["GDAL_NUM_THREADS"] = "1"
        env["VSI_CACHE"] = "TRUE"
        env["VSI_CACHE_SIZE"] = "10000000"
        env["GDAL_CACHEMAX"] = "512"
        env["CPL_VSIL_USE_TEMP_FILE_FOR_RANDOM_WRITE"] = "NO"
        env["GDAL_TIFF_OVR_BLOCKSIZE"] = "512"
        # Suppress numpy cast warnings that spam stderr
        warning_filter = "ignore:invalid value encountered in cast:RuntimeWarning"
        existing_filters = env.get("PYTHONWARNINGS", "").strip()
        env["PYTHONWARNINGS"] = (
            f"{existing_filters},{warning_filter}" if existing_filters else warning_filter
        )

        command: Sequence[str] = (sys.executable, "-c", bootstrap_code)

        # ── Windows-specific subprocess flags ─────────────────────────────────
        kwargs: dict = dict(env=env, stderr=subprocess.PIPE)
        if platform.system() == "Windows":
            # CREATE_NO_WINDOW (0x08000000): suppress console flash
            # CREATE_NEW_PROCESS_GROUP (0x00000200): isolate signal handling
            kwargs["creationflags"] = 0x08000000 | 0x00000200

        self._process = subprocess.Popen(command, **kwargs)
        self._logger.warning(
            "Auto-started TiTiler process pid=%s gdal_data=%s proj_data=%s",
            self._process.pid,
            env.get("GDAL_DATA", "not-set"),
            env.get("PROJ_DATA", "not-set"),
        )
        # Give the process 500 ms to fail fast (import error, port conflict, etc.)
        # and log stderr if it exits immediately.
        time.sleep(0.5)
        if self._process.poll() is not None:
            try:
                stderr_out = self._process.stderr.read().decode("utf-8", errors="replace") if self._process.stderr else ""
            except Exception:
                stderr_out = ""
            self._logger.error(
                "TiTiler process exited immediately (rc=%s). stderr: %s",
                self._process.returncode,
                stderr_out[:2000],
            )
            self._process = None
