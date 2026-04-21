from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TileRequest:
    source_path: str
    z: int
    x: int
    y: int


class TileUrlPolicy(Protocol):
    """Defines how source datasets map to tile service URLs."""

    def build_url(self, source_path: str) -> str:
        ...
