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
from dataclasses import dataclass
from pathlib import Path
from threading import Semaphore
from typing import Any, cast

from src_new.shared.config import settings
from src_new.shared.constants import (
    COG_BLOCKSIZE,
    COG_COMPRESSION,
)

LOGGER = logging.getLogger("services.ingestion.gdal_pipelines.cog_converter")


# --------------------------------------------------------------------------- Result dataclass ---------------------------------------------------------------------------


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


# --------------------------------------------------------------------------- Public converter class ---------------------------------------------------------------------------


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

    _lock = Semaphore(1)

    def convert(self, source_path: Path) -> CogConversionResult:
        """Convert *source_path* to a COG if needed and return the result.

        Args:
            source_path: Path to the input raster file.

        Returns:
            :class:`CogConversionResult` describing the outcome.
        """
        with self._lock:
            # Apply GDAL env vars before any GDAL operation (Requirement 9.4).
            settings.apply_gdal_env()

            source, skip_result = self._validate_and_resolve_source(source_path)
            if skip_result is not None:
                return skip_result

            cog_path = self._target_cog_path(source)
            temp_cog_path = cog_path.with_suffix(cog_path.suffix + ".tmp")
            try:
                if temp_cog_path.exists():
                    temp_cog_path.unlink()
            except Exception:
                pass

            # For JPEG2000 sources, try gdal_translate first (avoids rasterio JP2 issues).
            if source.suffix.lower() in {".jp2", ".j2k"}:
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

            # Primary path: Attempt 1 with rasterio COG driver.
            attempt_1_res = self._run_attempt_1_rasterio(source, temp_cog_path, cog_path)
            if attempt_1_res is not None:
                return attempt_1_res

            # Attempt 2: tiled GeoTIFF with internal overviews (TiTiler-compatible).
            attempt_2_res = self._run_attempt_2_tiled_geotiff(source, temp_cog_path, cog_path)
            if attempt_2_res is not None:
                return attempt_2_res

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

    def _validate_and_resolve_source(self, source_path: Path) -> tuple[Path, CogConversionResult | None]:
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
            return source, CogConversionResult(
                source_path=source, working_path=source, converted=False
            )

        suffix = source.suffix.lower()
        if suffix not in {".tif", ".tiff", ".jp2", ".j2k"}:
            LOGGER.debug(
                "Unsupported format for COG conversion; skipping source=%s", source
            )
            return source, CogConversionResult(
                source_path=source, working_path=source, converted=False
            )

        if self._looks_like_cog(source):
            LOGGER.debug("Source already looks like a COG; skipping source=%s", source)
            return source, CogConversionResult(
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
            return source, CogConversionResult(
                source_path=source, working_path=cog_path, converted=False
            )
        return source, None

    def _run_attempt_1_rasterio(self, source: Path, temp_cog_path: Path, cog_path: Path) -> CogConversionResult | None:
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
            # Assign CRS to temp_cog_path if it lacks one
            with rasterio.open(temp_cog_path, "r+") as dst:
                if dst.crs is None:
                    prj_path = source.with_suffix(".prj")
                    assigned_crs = None
                    if prj_path.exists():
                        try:
                            prj_content = prj_path.read_text().strip()
                            if prj_content:
                                from rasterio.crs import CRS  # type: ignore
                                assigned_crs = CRS.from_user_input(prj_content)
                        except Exception:
                            pass
                    if assigned_crs is None:
                        from rasterio.crs import CRS  # type: ignore
                        assigned_crs = CRS.from_epsg(4326)
                    dst.crs = assigned_crs
                    LOGGER.info("Assigned fallback CRS to COG after Attempt 1 copy: %s", assigned_crs)
            temp_cog_path.replace(cog_path)
            LOGGER.info(
                "COG conversion succeeded source=%s target=%s operation=cog_convert",
                source,
                cog_path,
            )
            return CogConversionResult(
                source_path=source, working_path=cog_path, converted=True
            )
        except Exception as exc:
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
            return None

    def _run_attempt_2_tiled_geotiff(self, source: Path, temp_cog_path: Path, cog_path: Path) -> CogConversionResult | None:
        try:
            import numpy as np
            import rasterio  # type: ignore
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
                has_crs = False
                if prj_path.exists():
                    try:
                        prj_content = prj_path.read_text().strip()
                        if prj_content:
                            from rasterio.crs import CRS  # type: ignore
                            profile["crs"] = CRS.from_user_input(prj_content)
                            LOGGER.info("Applied sidecar CRS from %s during fallback conversion", prj_path.name)
                            has_crs = True
                    except Exception as prj_exc:
                        LOGGER.warning("Failed to apply sidecar CRS from %s: %s", prj_path.name, prj_exc)
                if not has_crs and profile.get("crs") is None:
                    from rasterio.crs import CRS  # type: ignore
                    profile["crs"] = CRS.from_epsg(4326)
                    LOGGER.warning("No CRS or sidecar PRJ found for fallback conversion of %s. Defaulting to EPSG:4326.", source.name)

                with rasterio.open(temp_cog_path, "w", **profile) as dst:
                    for _ji, window in src.block_windows(1):
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
                        [2, 4, 8, 16], rasterio.enums.Resampling.nearest  # type: ignore
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
        except Exception as exc2:
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
            return None

    # ------------------------------------------------------------------ gdal.Translate / gdal.Warp helpers ------------------------------------------------------------------

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

        gdal = None
        try:
            from osgeo import gdal  # type: ignore

            gdal.UseExceptions()

            a_srs = CogConverter._detect_spatial_reference(gdal, source)

            translate_kwargs = {
                "format": "GTiff",
                "creationOptions": creation_options,
            }
            if a_srs:
                translate_kwargs["outputSRS"] = a_srs

            options = gdal.TranslateOptions(
                *(cast(Any, extra_args) or []),
                **translate_kwargs
            )
            result_ds = gdal.Translate(str(target), str(source), options=options)
            if result_ds is None:
                err_msg = gdal.GetLastErrorMsg()
                LOGGER.error(
                    "gdal.Translate returned None source=%s target=%s "
                    "operation=gdal_translate error=%s",
                    source,
                    target,
                    err_msg,
                )
                return False
            result_ds = None  # Close dataset
            LOGGER.info(
                "gdal.Translate succeeded source=%s target=%s operation=gdal_translate",
                source,
                target,
                )
            return True
        except Exception as exc:
            err_msg = gdal.GetLastErrorMsg() if gdal is not None else ""
            LOGGER.error(
                "gdal.Translate failed source=%s target=%s operation=gdal_translate "
                "error=%s gdal_error=%s",
                source,
                target,
                exc,
                err_msg,
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

        gdal = None
        try:
            from osgeo import gdal  # type: ignore

            gdal.UseExceptions()

            src_srs = CogConverter._detect_spatial_reference(gdal, source)

            warp_kwargs = {
                "format": "GTiff",
                "dstSRS": target_srs,
                "creationOptions": creation_options,
            }
            if src_srs:
                warp_kwargs["srcSRS"] = src_srs

            options = gdal.WarpOptions(
                *(cast(Any, extra_args) or []),
                **warp_kwargs
            )
            result_ds = gdal.Warp(str(target), str(source), options=options)
            if result_ds is None:
                err_msg = gdal.GetLastErrorMsg()
                LOGGER.error(
                    "gdal.Warp returned None source=%s target=%s "
                    "operation=gdal_warp error=%s",
                    source,
                    target,
                    err_msg,
                )
                return False
            result_ds = None  # Close dataset
            LOGGER.info(
                "gdal.Warp succeeded source=%s target=%s operation=gdal_warp",
                source,
                target,
            )
            return True
        except Exception as exc:
            err_msg = gdal.GetLastErrorMsg() if gdal is not None else ""
            LOGGER.error(
                "gdal.Warp failed source=%s target=%s operation=gdal_warp error=%s gdal_error=%s",
                source,
                target,
                exc,
                err_msg,
            )
            return False

    # ------------------------------------------------------------------ Internal helpers ------------------------------------------------------------------

    @staticmethod
    def _try_gdal_translate(source: Path, target: Path) -> bool:
        """Attempt GDAL Translate using Python GDAL bindings.

        This replaces the subprocess CLI call to avoid issues with broken
        system/Homebrew GDAL library dependencies.
        """
        settings.apply_gdal_env()
        gdal = None
        try:
            from osgeo import gdal  # type: ignore

            gdal.UseExceptions()

            creation_options = CogConverter._build_gdal_translate_options(source)

            a_srs = CogConverter._detect_spatial_reference(gdal, source)

            translate_kwargs = {
                "format": "GTiff",
                "creationOptions": creation_options,
            }
            if a_srs:
                translate_kwargs["outputSRS"] = a_srs

            options = gdal.TranslateOptions(**translate_kwargs)
            result_ds = gdal.Translate(str(target), str(source), options=options)
            if result_ds is None:
                err_msg = gdal.GetLastErrorMsg()
                LOGGER.error(
                    "Python gdal.Translate fallback returned None source=%s target=%s "
                    "error=%s",
                    source,
                    target,
                    err_msg,
                )
                return False

            # Build overview pyramids so it behaves as a valid, optimized Cloud Optimized GeoTIFF (COG).
            result_ds.BuildOverviews("NEAREST", [2, 4, 8, 16])
            result_ds = None  # Close dataset
            LOGGER.info(
                "Python gdal.Translate fallback succeeded source=%s target=%s",
                source,
                target,
            )
            return True
        except Exception as exc:
            err_msg = gdal.GetLastErrorMsg() if gdal is not None else ""
            LOGGER.error(
                "Python gdal.Translate fallback failed source=%s target=%s error=%s gdal_error=%s",
                source,
                target,
                exc,
                err_msg,
            )
            return False

    @staticmethod
    def _detect_spatial_reference(gdal_module: Any, source: Path) -> str | None:
        """Check if source has CRS, find sidecar PRJ or assign default EPSG:4326 if missing."""
        src_ds = gdal_module.Open(str(source))
        a_srs = None
        if src_ds is not None:
            spatial_ref = src_ds.GetSpatialRef()
            if spatial_ref is None:
                prj_path = source.with_suffix(".prj")
                if prj_path.exists():
                    try:
                        prj_content = prj_path.read_text().strip()
                        if prj_content:
                            a_srs = prj_content
                    except Exception:
                        pass
                if a_srs is None:
                    a_srs = "EPSG:4326"
            src_ds = None
        return a_srs

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
    def _default_creation_options(_source: Path) -> list[str]:
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
                _rows, cols = block_shapes[0]
                return cols < dataset.width
        except Exception:
            return False


# --------------------------------------------------------------------------- Convenience alias — preserves the original class name used in src/ ---------------------------------------------------------------------------

# : Backward-compatible alias for code that imported ``CogPreparationService`` : from the old ``cog_service`` package.
CogPreparationService = CogConverter

__all__ = [
    "CogConversionResult",
    "CogConverter",
    "CogPreparationService",  # backward-compat alias
]
