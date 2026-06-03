# Migration Guide: src/ → src_new/

## Overview

This guide explains how to transition from the original monolithic `src/` codebase to the refactored modular `src_new/` structure. The refactoring preserves all existing functionality while reorganizing code for better maintainability, deployment flexibility, and scalability.

## Key Principles

1. **No Logic Rewriting**: All working code from `src/` is preserved; only file organization changes
2. **Backward Compatibility**: All public APIs maintain original signatures
3. **Deployment Boundaries**: Code organized by deployment targets (Server 1, Server 2, clients)
4. **Centralized Configuration**: Hardcoded values moved to .env files
5. **Single Responsibility**: Large files split into focused modules

## Path Mapping Table

### Platform Core → Shared

| Original Path | New Path | Notes |
|--------------|----------|-------|
| `src/platform_core/config/settings.py` | `src_new/shared/config.py` | Now uses python-dotenv |
| `src/platform_core/utils/crs.py` | `src_new/shared/utils/coordinate_conversion.py` | CRS helpers |
| `src/platform_core/utils/geometry.py` | `src_new/shared/utils/file_validation.py` | Geometry + validators |
| `src/platform_core/ingestion/services/metadata_extractor.py` | `src_new/services/ingestion/gdal_pipelines/metadata_extractor.py` | GDAL metadata extraction |
| `src/platform_core/ingestion/services/cog_service/` | `src_new/services/ingestion/gdal_pipelines/cog_converter.py` | COG conversion |
| `src/platform_core/ingestion/services/file_kind.py` | `src_new/services/ingestion/format_handlers/` | Split by format |

### Server VM → Server 1 Services

| Original Path | New Path | Notes |
|--------------|----------|-------|
| `src/server_vm/server_backend/routes/ingest.py` | `src_new/services/ingestion/api/routes.py` | Ingestion endpoints |
| `src/server_vm/server_backend/routes/search.py` | `src_new/services/query/api/routes.py` | Query endpoints |
| `src/server_vm/server_backend/catalog/catalog_repository.py` | `src_new/services/query/repositories/raster_repository.py` | PostGIS data access |
| `src/server_vm/server_backend/schemas.py` | `src_new/shared/models/raster_metadata.py` | Pydantic models |
| `src/server_vm/titiler_service/service.py` | `src_new/services/tile_serving/titiler_config.py` | TiTiler setup |
| `src/server_vm/security.py` | `src_new/shared/auth/lan_security.py` | LAN security middleware |

### Server Gateway → Server 2 Services

| Original Path | New Path | Notes |
|--------------|----------|-------|
| `src/server_gateway/api/routes/search.py` | `src_new/services/query/api/routes.py` | Consolidated with server_vm |
| `src/server_gateway/api/catalog/catalog_repository.py` | `src_new/services/query/repositories/raster_repository.py` | Consolidated with server_vm |

### Desktop Clients → Clients

| Original Path | New Path | Notes |
|--------------|----------|-------|
| `src/desktop_ingestion/gui_admin/app.py` | `src_new/clients/desktop_ingestion/ui/main_window.py` | Ingestion client UI |
| `src/client_desktop/backend/main_window.py` | `src_new/clients/desktop_search/main_window.py` | Search client UI |
| `src/client_desktop/backend/bridge.py` | `src_new/clients/desktop_search/bridge/channel_setup.py` | QWebChannel setup |
| `src/client_desktop/frontend/bridge.js` | `src_new/clients/desktop_search/cesium/` | Split into modules |
| `src/client_desktop/client_frontend/web_assets/` | `src_new/clients/desktop_search/web_assets/` | HTML, CSS, CesiumJS |

## Step-by-Step Transition

### Phase 1: Environment Setup

1. **Create .env file** at project root:
   ```bash
   cp .env.example .env
   ```

2. **Edit .env** with your configuration:
   ```bash
   # Data storage
   DATA_ROOT=/path/to/geospatial/data
   
   # Database
   DATABASE_URL=postgresql://user:password@localhost:5432/gis_db
   
   # Service URLs
   INGESTION_SERVICE_URL=http://192.168.1.10:8001
   TILE_SERVICE_URL=http://192.168.1.10:8002
   QUERY_SERVICE_URL=http://192.168.1.20:8003
   
   # Security
   ALLOWED_HOSTS=192.168.1.0/24
   
   # Logging
   LOG_LEVEL=INFO
   LOG_FORMAT=json
   LOG_OUTPUT_PATH=/var/log/gis/service.log
   ```

