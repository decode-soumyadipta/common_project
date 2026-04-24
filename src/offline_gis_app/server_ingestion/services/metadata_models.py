from dataclasses import dataclass
from pathlib import Path

from offline_gis_app.db.models import RasterKind
from offline_gis_app.utils.geometry import Bounds


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
