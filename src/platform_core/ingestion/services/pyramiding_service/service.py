from __future__ import annotations

from pathlib import Path


class RasterPyramidingService:
    """Build internal overviews for large rasters to reduce tile read pressure."""

    def ensure(self, source_path: Path, *, minimum_base_tile: int = 256) -> bool:
        try:
            import rasterio  # type: ignore
            from rasterio.enums import Resampling  # type: ignore
        except Exception:
            return False

        suffix = source_path.suffix.lower()
        if suffix not in {".tif", ".tiff"}:
            return False

        try:
            with rasterio.open(source_path, "r+") as dataset:
                if dataset.count < 1:
                    return False
                if dataset.overviews(1):
                    return False

                min_dim = min(int(dataset.width), int(dataset.height))
                factors: list[int] = []
                factor = 2
                while min_dim // factor >= minimum_base_tile:
                    factors.append(factor)
                    factor *= 2

                if not factors:
                    return False

                dataset.build_overviews(factors, Resampling.average)
                dataset.update_tags(ns="rio_overview", resampling="average")
                return True
        except Exception:
            return False
