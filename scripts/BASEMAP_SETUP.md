# OpenStreetMap Basemap Setup for Asia

This guide explains how to download and set up an offline OpenStreetMap basemap for the Asia region with labels, borders, and place names.

## Overview

The basemap provides:
- ✅ Country borders and boundaries
- ✅ Place names (cities, towns, villages)
- ✅ Roads and highways
- ✅ Water bodies (rivers, lakes, oceans)
- ✅ Land use and terrain features
- ✅ Complete offline functionality

## Quick Start

### 1. Download OSM Tiles for Asia

```bash
# Download zoom levels 0-8 (recommended for Asia coverage)
python scripts/download_asia_basemap.py --zoom-levels 0-8

# Or download specific zoom levels
python scripts/download_asia_basemap.py --zoom-levels 5,6,7,8

# Or download with custom rate limiting (slower but more respectful)
python scripts/download_asia_basemap.py --zoom-levels 0-8 --rate-limit 0.5
```

### 2. Verify Tiles

Check that tiles are downloaded to:
```
src/offline_gis_app/desktop/web_assets/basemap/xyz/
├── 0/
├── 1/
├── 2/
├── ...
└── 8/
```

### 3. Run the Application

The basemap will automatically load when you start the application:

```bash
python -m offline_gis_app.cli desktop-server
```

## Download Options

### Zoom Levels

| Zoom | Coverage | Tile Count (Asia) | Download Time | Storage |
|------|----------|-------------------|---------------|---------|
| 0-4  | Continental | ~500 tiles | 5 minutes | ~50 MB |
| 0-6  | Regional | ~8,000 tiles | 1 hour | ~800 MB |
| 0-8  | Detailed | ~130,000 tiles | 12-18 hours | ~13 GB |
| 0-10 | Very Detailed | ~2M tiles | 7-10 days | ~200 GB |

**Recommended**: Zoom 0-8 provides excellent detail for most use cases.

### Rate Limiting

Be respectful to OpenStreetMap servers:

```bash
# Fast (0.1s delay) - use for small downloads
python scripts/download_asia_basemap.py --zoom-levels 0-6 --rate-limit 0.1

# Medium (0.5s delay) - recommended for zoom 0-8
python scripts/download_asia_basemap.py --zoom-levels 0-8 --rate-limit 0.5

# Slow (1.0s delay) - most respectful for large downloads
python scripts/download_asia_basemap.py --zoom-levels 0-10 --rate-limit 1.0
```

### Custom Region

To download a different region, edit `ASIA_BOUNDS` in `download_asia_basemap.py`:

```python
ASIA_BOUNDS = {
    "min_lat": -10.0,   # Southern boundary
    "max_lat": 55.0,    # Northern boundary
    "min_lon": 60.0,    # Western boundary
    "max_lon": 150.0,   # Eastern boundary
}
```

## Tile Server Options

### Default: OpenStreetMap Standard

```bash
python scripts/download_asia_basemap.py --tile-server "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
```

Features:
- ✅ Labels in local languages
- ✅ Country borders
- ✅ Roads and highways
- ✅ Place names
- ✅ Water bodies

### Alternative Tile Servers

**Note**: Always check the tile server's usage policy before downloading.

```bash
# OpenStreetMap (alternative server)
--tile-server "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"

# OpenStreetMap Humanitarian (more labels)
--tile-server "https://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png"

# OpenTopoMap (topographic style)
--tile-server "https://a.tile.opentopomap.org/{z}/{x}/{y}.png"
```

## Basemap Layer Behavior

### Layer Ordering

The basemap is automatically placed at the **bottom** of the layer stack:

```
┌─────────────────────────────┐
│  Your DEM/Imagery Layers    │  ← Top (user data)
├─────────────────────────────┤
│  OSM Basemap (labels, etc)  │  ← Bottom (reference)
└─────────────────────────────┘
```

### Non-Interference Guarantee

