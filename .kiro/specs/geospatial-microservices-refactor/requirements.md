# Requirements Document: Geospatial Microservices Refactoring

## Introduction

This document specifies the requirements for refactoring an existing offline 3D GIS desktop application into a modular, microservices-style architecture. The system processes terabyte-scale geospatial data (2-3cm resolution aerial imagery and DEM) and must be restructured to support a two-server deployment model while maintaining full backward compatibility with the existing working codebase.

The refactoring creates a new modular structure (src_new/) that organizes code by deployment boundaries and single responsibility principles, enabling independent deployment of ingestion processing, tile serving, and search/query components across a secure LAN network.

## Glossary

- **Refactoring_System**: The automated code reorganization system that transforms the existing src/ folder into the modular src_new/ structure
- **Ingestion_Service**: The microservice responsible for processing uploaded geospatial files (GeoTIFF, JPEG2000, MBTiles) and cataloging metadata into PostGIS
- **Tile_Service**: The microservice responsible for serving dynamic map tiles via TiTiler from cataloged geospatial data
- **Query_Service**: The microservice responsible for spatial search, metadata queries, and coordinate-based lookups via PostGIS
- **Desktop_Ingestion_Client**: The PySide6 desktop application for uploading and managing geospatial data ingestion
- **Desktop_Search_Client**: The PySide6 desktop application with embedded CesiumJS for 3D visualization and spatial queries
- **Configuration_Manager**: The centralized .env-based configuration system managing all paths, URLs, database connections, and service endpoints
- **Module_Analyzer**: The component that identifies dead code, duplicate logic, and refactoring opportunities in the existing codebase
- **Import_Updater**: The component that automatically updates all import statements and file paths after code reorganization
- **Deployment_Manifest**: The documentation specifying which modules deploy to Server 1 (Ingestion + Tile) vs Server 2 (Query)
- **COG**: Cloud-Optimized GeoTIFF format optimized for range-request tile serving
- **PostGIS**: PostgreSQL spatial extension providing geospatial indexing and query capabilities
- **TiTiler**: FastAPI-based dynamic tile server for serving geospatial rasters as web map tiles
- **QWebChannel**: Qt framework component enabling bidirectional Python-JavaScript communication
- **CesiumJS**: WebGL-based 3D globe rendering library embedded in the desktop client

## Requirements

### Requirement 1: Modular Architecture Creation

**User Story:** As a system architect, I want the existing monolithic codebase reorganized into single-responsibility modules, so that I can understand component boundaries and deploy services independently.

#### Acceptance Criteria

1. THE Refactoring_System SHALL create a src_new/ directory structure organized by deployment boundaries (ingestion, tile_serving, query, shared, clients)
2. THE Refactoring_System SHALL preserve all existing working code from src/ without rewriting logic
3. WHEN a module contains multiple responsibilities, THE Module_Analyzer SHALL split it into separate files with clear, descriptive names
4. THE Refactoring_System SHALL organize modules to match the two-server deployment architecture (Server 1: ingestion + tile serving, Server 2: query processing)
5. FOR ALL modules in src_new/, the file and folder names SHALL clearly indicate their purpose and deployment target
6. THE Refactoring_System SHALL maintain a mapping document showing the transformation from src/ paths to src_new/ paths

### Requirement 2: Dead Code Elimination

**User Story:** As a developer, I want unused code removed during refactoring, so that the codebase contains only functional, necessary logic.

#### Acceptance Criteria

1. THE Module_Analyzer SHALL identify all unreferenced functions, classes, and imports in the existing src/ codebase
2. THE Module_Analyzer SHALL identify duplicate code blocks across multiple files
3. THE Refactoring_System SHALL exclude identified dead code from the src_new/ structure
4. THE Refactoring_System SHALL consolidate duplicate logic into shared utility modules
5. THE Refactoring_System SHALL generate a report listing all removed dead code and consolidated duplicates
6. WHEN dead code is referenced by working code, THE Module_Analyzer SHALL flag it for manual review rather than automatic removal

