"""Volume calculation for fill-volume analysis.

Detects closed depressions (pits) within a user-drawn polygon, computes the
fill volume needed to bring each depression up to its local spill-point
elevation, and returns per-region geometry for 3-D visualisation.

Algorithm
---------
1. Read the DEM window clipped to the polygon.
2. Compute the *reference surface* as the mean elevation of the polygon rim
   (pixels on the polygon boundary), which approximates the natural ground
   level before erosion.
3. Identify *depression pixels*: valid pixels inside the polygon whose
   elevation is below the reference surface.
4. Label connected depression regions (4-connectivity).
5. For each region compute:
   - Fill volume  = Σ (ref − z_i) × pixel_area   [m³]
   - Centroid lon/lat for label placement
   - Convex-hull outline in lon/lat for 3-D extrusion
"""
from __future__ import annotations

import numpy as np

try:
    from shapely.geometry import Polygon, mapping
    from pyproj import Transformer
    import rasterio
    from rasterio.features import rasterize, shapes
    from scipy.ndimage import label as ndlabel
except ImportError:
    rasterio = None
    rasterize = None
    shapes = None
    Transformer = None
    Polygon = None
    mapping = None
    ndlabel = None

from desktop_client.client_backend.measurement_tools.models import (
    DepressionRegion,
    FillVolumeResult,
    VolumeMeasurement,
)
from desktop_client.client_backend.measurement_tools.dem_utils import read_dem_window


# ── Legacy entry-point (kept for backward compatibility) ─────────────────────

def compute_volume(
    lon_lat_points: list[tuple[float, float]],
    dem_path: str,
) -> VolumeMeasurement:
    """Compute cut/fill volume inside a polygon relative to mean elevation."""
    result = compute_fill_volume(lon_lat_points, dem_path)
    total_fill = sum(r.fill_volume_m3 for r in result.regions)
    return VolumeMeasurement(
        cut_volume_m3=0.0,
        fill_volume_m3=total_fill,
        net_volume_m3=-total_fill,
        reference_elevation_m=result.reference_elevation_m,
        void_fraction=result.void_fraction,
    )


# ── Main entry-point ──────────────────────────────────────────────────────────

