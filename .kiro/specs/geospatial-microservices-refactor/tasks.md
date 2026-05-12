
# Implementation Plan: Geospatial Microservices Refactoring

## Overview

This plan converts the existing monolithic `src/` codebase into the modular `src_new/` structure defined in the design document. Every task is a **copy-reorganize-update** operation — no business logic is rewritten. Tasks are ordered so each step builds on the previous, with shared foundations laid before service-specific code, and tests wired in close to the code they validate.

Source mapping reference:
- `src/platform_core/` → shared models, utils, db, config
- `src/server_vm/` → ingestion service + tile service (Server 1)
- `src/server_gateway/` → query service (Server 2)
- `src/client_desktop/` + `src/desktop_client/` → desktop_search client
- `src/desktop_ingestion/` → desktop_ingestion client
- `src/client_desktop/frontend/bridge.js` → cesium/ modules

---

## Tasks

- [x] 1. Bootstrap src_new/ scaffold and shared configuration foundation
  - Create the full `src_new/` directory tree with all `__init__.py` files as defined in the design
  - Copy `src/platform_core/config/settings.py` → `src_new/shared/config.py`; update to use `python-dotenv` loading from project-root `.env`
  - Copy `src/platform_core/utils/crs.py` → `src_new/shared/utils/coordinate_conversion.py`
  - Copy `src/platform_core/utils/geometry.py` → `src_new/shared/utils/file_validation.py` (keep geometry helpers, add file-format validators)
  - Create `src_new/shared/utils/logging_config.py` from `src/client_desktop/backend/logging_setup.py`
  - Create `src_new/shared/utils/error_handlers.py` with FastAPI exception handlers extracted from existing route files
  - Create `src_new/shared/constants.py` defining SUPPORTED_FORMATS, EPSG codes, TILE_SIZE, MAX_UPLOAD_SIZE_DEFAULT
  - Write `.env.example` at project root with all variables from Requirement 4 (DATA_ROOT, DATABASE_URL, API_HOST, API_PORT, TITILER_BASE_URL, CESIUM_BASE_URL, INGESTION_SERVICE_URL, QUERY_SERVICE_URL, TILE_SERVICE_URL, MAX_UPLOAD_SIZE, TILE_CACHE_SIZE, GDAL_DISABLE_READDIR_ON_OPEN, GDAL_HTTP_MERGE_CONSECUTIVE_RANGES, ALLOWED_HOSTS, LOG_LEVEL, LOG_FORMAT, LOG_OUTPUT_PATH)
  - _Requirements: 1.1, 4.1, 4.2, 4.3, 4.4, 4.6, 12.5_

- [x] 2. Implement shared Pydantic data models
  - [x] 2.1 Create core shared models
    - Copy and adapt `src/server_vm/server_backend/schemas.py` → `src_new/shared/models/raster_metadata.py` (RasterMetadata Pydantic model)
    - Create `src_new/shared/models/bounding_box.py` (BoundingBox with min_lon, min_lat, max_lon, max_lat)
    - Create `src_new/shared/models/crs.py` (CoordinateReferenceSystem with epsg_code, wkt fields)
    - Create `src_new/shared/models/tile_request.py` (TileRequest with z, x, y, raster_id, contrast, brightness, colormap)
    - Create `src_new/shared/models/query_result.py` (QueryResult with rasters list and count)
    - Create `src_new/shared/models/__init__.py` re-exporting all models
    - _Requirements: 12.1, 12.4_

  - [-]* 2.2 Write unit tests for shared models
    - Test BoundingBox validation (invalid coordinate ranges, CRS mismatch)
    - Test RasterMetadata serialization round-trip
    - Test QueryResult with empty and populated rasters list
    - _Requirements: 19.2_

- [x] 3. Implement shared auth and LAN security module
  - [x] 3.1 Create lan_security.py from src/server_vm/security.py
    - Copy `src/server_vm/security.py` → `src_new/shared/auth/lan_security.py`
    - Update to read ALLOWED_HOSTS from `shared/config.py` (env var) instead of hardcoded values
    - Implement FastAPI middleware returning 403 for unauthorized IPs
    - Ensure services bind to LAN interface only (not 0.0.0.0) unless BIND_ALL_INTERFACES=true
    - _Requirements: 16.1, 16.2, 16.5, 16.6_

  - [-]* 3.2 Write unit tests for LAN security
    - Test IP allowlist enforcement (allowed IP passes, blocked IP returns 403)
    - Test missing ALLOWED_HOSTS env var falls back to localhost-only
    - _Requirements: 16.6, 19.2_