### Requirement 3: Large File Decomposition

**User Story:** As a maintainer, I want large monolithic files (bridge.js, controller.py) split into logical modules, so that I can navigate and debug specific functionality easily.

#### Acceptance Criteria

1. WHEN a Python file exceeds 500 lines, THE Refactoring_System SHALL analyze it for logical separation boundaries
2. WHEN a JavaScript file exceeds 400 lines, THE Refactoring_System SHALL analyze it for logical separation boundaries
3. THE Refactoring_System SHALL split bridge.js into separate modules for QWebChannel communication, CesiumJS camera control, layer management, and event handling
4. THE Refactoring_System SHALL split controller.py into separate modules for request routing, business logic, database operations, and GDAL processing
5. FOR ALL split modules, THE Refactoring_System SHALL maintain the original public API surface to ensure backward compatibility
6. THE Refactoring_System SHALL create index files (\_\_init\_\_.py, index.js) that re-export the split module interfaces

### Requirement 4: Centralized Configuration Management

**User Story:** As a deployment engineer, I want all configuration values (paths, URLs, database connections, constants) centralized in a .env file, so that I can configure the system for different environments without modifying code.

#### Acceptance Criteria

1. THE Configuration_Manager SHALL create a .env file at the project root containing all configurable parameters
2. THE Configuration_Manager SHALL extract hardcoded paths, URLs, port numbers, and database connection strings from the src/ codebase
3. THE Configuration_Manager SHALL define environment variables for: DATA_ROOT, DATABASE_URL, API_HOST, API_PORT, TITILER_BASE_URL, CESIUM_BASE_URL, INGESTION_SERVICE_URL, QUERY_SERVICE_URL, TILE_SERVICE_URL
4. THE Configuration_Manager SHALL define environment variables for: MAX_UPLOAD_SIZE, TILE_CACHE_SIZE, GDAL_DISABLE_READDIR_ON_OPEN, GDAL_HTTP_MERGE_CONSECUTIVE_RANGES
5. THE Refactoring_System SHALL replace all hardcoded configuration values in src_new/ with environment variable lookups
6. THE Configuration_Manager SHALL provide a .env.example file with documented default values and descriptions for each variable
7. WHEN an environment variable is missing, THE Configuration_Manager SHALL use documented default values and log a warning

### Requirement 5: Import Statement and Path Updates

**User Story:** As a developer, I want all import statements and file paths automatically updated after refactoring, so that the refactored codebase runs without manual path corrections.

#### Acceptance Criteria

1. THE Import_Updater SHALL scan all Python files in src_new/ and update import statements to reflect the new module structure
2. THE Import_Updater SHALL scan all JavaScript files in src_new/ and update import/require statements to reflect the new module structure
3. THE Import_Updater SHALL update all file path references (data paths, template paths, asset paths) to use Configuration_Manager environment variables
4. THE Import_Updater SHALL update all relative imports to use absolute imports from the src_new/ root
5. THE Import_Updater SHALL generate a verification report listing all updated import statements
6. WHEN an import cannot be automatically resolved, THE Import_Updater SHALL flag it for manual review with the original and attempted new path

### Requirement 6: Two-Server Deployment Architecture

**User Story:** As a deployment engineer, I want clear separation between Server 1 components (ingestion + tile serving) and Server 2 components (query processing), so that I can deploy them independently on separate hardware.

#### Acceptance Criteria