def compute_fill_volume(
    lon_lat_points: list[tuple[float, float]],
    dem_path: str,
    min_region_area_m2: float = 1.0,
    progress_callback=None,
) -> FillVolumeResult:
    """Detect depressions and compute fill volume per region.

    Parameters
    ----------
    lon_lat_points:
        Polygon vertices as (lon, lat) pairs in WGS-84.
    dem_path:
        Path to the DEM GeoTIFF.
    min_region_area_m2:
        Minimum depression area to report (filters noise).
    progress_callback:
        Optional callback(percent, message) for progress updates.

    Returns
    -------
    FillVolumeResult
        Reference elevation, per-region results, and void fraction.
    """
    if rasterio is None or ndlabel is None:
        raise RuntimeError("rasterio and scipy are required for fill-volume analysis")
    if len(lon_lat_points) < 3:
        raise ValueError("At least 3 polygon vertices are required")

    def report_progress(pct: float, msg: str):
        if progress_callback:
            progress_callback(pct, msg)

    report_progress(5, "Reading DEM window")

    # ── 1. Read DEM window ────────────────────────────────────────────────────
    is_geographic = False  # Initialize flag
    with rasterio.open(dem_path) as src:
        dem_crs = src.crs
        is_geographic = dem_crs.is_geographic if dem_crs else False
        
        if is_geographic:
            # DEM is already in EPSG:4326 (WGS84) - no transformation needed
            # Identity transformers that just pass through coordinates
            class IdentityTransformer:
                @staticmethod
                def transform(x, y):
                    return (x, y)
            
            to_dem = IdentityTransformer()
            from_dem = IdentityTransformer()
            poly_dem = Polygon(lon_lat_points)
        else:
            # DEM is in a projected CRS - need transformation
            to_dem = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
            from_dem = Transformer.from_crs(src.crs, "EPSG:4326", always_xy=True)
            poly_dem = Polygon([to_dem.transform(lon, lat) for lon, lat in lon_lat_points])
        
        poly_dem = poly_dem if poly_dem.is_valid else poly_dem.buffer(0)

    dem, transform, res = read_dem_window(dem_path, poly_dem.bounds)
    if dem.size == 0:
        return FillVolumeResult(
            regions=[], reference_elevation_m=float("nan"), void_fraction=1.0
        )

    # Calculate pixel area correctly based on CRS type
    if is_geographic:
        # For geographic CRS (EPSG:4326), resolution is in degrees
        # Convert to approximate meters using latitude-dependent scaling
        # At the equator: 1 degree ≈ 111,320 meters
        # Use the center latitude of the polygon for approximation
        center_lat = (poly_dem.bounds[1] + poly_dem.bounds[3]) / 2
        meters_per_degree_lat = 111320.0
        meters_per_degree_lon = 111320.0 * np.cos(np.radians(center_lat))
        
        # res is in degrees, convert to meters
        res_x_m = res * meters_per_degree_lon
        res_y_m = res * meters_per_degree_lat
        px_area = res_x_m * res_y_m  # m²
    else:
        # For projected CRS, resolution is already in meters
        px_area = res * res  # m²
    
    report_progress(15, "Rasterizing polygon mask")

    # ── 2. Rasterise polygon mask ─────────────────────────────────────────────
    poly_mask = rasterize(
        [poly_dem.__geo_interface__],
        out_shape=dem.shape,
        transform=transform,
        fill=0,
        default_value=1,
        dtype=np.uint8,
        all_touched=False,
    )
    inside = poly_mask == 1
    valid_inside = inside & ~np.isnan(dem)

    total_inside = int(np.sum(inside))
    void_inside = int(np.sum(np.isnan(dem) & inside))
    void_fraction = (void_inside / total_inside) if total_inside > 0 else 0.0

    z_vals = dem[valid_inside]
    if z_vals.size == 0:
        return FillVolumeResult(
            regions=[], reference_elevation_m=float("nan"), void_fraction=void_fraction
        )

    # ── 3. Reference surface = 0 elevation (sea level) ────────────────────────
    # Find all pixels below zero elevation within the DEM tiles
    ref = 0.0  # Sea level reference

    report_progress(35, f"Reference elevation: {ref:.2f} m (sea level)")

    # ── 4. Depression pixels: inside polygon, below zero elevation ────────────
    depression_mask = valid_inside & (dem < ref)

    if not np.any(depression_mask):
        report_progress(100, "No depressions found")
        return FillVolumeResult(
            regions=[], reference_elevation_m=ref, void_fraction=void_fraction
        )

    report_progress(45, "Labeling connected regions")

    # ── 5. Label connected regions ────────────────────────────────────────────
    labeled, n_regions = ndlabel(depression_mask)

    report_progress(55, f"Found {n_regions} potential regions")

    regions: list[DepressionRegion] = []
    processed = 0

    for region_id in range(1, n_regions + 1):
        region_pixels = labeled == region_id
        n_px = int(np.sum(region_pixels))
        area_m2 = n_px * px_area
        if area_m2 < min_region_area_m2:
            processed += 1
            continue

        z_region = dem[region_pixels]
        dz = ref - z_region          # depth below reference (always > 0)
        fill_vol = float(np.sum(dz) * px_area)
        max_depth = float(np.max(dz))
        mean_depth = float(np.mean(dz))

        # Mean elevation of the surrounding rim (valid pixels inside polygon but NOT in depression)
        # Used by the JS renderer to place the polygon at the correct terrain height
        rim_pixels = valid_inside & ~depression_mask
        rim_elevation_m = float(np.mean(dem[rim_pixels])) if np.any(rim_pixels) else ref

        # Centroid in pixel space → lon/lat
        rows, cols = np.where(region_pixels)
        cx_px = float(np.mean(cols))
        cy_px = float(np.mean(rows))
        
        # Use rasterio's transform to convert pixel coordinates to DEM CRS coordinates
        # The * operator applies the affine transform: (x, y) = transform * (col, row)
        cx_dem, cy_dem = transform * (cx_px, cy_px)
        
        # Transform from DEM CRS to WGS84 lon/lat
        # pyproj Transformer with always_xy=True expects (x, y) order and returns (x, y)
        clon, clat = from_dem.transform(cx_dem, cy_dem)

        # Outline: vectorise the region mask → polygon ring in lon/lat
        outline_lonlat = _region_outline_lonlat(region_pixels, transform, from_dem)
        if len(outline_lonlat) < 3:
            # Fallback: use bounding box of the region pixels as outline
            rows_r, cols_r = np.where(region_pixels)
            if rows_r.size == 0:
                processed += 1
                continue
            r_min, r_max = int(rows_r.min()), int(rows_r.max())
            c_min, c_max = int(cols_r.min()), int(cols_r.max())
            # Add 1-pixel padding so tiny regions still form a valid polygon
            corners = [
                transform * (c_min - 0.5, r_min - 0.5),
                transform * (c_max + 0.5, r_min - 0.5),
                transform * (c_max + 0.5, r_max + 0.5),
                transform * (c_min - 0.5, r_max + 0.5),
                transform * (c_min - 0.5, r_min - 0.5),
            ]
            outline_lonlat = [from_dem.transform(x, y) for x, y in corners]

        regions.append(
            DepressionRegion(
                region_id=region_id,
                fill_volume_m3=fill_vol,
                area_m2=area_m2,
                max_depth_m=max_depth,
                mean_depth_m=mean_depth,
                reference_elevation_m=ref,
                rim_elevation_m=rim_elevation_m,
                centroid_lon=clon,
                centroid_lat=clat,
                outline_lonlat=outline_lonlat,
            )
        )
        
        processed += 1
        progress_pct = 55 + int((processed / n_regions) * 40)
        report_progress(progress_pct, f"Processing region {processed}/{n_regions}")

    # Sort largest first
    regions.sort(key=lambda r: r.fill_volume_m3, reverse=True)

    report_progress(100, f"Completed: {len(regions)} regions detected")

    return FillVolumeResult(
        regions=regions,
        reference_elevation_m=ref,
        void_fraction=void_fraction,
    )