- [x] 4. Implement shared UI components
  - Copy `src/client_desktop/backend/main_window.py` login/settings/about dialog code → `src_new/shared/ui_components/login_dialog.py`, `settings_dialog.py`, `about_dialog.py`
  - Ensure all dialogs import config from `src_new/shared/config.py` rather than hardcoded values
  - Create `src_new/shared/ui_components/__init__.py` re-exporting all dialog classes
  - _Requirements: 7.6, 12.4_

- [x] 5. Checkpoint — shared foundation complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement PostGIS repository layer (Query Service — Server 2)
  - [x] 6.1 Create raster_repository.py
    - Copy PostGIS query logic from `src/server_vm/server_backend/catalog/catalog_repository.py` and `src/server_gateway/api/catalog/catalog_repository.py`
    - Consolidate into `src_new/services/query/repositories/raster_repository.py`
    - Implement methods: `find_by_bbox()`, `find_by_point()`, `find_by_id()`, `insert_metadata()`, `update_metadata()`
    - All queries must use parameterized statements (no f-string SQL)
    - All methods return typed models from `src_new/shared/models/`
    - _Requirements: 10.1, 10.2, 10.4, 10.5_

  - [x] 6.2 Create spatial_index_repository.py
    - Extract spatial index operations from existing catalog/repository files
    - Implement `create_gist_index()`, `query_intersects()`, `query_contains()` in `src_new/services/query/repositories/spatial_index_repository.py`
    - Use parameterized PostGIS ST_Intersects / ST_Contains queries
    - _Requirements: 10.3, 10.4_

  - [-]* 6.3 Write unit tests for repositories
    - Test `find_by_point()` with known coordinates against fixture data
    - Test `find_by_bbox()` returns correct subset of rasters
    - Test parameterized query safety (SQL injection attempt returns empty, not error)
    - _Requirements: 10.4, 19.2_

- [x] 7. Implement Query Service business logic and FastAPI app (Server 2)
  - [x] 7.1 Create spatial_queries.py
    - Copy business logic from `src/server_vm/server_backend/routes/search.py` and `src/server_gateway/api/routes/search.py`
    - Consolidate into `src_new/services/query/spatial_queries.py`
    - Compose `raster_repository` and `spatial_index_repository` methods; no raw SQL here
    - _Requirements: 10.6_

  - [x] 7.2 Create Query Service API routes and FastAPI app
    - Copy route handlers from `src/server_vm/server_backend/routes/` → `src_new/services/query/api/routes.py`
    - Implement endpoints: `POST /query/point`, `POST /query/bbox`, `GET /raster/{raster_id}`, `GET /health`
    - Create `src_new/services/query/api/dependencies.py` for DB session and config injection
    - Create `src_new/services/query/service.py` as the FastAPI app entry point; read port from `QUERY_SERVICE_PORT` env var
    - Apply `lan_security` middleware from `src_new/shared/auth/`
    - _Requirements: 6.3, 6.6, 16.1_

  - [ ]* 7.3 Write integration tests for Query Service API
    - Test `POST /query/point` returns correct rasters for known coordinates
    - Test `POST /query/bbox` with bounding box covering test fixture
    - Test `GET /health` returns healthy status
    - _Requirements: 14.2, 19.3_

