"""CRS reprojection pipeline for the Ingestion Service.

Extracts and adapts the reprojection logic from
``src/platform_core/ingestion/services/ingestion_service/transform_stage.py``
into a standalone, reusable module.

All GDAL operations are preceded by ``settings.apply_gdal_env()`` to ensure
the environment variables defined in ``src_new/shared/config.py`` are applied
before any GDAL call.

Requirements: 9.1, 9.2, 9.4
"""
from __future__ import annotations

import logging
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src_new.shared.config import settings
from src_new.shared.constants import EPSG_WEB_MERCATOR

LOGGER = logging.getLogger("services.ingestion.reprojector")


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReprojectionResult:
    """Outcome of a reprojection operation.

    Attributes:
        source_path: Original input raster path.
        output_path: Path to the reprojected output raster.
        reprojected: ``True`` when a new file was written; ``False`` when the
            source was already in the target CRS and no conversion was needed.
        source_crs: CRS string of the source raster (e.g. ``"EPSG:4326"``).
        target_crs: CRS string of the output raster (e.g. ``"EPSG:3857"``).
    """

    source_path: Path
    output_path: Path
    reprojected: bool
    source_crs: str
    target_crs: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_stem(original_stem: str) -> str:
    """Return a filesystem-safe version of *original_stem*.

    Replaces spaces and special characters with underscores and collapses
    consecutive underscores.  Preserved from the original transform_stage.py
    implementation.
    """
    safe_chars: list[str] = []
    for char in original_stem:
        if char.isalnum() or char in "-_.":
            safe_chars.append(char)
        elif char in " ()[]{}":
            safe_chars.append("_")
        else:
            safe_chars.append("_")

    safe_name = "".join(safe_chars)
    while "__" in safe_name:
        safe_name = safe_name.replace("__", "_")
    safe_name = safe_name.strip("_")
    return safe_name or "raster"


def _build_warp_options(input_path: Path, target_epsg: int):  # type: ignore[return]
    """Build ``gdal.WarpOptions`` tuned for the input raster and host platform.

    Mirrors the logic in ``TransformToEPSG3857Stage._get_warp_options`` from
    the original codebase, adapted to accept an arbitrary *target_epsg*.
    """
    try:
        from osgeo import gdal  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "GDAL (osgeo) is required for reprojection. "
            "Install the 'gdal' conda package or 'gdal' pip extra."
        ) from exc

    ds = gdal.Open(str(input_path))
    if ds is None:
        raise RuntimeError(f"Cannot open input raster for analysis: {input_path}")

    band_count: int = ds.RasterCount
    width: int = ds.RasterXSize
    height: int = ds.RasterYSize
    data_type: int = (
        ds.GetRasterBand(1).DataType if band_count > 0 else gdal.GDT_Unknown
    )
    ds = None

    # Base creation options
    creation_options: list[str] = ["COMPRESS=LZW", "TILED=YES", "BIGTIFF=IF_SAFER"]

    # Platform-specific block sizes and cache limits
    if platform.system() == "Windows":
        creation_options.extend(
            ["BLOCKXSIZE=512", "BLOCKYSIZE=512", "NUM_THREADS=ALL_CPUS"]
        )
        warp_opts: dict[str, str] = {
            "NUM_THREADS": "ALL_CPUS",
            "GDAL_CACHEMAX": "512",
        }
    else:
        creation_options.extend(["BLOCKXSIZE=1024", "BLOCKYSIZE=1024"])
        warp_opts = {"NUM_THREADS": "ALL_CPUS", "GDAL_CACHEMAX": "1024"}

    # Large-raster adjustments
    total_pixels = width * height
    if total_pixels > 100_000_000:
        LOGGER.info(
            "Large raster detected (%d pixels) — using conservative warp settings",
            total_pixels,
        )
        creation_options.append("BIGTIFF=YES")
        warp_opts["GDAL_CACHEMAX"] = "256"

    # Multi-band interleaving
    if band_count > 4:
        LOGGER.info(
            "Multi-band raster (%d bands) — using band-interleaved output", band_count
        )
        creation_options.append("INTERLEAVE=BAND")

    # Data-type predictors
    if data_type in (gdal.GDT_Float32, gdal.GDT_Float64):
        creation_options.append("PREDICTOR=3")
    elif data_type in (gdal.GDT_Byte, gdal.GDT_UInt16, gdal.GDT_Int16):
        creation_options.append("PREDICTOR=2")

    return gdal.WarpOptions(
        dstSRS=f"EPSG:{target_epsg}",
        format="GTiff",
        creationOptions=creation_options,
        multithread=True,
        warpOptions=[f"{k}={v}" for k, v in warp_opts.items()],
        errorThreshold=0.125,
        resampleAlg="bilinear",
    )