def _region_outline_lonlat(
    mask: np.ndarray,
    transform,
    from_dem,
) -> list[tuple[float, float]]:
    """Extract the outer polygon ring of a binary mask in lon/lat."""
    try:
        from shapely.geometry import shape
        geoms = [
            shape(geom)
            for geom, val in shapes(mask.astype(np.uint8), transform=transform)
            if val == 1
        ]
        if not geoms:
            return []
        # Union all fragments (handles fragmented geometry from raster tracing)
        from shapely.ops import unary_union
        merged = unary_union(geoms)

        # Keep the actual region boundary (do not inflate with convex hull),
        # otherwise the rendered overlay can incorrectly spill into nearby
        # non-depression/high-elevation pixels.
        if merged.geom_type == "Polygon":
            boundary = merged
        elif merged.geom_type == "MultiPolygon":
            # Connected-component regions are expected to be single polygons.
            # If raster-to-vector yields multiple parts, use the largest part.
            boundary = max(merged.geoms, key=lambda g: g.area)
        else:
            return []

        # Pixel-aware smoothing to reduce stair-step boundaries from raster masks.
        # 1) small topology-preserving simplify removes one-pixel zig-zags
        # 2) light round buffer in/out softens hard orthogonal corners
        px_x = float(abs(transform.a)) if hasattr(transform, "a") else 0.0
        px_y = float(abs(transform.e)) if hasattr(transform, "e") else 0.0
        px = min(v for v in [px_x, px_y] if v > 0.0) if (px_x > 0.0 or px_y > 0.0) else 0.0

        if px > 0.0:
            simplified = boundary.simplify(px * 0.35, preserve_topology=True)
            if simplified is not None and not simplified.is_empty and simplified.geom_type == "Polygon":
                boundary = simplified

            smooth_r = px * 0.55
            smoothed = boundary.buffer(smooth_r, resolution=8, join_style=1).buffer(-smooth_r, resolution=8, join_style=1)
            if smoothed is not None and not smoothed.is_empty:
                if smoothed.geom_type == "Polygon":
                    boundary = smoothed
                elif smoothed.geom_type == "MultiPolygon":
                    boundary = max(smoothed.geoms, key=lambda g: g.area)

        coords = list(boundary.exterior.coords)
        return [from_dem.transform(x, y) for x, y in coords]
    except Exception:
        return []

