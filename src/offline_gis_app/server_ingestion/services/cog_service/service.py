from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging

from offline_gis_app.config.settings import settings

LOGGER = logging.getLogger("services.cog")


@dataclass(frozen=True)
class CogPreparationResult:
    source_path: Path
    working_path: Path
    converted: bool


class CogPreparationService:
    """Prepare raster sources for stable local tiling by preferring COG layout."""

    def prepare(self, source_path: Path) -> CogPreparationResult:
        source = source_path.resolve()
        if not settings.ingest_enable_cog_conversion:
            return CogPreparationResult(source_path=source, working_path=source, converted=False)

        suffix = source.suffix.lower()
        if suffix not in {".tif", ".tiff", ".jp2", ".j2k"}:
            return CogPreparationResult(source_path=source, working_path=source, converted=False)

        if self._looks_like_cog(source):
            return CogPreparationResult(source_path=source, working_path=source, converted=False)

        cog_path = self._target_cog_path(source)
        if cog_path.exists() and not settings.ingest_cog_overwrite:
            return CogPreparationResult(source_path=source, working_path=cog_path, converted=False)

        try:
            import rasterio  # type: ignore
            from rasterio.shutil import copy as rio_copy  # type: ignore
        except Exception:
            LOGGER.warning("COG conversion skipped because rasterio COG support is unavailable")
            return CogPreparationResult(source_path=source, working_path=source, converted=False)

        try:
            with rasterio.open(source) as src:
                rio_copy(
                    src,
                    cog_path,
                    driver="COG",
                    BLOCKSIZE=str(settings.cog_blocksize),
                    COMPRESS=settings.cog_compression,
                    BIGTIFF="IF_SAFER",
                    NUM_THREADS="ALL_CPUS",
                    RESAMPLING=settings.cog_overview_resampling,
                    OVERVIEWS="AUTO",
                )
            LOGGER.info("COG conversion succeeded source=%s target=%s", source, cog_path)
            return CogPreparationResult(source_path=source, working_path=cog_path, converted=True)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("COG conversion failed for %s: %s", source, exc)
            return CogPreparationResult(source_path=source, working_path=source, converted=False)

    @staticmethod
    def _target_cog_path(source_path: Path) -> Path:
        stem = source_path.stem
        if stem.endswith(".cog"):
            return source_path.with_suffix(".tif")
        return source_path.with_name(f"{stem}.cog.tif")

    @staticmethod
    def _looks_like_cog(path: Path) -> bool:
        lower_name = path.name.lower()
        if lower_name.endswith(".cog.tif") or lower_name.endswith(".cog.tiff"):
            return True
        try:
            import rasterio  # type: ignore
        except Exception:
            return False

        try:
            with rasterio.open(path) as dataset:
                if str(dataset.driver).upper() == "COG":
                    return True
                if dataset.driver != "GTiff":
                    return False
                if not dataset.is_tiled:
                    return False
                return bool(dataset.overviews(1))
        except Exception:
            return False
