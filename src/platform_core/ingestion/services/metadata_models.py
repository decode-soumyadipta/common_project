from dataclasses import dataclass
from pathlib import Path

from platform_core.db.models import RasterKind
from platform_core.utils.geometry import Bounds


@dataclass(frozen=True)
class RasterMetadata:
    file_path: Path
    file_name: str
    kind: RasterKind
    crs: str
    bounds: Bounds
    resolution_x: float
    resolution_y: float
    width: int
    height: int