1. THE Refactoring_System SHALL organize src_new/services/ingestion/ to contain all data upload, GDAL processing, and metadata extraction logic deployable to Server 1
2. THE Refactoring_System SHALL organize src_new/services/tile_serving/ to contain all TiTiler configuration, tile generation, and raster serving logic deployable to Server 1
3. THE Refactoring_System SHALL organize src_new/services/query/ to contain all PostGIS spatial queries, search engine logic, and metadata retrieval deployable to Server 2
4. THE Refactoring_System SHALL organize src_new/shared/ to contain common utilities, data models, and authentication logic used by all services
5. THE Refactoring_System SHALL create deployment manifests (deploy_server1.txt, deploy_server2.txt) listing which modules belong to each server
6. THE Refactoring_System SHALL ensure services communicate only via documented REST API endpoints defined in the Configuration_Manager
7. WHEN a module has dependencies on both Server 1 and Server 2 components, THE Module_Analyzer SHALL flag it as a cross-server dependency requiring API-based communication

### Requirement 7: Desktop Client Separation

**User Story:** As a user, I want separate desktop applications for ingestion and search, so that I can run the appropriate client based on my role (data manager vs analyst).

#### Acceptance Criteria

1. THE Refactoring_System SHALL organize src_new/clients/desktop_ingestion/ to contain the PySide6 UI for file upload, ingestion monitoring, and data management
2. THE Refactoring_System SHALL organize src_new/clients/desktop_search/ to contain the PySide6 UI with embedded CesiumJS for 3D visualization and spatial queries
3. THE Desktop_Ingestion_Client SHALL communicate exclusively with the Ingestion_Service and Tile_Service APIs
4. THE Desktop_Search_Client SHALL communicate exclusively with the Query_Service and Tile_Service APIs
5. THE Refactoring_System SHALL create separate entry point scripts (run_ingestion_client.py, run_search_client.py) for launching each desktop application
6. THE Refactoring_System SHALL ensure both clients share common UI components (login, settings, about dialogs) from src_new/shared/ui_components/

### Requirement 8: QWebChannel Communication Modularization

**User Story:** As a frontend developer, I want the Python-JavaScript bridge code organized into clear modules, so that I can understand and extend the bidirectional communication logic.

#### Acceptance Criteria

1. THE Refactoring_System SHALL create src_new/clients/desktop_search/bridge/ containing all QWebChannel communication logic
2. THE Refactoring_System SHALL split bridge functionality into: channel_setup.py (QWebChannel initialization), signal_handlers.py (Python signal definitions), js_callbacks.js (JavaScript callback registration)
3. THE Refactoring_System SHALL create src_new/clients/desktop_search/cesium/ containing all CesiumJS-specific logic
4. THE Refactoring_System SHALL split CesiumJS functionality into: viewer_init.js (offline Cesium viewer setup), camera_control.js (flyTo, camera manipulation), layer_manager.js (imagery layer management), event_handlers.js (mouse click, measurement tools)
5. FOR ALL QWebChannel signal-slot connections, THE Refactoring_System SHALL document the message format and data types in inline comments
6. THE Refactoring_System SHALL ensure the bridge modules expose a simple, documented API for adding new Python-JavaScript communication channels

### Requirement 9: GDAL Processing Pipeline Modularization

**User Story:** As a geospatial engineer, I want GDAL processing logic organized by operation type, so that I can locate and modify specific raster processing workflows.

#### Acceptance Criteria

1. THE Refactoring_System SHALL create src_new/services/ingestion/gdal_pipelines/ containing all GDAL-based raster processing logic
2. THE Refactoring_System SHALL organize GDAL pipelines into: metadata_extractor.py (CRS, bounds, resolution extraction), cog_converter.py (GeoTIFF to COG conversion), reprojector.py (CRS transformation), thumbnail_generator.py (preview image creation)
3. THE Refactoring_System SHALL create src_new/services/ingestion/format_handlers/ containing format-specific parsers for GeoTIFF, JPEG2000, and MBTiles
4. THE Refactoring_System SHALL ensure all GDAL operations use environment variables from Configuration_Manager (GDAL_DISABLE_READDIR_ON_OPEN, GDAL_HTTP_MERGE_CONSECUTIVE_RANGES)
5. THE Refactoring_System SHALL create src_new/services/ingestion/rust_accelerators/ for PyO3-based Rust modules (rasterize, coordinate transformation)
6. WHEN a GDAL operation fails, THE Ingestion_Service SHALL log the error with the file path, operation type, and GDAL error message

