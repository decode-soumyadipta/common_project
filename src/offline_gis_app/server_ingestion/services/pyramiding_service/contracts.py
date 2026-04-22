from __future__ import annotations

from typing import Protocol
from pathlib import Path


class PyramidPolicy(Protocol):
    """Defines overview generation strategy for raster datasets."""

    def ensure(self, source_path: Path, *, minimum_base_tile: int = 256) -> bool:
        ...
