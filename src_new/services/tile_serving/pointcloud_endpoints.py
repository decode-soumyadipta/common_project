"""Point-cloud 3D Tiles endpoint.

Converts a raw LAS/LAZ file to Cesium 3D Tiles on-the-fly so that the
CesiumJS viewer can render it as a native Cesium3DTileset rather than
trying to pass it through the raster/TiTiler pipeline.

No external LAS library is required — the LAS 1.x binary header is parsed
with Python's ``struct`` module, and the point records are read in a tight
NumPy loop.  ``laspy`` is used when available for better CRS / LAS 1.4
support.

Endpoints
---------
GET /pointcloud/tileset/{file_path_b64}/tileset.json
    Returns the Cesium 3D Tiles ``tileset.json`` for the given file.
GET /pointcloud/tileset/{file_path_b64}/points.pnts
    Returns the binary ``.pnts`` tile containing all (or a sampled subset
    of) the point-cloud points.
GET /pointcloud/info/{file_path_b64}
    Returns JSON metadata (bounds, point count, CRS) without building the
    full tile.
"""
from __future__ import annotations

import base64
import logging
import math
import struct
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, Response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pointcloud", tags=["pointcloud"])

# Maximum number of points to include in a single .pnts tile.
# For the NEON sample (~1 M pts) this is well within reason; for very large
# files we sub-sample uniformly so the tile stays under ~50 MB.
MAX_POINTS = 500_000

# Cesium magic numbers
_PNTS_MAGIC = b"pnts"
_PNTS_VERSION = 1


# ---------------------------------------------------------------------------
# Helpers — LAS binary reader (pure Python + NumPy, no laspy required)
# ---------------------------------------------------------------------------