### Requirement 10: PostGIS Query Abstraction

**User Story:** As a backend developer, I want PostGIS spatial queries abstracted into a repository pattern, so that I can modify database queries without changing service logic.

#### Acceptance Criteria

1. THE Refactoring_System SHALL create src_new/services/query/repositories/ containing database access layer modules
2. THE Refactoring_System SHALL create raster_repository.py with methods: find_by_bbox(), find_by_point(), find_by_id(), insert_metadata(), update_metadata()
3. THE Refactoring_System SHALL create spatial_index_repository.py with methods: create_gist_index(), query_intersects(), query_contains()
4. THE Refactoring_System SHALL ensure all PostGIS queries use parameterized statements to prevent SQL injection
5. THE Refactoring_System SHALL ensure all repository methods return typed data models from src_new/shared/models/ rather than raw database rows
6. THE Refactoring_System SHALL create src_new/services/query/spatial_queries.py containing high-level business logic that composes repository methods

### Requirement 11: TiTiler Service Configuration

**User Story:** As a deployment engineer, I want TiTiler configuration isolated into a dedicated service module, so that I can tune tile serving performance independently.

#### Acceptance Criteria

1. THE Refactoring_System SHALL create src_new/services/tile_serving/titiler_config.py containing all TiTiler FastAPI application setup
2. THE Refactoring_System SHALL create src_new/services/tile_serving/tile_endpoints.py defining custom tile serving routes beyond default TiTiler endpoints
3. THE Refactoring_System SHALL create src_new/services/tile_serving/cache_manager.py for managing tile cache policies and invalidation
4. THE Tile_Service SHALL read GDAL environment variables from Configuration_Manager and apply them before TiTiler initialization
5. THE Tile_Service SHALL expose endpoints: /tiles/{z}/{x}/{y}.png, /preview/{raster_id}, /metadata/{raster_id}, /health
6. THE Tile_Service SHALL support query parameters for real-time image manipulation: ?contrast=1.2&brightness=0.8&colormap=viridis

### Requirement 12: Shared Data Models and Utilities

**User Story:** As a developer, I want common data structures and utilities shared across all services, so that I avoid code duplication and maintain consistency.

#### Acceptance Criteria

1. THE Refactoring_System SHALL create src_new/shared/models/ containing Pydantic data models for: RasterMetadata, BoundingBox, CoordinateReferenceSystem, TileRequest, QueryResult
2. THE Refactoring_System SHALL create src_new/shared/utils/ containing utility modules for: coordinate_conversion.py, file_validation.py, logging_config.py, error_handlers.py
3. THE Refactoring_System SHALL create src_new/shared/auth/ containing authentication and authorization logic shared by all services
4. THE Refactoring_System SHALL ensure all services import shared models and utilities rather than duplicating logic
5. THE Refactoring_System SHALL create src_new/shared/constants.py defining system-wide constants (supported file formats, CRS codes, tile sizes)
6. FOR ALL shared modules, THE Refactoring_System SHALL ensure they have no dependencies on service-specific logic (ingestion, query, tile_serving)

### Requirement 13: Deployment and Startup Scripts

**User Story:** As a deployment engineer, I want automated startup scripts for each service and client, so that I can launch the system components without manual configuration.

#### Acceptance Criteria

