from __future__ import annotations

from typing import Protocol


class PyramidPolicy(Protocol):
    """Defines overview generation strategy for raster datasets."""

    def ensure(self, source_path: str) -> bool:
        ...
