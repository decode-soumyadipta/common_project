from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DesktopState:
    selected_asset: dict[str, Any] | None = None
    clicked_points: list[tuple[float, float]] = field(default_factory=list)