- [x] 8. Checkpoint — Query Service complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement GDAL processing pipelines (Ingestion Service — Server 1)
  - [x] 9.1 Create metadata_extractor.py
    - Copy `src/platform_core/ingestion/services/metadata_extractor.py` → `src_new/services/ingestion/gdal_pipelines/metadata_extractor.py`
    - Update imports to use `src_new/shared/models/` and `src_new/shared/config.py`
    - Ensure GDAL env vars (GDAL_DISABLE_READDIR_ON_OPEN, GDAL_HTTP_MERGE_CONSECUTIVE_RANGES) are read from config before any GDAL call
    - _Requirements: 9.1, 9.2, 9.4_

  - [x] 9.2 Create cog_converter.py
    - Extract COG conversion logic from `src/platform_core/ingestion/services/cog_service/` → `src_new/services/ingestion/gdal_pipelines/cog_converter.py`
    - Preserve existing gdal.Translate / gdal.Warp call signatures
    - _Requirements: 9.1, 9.2_

  - [x] 9.3 Create reprojector.py and thumbnail_generator.py
    - Extract CRS reprojection logic → `src_new/services/ingestion/gdal_pipelines/reprojector.py`
    - Extract thumbnail/preview generation → `src_new/services/ingestion/gdal_pipelines/thumbnail_generator.py`
    - Both modules read GDAL config from `src_new/shared/config.py`
    - _Requirements: 9.1, 9.2_

  - [x] 9.4 Create format handlers
    - Copy format-detection logic from `src/platform_core/ingestion/services/file_kind.py` and `file_grouping_service.py`
    - Create `src_new/services/ingestion/format_handlers/geotiff_handler.py`, `jpeg2000_handler.py`, `mbtiles_handler.py`
    - Each handler exposes `validate(path)` and `extract_metadata(path)` functions
    - _Requirements: 9.3_

  - [~]* 9.5 Write unit tests for GDAL pipelines
    - Test `metadata_extractor` against `tests/data/sample.tif` fixture
    - Test `cog_converter` produces valid COG output (check IFD structure)
    - Test format handlers correctly identify GeoTIFF vs JPEG2000 vs MBTiles
    - _Requirements: 9.6, 19.2, 19.7_

- [x] 10. Implement Rust accelerators scaffold (Ingestion Service — Server 1)
  - Create `src_new/services/ingestion/rust_accelerators/Cargo.toml` with PyO3 dependency
  - Create `src_new/services/ingestion/rust_accelerators/rasterize.rs` stub implementing `rasterize_vectors()` using rusterize; include Python GIL release
  - Create `src_new/services/ingestion/rust_accelerators/transform.rs` stub implementing `transform_coordinates()` batch CRS transform
  - Create `src_new/services/ingestion/rust_accelerators/__init__.py` with try/except import: load compiled `.so`/`.pyd` if available, else fall back to pure-Python equivalents with a `logging.warning`
  - Create `scripts/build_rust.sh` running `maturin develop` or `cargo build --release` + copy `.so` to package dir
  - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7_

- [x] 11. Implement Ingestion Service API and FastAPI app (Server 1)
  - [x] 11.1 Create Ingestion Service routes and app
    - Copy route handlers from `src/server_vm/server_backend/routes/ingest.py` and `src/server_gateway/api/routes/ingest.py`
    - Consolidate into `src_new/services/ingestion/api/routes.py`
    - Implement endpoints: `POST /upload`, `GET /status/{raster_id}`, `GET /health`
    - Create `src_new/services/ingestion/api/dependencies.py` for config, DB session, and pipeline injection
    - Create `src_new/services/ingestion/service.py` as FastAPI app entry point; read port from `INGESTION_SERVICE_PORT` env var
    - Apply `lan_security` middleware
    - Wire GDAL pipelines and format handlers into upload handler
    - _Requirements: 6.1, 6.6, 9.6, 16.1_

  - [~]* 11.2 Write integration tests for Ingestion Service API
    - Test `POST /upload` with `tests/data/sample.tif` returns raster_id and status "cataloged"
    - Test `GET /status/{raster_id}` returns progress 1.0 after successful ingestion
    - Test `GET /health` returns healthy status with disk_space_gb populated
    - _Requirements: 14.4, 19.3_

- [x] 12. Implement TiTiler Tile Service (Server 1)
  - [x] 12.1 Create titiler_config.py and tile_endpoints.py
    - Copy `src/server_vm/titiler_service/service.py` → `src_new/services/tile_serving/titiler_config.py`
    - Apply GDAL env vars from config before TiTiler app initialization
    - Create `src_new/services/tile_serving/tile_endpoints.py` with custom routes: `/tiles/{z}/{x}/{y}.png`, `/preview/{raster_id}`, `/metadata/{raster_id}`, `/health`
    - Support query params: `contrast`, `brightness`, `colormap` (Requirement 11.6)
    - Disable all external HTTP requests in TiTiler config (no remote raster fetching)
    - _Requirements: 11.1, 11.2, 11.4, 11.5, 11.6, 16.4_

  - [x] 12.2 Create cache_manager.py and service entry point
    - Create `src_new/services/tile_serving/cache_manager.py` with tile cache policy (LRU, max size from TILE_CACHE_SIZE env var) and invalidation logic
    - Create `src_new/services/tile_serving/service.py` as FastAPI app entry point; read port from `TILE_SERVICE_PORT` env var
    - Apply `lan_security` middleware
    - _Requirements: 11.3, 16.1_

  - [~]* 12.3 Write integration tests for Tile Service
    - Test `/tiles/0/0/0.png` returns valid PNG for a cataloged test raster
    - Test `/preview/{raster_id}` returns 512×512 PNG
    - Test `/metadata/{raster_id}` returns correct bounds and zoom levels
    - _Requirements: 14.5, 19.3_