The basemap will **never interfere** with your data layers:
- ✅ Always stays at the bottom (index 0)
- ✅ Your DEM/imagery layers render on top
- ✅ Transparent areas in your data show the basemap underneath
- ✅ Opaque areas in your data completely hide the basemap

### Pixel-Perfect Alignment

The basemap uses Web Mercator projection (EPSG:3857), same as Cesium:
- ✅ Pixel-perfect alignment with your data
- ✅ No reprojection artifacts
- ✅ Accurate borders and place names

## Troubleshooting

### Tiles Not Loading

1. **Check tile directory**:
   ```bash
   ls -la src/offline_gis_app/desktop/web_assets/basemap/xyz/
   ```

2. **Verify tile format**:
   - OSM tiles should be `.png` files
   - Check a few tiles: `file src/offline_gis_app/desktop/web_assets/basemap/xyz/5/20/12.png`

3. **Check browser console**:
   - Open DevTools (F12)
   - Look for 404 errors on tile requests

### Download Interrupted

Resume from where you left off:
```bash
# The script automatically skips existing tiles
python scripts/download_asia_basemap.py --zoom-levels 0-8
```

### Rate Limited (HTTP 429)

Increase the rate limit delay:
```bash
python scripts/download_asia_basemap.py --zoom-levels 0-8 --rate-limit 1.0
```

### Disk Space Issues

Check available space before downloading:
```bash
df -h .
```

For zoom 0-8, you need at least **15 GB free space**.

## Advanced Configuration

### Custom Tile Format

If you have tiles in a different format (e.g., JPEG), update `bridge.js`:

```javascript
const osmProvider = new Cesium.UrlTemplateImageryProvider({
  url: `${LOCAL_SATELLITE_TILE_ROOT}/{z}/{x}/{y}.jpg`,  // Change to .jpg
  // ... rest of config
});
```

### Adjust Maximum Zoom Level

Edit `bridge.js`:

```javascript
const LOCAL_SATELLITE_DEFAULT_MAX_LEVEL = 10;  // Increase for more detail
```

### Basemap Opacity

To make the basemap semi-transparent:

```javascript
globalBasemapLayer.alpha = 0.7;  // 70% opacity
```

## OpenStreetMap Usage Policy

When using OpenStreetMap tiles, please:

1. **Respect rate limits**: Use `--rate-limit` to avoid overloading servers
2. **Cache tiles locally**: Don't re-download tiles you already have
3. **Attribute properly**: The application automatically includes OSM attribution
4. **Read the policy**: https://operations.osmfoundation.org/policies/tiles/

## Storage Estimates

| Zoom Levels | Asia Tiles | Storage | Download Time (0.5s/tile) |
|-------------|------------|---------|---------------------------|
| 0-4         | ~500       | ~50 MB  | ~4 minutes                |
| 0-5         | ~2,000     | ~200 MB | ~17 minutes               |
| 0-6         | ~8,000     | ~800 MB | ~1.1 hours                |
| 0-7         | ~32,000    | ~3.2 GB | ~4.4 hours                |
| 0-8         | ~130,000   | ~13 GB  | ~18 hours                 |
| 0-9         | ~520,000   | ~52 GB  | ~3 days                   |
| 0-10        | ~2,000,000 | ~200 GB | ~12 days                  |

**Note**: Actual tile counts and storage may vary based on the region and tile availability.

## Alternative: Pre-Downloaded Tile Packs

If you don't want to download tiles yourself, you can:

1. **Use existing tile packs**: Some organizations provide pre-downloaded OSM tile packs
2. **Share tiles**: If multiple users need the same region, download once and share
3. **Use a tile server**: Set up a local tile server (e.g., TileServer GL) instead

## Support

For issues or questions:
- Check the browser console for errors
- Verify tile paths and formats
- Ensure sufficient disk space
- Test with a small zoom range first (0-4)

## License

OpenStreetMap data is © OpenStreetMap contributors, available under the Open Database License (ODbL).
