# API Reference: Geospatial Microservices

## Overview

This document provides complete API reference for all three backend services:
- **Ingestion Service** (Server 1, port 8001): File upload and processing
- **Tile Service** (Server 1, port 8002): Dynamic tile generation
- **Query Service** (Server 2, port 8003): Spatial search and metadata

All services use REST APIs with JSON request/response bodies (except file uploads and tile images).

## Base URLs

```
Ingestion Service: http://{INGESTION_SERVICE_HOST}:8001
Tile Service:      http://{TILE_SERVICE_HOST}:8002
Query Service:     http://{QUERY_SERVICE_HOST}:8003
```

## Authentication

All services use IP-based access control via the `ALLOWED_HOSTS` environment variable. No API keys or tokens are required for LAN clients within the allowed IP range.

---

## Ingestion Service API

### POST /upload

Upload and ingest a geospatial raster file.

**Request**:
- Method: `POST`
- Content-Type: `multipart/form-data`
- Body:
  - `file`: Binary file data (GeoTIFF, JPEG2000, or MBTiles)

**Response** (200 OK):
```json
{
  "raster_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "cataloged",
  "message": "Raster 'example.tif' successfully ingested and cataloged.",
  "bbox": {
    "min_lon": -105.5,
    "min_lat": 39.5,
    "max_lon": -104.5,
    "max_lat": 40.5
  }
}
```

**Response Fields**:
- `raster_id` (string): UUID assigned to the ingested raster
- `status` (string): One of `"processing"`, `"cataloged"`, `"failed"`
- `message` (string): Human-readable status message
- `bbox` (object, optional): Geographic bounding box in WGS 84 (EPSG:4326)
  - `min_lon` (number): Minimum longitude
  - `min_lat` (number): Minimum latitude
  - `max_lon` (number): Maximum longitude
  - `max_lat` (number): Maximum latitude

**Error Responses**:
- `400 Bad Request`: Invalid file format or missing filename
- `413 Payload Too Large`: File exceeds MAX_UPLOAD_SIZE
- `422 Unprocessable Entity`: File failed format validation
- `500 Internal Server Error`: Metadata extraction or database error

**Example**:
```bash
curl -X POST http://192.168.1.10:8001/upload \
  -F "file=@/path/to/raster.tif"
```

---

### GET /status/{raster_id}

Get ingestion status for a previously uploaded raster.

**Request**:
- Method: `GET`
- Path Parameters:
  - `raster_id` (string): UUID of the raster asset

**Response** (200 OK):
```json
{
  "raster_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "cataloged",
  "progress": 1.0,
  "error": null
}
```

**Response Fields**:
- `raster_id` (string): UUID of the raster asset
- `status` (string): Current ingestion status
- `progress` (number): Progress from 0.0 (queued) to 1.0 (complete)
- `error` (string, nullable): Error message if ingestion failed

**Error Responses**:
- `404 Not Found`: No ingestion record found for the given raster_id

**Example**:
```bash
curl http://192.168.1.10:8001/status/550e8400-e29b-41d4-a716-446655440000
```

---

### GET /health

Health check endpoint for monitoring.

**Request**:
- Method: `GET`

**Response** (200 OK):
```json
{
  "status": "healthy",
  "database": true,
  "disk_space_gb": 523.45
}
```

**Response Fields**:
- `status` (string): One of `"healthy"`, `"degraded"`, `"unhealthy"`
- `database` (boolean): Database connectivity status
- `disk_space_gb` (number): Free disk space in gigabytes

**Example**:
```bash
curl http://192.168.1.10:8001/health
```

---

## Tile Service API

### GET /tiles/{z}/{x}/{y}.png

Get a map tile for a specific raster at the given zoom level and tile coordinates.

**Request**:
- Method: `GET`
- Path Parameters:
  - `z` (integer): Zoom level (0-22)
  - `x` (integer): Tile X coordinate
  - `y` (integer): Tile Y coordinate
- Query Parameters:
  - `raster_id` (string, required): UUID of the raster to tile
  - `contrast` (number, optional): Contrast adjustment (default: 1.0)
  - `brightness` (number, optional): Brightness adjustment (default: 0.0)
  - `colormap` (string, optional): Colormap name (e.g., "viridis", "terrain")

**Response** (200 OK):
- Content-Type: `image/png`
- Body: PNG image data (256×256 pixels)