- [x] 13. Checkpoint — all backend services complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Implement desktop_ingestion client (PySide6)
  - [x] 14.1 Create ingestion client UI modules
    - Copy `src/desktop_ingestion/gui_admin/app.py` → `src_new/clients/desktop_ingestion/ui/main_window.py`
    - Extract upload dialog logic → `src_new/clients/desktop_ingestion/ui/upload_dialog.py`
    - Extract ingestion monitoring/progress panel → `src_new/clients/desktop_ingestion/ui/monitoring_panel.py`
    - Update all imports to use `src_new/shared/ui_components/` for login/settings/about dialogs
    - _Requirements: 7.1, 7.6_

  - [x] 14.2 Create ingestion client API client and entry point
    - Copy `src/desktop_ingestion/` HTTP client logic → `src_new/clients/desktop_ingestion/api_client.py`
    - Client reads INGESTION_SERVICE_URL and TILE_SERVICE_URL from config; communicates with Server 1 only
    - Create `src_new/clients/desktop_ingestion/main.py` as entry point calling `QApplication` + `MainWindow`
    - _Requirements: 7.1, 7.3, 7.5_

  - [~]* 14.3 Write unit tests for ingestion client API client
    - Test `api_client.upload_file()` sends correct multipart request to INGESTION_SERVICE_URL
    - Test `api_client.get_status()` parses IngestionStatus response correctly
    - _Requirements: 19.2_

- [x] 15. Implement desktop_search client — Python backend (PySide6)
  - [x] 15.1 Create search client UI modules
    - Copy `src/client_desktop/backend/main_window.py` → `src_new/clients/desktop_search/ui/main_window.py`
    - Extract search panel (query input, results list) → `src_new/clients/desktop_search/ui/search_panel.py`
    - Extract controls panel (layer controls, contrast/brightness sliders) → `src_new/clients/desktop_search/ui/controls_panel.py`
    - Update all imports to use `src_new/shared/ui_components/`
    - _Requirements: 7.2, 7.6_

  - [x] 15.2 Create QWebChannel bridge modules
    - Copy `src/client_desktop/backend/bridge.py` → `src_new/clients/desktop_search/bridge/channel_setup.py` (QWebChannel initialization, page setup)
    - Extract Python signal/slot definitions → `src_new/clients/desktop_search/bridge/signal_handlers.py` (BridgeSignals QObject with fly_to_location, add_imagery_layer, on_map_click, query_elevation)
    - Add inline comments documenting each signal's message format and data types
    - _Requirements: 8.1, 8.2, 8.5, 8.6_

  - [x] 15.3 Create search client API client and entry point
    - Copy `src/desktop_client/api_client.py` → `src_new/clients/desktop_search/api_client.py`
    - Client reads QUERY_SERVICE_URL and TILE_SERVICE_URL from config; communicates with Server 2 (queries) and Server 1 (tiles) only
    - Create `src_new/clients/desktop_search/main.py` as entry point
    - _Requirements: 7.2, 7.4, 7.5_

  - [~]* 15.4 Write unit tests for search client bridge and API client
    - Test `signal_handlers.on_map_click()` emits correct lat/lon values
    - Test `api_client.query_point()` sends correct JSON body to QUERY_SERVICE_URL
    - _Requirements: 19.2_

