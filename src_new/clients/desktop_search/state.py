from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DesktopState:
    selected_asset: dict[str, Any] | None = None
    clicked_points: list[tuple[float, float]] = field(default_factory=list)
    search_geometry_type: str | None = None
    search_geometry_payload: dict[str, Any] | None = None
    active_ingest_job_id: str | None = None
    active_layer_is_dem: bool = False
    pending_ingest_source_path: str | None = None
    auto_visualize_ingest_result: bool = False