**Error Responses**:
- `400 Bad Request`: Invalid parameters
- `404 Not Found`: Raster not found or tile outside bounds
- `500 Internal Server Error`: GDAL processing error

**Example**:
```bash
# Basic tile request
curl http://192.168.1.10:8002/tiles/10/512/384.png?raster_id=550e8400-e29b-41d4-a716-446655440000 \
  -o tile.png

# With image adjustments
curl "http://192.168.1.10:8002/tiles/10/512/384.png?raster_id=550e8400-e29b-41d4-a716-446655440000&contrast=1.2&brightness=0.1&colormap=viridis" \
  -o tile_adjusted.png
```

---

### GET /preview/{raster_id}

Get a preview thumbnail of a raster.

**Request**:
- Method: `GET`
- Path Parameters:
  - `raster_id` (string): UUID of the raster

**Response** (200 OK):
- Content-Type: `image/png`
- Body: PNG image data (512×512 pixels)

**Error Responses**:
- `404 Not Found`: Raster not found
- `500 Internal Server Error`: GDAL processing error

**Example**:
```bash
curl http://192.168.1.10:8002/preview/550e8400-e29b-41d4-a716-446655440000 \
  -o preview.png
```

---

### GET /metadata/{raster_id}

Get tile metadata for a raster (bounds, zoom levels, center point).

**Request**:
- Method: `GET`
- Path Parameters:
  - `raster_id` (string): UUID of the raster

**Response** (200 OK):
```json
{
  "bounds": {
    "min_lon": -105.5,
    "min_lat": 39.5,
    "max_lon": -104.5,
    "max_lat": 40.5
  },
  "minzoom": 0,
  "maxzoom": 18,
  "center": [-105.0, 40.0]
}
```

**Response Fields**:
- `bounds` (object): Geographic bounding box in WGS 84
- `minzoom` (integer): Minimum recommended zoom level
- `maxzoom` (integer): Maximum recommended zoom level
- `center` (array): Center point [longitude, latitude]

**Error Responses**:
- `404 Not Found`: Raster not found

**Example**:
```bash
curl http://192.168.1.10:8002/metadata/550e8400-e29b-41d4-a716-446655440000
```

---

### GET /health

Health check endpoint for monitoring.

**Request**:
- Method: `GET`

**Response** (200 OK):
```json
{
  "status": "healthy"
}
```

**Example**:
```bash
curl http://192.168.1.10:8002/health
```

---

## Query Service API

### POST /query/point

Find all rasters that contain a specific geographic point.

**Request**:
- Method: `POST`
- Content-Type: `application/json`
- Body:
```json
{
  "lat": 40.0,
  "lon": -105.0,
  "crs": "EPSG:4326"
}
```

**Request Fields**:
- `lat` (number): Latitude in decimal degrees
- `lon` (number): Longitude in decimal degrees
- `crs` (string, optional): Coordinate reference system (default: "EPSG:4326")

**Response** (200 OK):
```json
{
  "rasters": [
    {
      "raster_id": "550e8400-e29b-41d4-a716-446655440000",
      "file_path": "/data/uploads/abc123/example.tif",
      "file_name": "example.tif",
      "kind": "GEOTIFF",
      "crs": "EPSG:32613",
      "bbox": {
        "min_lon": -105.5,
        "min_lat": 39.5,
        "max_lon": -104.5,
        "max_lat": 40.5
      },
      "resolution_x": 0.02,
      "resolution_y": 0.02,
      "width": 5000,
      "height": 5000,
      "upload_date": "2024-01-15T10:30:00Z"
    }
  ],
  "count": 1
}
```

**Response Fields**:
- `rasters` (array): List of matching raster metadata objects
  - `raster_id` (string): UUID of the raster
  - `file_path` (string): Absolute path to the raster file
  - `file_name` (string): Original filename
  - `kind` (string): Raster type (GEOTIFF, JPEG2000, MBTILES, DEM, UNKNOWN)
  - `crs` (string): Coordinate reference system (EPSG code or WKT)
  - `bbox` (object): Geographic bounding box in WGS 84
  - `resolution_x` (number): Pixel resolution in X direction (degrees)
  - `resolution_y` (number): Pixel resolution in Y direction (degrees)
  - `width` (integer): Raster width in pixels
  - `height` (integer): Raster height in pixels
  - `upload_date` (string): ISO 8601 timestamp of upload