def _decode_file_path(b64: str) -> Path:
    """Decode a URL-safe base64-encoded file path."""
    try:
        raw = base64.urlsafe_b64decode(b64 + "==")
        return Path(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid file path encoding: {exc}") from exc


def _read_las_header(path: Path) -> dict[str, Any]:
    """Parse the fixed LAS 1.x header (first 375 bytes) with struct."""
    with path.open("rb") as fh:
        raw = fh.read(375)

    if len(raw) < 227:
        raise HTTPException(status_code=400, detail="File too small to be a valid LAS file.")

    magic = raw[:4]
    if magic != b"LASF":
        raise HTTPException(status_code=400, detail=f"Not a LAS file (magic={magic!r}).")

    ver_major = raw[24]
    ver_minor = raw[25]

    # Point data record format and header size
    header_size = struct.unpack_from("<H", raw, 96)[0]
    offset_to_point_data = struct.unpack_from("<I", raw, 98)[0]
    point_format_id = raw[104] if len(raw) > 104 else raw[106]
    point_record_length = struct.unpack_from("<H", raw, 105)[0] if len(raw) > 105 else struct.unpack_from("<H", raw, 107)[0]

    # Legacy point count (LAS 1.0-1.3 uses 4-byte field at offset 107;
    # LAS 1.4 stores 0 there and uses 8-byte field at offset 247)
    legacy_count = struct.unpack_from("<I", raw, 107)[0]
    point_count = legacy_count

    if ver_major == 1 and ver_minor >= 4 and len(raw) >= 255:
        count_14 = struct.unpack_from("<Q", raw, 247)[0]
        if count_14 > 0:
            point_count = count_14

    # Scale / offset / extent
    x_scale = struct.unpack_from("<d", raw, 131)[0]
    y_scale = struct.unpack_from("<d", raw, 139)[0]
    z_scale = struct.unpack_from("<d", raw, 147)[0]
    x_off   = struct.unpack_from("<d", raw, 155)[0]
    y_off   = struct.unpack_from("<d", raw, 163)[0]
    z_off   = struct.unpack_from("<d", raw, 171)[0]
    max_x   = struct.unpack_from("<d", raw, 179)[0]
    min_x   = struct.unpack_from("<d", raw, 187)[0]
    max_y   = struct.unpack_from("<d", raw, 195)[0]
    min_y   = struct.unpack_from("<d", raw, 203)[0]
    max_z   = struct.unpack_from("<d", raw, 211)[0]
    min_z   = struct.unpack_from("<d", raw, 219)[0]

    return {
        "version": (ver_major, ver_minor),
        "header_size": header_size,
        "offset_to_point_data": offset_to_point_data,
        "point_format_id": point_format_id,
        "point_record_length": point_record_length,
        "point_count": point_count,
        "x_scale": x_scale, "y_scale": y_scale, "z_scale": z_scale,
        "x_off": x_off, "y_off": y_off, "z_off": z_off,
        "min_x": min_x, "max_x": max_x,
        "min_y": min_y, "max_y": max_y,
        "min_z": min_z, "max_z": max_z,
    }


def _read_las_xyz(path: Path, hdr: dict[str, Any]) -> np.ndarray:
    """Read XYZ point coordinates from a LAS file using NumPy.

    Returns an (N, 3) float64 array in the file's native CRS units.
    Sub-samples uniformly when the point count exceeds MAX_POINTS.
    """
    record_len = hdr["point_record_length"]
    if record_len < 12:
        raise HTTPException(status_code=500, detail="Point record too short to contain XYZ.")

    # Raw integer XYZ occupy the first 12 bytes of every point record
    count = hdr["point_count"]
    if count == 0:
        return np.empty((0, 3), dtype=np.float64)

    stride = record_len  # bytes per point record

    with path.open("rb") as fh:
        fh.seek(hdr["offset_to_point_data"])
        raw_bytes = fh.read(count * stride)

    actual = len(raw_bytes) // stride
    if actual == 0:
        return np.empty((0, 3), dtype=np.float64)

    # Build a structured dtype with one int32[3] sub-array at offset 0 and
    # skip the rest via padding.
    dt = np.dtype([
        ("xyz", "<i4", (3,)),
        ("_pad", "u1", (stride - 12,)),
    ])
    arr = np.frombuffer(raw_bytes[:actual * stride], dtype=dt)
    xyz_int = arr["xyz"].astype(np.float64)  # (N, 3)

    # Apply scale + offset to convert to real-world coordinates
    xyz_int[:, 0] = xyz_int[:, 0] * hdr["x_scale"] + hdr["x_off"]
    xyz_int[:, 1] = xyz_int[:, 1] * hdr["y_scale"] + hdr["y_off"]
    xyz_int[:, 2] = xyz_int[:, 2] * hdr["z_scale"] + hdr["z_off"]

    if actual > MAX_POINTS:
        step = actual // MAX_POINTS
        xyz_int = xyz_int[::step]

    return xyz_int


def _try_read_xyz_with_laspy(path: Path, max_pts: int) -> np.ndarray | None:
    """Attempt to read XYZ using laspy for better LAS 1.4 / LAZ support."""
    try:
        import laspy  # noqa: PLC0415
        with laspy.open(str(path)) as reader:
            total = reader.header.point_count
            step = max(1, total // max_pts)
            las = reader.read()
        x = np.array(las.x)[::step]
        y = np.array(las.y)[::step]
        z = np.array(las.z)[::step]
        try:
            r = (np.array(las.red)[::step] / 256).astype(np.uint8)
            g = (np.array(las.green)[::step] / 256).astype(np.uint8)
            b = (np.array(las.blue)[::step] / 256).astype(np.uint8)
            rgb = np.stack([r, g, b], axis=1)
        except Exception:
            rgb = None
        xyz = np.stack([x, y, z], axis=1)
        return xyz, rgb
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# CRS / coordinate reprojection helpers
# ---------------------------------------------------------------------------

def _reproject_to_wgs84(xyz: np.ndarray, crs_str: str) -> np.ndarray:
    """Reproject an (N,3) array from *crs_str* to EPSG:4326 (lon, lat, alt).

    Falls back to identity if reprojection is unavailable.
    """
    if crs_str in {"EPSG:4326", "WGS84", "WGS 84", "UNKNOWN", ""}:
        return xyz  # already lon/lat

    try:
        from pyproj import Transformer  # noqa: PLC0415
        t = Transformer.from_crs(crs_str, "EPSG:4326", always_xy=True)
        lon, lat = t.transform(xyz[:, 0], xyz[:, 1])
        return np.stack([lon, lat, xyz[:, 2]], axis=1)
    except Exception as exc:
        logger.warning("Could not reproject point cloud to WGS84: %s", exc)
        return xyz


def _guess_crs(hdr: dict[str, Any]) -> str:
    """Guess EPSG code from coordinate ranges."""
    min_x, max_x = hdr["min_x"], hdr["max_x"]
    min_y, max_y = hdr["min_y"], hdr["max_y"]

    # Geographic range → EPSG:4326
    if -180 <= min_x <= 180 and -90 <= min_y <= 90:
        return "EPSG:4326"

    # Common US projected CRS heuristics (easting in ~200000–900000, northing ~3000000–5500000)
    if 200_000 < min_x < 900_000 and 3_000_000 < min_y < 6_000_000:
        return "EPSG:32610"  # UTM Zone 10N — covers central CA (NEON data)

    return "UNKNOWN"


def _get_crs_from_file(path: Path, hdr: dict[str, Any]) -> str:
    """Extract CRS from a LAS/LAZ file using laspy, falling back to _guess_crs."""
    try:
        import laspy
        with laspy.open(str(path)) as reader:
            header = reader.header
            from src_new.services.ingestion.format_handlers.las_handler import _extract_crs_from_header
            return _extract_crs_from_header(header)
    except Exception as exc:
        logger.warning("Failed to extract CRS using laspy for %s: %s", path.name, exc)

    return _guess_crs(hdr)


# ---------------------------------------------------------------------------
# .pnts (Cesium Point Cloud) builder
# ---------------------------------------------------------------------------

def _wgs84_to_ecef(lon_deg: np.ndarray, lat_deg: np.ndarray, alt: np.ndarray) -> np.ndarray:
    """Convert WGS-84 geodetic coordinates to ECEF (metres)."""
    a = 6_378_137.0       # WGS-84 semi-major axis
    e2 = 6.694_379_990_14e-3  # first eccentricity squared
    lon = np.radians(lon_deg)
    lat = np.radians(lat_deg)
    N = a / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    x = (N + alt) * np.cos(lat) * np.cos(lon)
    y = (N + alt) * np.cos(lat) * np.sin(lon)
    z = (N * (1 - e2) + alt) * np.sin(lat)
    return np.stack([x, y, z], axis=1)


def _build_pnts(xyz_wgs84: np.ndarray, rgb: np.ndarray | None = None) -> bytes:
    """Build a Cesium .pnts binary tile from (N,3) WGS-84 lon/lat/alt array.

    The .pnts format stores positions as ECEF float32 relative to the tile
    centre (the ``RTC_CENTER`` Feature Table global property).
    """
    lon, lat, alt = xyz_wgs84[:, 0], xyz_wgs84[:, 1], xyz_wgs84[:, 2]
    ecef = _wgs84_to_ecef(lon, lat, alt)

    # Centre of tile
    centre = ecef.mean(axis=0)
    local = (ecef - centre).astype(np.float32)

    n_pts = len(local)
    positions_bytes = local.tobytes()

    has_color = rgb is not None and len(rgb) == n_pts

    # ---- Feature Table JSON ------------------------------------------------
    ft_json: dict[str, Any] = {
        "POINTS_LENGTH": n_pts,
        "RTC_CENTER": centre.tolist(),
        "POSITION": {"byteOffset": 0},
    }
    if has_color:
        ft_json["RGB"] = {"byteOffset": len(positions_bytes)}

    import json
    ft_json_bytes = json.dumps(ft_json, separators=(",", ":")).encode("utf-8")
    # Pad to 8-byte boundary
    ft_json_pad = (8 - len(ft_json_bytes) % 8) % 8
    ft_json_bytes += b" " * ft_json_pad

    ft_binary = positions_bytes
    if has_color:
        ft_binary += rgb.astype(np.uint8).tobytes()
    # Pad to 8-byte boundary
    ft_binary_pad = (8 - len(ft_binary) % 8) % 8
    ft_binary += b"\x00" * ft_binary_pad

    batch_json_bytes = b"{}"
    batch_json_pad = (8 - len(batch_json_bytes) % 8) % 8
    batch_json_bytes += b" " * batch_json_pad

    batch_binary = b""

    # ---- Header ------------------------------------------------------------
    # Magic(4) + Version(4) + ByteLength(4) + FeatureTableJSONByteLength(4)
    # + FeatureTableBinaryByteLength(4) + BatchTableJSONByteLength(4)
    # + BatchTableBinaryByteLength(4)  = 28 bytes
    header_size = 28
    total_length = (
        header_size
        + len(ft_json_bytes)
        + len(ft_binary)
        + len(batch_json_bytes)
        + len(batch_binary)
    )

    header = struct.pack(
        "<4sIIIIII",
        _PNTS_MAGIC,
        _PNTS_VERSION,
        total_length,
        len(ft_json_bytes),
        len(ft_binary),
        len(batch_json_bytes),
        len(batch_binary),
    )

    return header + ft_json_bytes + ft_binary + batch_json_bytes + batch_binary


# ---------------------------------------------------------------------------
# Bounds → tileset.json helpers
# ---------------------------------------------------------------------------

def _build_tileset_json(
    min_lon: float, min_lat: float, max_lon: float, max_lat: float,
    min_z: float, max_z: float,
    file_path_b64: str,
    point_count: int,
) -> dict:
    """Build a minimal Cesium 3D Tiles tileset.json."""
    import json

    # Bounding sphere: convert WGS-84 box to approximate ECEF sphere
    cx = (min_lon + max_lon) / 2
    cy = (min_lat + max_lat) / 2
    cz = (min_z + max_z) / 2

    lon_r = math.radians(cx)
    lat_r = math.radians(cy)
    a = 6_378_137.0
    e2 = 6.694_379_990_14e-3
    N = a / math.sqrt(1 - e2 * math.sin(lat_r) ** 2)
    centre_ecef_x = (N + cz) * math.cos(lat_r) * math.cos(lon_r)
    centre_ecef_y = (N + cz) * math.cos(lat_r) * math.sin(lon_r)
    centre_ecef_z = (N * (1 - e2) + cz) * math.sin(lat_r)

    # Rough radius: half diagonal of the bounding box in metres
    lat_m = (max_lat - min_lat) * 111_320
    lon_m = (max_lon - min_lon) * 111_320 * math.cos(math.radians(cy))
    z_m = max_z - min_z
    radius = math.sqrt(lat_m**2 + lon_m**2 + z_m**2) / 2 + 10.0  # +10 m buffer

    return {
        "asset": {"version": "1.0"},
        "geometricError": radius,
        "root": {
            "boundingVolume": {
                "sphere": [centre_ecef_x, centre_ecef_y, centre_ecef_z, radius]
            },
            "geometricError": radius,
            "refine": "ADD",
            "content": {
                "uri": "points.pnts"
            },
        },
    }


# ---------------------------------------------------------------------------
# In-memory cache (keyed by absolute path) so we don't re-parse on every
# tile request (useful when CesiumJS requests tileset.json + points.pnts
# in rapid succession).
# ---------------------------------------------------------------------------
_PNTS_CACHE: dict[str, bytes] = {}
_HDR_CACHE: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/tileset/{file_path_b64}/tileset.json",
    response_class=Response,
    summary="Cesium 3D Tiles tileset.json for a point cloud",
)
async def get_tileset_json(file_path_b64: str) -> Response:
    """Return the 3D Tiles tileset.json for a LAS/LAZ point cloud."""
    import json

    path = _decode_file_path(file_path_b64)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    if path.suffix.lower() not in (".las", ".laz"):
        raise HTTPException(status_code=400, detail="Only .las/.laz files are supported.")

    cache_key = str(path.resolve())
    if cache_key not in _HDR_CACHE:
        try:
            hdr = _read_las_header(path)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to read LAS header: {exc}") from exc
        _HDR_CACHE[cache_key] = hdr
    else:
        hdr = _HDR_CACHE[cache_key]

    # Determine CRS and reproject bounds to WGS-84
    crs = _get_crs_from_file(path, hdr)
    min_lon, min_lat = hdr["min_x"], hdr["min_y"]
    max_lon, max_lat = hdr["max_x"], hdr["max_y"]

    if crs not in {"EPSG:4326", "WGS84"}:
        # Try to reproject corner points
        corners = np.array([
            [hdr["min_x"], hdr["min_y"], 0.0],
            [hdr["max_x"], hdr["max_y"], 0.0],
        ])
        reprojected = _reproject_to_wgs84(corners, crs)
        min_lon = float(reprojected[:, 0].min())
        max_lon = float(reprojected[:, 0].max())
        min_lat = float(reprojected[:, 1].min())
        max_lat = float(reprojected[:, 1].max())

    tileset = _build_tileset_json(
        min_lon, min_lat, max_lon, max_lat,
        hdr["min_z"], hdr["max_z"],
        file_path_b64,
        hdr["point_count"],
    )

    logger.info(
        "Serving tileset.json for %s (crs=%s pts=%d bounds=[%.4f,%.4f,%.4f,%.4f])",
        path.name, crs, hdr["point_count"], min_lon, min_lat, max_lon, max_lat,
    )

    return Response(
        content=json.dumps(tileset),
        media_type="application/json",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get(
    "/tileset/{file_path_b64}/points.pnts",
    response_class=Response,
    summary="Cesium 3D Tiles .pnts tile for a point cloud",
)
async def get_points_pnts(file_path_b64: str) -> Response:
    """Return the binary .pnts tile containing point-cloud data."""
    path = _decode_file_path(file_path_b64)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    if path.suffix.lower() not in (".las", ".laz"):
        raise HTTPException(status_code=400, detail="Only .las/.laz files are supported.")

    cache_key = str(path.resolve())
    if cache_key in _PNTS_CACHE:
        logger.debug("Serving cached .pnts for %s", path.name)
        return Response(
            content=_PNTS_CACHE[cache_key],
            media_type="application/octet-stream",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=3600",
            },
        )

    # Try laspy first (better LAZ + color support)
    xyz_wgs84 = None
    rgb = None
    xyz_native, rgb = _try_read_xyz_with_laspy(path, MAX_POINTS)

    if xyz_native is not None and len(xyz_native) > 0:
        # Determine CRS from the LAS header for reprojection
        hdr = _HDR_CACHE.get(cache_key)
        if hdr is None:
            try:
                hdr = _read_las_header(path)
                _HDR_CACHE[cache_key] = hdr
            except Exception:
                hdr = {}
        crs = _get_crs_from_file(path, hdr) if hdr else "EPSG:4326"
        xyz_wgs84 = _reproject_to_wgs84(xyz_native, crs)
    else:
        # Pure-Python / NumPy fallback
        try:
            hdr = _HDR_CACHE.get(cache_key)
            if hdr is None:
                hdr = _read_las_header(path)
                _HDR_CACHE[cache_key] = hdr
            xyz_native = _read_las_xyz(path, hdr)
            crs = _get_crs_from_file(path, hdr)
            xyz_wgs84 = _reproject_to_wgs84(xyz_native, crs)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Failed to read point cloud %s: %s", path.name, exc, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to read point cloud: {exc}") from exc

    if xyz_wgs84 is None or len(xyz_wgs84) == 0:
        raise HTTPException(status_code=500, detail="No point data could be extracted from the file.")

    logger.info("Building .pnts for %s: %d points", path.name, len(xyz_wgs84))

    try:
        pnts_bytes = _build_pnts(xyz_wgs84, rgb)
    except Exception as exc:
        logger.error("Failed to build .pnts for %s: %s", path.name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to build .pnts tile: {exc}") from exc

    _PNTS_CACHE[cache_key] = pnts_bytes

    logger.info("Serving .pnts for %s: %d bytes", path.name, len(pnts_bytes))

    return Response(
        content=pnts_bytes,
        media_type="application/octet-stream",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get(
    "/info/{file_path_b64}",
    summary="Point cloud metadata (bounds, CRS, point count)",
)
async def get_pointcloud_info(file_path_b64: str) -> dict:
    """Return JSON metadata for a LAS/LAZ point cloud."""
    path = _decode_file_path(file_path_b64)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    cache_key = str(path.resolve())
    hdr = _HDR_CACHE.get(cache_key)
    if hdr is None:
        try:
            hdr = _read_las_header(path)
            _HDR_CACHE[cache_key] = hdr
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to read LAS header: {exc}") from exc

    crs = _guess_crs(hdr)
    return {
        "file": path.name,
        "point_count": hdr["point_count"],
        "crs_native": crs,
        "bounds_native": {
            "min_x": hdr["min_x"], "max_x": hdr["max_x"],
            "min_y": hdr["min_y"], "max_y": hdr["max_y"],
            "min_z": hdr["min_z"], "max_z": hdr["max_z"],
        },
        "las_version": f"{hdr['version'][0]}.{hdr['version'][1]}",
    }


__all__ = ["router"]
