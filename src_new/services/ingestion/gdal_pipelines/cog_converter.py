"""COG Converter — GDAL processing pipeline for Cloud-Optimized GeoTIFF creation.

Extracted from ``src/platform_core/ingestion/services/cog_service/service.py``.
Preserves all existing gdal.Translate / gdal.Warp call signatures and rasterio
COG driver usage while adapting imports to the src_new/ module structure.

Requirement 9.1: src_new/services/ingestion/gdal_pipelines/ contains all
    GDAL-based raster processing logic.
Requirement 9.2: cog_converter.py handles GeoTIFF-to-COG conversion;
    existing gdal.Translate / gdal.Warp call signatures are preserved.
Requirement 9.4: GDAL environment variables are read from Configuration_Manager
    (settings.apply_gdal_env()) before any GDAL operation.
Requirement 9.6: GDAL operation failures are logged with file path, operation
    type, and GDAL error message.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src_new.shared.config import settings
from src_new.shared.constants import (
    COG_BLOCKSIZE,
    COG_COMPRESSION,
)

LOGGER = logging.getLogger("services.ingestion.gdal_pipelines.cog_converter")


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CogConversionResult:
    """Outcome of a COG preparation/conversion attempt.

    Attributes:
        source_path:  Resolved path of the original input file.
        working_path: Path to use for downstream processing.  Equal to
                      ``source_path`` when no conversion was performed.
        converted:    ``True`` when a new COG file was written to disk.
    """

    source_path: Path
    working_path: Path
    converted: bool


# ---------------------------------------------------------------------------
# Public converter class
# ---------------------------------------------------------------------------


class CogConverter:
    """Prepare raster sources for stable local tiling by preferring COG layout.

    Conversion strategy (in priority order):
    1. Skip if COG conversion is disabled in config.
    2. Skip if the source already looks like a COG.
    3. Skip if a COG output already exists and overwrite is disabled.
    4. Try rasterio COG driver (fastest, most portable).
    5. Fall back to a tiled GeoTIFF with internal overviews (TiTiler-compatible).
    6. Fall back to ``gdal_translate`` CLI for JPEG2000 sources.

    All GDAL environment variables are applied via ``settings.apply_gdal_env()``
    before any GDAL/rasterio operation (Requirement 9.4).
    """

    def convert(self, source_path: Path) -> CogConversionResult:
        """Convert *source_path* to a COG if needed and return the result.

        Args:
            source_path: Path to the input raster file.

        Returns:
            :class:`CogConversionResult` describing the outcome.
        """
        # Apply GDAL env vars before any GDAL operation (Requirement 9.4).
        settings.apply_gdal_env()

        source = source_path.resolve()

        # Normalise .j2k → .jp2 when a sibling .jp2 exists.
        if source.suffix.lower() == ".j2k":
            jp2_candidate = source.with_suffix(".jp2")
            if jp2_candidate.exists():
                source = jp2_candidate.resolve()

        # Respect the global COG conversion toggle.
        if not settings.ingest_enable_cog_conversion:
            LOGGER.debug(
                "COG conversion disabled by config; skipping source=%s", source
            )
            return CogConversionResult(
                source_path=source, working_path=source, converted=False
            )

        suffix = source.suffix.lower()
        if suffix not in {".tif", ".tiff", ".jp2", ".j2k"}:
            LOGGER.debug(
                "Unsupported format for COG conversion; skipping source=%s", source
            )
            return CogConversionResult(
                source_path=source, working_path=source, converted=False
            )

        if self._looks_like_cog(source):
            LOGGER.debug("Source already looks like a COG; skipping source=%s", source)
            return CogConversionResult(
                source_path=source, working_path=source, converted=False
            )

        cog_path = self._target_cog_path(source)
        if cog_path.exists() and not settings.ingest_cog_overwrite:
            LOGGER.debug(
                "COG output already exists and overwrite disabled; "
                "reusing existing source=%s cog=%s",
                source,
                cog_path,
            )
            return CogConversionResult(
                source_path=source, working_path=cog_path, converted=False
            )

        temp_cog_path = cog_path.with_suffix(cog_path.suffix + ".tmp")
        try:
            if temp_cog_path.exists():
                temp_cog_path.unlink()
        except Exception:
            pass

        # For JPEG2000 sources, try gdal_translate first (avoids rasterio JP2 issues).
        if suffix in {".jp2", ".j2k"}:
            if self._try_gdal_translate(source, temp_cog_path):
                try:
                    temp_cog_path.replace(cog_path)
                    return CogConversionResult(
                        source_path=source, working_path=cog_path, converted=True
                    )
                except Exception as exc_rename:
                    LOGGER.error("Failed to rename temp COG after initial gdal_translate: %s", exc_rename)
            try:
                if temp_cog_path.exists():
                    temp_cog_path.unlink()
            except Exception:
                pass

        # Primary path: rasterio COG driver.
        try:
            import rasterio  # type: ignore
            from rasterio.shutil import copy as rio_copy  # type: ignore
        except Exception:
            LOGGER.warning(
                "COG conversion skipped because rasterio COG support is unavailable "
                "source=%s operation=cog_convert",
                source,
            )
            # Last-resort gdal_translate for JP2 sources.
            if source.suffix.lower() in {".jp2", ".j2k"}:
                if self._try_gdal_translate(source, temp_cog_path):
                    try:
                        temp_cog_path.replace(cog_path)
                        return CogConversionResult(
                            source_path=source, working_path=cog_path, converted=True
                        )
                    except Exception as exc_rename:
                        LOGGER.error("Failed to rename temp COG after fallback gdal_translate: %s", exc_rename)
                try:
                    if temp_cog_path.exists():
                        temp_cog_path.unlink()
                except Exception:
                    pass
            return CogConversionResult(
                source_path=source, working_path=source, converted=False
            )

        # Attempt 1: rasterio COG driver.
        try:
            with rasterio.open(source) as src:
                rio_copy(
                    src,
                    temp_cog_path,
                    driver="COG",
                    BLOCKSIZE=str(settings.cog_blocksize),
                    COMPRESS=settings.cog_compression,
                    BIGTIFF="IF_SAFER",
                    NUM_THREADS="ALL_CPUS",
                    RESAMPLING=settings.cog_overview_resampling,
                    OVERVIEWS="AUTO",
                )
            temp_cog_path.replace(cog_path)
            LOGGER.info(
                "COG conversion succeeded source=%s target=%s operation=cog_convert",
                source,
                cog_path,
            )
            return CogConversionResult(
                source_path=source, working_path=cog_path, converted=True
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "COG driver failed for source=%s operation=cog_convert error=%s "
                "— trying tiled GeoTIFF fallback",
                source,
                exc,
            )
            try:
                if temp_cog_path.exists():
                    temp_cog_path.unlink()
            except Exception:
                pass

        # Attempt 2: tiled GeoTIFF with internal overviews (TiTiler-compatible).
        try:
            import numpy as np
            with rasterio.open(source) as src:
                profile = src.profile.copy()
                profile.update(
                    driver="GTiff",
                    tiled=True,
                    blockxsize=COG_BLOCKSIZE,
                    blockysize=COG_BLOCKSIZE,
                    compress=COG_COMPRESSION.lower(),
                    bigtiff="IF_SAFER",
                    interleave="pixel",
                )

                # Check for sidecar PRJ file to get native CRS
                prj_path = source.with_suffix(".prj")
                if prj_path.exists():
                    try:
                        prj_content = prj_path.read_text().strip()
                        if prj_content:
                            from rasterio.crs import CRS
                            profile["crs"] = CRS.from_user_input(prj_content)
                            LOGGER.info("Applied sidecar CRS from %s during fallback conversion", prj_path.name)
                    except Exception as prj_exc:
                        LOGGER.warning("Failed to apply sidecar CRS from %s: %s", prj_path.name, prj_exc)

                with rasterio.open(temp_cog_path, "w", **profile) as dst:
                    for ji, window in src.block_windows(1):
                        for i in range(1, src.count + 1):
                            try:
                                data = src.read(i, window=window)
                            except Exception as exc:
                                LOGGER.warning(
                                    "Read failed for band %d window %s of source %s: %s. Filling with zeros.",
                                    i, window, source.name, exc
                                )
                                data = np.zeros((window.height, window.width), dtype=src.dtypes[i-1])
                            dst.write(data, i, window=window)

                    dst.build_overviews(
                        [2, 4, 8, 16], rasterio.enums.Resampling.nearest
                    )
                    dst.update_tags(ns="rio_overview", resampling="nearest")
            temp_cog_path.replace(cog_path)
            LOGGER.info(
                "Tiled GeoTIFF fallback succeeded source=%s target=%s "
                "operation=cog_convert_fallback",
                source,
                cog_path,
            )
            return CogConversionResult(
                source_path=source, working_path=cog_path, converted=True
            )
        except Exception as exc2:  # noqa: BLE001
            LOGGER.warning(
                "Tiled GeoTIFF fallback also failed source=%s "
                "operation=cog_convert_fallback error=%s",
                source,
                exc2,
            )
            try:
                if temp_cog_path.exists():
                    temp_cog_path.unlink()
            except Exception:
                pass

        # Attempt 3: gdal_translate CLI (last resort for JP2 sources).
        if source.suffix.lower() in {".jp2", ".j2k"}:
            if self._try_gdal_translate(source, temp_cog_path):
                try:
                    temp_cog_path.replace(cog_path)
                    return CogConversionResult(
                        source_path=source, working_path=cog_path, converted=True
                    )
                except Exception as exc_rename:
                    LOGGER.error("Failed to rename temp COG after Attempt 3 gdal_translate: %s", exc_rename)
            try:
                if temp_cog_path.exists():
                    temp_cog_path.unlink()
            except Exception:
                pass

        # All attempts failed — clean up any partial output and return original.
        try:
            if cog_path.exists():
                cog_path.unlink()
        except Exception:
            pass
        try:
            if temp_cog_path.exists():
                temp_cog_path.unlink()
        except Exception:
            pass

        LOGGER.error(
            "All COG conversion attempts failed source=%s operation=cog_convert; "
            "downstream processing will use original file",
            source,
        )
        return CogConversionResult(
            source_path=source, working_path=source, converted=False
        )

    # ------------------------------------------------------------------
    # gdal.Translate / gdal.Warp helpers
    # ------------------------------------------------------------------

    @staticmethod
    def translate(
        source: Path,
        target: Path,
        creation_options: list[str] | None = None,
        extra_args: list[str] | None = None,
    ) -> bool:
        """Wrap ``gdal.Translate`` to produce a tiled GeoTIFF / COG.

        Preserves the existing ``gdal.Translate`` call signature used in the
        original codebase (Requirement 9.2).  Applies GDAL env vars before
        opening the dataset.

        Args:
            source:           Input raster path.
            target:           Output raster path.
            creation_options: List of ``KEY=VALUE`` creation option strings.
                              Defaults to standard COG options when ``None``.
            extra_args:       Additional ``gdal.TranslateOptions`` keyword
                              arguments passed through as-is.

        Returns:
            ``True`` on success, ``False`` on failure.
        """
        settings.apply_gdal_env()

        if creation_options is None:
            creation_options = CogConverter._default_creation_options(source)

        try:
            from osgeo import gdal  # type: ignore

            gdal.UseExceptions()
            options = gdal.TranslateOptions(
                format="GTiff",
                creationOptions=creation_options,
                *(extra_args or []),
            )
            result_ds = gdal.Translate(str(target), str(source), options=options)
            if result_ds is None:
                LOGGER.error(
                    "gdal.Translate returned None source=%s target=%s "
                    "operation=gdal_translate",
                    source,
                    target,
                )
                return False
            result_ds = None  # Close dataset
            LOGGER.info(
                "gdal.Translate succeeded source=%s target=%s operation=gdal_translate",
                source,
                target,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            LOGGER.error(
                "gdal.Translate failed source=%s target=%s operation=gdal_translate "
                "error=%s",
                source,
                target,
                exc,
            )
            return False

    @staticmethod
    def warp(
        source: Path,
        target: Path,
        target_srs: str = "EPSG:3857",
        creation_options: list[str] | None = None,
        extra_args: list[str] | None = None,
    ) -> bool:
        """Wrap ``gdal.Warp`` to reproject and optionally COG-ify a raster.

        Preserves the existing ``gdal.Warp`` call signature used in the
        original codebase (Requirement 9.2).  Applies GDAL env vars before
        opening the dataset.

        Args:
            source:           Input raster path.
            target:           Output raster path.
            target_srs:       Target spatial reference (e.g. ``"EPSG:3857"``).
            creation_options: List of ``KEY=VALUE`` creation option strings.
                              Defaults to standard COG options when ``None``.
            extra_args:       Additional ``gdal.WarpOptions`` keyword arguments
                              passed through as-is.

        Returns:
            ``True`` on success, ``False`` on failure.
        """
        settings.apply_gdal_env()

        if creation_options is None:
            creation_options = CogConverter._default_creation_options(source)

        try:
            from osgeo import gdal  # type: ignore

            gdal.UseExceptions()
            options = gdal.WarpOptions(
                format="GTiff",
                dstSRS=target_srs,
                creationOptions=creation_options,
                *(extra_args or []),
            )
            result_ds = gdal.Warp(str(target), str(source), options=options)
            if result_ds is None:
                LOGGER.error(
                    "gdal.Warp returned None source=%s target=%s "
                    "operation=gdal_warp",
                    source,
                    target,
                )
                return False
            result_ds = None  # Close dataset
            LOGGER.info(
                "gdal.Warp succeeded source=%s target=%s operation=gdal_warp",
                source,
                target,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            LOGGER.error(
                "gdal.Warp failed source=%s target=%s operation=gdal_warp error=%s",
                source,
                target,
                exc,
            )
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _try_gdal_translate(source: Path, target: Path) -> bool:
        """Attempt a GDAL CLI translate when Python GDAL/rasterio fails.

        Mirrors the original ``CogPreparationService._try_gdal_translate``
        implementation to preserve call semantics (Requirement 9.2).
        """
        gdal_translate = shutil.which("gdal_translate")
        if gdal_translate is None:
            LOGGER.warning(
                "gdal_translate not available on PATH; cannot fallback "
                "source=%s operation=gdal_translate_cli",
                source,
            )
            return False

        creation_options = CogConverter._build_gdal_translate_options(source)

        command = [gdal_translate, "-of", "GTiff"]
        for option in creation_options:
            command.extend(["-co", option])
        command.extend([str(source), str(target)])

        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "gdal_translate CLI failed to start source=%s "
                "operation=gdal_translate_cli error=%s",
                source,
                exc,
            )
            return False

        if result.returncode != 0:
            LOGGER.warning(
                "gdal_translate CLI failed source=%s operation=gdal_translate_cli "
                "stderr=%s",
                source,
                result.stderr.strip(),
            )
            return False

        if not target.exists():
            LOGGER.warning(
                "gdal_translate CLI reported success but output missing "
                "source=%s target=%s operation=gdal_translate_cli",
                source,
                target,
            )
            return False

        LOGGER.info(
            "gdal_translate CLI fallback succeeded source=%s target=%s "
            "operation=gdal_translate_cli",
            source,
            target,
        )
        return True

    @staticmethod
    def _build_gdal_translate_options(source: Path) -> list[str]:
        """Build creation option list for ``gdal_translate`` CLI.

        Mirrors the original ``CogPreparationService._build_gdal_translate_options``
        implementation (Requirement 9.2).  Selects JPEG compression for 3/4-band
        Byte rasters and DEFLATE for everything else.
        """
        options = ["TILED=YES", "BIGTIFF=IF_SAFER"]
        compress = "DEFLATE"
        extra: list[str] = []

        try:
            from osgeo import gdal  # type: ignore

            gdal.UseExceptions()
            dataset = gdal.Open(str(source))
            if dataset is not None:
                band_count = int(dataset.RasterCount)
                data_type = (
                    dataset.GetRasterBand(1).DataType
                    if band_count > 0
                    else gdal.GDT_Unknown
                )

                if band_count in {3, 4} and data_type == gdal.GDT_Byte:
                    compress = "JPEG"
                    extra.append("JPEG_QUALITY=90")
                    if band_count == 3:
                        extra.append("PHOTOMETRIC=YCBCR")
                    else:
                        extra.append("PHOTOMETRIC=RGB")
                else:
                    if data_type in {gdal.GDT_Float32, gdal.GDT_Float64}:
                        extra.append("PREDICTOR=3")
                    elif data_type in {
                        gdal.GDT_Byte,
                        gdal.GDT_UInt16,
                        gdal.GDT_Int16,
                    }:
                        extra.append("PREDICTOR=2")
                dataset = None
        except Exception:
            pass

        options.append(f"COMPRESS={compress}")
        options.extend(extra)
        return options

    @staticmethod
    def _default_creation_options(source: Path) -> list[str]:
        """Return default COG creation options using config-driven block size and compression.

        Used by :meth:`translate` and :meth:`warp` when no explicit options are provided.
        """
        blocksize = str(settings.cog_blocksize)
        return [
            "TILED=YES",
            f"BLOCKXSIZE={blocksize}",
            f"BLOCKYSIZE={blocksize}",
            f"COMPRESS={settings.cog_compression}",
            "COPY_SRC_OVERVIEWS=YES",
            "BIGTIFF=IF_SAFER",
        ]

    @staticmethod
    def _target_cog_path(source_path: Path) -> Path:
        """Derive the output COG path from the source path.

        Mirrors the original ``CogPreparationService._target_cog_path``
        naming convention (Requirement 9.2).
        """
        stem = source_path.stem
        if stem.endswith(".cog"):
            return source_path.with_suffix(".tif")
        return source_path.with_name(f"{stem}.cog.tif")

    @staticmethod
    def _looks_like_cog(path: Path) -> bool:
        """Return ``True`` when *path* appears to already be a COG.

        Mirrors the original ``CogPreparationService._looks_like_cog``
        heuristic (Requirement 9.2).  Checks filename convention first,
        then rasterio driver metadata.
        """
        lower_name = path.name.lower()
        if lower_name.endswith(".cog.tif") or lower_name.endswith(".cog.tiff"):
            return True

        try:
            import rasterio  # type: ignore
        except Exception:
            return False

        try:
            with rasterio.open(path) as dataset:
                # Only trust the GDAL COG driver as definitive proof.
                if str(dataset.driver).upper() == "COG":
                    return True
                if dataset.driver != "GTiff":
                    return False
                # Must be internally tiled AND have overviews to be COG-compatible.
                if not dataset.is_tiled:
                    return False
                if not dataset.overviews(1):
                    return False
                # Strip layout (block width == raster width) is not a COG.
                block_shapes = dataset.block_shapes
                if not block_shapes:
                    return False
                rows, cols = block_shapes[0]
                if cols >= dataset.width:
                    return False
                return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Convenience alias — preserves the original class name used in src/
# ---------------------------------------------------------------------------

#: Backward-compatible alias for code that imported ``CogPreparationService``
#: from the old ``cog_service`` package.
CogPreparationService = CogConverter

__all__ = [
    "CogConversionResult",
    "CogConverter",
    "CogPreparationService",  # backward-compat alias
]