- `count` (integer): Total number of matching rasters

**Error Responses**:
- `400 Bad Request`: Invalid coordinates or CRS
- `500 Internal Server Error`: Database query error

**Example**:
```bash
curl -X POST http://192.168.1.20:8003/query/point \
  -H "Content-Type: application/json" \
  -d '{"lat": 40.0, "lon": -105.0}'
```

---

### POST /query/bbox

Find all rasters that intersect a bounding box.

**Request**:
- Method: `POST`
- Content-Type: `application/json`
- Body:
```json
{
  "min_lon": -106.0,
  "min_lat": 39.0,
  "max_lon": -104.0,
  "max_lat": 41.0,
  "crs": "EPSG:4326"
}
```

**Request Fields**:
- `min_lon` (number): Minimum longitude
- `min_lat` (number): Minimum latitude
- `max_lon` (number): Maximum longitude
- `max_lat` (number): Maximum latitude
- `crs` (string, optional): Coordinate reference system (default: "EPSG:4326")

**Response** (200 OK):
```json
{
  "rasters": [
    {
      "raster_id": "550e8400-e29b-41d4-a716-446655440000",
      "file_path": "/data/uploads/abc123/example.tif",
      "file_name": "example.tif",
      "kind": "GEOTIFF",
      "crs": "EPSG:32613",
      "bbox": {
        "min_lon": -105.5,
        "min_lat": 39.5,
        "max_lon": -104.5,
        "max_lat": 40.5
      },
      "resolution_x": 0.02,
      "resolution_y": 0.02,
      "width": 5000,
      "height": 5000,
      "upload_date": "2024-01-15T10:30:00Z"
    }
  ],
  "count": 1
}
```

**Response Fields**: Same as `/query/point`

**Error Responses**:
- `400 Bad Request`: Invalid bounding box or CRS
- `500 Internal Server Error`: Database query error

**Example**:
```bash
curl -X POST http://192.168.1.20:8003/query/bbox \
  -H "Content-Type: application/json" \
  -d '{"min_lon": -106.0, "min_lat": 39.0, "max_lon": -104.0, "max_lat": 41.0}'
```

---

### GET /raster/{raster_id}

Get metadata for a specific raster by ID.

**Request**:
- Method: `GET`
- Path Parameters:
  - `raster_id` (string): UUID of the raster

**Response** (200 OK):
```json
{
  "raster_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_path": "/data/uploads/abc123/example.tif",
  "file_name": "example.tif",
  "kind": "GEOTIFF",
  "crs": "EPSG:32613",
  "bbox": {
    "min_lon": -105.5,
    "min_lat": 39.5,
    "max_lon": -104.5,
    "max_lat": 40.5
  },
  "resolution_x": 0.02,
  "resolution_y": 0.02,
  "width": 5000,
  "height": 5000,
  "upload_date": "2024-01-15T10:30:00Z"
}
```

**Response Fields**: Same as raster objects in query responses

**Error Responses**:
- `404 Not Found`: Raster not found

**Example**:
```bash
curl http://192.168.1.20:8003/raster/550e8400-e29b-41d4-a716-446655440000
```

---

### GET /health

Health check endpoint for monitoring.

**Request**:
- Method: `GET`

**Response** (200 OK):
```json
{
  "status": "healthy",
  "database": true
}
```

**Response Fields**:
- `status` (string): One of `"healthy"`, `"degraded"`, `"unhealthy"`
- `database` (boolean): Database connectivity status

**Example**:
```bash
curl http://192.168.1.20:8003/health
```

---

## Common Data Models

### BoundingBox

Geographic bounding box in WGS 84 (EPSG:4326).

```json
{
  "min_lon": -105.5,
  "min_lat": 39.5,
  "max_lon": -104.5,
  "max_lat": 40.5
}
```

**Fields**:
- `min_lon` (number): Minimum longitude (-180 to 180)
- `min_lat` (number): Minimum latitude (-90 to 90)
- `max_lon` (number): Maximum longitude (-180 to 180)
- `max_lat` (number): Maximum latitude (-90 to 90)

### RasterMetadata

Complete metadata for a cataloged raster.

