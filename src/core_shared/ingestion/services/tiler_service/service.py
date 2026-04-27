from __future__ import annotations

import re
from urllib.parse import quote

from core_shared.config_pkg.settings import settings


class TiTilerUrlPolicy:
    """Build deterministic local TiTiler XYZ URLs for offline desktop flows."""

    def build_url(self, source_path: str) -> str:
        normalized = self._normalize_source_path(source_path)
        encoded_file_url = quote(normalized, safe="/:")
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
            # UNC path -> file:////server/share/path
            return "file:////" + tail

        while "//" in normalized:
            normalized = normalized.replace("//", "/")

        # Windows drive path -> file:///C:/...
        if re.match(r"^[A-Za-z]:/", normalized):
            return f"file:///{normalized}"

        # POSIX absolute path -> file:///...
        if normalized.startswith("/"):
            return f"file://{normalized}"

        # Relative path fallback
        return f"file:///{normalized}"