- [x] 16. Implement desktop_search client — CesiumJS frontend modules
  - [x] 16.1 Split bridge.js into cesium/ modules
    - Read `src/client_desktop/frontend/bridge.js` and `src/client_desktop/client_frontend/web_assets/bridge.js`
    - Extract Cesium.Viewer instantiation + offline config → `src_new/clients/desktop_search/cesium/viewer_init.js`
    - Extract flyTo / camera manipulation → `src_new/clients/desktop_search/cesium/camera_control.js`
    - Extract ImageryLayer add/remove → `src_new/clients/desktop_search/cesium/layer_manager.js`
    - Extract mouse click, measurement, annotation handlers → `src_new/clients/desktop_search/cesium/event_handlers.js`
    - Create `src_new/clients/desktop_search/cesium/index.js` re-exporting all public functions (preserves original API surface)
    - Disable all Cesium Ion, Bing Maps, and terrain provider URLs in viewer_init.js (air-gap compliance)
    - _Requirements: 3.3, 3.5, 3.6, 8.3, 8.4, 16.3_

  - [x] 16.2 Create web_assets and wire HTML entry point
    - Copy `src/client_desktop/client_frontend/web_assets/index.html` → `src_new/clients/desktop_search/web_assets/index.html`
    - Update `<script>` imports to reference `cesium/index.js` modules
    - Copy `src/client_desktop/client_frontend/web_assets/styles.css` → `src_new/clients/desktop_search/web_assets/styles/`
    - Copy offline CesiumJS vendor assets from `src/client_desktop/client_frontend/web_assets/cesium/` → `src_new/clients/desktop_search/web_assets/vendor/`
    - Update all asset paths to use CESIUM_BASE_URL from config
    - _Requirements: 5.2, 5.3, 20.5_

  - [~]* 16.3 Write unit tests for CesiumJS modules
    - Test `viewer_init.js` does not reference any external URLs (Cesium Ion, Bing, terrain)
    - Test `layer_manager.js` addImageryLayer / removeLayer functions with mock viewer
    - _Requirements: 16.3, 19.2_

- [x] 17. Checkpoint — all clients complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 18. Update all import statements across src_new/
  - [x] 18.1 Update Python imports
    - Scan all `.py` files in `src_new/` and replace any remaining `src.` or relative imports with absolute `src_new.` imports
    - Replace all hardcoded paths, URLs, and port numbers with `config.get()` / `os.getenv()` calls referencing the centralized config
    - Verify no file imports from `src/` (old codebase) — all cross-module imports must resolve within `src_new/`
    - _Requirements: 5.1, 5.3, 5.4, 4.5_

  - [x] 18.2 Update JavaScript imports
    - Scan all `.js` files in `src_new/` and update `import`/`require` paths to reflect new `cesium/` module structure
    - Replace any hardcoded tile URLs or service URLs with values read from the QWebChannel bridge config object
    - _Requirements: 5.2, 5.3_

  - [~]* 18.3 Generate import verification report
    - Write `scripts/verify_imports.py` that scans `src_new/` for any remaining `src.` references or hardcoded localhost URLs and prints a report
    - Run the script and confirm zero violations
    - _Requirements: 5.5, 5.6_

- [x] 19. Create deployment and startup scripts
  - Create `src_new/scripts/start_ingestion_service.sh`: sources `.env`, activates conda env, runs `uvicorn services.ingestion.service:app --host $API_HOST --port $INGESTION_SERVICE_PORT`
  - Create `src_new/scripts/start_tile_service.sh`: sources `.env`, runs `uvicorn services.tile_serving.service:app --host $API_HOST --port $TILE_SERVICE_PORT`
  - Create `src_new/scripts/start_query_service.sh`: sources `.env`, runs `uvicorn services.query.service:app --host $API_HOST --port $QUERY_SERVICE_PORT`
  - Create `src_new/scripts/start_ingestion_client.sh`: sources `.env`, runs `python -m clients.desktop_ingestion.main`
  - Create `src_new/scripts/start_search_client.sh`: sources `.env`, runs `python -m clients.desktop_search.main`
  - Create `src_new/scripts/deploy_server1.sh`: calls `start_ingestion_service.sh` and `start_tile_service.sh` in background; logs PIDs; exits non-zero on failure
  - Create `src_new/scripts/deploy_server2.sh`: calls `start_query_service.sh`; exits non-zero on failure
  - Create `src_new/scripts/setup_environment.sh`: creates conda env from `environment.yml`, installs deps, runs `build_rust.sh`
  - All scripts: check for missing env vars and print clear error messages with installation instructions
  - _Requirements: 13.1–13.8, 20.6, 20.7_