1. THE Refactoring_System SHALL create start_ingestion_service.sh launching the Ingestion_Service with environment variables from .env
2. THE Refactoring_System SHALL create start_tile_service.sh launching the Tile_Service with environment variables from .env
3. THE Refactoring_System SHALL create start_query_service.sh launching the Query_Service with environment variables from .env
4. THE Refactoring_System SHALL create start_ingestion_client.sh launching the Desktop_Ingestion_Client
5. THE Refactoring_System SHALL create start_search_client.sh launching the Desktop_Search_Client
6. THE Refactoring_System SHALL create deploy_server1.sh that starts both Ingestion_Service and Tile_Service for Server 1 deployment
7. THE Refactoring_System SHALL create deploy_server2.sh that starts Query_Service for Server 2 deployment
8. WHEN a service fails to start, THE startup script SHALL log the error and exit with a non-zero status code

### Requirement 14: Backward Compatibility Verification

**User Story:** As a quality assurance engineer, I want automated verification that the refactored system maintains full functional compatibility with the original src/ codebase, so that I can ensure no regressions were introduced.

#### Acceptance Criteria

1. THE Refactoring_System SHALL create a compatibility test suite comparing src/ and src_new/ behavior
2. THE Refactoring_System SHALL verify that all public API endpoints in src_new/ match the signatures and responses of src/
3. THE Refactoring_System SHALL verify that the Desktop_Search_Client in src_new/ can load and render the same test datasets as the original client
4. THE Refactoring_System SHALL verify that the Ingestion_Service in src_new/ produces identical PostGIS metadata entries as the original ingestion logic
5. THE Refactoring_System SHALL verify that the Tile_Service in src_new/ generates pixel-identical tiles compared to the original tile serving logic
6. WHEN a compatibility test fails, THE Refactoring_System SHALL generate a detailed report showing the expected vs actual behavior

### Requirement 15: Documentation and Migration Guide

**User Story:** As a developer, I want comprehensive documentation explaining the new architecture and migration path, so that I can understand the refactored system and contribute effectively.

#### Acceptance Criteria

1. THE Refactoring_System SHALL generate ARCHITECTURE.md documenting the src_new/ structure, module responsibilities, and deployment boundaries
2. THE Refactoring_System SHALL generate MIGRATION_GUIDE.md explaining how to transition from src/ to src_new/ for development and deployment
3. THE Refactoring_System SHALL generate API_REFERENCE.md documenting all REST API endpoints for Ingestion_Service, Query_Service, and Tile_Service
4. THE Refactoring_System SHALL generate CONFIGURATION.md explaining all .env variables, their purposes, and recommended values
5. THE Refactoring_System SHALL generate DEPLOYMENT.md with step-by-step instructions for deploying to the two-server architecture
6. THE Refactoring_System SHALL include inline code comments explaining complex refactoring decisions and architectural patterns
7. FOR ALL documentation, THE Refactoring_System SHALL include diagrams showing component interactions and data flow

### Requirement 16: Security and Network Configuration

**User Story:** As a security engineer, I want the refactored system to maintain strict security controls for the air-gapped LAN environment, so that no unauthorized network access or data leakage occurs.

#### Acceptance Criteria

1. THE Configuration_Manager SHALL define ALLOWED_HOSTS environment variable restricting API access to specific LAN IP addresses
2. THE Refactoring_System SHALL ensure all services bind only to LAN-accessible interfaces (not 0.0.0.0) unless explicitly configured
3. THE Refactoring_System SHALL ensure the Desktop_Search_Client disables all external CesiumJS network requests (Cesium Ion, Bing Maps, terrain providers)
4. THE Refactoring_System SHALL ensure TiTiler does not make external HTTP requests for remote rasters
5. THE Refactoring_System SHALL create src_new/shared/auth/lan_security.py implementing IP-based access control for service-to-service communication
6. WHEN an unauthorized network request is attempted, THE service SHALL log the attempt and return a 403 Forbidden response

### Requirement 17: Performance Optimization and Rust Integration

**User Story:** As a performance engineer, I want computationally expensive operations isolated and optimized with Rust, so that the system maintains responsiveness with terabyte-scale datasets.

#### Acceptance Criteria