3. **Set up conda environment**:
   ```bash
   bash src_new/scripts/setup_environment.sh
   ```

4. **Build Rust accelerators** (optional):
   ```bash
   bash src_new/scripts/build_rust.sh
   ```

### Phase 2: Database Migration

The database schema remains unchanged, but you may want to verify:

1. **Check PostGIS extension**:
   ```sql
   SELECT PostGIS_Version();
   ```

2. **Verify raster_assets table**:
   ```sql
   \d raster_assets
   ```

3. **Check spatial indexes**:
   ```sql
   SELECT indexname, indexdef 
   FROM pg_indexes 
   WHERE tablename = 'raster_assets';
   ```

No schema changes are required; `src_new/` uses the same database structure as `src/`.

### Phase 3: Server 1 Deployment (Ingestion + Tile)

1. **Copy deployment files** to Server 1:
   ```bash
   rsync -av src_new/ server1:/opt/gis/src_new/
   rsync -av .env server1:/opt/gis/
   ```

2. **Start services**:
   ```bash
   ssh server1
   cd /opt/gis
   bash src_new/scripts/deploy_server1.sh
   ```

3. **Verify services are running**:
   ```bash
   curl http://localhost:8001/health  # Ingestion Service
   curl http://localhost:8002/health  # Tile Service
   ```

4. **Check logs**:
   ```bash
   tail -f /var/log/gis/ingestion.log
   tail -f /var/log/gis/tile.log
   ```

### Phase 4: Server 2 Deployment (Query)

1. **Copy deployment files** to Server 2:
   ```bash
   rsync -av src_new/ server2:/opt/gis/src_new/
   rsync -av .env server2:/opt/gis/
   ```

2. **Start service**:
   ```bash
   ssh server2
   cd /opt/gis
   bash src_new/scripts/deploy_server2.sh
   ```

3. **Verify service is running**:
   ```bash
   curl http://localhost:8003/health  # Query Service
   ```

4. **Check logs**:
   ```bash
   tail -f /var/log/gis/query.log
   ```

### Phase 5: Desktop Client Deployment

#### Ingestion Client

1. **Copy client files** to data manager workstations:
   ```bash
   rsync -av src_new/clients/desktop_ingestion/ workstation:/opt/gis/ingestion_client/
   rsync -av src_new/shared/ workstation:/opt/gis/shared/
   rsync -av .env workstation:/opt/gis/
   ```

2. **Update .env** with Server 1 URL:
   ```bash
   INGESTION_SERVICE_URL=http://192.168.1.10:8001
   TILE_SERVICE_URL=http://192.168.1.10:8002
   ```

3. **Launch client**:
   ```bash
   bash src_new/scripts/start_ingestion_client.sh
   ```

#### Search Client

1. **Copy client files** to analyst workstations:
   ```bash
   rsync -av src_new/clients/desktop_search/ workstation:/opt/gis/search_client/
   rsync -av src_new/shared/ workstation:/opt/gis/shared/
   rsync -av .env workstation:/opt/gis/
   ```

2. **Update .env** with service URLs:
   ```bash
   QUERY_SERVICE_URL=http://192.168.1.20:8003
   TILE_SERVICE_URL=http://192.168.1.10:8002
   ```

3. **Launch client**:
   ```bash
   bash src_new/scripts/start_search_client.sh
   ```

### Phase 6: Verification

1. **Test ingestion workflow**:
   - Open Ingestion Client
   - Upload a test GeoTIFF
   - Verify status shows "cataloged"
   - Check PostGIS for new raster entry

2. **Test tile serving**:
   - Open Search Client
   - Navigate to uploaded raster location
   - Verify tiles load on 3D globe

3. **Test spatial queries**:
   - Click on map in Search Client
   - Verify query results appear
   - Check that uploaded raster is found

4. **Test health endpoints**:
   ```bash
   curl http://192.168.1.10:8001/health
   curl http://192.168.1.10:8002/health
   curl http://192.168.1.20:8003/health
   ```

## Configuration Changes

### Environment Variables

All configuration now uses environment variables instead of hardcoded values:

| Variable | Purpose | Default | Example |
|----------|---------|---------|---------|
| `DATA_ROOT` | Geospatial data storage | `/data` | `/mnt/gis/data` |
| `DATABASE_URL` | PostgreSQL connection | `postgresql://localhost/gis` | `postgresql://user:pass@host:5432/db` |
| `API_HOST` | Service bind address | `127.0.0.1` | `192.168.1.10` |
| `INGESTION_SERVICE_PORT` | Ingestion service port | `8001` | `8001` |
| `TILE_SERVICE_PORT` | Tile service port | `8002` | `8002` |
| `QUERY_SERVICE_PORT` | Query service port | `8003` | `8003` |
| `INGESTION_SERVICE_URL` | Ingestion service URL | `http://localhost:8001` | `http://192.168.1.10:8001` |
| `TILE_SERVICE_URL` | Tile service URL | `http://localhost:8002` | `http://192.168.1.10:8002` |
| `QUERY_SERVICE_URL` | Query service URL | `http://localhost:8003` | `http://192.168.1.20:8003` |
| `CESIUM_BASE_URL` | CesiumJS assets path | `/web_assets/vendor/cesium` | `/web_assets/vendor/cesium` |
| `MAX_UPLOAD_SIZE` | Max file upload size (bytes) | `10737418240` (10GB) | `21474836480` (20GB) |
| `TILE_CACHE_SIZE` | Tile cache size (tiles) | `1000` | `5000` |
| `GDAL_DISABLE_READDIR_ON_OPEN` | GDAL optimization | `EMPTY_DIR` | `EMPTY_DIR` |
| `GDAL_HTTP_MERGE_CONSECUTIVE_RANGES` | GDAL optimization | `YES` | `YES` |
| `ALLOWED_HOSTS` | IP whitelist | `127.0.0.1` | `192.168.1.0/24` |
| `LOG_LEVEL` | Logging level | `INFO` | `DEBUG` |
| `LOG_FORMAT` | Log format | `text` | `json` |
| `LOG_OUTPUT_PATH` | Log file path | `` (stdout only) | `/var/log/gis/service.log` |

### Import Statement Changes

Update imports in any custom code:

**Old**:
```python
from src.platform_core.config.settings import settings
from src.server_vm.server_backend.schemas import RasterMetadata
from src.platform_core.utils.crs import normalize_crs
```

**New**:
```python
from src_new.shared.config import settings
from src_new.shared.models.raster_metadata import RasterMetadata
from src_new.shared.utils.coordinate_conversion import normalize_crs
```

### API Endpoint Changes

All endpoints maintain backward compatibility, but URLs now include service-specific prefixes:

**Old** (monolithic):
```
POST http://localhost:8000/upload
GET  http://localhost:8000/status/{raster_id}
POST http://localhost:8000/query/point
GET  http://localhost:8000/tiles/{z}/{x}/{y}.png
```

**New** (microservices):
```
POST http://192.168.1.10:8001/upload              # Ingestion Service
GET  http://192.168.1.10:8001/status/{raster_id}  # Ingestion Service
POST http://192.168.1.20:8003/query/point         # Query Service
GET  http://192.168.1.10:8002/tiles/{z}/{x}/{y}.png  # Tile Service
```

## Common Issues and Solutions

### Issue: Services fail to start

**Symptoms**: Services exit immediately or show connection errors

**Solutions**:
1. Check .env file exists and has correct values
2. Verify database is accessible: `psql $DATABASE_URL`
3. Check port availability: `netstat -tuln | grep 8001`
4. Review logs: `tail -f /var/log/gis/*.log`
5. Verify conda environment is activated: `conda env list`

### Issue: Clients cannot connect to services

**Symptoms**: "Connection refused" or timeout errors

**Solutions**:
1. Verify service URLs in .env match actual server IPs
2. Check firewall rules allow LAN access
3. Verify services are running: `curl http://server:port/health`
4. Check ALLOWED_HOSTS includes client IP range
5. Test network connectivity: `ping server_ip`

### Issue: Tiles not loading

**Symptoms**: Blank tiles or 404 errors in Search Client

**Solutions**:
1. Verify raster was successfully ingested: `curl http://server:8001/status/{raster_id}`
2. Check DATA_ROOT path is accessible by Tile Service
3. Verify COG files exist: `ls -lh $DATA_ROOT/uploads/`
4. Check Tile Service logs for GDAL errors
5. Test tile endpoint directly: `curl http://server:8002/tiles/0/0/0.png?raster_id=...`

