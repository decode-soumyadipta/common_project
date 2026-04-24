from __future__ import annotations

from urllib.parse import quote

from offline_gis_app.config.settings import settings


class TiTilerUrlPolicy:
    """Build deterministic local TiTiler XYZ URLs for offline desktop flows."""

    def build_url(self, source_path: str) -> str:
        normalized = self._normalize_source_path(source_path)
        # Pass the raw normalized path directly. GDAL handles "C:/..." natively.
        # Do NOT use the file:/// prefix, as it breaks on Windows when spaces exist.
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

        # Strip out file:// prefixes if they were added elsewhere
        if path.startswith("file:///"):
            path = path[8:]
        elif path.startswith("file://"):
            path = path[7:]

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