def _detect_source_crs(input_path: Path) -> str:
    """Return the CRS authority string of *input_path* (e.g. ``"EPSG:4326"``).

    Falls back to an empty string when the CRS cannot be determined.
    """
    try:
        from osgeo import gdal, osr  # type: ignore

        gdal.UseExceptions()
        ds = gdal.Open(str(input_path))
        if ds is None:
            return ""
        wkt = ds.GetProjection() or ""
        ds = None
        if not wkt:
            return ""
        srs = osr.SpatialReference()
        if srs.ImportFromWkt(wkt) != 0:
            return ""
        auth = srs.GetAuthorityName(None)
        code = srs.GetAuthorityCode(None)
        if auth and code:
            return f"{auth}:{code}"
        return wkt
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def reproject(
    input_path: Path,
    output_path: Optional[Path] = None,
    target_epsg: int = EPSG_WEB_MERCATOR,
) -> ReprojectionResult:
    """Reproject *input_path* to *target_epsg* and write the result to *output_path*.

    Args:
        input_path: Path to the source raster (GeoTIFF, JPEG2000, etc.).
        output_path: Destination path for the reprojected GeoTIFF.  When
            ``None``, the output is placed next to the source with a
            ``_{epsg}.tif`` suffix (e.g. ``raster_3857.tif``).
        target_epsg: EPSG code of the target CRS.  Defaults to
            ``EPSG_WEB_MERCATOR`` (3857).

    Returns:
        :class:`ReprojectionResult` describing the outcome.

    Raises:
        FileNotFoundError: When *input_path* does not exist.
        RuntimeError: When GDAL fails to reproject the raster.
        ImportError: When GDAL (osgeo) is not installed.
    """
    # Apply GDAL environment variables from centralized config before any GDAL call.
    settings.apply_gdal_env()

    try:
        from osgeo import gdal  # type: ignore

        gdal.UseExceptions()
    except ImportError as exc:
        raise ImportError(
            "GDAL (osgeo) is required for reprojection. "
            "Install the 'gdal' conda package or 'gdal' pip extra."
        ) from exc

    input_path = Path(input_path).resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input raster not found: {input_path}")

    # Determine output path
    if output_path is None:
        safe = _safe_stem(input_path.stem)
        output_path = input_path.parent / f"{safe}_{target_epsg}.tif"
    else:
        output_path = Path(output_path).resolve()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    source_crs = _detect_source_crs(input_path)
    target_crs = f"EPSG:{target_epsg}"

    LOGGER.info("=" * 80)
    LOGGER.info("REPROJECTION: %s", input_path.name)
    LOGGER.info("  Source CRS : %s", source_crs or "(unknown)")
    LOGGER.info("  Target CRS : %s", target_crs)
    LOGGER.info("  Output     : %s", output_path.name)
    LOGGER.info("=" * 80)

    # Skip if already in target CRS
    if source_crs and source_crs.upper() == target_crs.upper():
        LOGGER.info("✓ Already in %s — skipping reprojection", target_crs)
        return ReprojectionResult(
            source_path=input_path,
            output_path=input_path,
            reprojected=False,
            source_crs=source_crs,
            target_crs=target_crs,
        )

    # Warn about high-latitude distortion
    try:
        ds_check = gdal.Open(str(input_path))
        if ds_check is not None:
            gt = ds_check.GetGeoTransform()
            if gt:
                height_px = ds_check.RasterYSize
                y_min = gt[3] + height_px * gt[5]
                y_max = gt[3]
                max_lat = max(abs(y_min), abs(y_max))
                if max_lat > 60:
                    LOGGER.warning(
                        "⚠ HIGH LATITUDE DATA (%.1f°) — EPSG:3857 will have "
                        "significant distortion (>100%%)",
                        max_lat,
                    )
                elif max_lat > 45:
                    LOGGER.warning(
                        "⚠ MODERATE LATITUDE DATA (%.1f°) — EPSG:3857 will have "
                        "moderate distortion (~30–50%%)",
                        max_lat,
                    )
            ds_check = None
    except Exception:  # noqa: BLE001
        pass

    warp_options = _build_warp_options(input_path, target_epsg)

    # Use forward-slash paths for cross-platform GDAL compatibility
    input_str = str(input_path).replace("\\", "/")
    output_str = str(output_path).replace("\\", "/")

    LOGGER.info("Starting gdal.Warp …")
    ds = gdal.Warp(output_str, input_str, options=warp_options)
    if ds is None:
        error_msg = gdal.GetLastErrorMsg()
        # Clean up partial output
        if output_path.exists():
            try:
                output_path.unlink()
            except Exception:  # noqa: BLE001
                pass
        raise RuntimeError(
            f"gdal.Warp failed for {input_path.name}: {error_msg}"
        )

    if not output_path.exists():
        raise RuntimeError(f"Output file was not created: {output_path}")

    # Verify the output is readable
    verify_ds = gdal.Open(output_str)
    if verify_ds is None:
        raise RuntimeError(f"Reprojected output is not readable: {output_path}")

    output_size_mb = output_path.stat().st_size / (1024 * 1024)
    LOGGER.info(
        "✓ Reprojection successful — %s (%.2f MB, %d×%d px)",
        output_path.name,
        output_size_mb,
        verify_ds.RasterXSize,
        verify_ds.RasterYSize,
    )
    verify_ds = None
    ds = None

    return ReprojectionResult(
        source_path=input_path,
        output_path=output_path,
        reprojected=True,
        source_crs=source_crs,
        target_crs=target_crs,
    )


__all__ = [
    "ReprojectionResult",
    "reproject",
]