- [x] 20. Create deployment manifests and pyproject.toml
  - Create `src_new/scripts/deploy_server1.txt` listing all modules/packages required on Server 1 (services/ingestion, services/tile_serving, shared)
  - Create `src_new/scripts/deploy_server2.txt` listing all modules/packages required on Server 2 (services/query, shared)
  - Update `pyproject.toml` at project root to include `src_new/` as a package source with correct entry points for each service and client
  - Create `src_new/environment.yml` with pinned versions for all Python dependencies (FastAPI, TiTiler, GDAL, Rasterio, PySide6, PyProj, psycopg2, pydantic, python-dotenv, pytest, pytest-asyncio)
  - Create `src_new/requirements.txt` as pip-compatible alternative
  - _Requirements: 6.4, 6.5, 20.1, 20.2, 20.4_

- [x] 21. Set up pytest infrastructure and test fixtures
  - [x] 21.1 Create conftest.py and test data
    - Create `src_new/tests/conftest.py` with pytest fixtures: `db_session` (PostGIS test DB setup/teardown), `mock_ingestion_service`, `mock_query_service`, `sample_tif_path`, `sample_j2k_path`
    - Copy or symlink small sample GeoTIFF from `data_test/` → `src_new/tests/data/sample.tif`
    - Copy or symlink small JPEG2000 → `src_new/tests/data/sample.j2k`
    - _Requirements: 19.1, 19.5, 19.7_

  - [x] 21.2 Create end-to-end workflow test
    - Write `src_new/tests/e2e/test_full_workflow.py` testing: upload sample.tif → verify cataloged in PostGIS → request tile → verify PNG → query by point → verify raster returned
    - Use pytest-asyncio for async FastAPI test client
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 19.4_

  - [~]* 21.3 Write backward compatibility tests
    - Write `src_new/tests/integration/test_api_compatibility.py` comparing endpoint signatures and response schemas between `src/` and `src_new/` services
    - Test that all public API endpoints in src_new/ match the signatures of src/ equivalents
    - _Requirements: 14.2, 14.6_

- [x] 22. Checkpoint — test suite complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 23. Implement logging and monitoring across all services
  - Update `src_new/shared/utils/logging_config.py` to configure structured JSON logging reading LOG_LEVEL, LOG_FORMAT, LOG_OUTPUT_PATH from config
  - Add log rotation (RotatingFileHandler) with configurable max size and backup count
  - Add startup/shutdown event logging to all three service `service.py` entry points
  - Add request/response logging middleware to all FastAPI apps (log method, path, status code, duration)
  - Add GDAL operation logging (file path, operation type, duration) in all gdal_pipelines modules
  - Add database query logging in all repository methods
  - _Requirements: 18.1, 18.2, 18.3, 18.6, 18.7_

- [x] 24. Generate documentation files
  - Write `src_new/docs/ARCHITECTURE.md` documenting src_new/ structure, module responsibilities, deployment boundaries, and component interaction diagrams (Mermaid)
  - Write `src_new/docs/MIGRATION_GUIDE.md` with src/ → src_new/ path mapping table and step-by-step transition instructions
  - Write `src_new/docs/API_REFERENCE.md` documenting all REST endpoints for Ingestion, Query, and Tile services with request/response schemas
  - Write `src_new/docs/CONFIGURATION.md` documenting every .env variable, its purpose, type, default value, and example
  - Write `src_new/docs/DEPLOYMENT.md` with step-by-step Server 1 and Server 2 deployment instructions including hardware requirements
  - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.7_

- [x] 25. Final checkpoint — full system integration
  - Run `scripts/verify_imports.py` and confirm zero violations
  - Run full pytest suite (`pytest src_new/tests/ -v --tb=short`) and confirm all tests pass
  - Verify `deploy_server1.sh` and `deploy_server2.sh` start services without errors
  - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP delivery
- All tasks are copy-reorganize-update operations — no business logic is rewritten
- The `src/` directory is never modified; it remains the reference implementation throughout
- Each task references specific requirements for full traceability
- Checkpoints at tasks 5, 8, 13, 17, 22, and 25 ensure incremental validation
- Rust accelerators (task 10) have a pure-Python fallback so they do not block other tasks
- The import update pass (task 18) should be done after all modules are in place to avoid chasing moving targets
- Dead code from `src/` (e.g., duplicate `src/core_shared/` vs `src/platform_core/`, `.backup` files, `elevation_profile_panel_test.py`) is excluded from `src_new/` per Requirement 2