from __future__ import annotations

from pathlib import Path


def resolve_viewer_index_html() -> Path:
    """Return the canonical frontend entrypoint used by the desktop web viewer."""
    return (
        Path(__file__).resolve().parents[1]
        / "client_frontend"
        / "web_assets"
        / "index.html"
    )


def resolve_viewer_url() -> str:
    """Return the file:// URL consumed by QWebEngineView."""
    return resolve_viewer_index_html().resolve().as_uri()


__all__ = ["resolve_viewer_index_html", "resolve_viewer_url"]