1. THE Refactoring_System SHALL identify CPU-bound operations in the existing codebase suitable for Rust optimization (vector rasterization, coordinate transformation, array math)
2. THE Refactoring_System SHALL create src_new/services/ingestion/rust_accelerators/ containing PyO3-based Rust modules
3. THE Refactoring_System SHALL implement rasterize_vectors.rs using the rusterize library for fast vector-to-raster conversion
4. THE Refactoring_System SHALL implement transform_coordinates.rs for batch CRS transformations releasing the Python GIL
5. THE Refactoring_System SHALL create Python wrapper modules in src_new/services/ingestion/rust_accelerators/\_\_init\_\_.py exposing Rust functions with type hints
6. THE Refactoring_System SHALL include build scripts (build_rust.sh) for compiling Rust modules into Python-importable .so/.pyd files
7. WHEN Rust modules are unavailable, THE Ingestion_Service SHALL fall back to pure Python implementations and log a performance warning

### Requirement 18: Logging and Monitoring

**User Story:** As a system administrator, I want comprehensive logging across all services, so that I can debug issues and monitor system health.

#### Acceptance Criteria

1. THE Refactoring_System SHALL create src_new/shared/logging_config.py configuring structured logging for all services
2. THE Configuration_Manager SHALL define LOG_LEVEL, LOG_FORMAT, and LOG_OUTPUT_PATH environment variables
3. THE Refactoring_System SHALL ensure all services log: startup/shutdown events, API requests/responses, database queries, GDAL operations, errors with stack traces
4. THE Refactoring_System SHALL create src_new/services/monitoring/ containing health check endpoints for all services
5. THE Refactoring_System SHALL implement /health endpoints returning: service status, database connectivity, disk space, memory usage
6. THE Refactoring_System SHALL create log rotation policies preventing log files from consuming excessive disk space
7. WHEN a critical error occurs, THE service SHALL log the error at ERROR level and optionally send alerts via configured notification channels

### Requirement 19: Testing Infrastructure

**User Story:** As a quality assurance engineer, I want a comprehensive test suite for the refactored codebase, so that I can verify correctness and prevent regressions.

#### Acceptance Criteria

1. THE Refactoring_System SHALL create tests/ directory structure mirroring src_new/ organization
2. THE Refactoring_System SHALL create unit tests for all shared utilities, data models, and repository methods
3. THE Refactoring_System SHALL create integration tests for service API endpoints using test fixtures with sample GeoTIFF/JPEG2000 files
4. THE Refactoring_System SHALL create end-to-end tests simulating the full workflow: upload → ingestion → cataloging → tile serving → query → visualization
5. THE Refactoring_System SHALL use pytest as the test framework with fixtures for database setup/teardown and mock services
6. THE Refactoring_System SHALL achieve minimum 80% code coverage for shared modules and service logic
7. THE Refactoring_System SHALL create tests/data/ containing small sample geospatial files for testing without requiring large datasets

### Requirement 20: Conda Environment and Dependency Management

**User Story:** As a deployment engineer, I want clear dependency management and environment setup, so that I can reproduce the exact runtime environment on deployment servers.

#### Acceptance Criteria

1. THE Refactoring_System SHALL create environment.yml defining all Python dependencies with pinned versions for the offline-3d-gis conda environment
2. THE Refactoring_System SHALL create requirements.txt as an alternative pip-based dependency specification
3. THE Refactoring_System SHALL document all system-level dependencies (GDAL, PostgreSQL, PostGIS, Qt6) in INSTALLATION.md
4. THE Refactoring_System SHALL create setup.py or pyproject.toml for installing src_new/ as a Python package
5. THE Refactoring_System SHALL ensure all JavaScript dependencies (CesiumJS) are vendored locally in src_new/clients/desktop_search/web_assets/vendor/
6. THE Refactoring_System SHALL create scripts/setup_environment.sh automating conda environment creation and dependency installation
7. WHEN dependencies are missing, THE startup scripts SHALL detect the issue and provide clear error messages with installation instructions