```json
{
  "raster_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_path": "/data/uploads/abc123/example.tif",
  "file_name": "example.tif",
  "kind": "GEOTIFF",
  "crs": "EPSG:32613",
  "bbox": {
    "min_lon": -105.5,
    "min_lat": 39.5,
    "max_lon": -104.5,
    "max_lat": 40.5
  },
  "resolution_x": 0.02,
  "resolution_y": 0.02,
  "width": 5000,
  "height": 5000,
  "upload_date": "2024-01-15T10:30:00Z"
}
```

**Fields**:
- `raster_id` (string): UUID of the raster
- `file_path` (string): Absolute path to the raster file
- `file_name` (string): Original filename
- `kind` (string): Raster type enum
  - `GEOTIFF`: GeoTIFF format
  - `JPEG2000`: JPEG2000 format
  - `MBTILES`: MBTiles format
  - `DEM`: Digital Elevation Model
  - `UNKNOWN`: Unknown or unsupported format
- `crs` (string): Coordinate reference system (EPSG code or WKT)
- `bbox` (object): Geographic bounding box in WGS 84
- `resolution_x` (number): Pixel resolution in X direction (degrees or meters)
- `resolution_y` (number): Pixel resolution in Y direction (degrees or meters)
- `width` (integer): Raster width in pixels
- `height` (integer): Raster height in pixels
- `upload_date` (string): ISO 8601 timestamp of upload

---

## Error Handling

All services use standard HTTP status codes and return JSON error responses:

```json
{
  "detail": "Error message describing what went wrong"
}
```

### Common Status Codes

- `200 OK`: Request succeeded
- `400 Bad Request`: Invalid request parameters
- `404 Not Found`: Resource not found
- `413 Payload Too Large`: File upload exceeds size limit
- `422 Unprocessable Entity`: Request validation failed
- `500 Internal Server Error`: Server-side error
- `503 Service Unavailable`: Service is temporarily unavailable

---

## Rate Limiting

No rate limiting is currently enforced. All services are designed for LAN deployment with trusted clients.

---

## CORS

CORS is not enabled by default. All services are designed for same-network access only.

---

## OpenAPI Documentation

All services provide interactive API documentation:

- Ingestion Service: `http://192.168.1.10:8001/docs`
- Tile Service: `http://192.168.1.10:8002/docs`
- Query Service: `http://192.168.1.20:8003/docs`

Alternative ReDoc documentation:

- Ingestion Service: `http://192.168.1.10:8001/redoc`
- Tile Service: `http://192.168.1.10:8002/redoc`
- Query Service: `http://192.168.1.20:8003/redoc`

---

## Client Libraries

### Python Example

```python
import httpx

# Upload a raster
with open("example.tif", "rb") as f:
    response = httpx.post(
        "http://192.168.1.10:8001/upload",
        files={"file": ("example.tif", f, "image/tiff")}
    )
    data = response.json()
    raster_id = data["raster_id"]

# Query by point
response = httpx.post(
    "http://192.168.1.20:8003/query/point",
    json={"lat": 40.0, "lon": -105.0}
)
results = response.json()

# Get a tile
response = httpx.get(
    f"http://192.168.1.10:8002/tiles/10/512/384.png",
    params={"raster_id": raster_id}
)
with open("tile.png", "wb") as f:
    f.write(response.content)
```

### JavaScript Example

```javascript
// Upload a raster
const formData = new FormData();
formData.append('file', fileInput.files[0]);

const uploadResponse = await fetch('http://192.168.1.10:8001/upload', {
  method: 'POST',
  body: formData
});
const uploadData = await uploadResponse.json();
const rasterId = uploadData.raster_id;

// Query by point
const queryResponse = await fetch('http://192.168.1.20:8003/query/point', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ lat: 40.0, lon: -105.0 })
});
const queryData = await queryResponse.json();

// Get a tile URL
const tileUrl = `http://192.168.1.10:8002/tiles/10/512/384.png?raster_id=${rasterId}`;
```

---

## Versioning

The current API version is **1.0.0**. Future versions will maintain backward compatibility or provide versioned endpoints (e.g., `/v2/upload`).

---

## Support

For API questions or issues:
1. Check service logs for detailed error messages
2. Verify service health endpoints
3. Review this documentation
4. Consult `docs/ARCHITECTURE.md` for system design
5. See `docs/MIGRATION_GUIDE.md` for deployment guidance