### Issue: Spatial queries return no results

**Symptoms**: Empty results despite rasters being cataloged

**Solutions**:
1. Verify PostGIS extension is installed: `SELECT PostGIS_Version();`
2. Check spatial indexes exist: `\d raster_assets`
3. Verify raster bounds are in EPSG:4326: `SELECT raster_id, min_lon, min_lat, max_lon, max_lat FROM raster_assets;`
4. Test query directly: `curl -X POST http://server:8003/query/point -d '{"lat": 40.0, "lon": -105.0}'`
5. Check Query Service logs for SQL errors

### Issue: Rust accelerators not loading

**Symptoms**: Warning "Rust accelerators unavailable, using Python fallback"

**Solutions**:
1. This is non-fatal; system will use Python implementations
2. To enable Rust: `bash src_new/scripts/build_rust.sh`
3. Verify Rust toolchain: `rustc --version`
4. Check maturin is installed: `pip list | grep maturin`
5. Rebuild: `cd src_new/services/ingestion/rust_accelerators && maturin develop`

### Issue: CesiumJS not rendering

**Symptoms**: Blank 3D globe in Search Client

**Solutions**:
1. Verify CesiumJS assets exist: `ls src_new/clients/desktop_search/web_assets/vendor/cesium/`
2. Check CESIUM_BASE_URL in .env
3. Open browser console (F12) for JavaScript errors
4. Verify QtWebEngine is installed: `python -c "from PySide6.QtWebEngine import *"`
5. Check web_assets/index.html loads correctly

## Rollback Procedure

If issues arise, you can rollback to the original `src/` codebase:

1. **Stop src_new/ services**:
   ```bash
   pkill -f "src_new.services"
   ```

2. **Restart original services**:
   ```bash
   # Use your original startup scripts
   bash src/start_services.sh
   ```

3. **Revert client configurations**:
   - Update service URLs back to original endpoints
   - Restart desktop clients

4. **Database remains unchanged** (no rollback needed)

## Testing Checklist

Before declaring migration complete, verify:

- [ ] All services start without errors
- [ ] Health endpoints return "healthy" status
- [ ] Ingestion Client can upload files
- [ ] Uploaded files appear in PostGIS
- [ ] Tiles load in Search Client
- [ ] Point queries return correct results
- [ ] Bounding box queries work
- [ ] Layer controls function (contrast, brightness)
- [ ] Camera controls work (flyTo, zoom)
- [ ] Logs are being written correctly
- [ ] Disk space monitoring works
- [ ] Database connectivity is stable
- [ ] No errors in service logs
- [ ] No errors in client logs

## Performance Tuning

After migration, consider these optimizations:

1. **Tile Cache Size**: Increase `TILE_CACHE_SIZE` for better performance
2. **Database Indexes**: Ensure GiST indexes exist on geometry columns
3. **GDAL Environment**: Verify GDAL env vars are applied
4. **Log Rotation**: Configure log rotation to prevent disk fill
5. **Uvicorn Workers**: Add `--workers N` to service startup scripts
6. **PostgreSQL Tuning**: Adjust `shared_buffers`, `work_mem` for PostGIS
7. **SSD Storage**: Use SSD for DATA_ROOT and database
8. **Network Bandwidth**: Ensure adequate LAN bandwidth for tile serving

## Support and Troubleshooting

For additional help:

1. **Check logs**: All services log to stdout and optionally to LOG_OUTPUT_PATH
2. **Review documentation**: See `docs/ARCHITECTURE.md`, `docs/API_REFERENCE.md`, `docs/CONFIGURATION.md`
3. **Run tests**: `pytest src_new/tests/ -v`
4. **Verify imports**: `python src_new/scripts/verify_imports.py`
5. **Check health endpoints**: All services expose `/health` for monitoring

## Next Steps

After successful migration:

1. **Monitor Performance**: Track service response times and resource usage
2. **Optimize Configuration**: Tune cache sizes, worker counts, etc.
3. **Document Custom Changes**: Record any site-specific modifications
4. **Plan Maintenance**: Schedule regular log rotation, database vacuuming
5. **Train Users**: Provide training on new client interfaces
6. **Backup Strategy**: Implement regular backups of DATA_ROOT and database
7. **Disaster Recovery**: Test restore procedures
8. **Capacity Planning**: Monitor growth and plan for scaling
