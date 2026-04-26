from __future__ import annotations

import platform
from urllib.parse import quote

from offline_gis_app.config.settings import settings


class TiTilerUrlPolicy:
    """Build deterministic local TiTiler XYZ URLs for offline desktop flows."""

    def build_url(self, source_path: str) -> str:
        normalized = self._normalize_source_path(source_path)
        # On Windows, GDAL requires a file:/// URI so the drive letter is
        # unambiguous and the path is not misinterpreted as a relative URL.
        # On macOS/Linux, pass the raw path — file:/// works there too but
        # the plain path is simpler and avoids any URI parsing edge cases.
        if platform.system() == "Windows" and len(normalized) >= 2 and normalized[1] == ":":
            # Windows absolute path like C:/Users/... → file:///C:/Users/...
            gdal_url = "file:///" + normalized
        else:
            gdal_url = normalized
        encoded_file_url = quote(gdal_url, safe="/:")
        return (
            f"{settings.titiler_base_url}/cog/tiles/{settings.titiler_tile_matrix_set_id}/{{z}}/{{x}}/{{y}}.png"
            f"?url={encoded_file_url}"
        )

    @staticmethod
    def _normalize_source_path(source_path: str) -> str:
        path = source_path.strip()
        if not path:
            raise ValueError("source_path cannot be empty")

        # Strip out file:// prefixes — we re-add them correctly below
        if path.startswith("file:///"):
            path = path[8:]
        elif path.startswith("file://"):
            path = path[7:]

        # Normalise backslashes to forward slashes
        normalized = path.replace("\\", "/")

        # Clean up double slashes (preserve UNC network paths starting with //)
        if normalized.startswith("//"):
            tail = normalized[2:]
            while "//" in tail:
                tail = tail.replace("//", "/")
            return "//" + tail

        while "//" in normalized:
            normalized = normalized.replace("//", "/")

        return normalized
