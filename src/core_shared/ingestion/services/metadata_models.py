from dataclasses import dataclass
from pathlib import Path

from core_shared.db.models import RasterKind
from core_shared.utils.geometry import Bounds


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
