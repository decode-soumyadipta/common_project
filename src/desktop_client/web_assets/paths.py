from __future__ import annotations

from pathlib import Path


def runtime_web_assets_dir() -> Path:
    """Return the packaged runtime web asset directory for the desktop client."""
    return (
        Path(__file__).resolve().parents[1]
        / "client_frontend"
        / "web_assets"
    )


def runtime_asset_path(*parts: str) -> Path:
    """Resolve a specific runtime web asset path."""
    return runtime_web_assets_dir().joinpath(*parts)


__all__ = ["runtime_web_assets_dir", "runtime_asset_path"]
