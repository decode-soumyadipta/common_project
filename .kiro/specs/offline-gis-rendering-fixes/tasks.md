# Implementation Plan

## Phase 1: Exploratory Testing (BEFORE Fix Implementation)

- [ ] 1. Write bug condition exploration tests
  - **Property 1: Bug Condition** - Offline GIS Rendering Failures
  - **CRITICAL**: These tests MUST FAIL on unfixed code - failure confirms the bugs exist
  - **DO NOT attempt to fix the tests or the code when they fail**
  - **NOTE**: These tests encode the expected behavior - they will validate the fix when they pass after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bugs exist across all 5 categories
  - **Scoped PBT Approach**: For deterministic bugs, scope properties to concrete failing cases to ensure reproducibility
  - Test implementation details from Bug Condition in design:
    - Globe rendering: CesiumJS fails to initialize when assets are missing or paths are incorrect
    - Asset visualization: GeoTIFF/JPEG2000/MBTiles/DEM focus camera but render nothing
    - Toolbar functionality: Icons don't load, buttons don't trigger actions
    - Comparator tool: Dropdown doesn't display, viewers don't initialize
    - Cross-platform: macOS path resolution fails for Windows-built assets
  - The test assertions should match the Expected Behavior Properties from design
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct - it proves the bugs exist)
  - Document counterexamples found to understand root causes:
    - Which CesiumJS asset paths fail to resolve
    - Which layer visibility/alpha settings cause invisible layers
    - Which icon registry paths fail on macOS
    - Which comparator DOM elements are missing
    - Which GDAL environment variables are not propagated
  - Mark task complete when tests are written, run, and failures are documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.14, 1.15, 1.16, 1.17, 1.18, 1.19, 1.20, 1.21, 1.22, 1.23, 1.24, 1.25_

- [ ] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Core Architecture and Functionality
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for non-buggy inputs:
    - Measurement tools (distance, area, elevation profile, volume, viewshed, slope/aspect)
    - Annotation tools (point, polygon)
    - Search operations with spatial indexing
    - Layer management and visibility controls (when working correctly)
    - Camera controls and navigation (when working correctly)
    - Database operations and spatial queries
    - QWebChannel Python-JavaScript communication
    - Offline operation (no external network calls)
    - GDAL optimization environment variables
    - Tile caching strategies
  - Write property-based tests capturing observed behavior patterns from Preservation Requirements
  - Property-based testing generates many test cases for stronger guarantees
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14, 3.15, 3.16, 3.17, 3.18, 3.19, 3.20, 3.21, 3.22, 3.23, 3.24_

## Phase 2: Implementation

- [ ] 3. Fix CesiumJS asset path resolution and HTML loading

  - [ ] 3.1 Fix main_window.py CesiumJS asset path resolution
    - Replace relative path traversal with robust multi-fallback path resolution
    - Try paths in order: parents[2], parents[3], parent.parent.parent, cwd()
    - Verify path exists before constructing QUrl
    - Add logging for path resolution success/failure
    - Verify Cesium assets directory exists relative to index.html
    - Log warning if Cesium assets are missing
    - Use `as_posix()` for cross-platform QUrl construction
    - _Bug_Condition: isBugCondition(input) where input.cesiumAssetsPath IS NULL OR NOT input.cesiumAssetsPath.exists() OR input.htmlPath IS NULL OR NOT input.htmlPath.exists()_
    - _Expected_Behavior: Application SHALL render 3D globe immediately on startup with base terrain at default coordinates_
    - _Preservation: PySide6 UI framework, QtWebEngine rendering, file structure must remain unchanged_
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.9_

  - [ ] 3.2 Fix index.html Cesium asset path and error handling
    - Verify `CESIUM_BASE_URL` points to correct relative path `./cesium/`
    - Add error event listener for Cesium.js loading failures
    - Display error message in status div if Cesium.js not found
    - Ensure comparator DOM elements exist: `#comparatorLeftViewer` and `#comparatorRightViewer`
    - Add proper styling for comparator viewer visibility
    - _Bug_Condition: isBugCondition(input) where input.cesiumAssetsPath IS NULL OR input.comparatorViewersInitialized == FALSE_
    - _Expected_Behavior: CesiumJS SHALL load all required assets from local file system without external network calls_
    - _Preservation: Offline operation, current HTML structure must remain unchanged_
    - _Requirements: 1.3, 1.18, 1.20, 2.2, 2.3, 2.18, 2.20, 3.6, 3.7, 3.15_

- [ ] 4. Fix CesiumJS layer visibility and rendering

  - [ ] 4.1 Fix bridge.js layer visibility on add
    - Set `ImageryLayer.show = true` after layer creation
    - Set `ImageryLayer.alpha` to appropriate value (1.0 for imagery, 0.35 for hillshade)
    - Use `viewer.imageryLayers.raiseToTop()` to manage z-index
    - Ensure new layers appear on top of existing layers
    - _Bug_Condition: isBugCondition(input) where input.layerVisibility == FALSE AND input.layerAlpha == 0_
    - _Expected_Behavior: Imagery layers SHALL render correctly draped on globe at correct geographic location_
    - _Preservation: CesiumJS rendering architecture must remain unchanged_
    - _Requirements: 1.6, 1.7, 1.8, 1.11, 2.6, 2.7, 2.8, 2.11, 3.2, 3.18_

  - [ ] 4.2 Fix bridge.js DEM terrain provider configuration
    - Create `CesiumTerrainProvider` with correct URL and options
    - Set `requestVertexNormals: true` for hillshading
    - Assign terrain provider to `viewer.terrainProvider`
    - Force terrain update with `viewer.scene.globe.terrainProvider`
    - _Bug_Condition: isBugCondition(input) where input.layerVisibility == FALSE for DEM layers_
    - _Expected_Behavior: DEM data SHALL render elevation visualization with proper hillshading and color mapping_
    - _Preservation: CesiumJS terrain rendering must remain unchanged_
    - _Requirements: 1.9, 1.12, 2.9, 2.12, 3.2_

  - [ ] 4.3 Fix controller.py layer visibility after add
    - Call `setLayerVisibility(layer_key, True)` after adding layer
    - Call `setLayerAlpha(layer_key, 1.0)` after adding layer
    - For DEM layers, use `setTerrainProvider()` instead of imagery layer
    - Set DEM exaggeration and hillshade alpha values
    - _Bug_Condition: isBugCondition(input) where input.layerVisibility == FALSE after layer add_
    - _Expected_Behavior: Layers SHALL set proper visibility, alpha, and z-index properties_
    - _Preservation: Layer management architecture must remain unchanged_
    - _Requirements: 1.11, 2.11, 3.18_

- [ ] 5. Fix icon registry and toolbar functionality

  - [ ] 5.1 Fix icon_registry.py path resolution
    - Replace single path with `_get_icon_dir()` function using multiple fallbacks
    - Try paths: parents[2], parents[3], cwd()
    - Return first existing directory path
    - Add logging for missing icon files with tool name
    - Handle packaged application scenarios
    - _Bug_Condition: isBugCondition(input) where input.iconRegistryPath IS NULL OR NOT input.iconRegistryPath.exists()_
    - _Expected_Behavior: Icon registry SHALL successfully load SVG icons from client_frontend/icons directory_
    - _Preservation: Icon registry architecture and QGIS icon sources must remain unchanged_
    - _Requirements: 1.13, 1.16, 2.13, 2.16, 3.9, 3.16_

  - [ ] 5.2 Verify toolbar action signal-slot connections
    - Ensure `_on_toolbar_action_triggered` is properly connected to toolbar actions
    - Verify action labels match controller method names
    - Fix checkable button state management logic
    - Add logging for toolbar action triggers
    - _Bug_Condition: isBugCondition(input) where toolbar button clicks don't trigger actions_
    - _Expected_Behavior: Toolbar buttons SHALL trigger corresponding controller actions when clicked_
    - _Preservation: Toolbar organization and action architecture must remain unchanged_
    - _Requirements: 1.14, 1.15, 1.17, 2.14, 2.15, 2.17, 3.16_

- [ ] 6. Fix comparator tool implementation

  - [ ] 6.1 Fix bridge.js comparator viewer initialization
    - Check DOM elements exist: `#comparatorLeftViewer` and `#comparatorRightViewer`
    - Log error if DOM elements not found
    - Initialize `comparatorLeftViewer` with proper Cesium.Viewer configuration
    - Initialize `comparatorRightViewer` with proper Cesium.Viewer configuration
    - Set `imageryProvider: false` and `baseLayerPicker: false`
    - Use `EllipsoidTerrainProvider` for base terrain
    - _Bug_Condition: isBugCondition(input) where input.comparatorViewersInitialized == FALSE_
    - _Expected_Behavior: Comparator panes SHALL successfully create and render independent CesiumJS viewer instances_
    - _Preservation: Comparator tool architecture must remain unchanged_
    - _Requirements: 1.18, 1.20, 2.18, 2.20, 3.2_

  - [ ] 6.2 Implement comparator camera synchronization
    - Add camera move event listeners to both viewers
    - Synchronize camera position, orientation, and zoom between panes
    - Handle race conditions with synchronization flags
    - Test camera sync with pan, zoom, rotate, and tilt operations
    - _Bug_Condition: isBugCondition(input) where camera movements don't sync between panes_
    - _Expected_Behavior: Camera movements SHALL synchronize position and orientation between comparator panes_
    - _Preservation: Camera control architecture must remain unchanged_
    - _Requirements: 1.21, 2.21, 3.18_

  - [ ] 6.3 Implement comparator layer selection dropdown
    - Populate dropdown with available layers from application state
    - Handle layer selection events
    - Add selected layers to appropriate comparator viewer
    - Update UI to reflect selected layers
    - _Bug_Condition: isBugCondition(input) where comparator dropdown doesn't display_
    - _Expected_Behavior: Comparator button SHALL display dropdown with available layers for selection_
    - _Preservation: Layer management and UI architecture must remain unchanged_
    - _Requirements: 1.18, 1.19, 2.18, 2.19, 3.15, 3.18_

- [ ] 7. Fix TiTiler and GDAL configuration

  - [ ] 7.1 Verify titiler_manager.py GDAL environment variables
    - Confirm `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR` is set
    - Confirm `GDAL_HTTP_MERGE_CONSECUTIVE_RANGES=YES` is set
    - Add logging to confirm environment variables are applied
    - Verify TiTiler process inherits environment correctly
    - _Bug_Condition: isBugCondition(input) where input.tiTilerGdalEnvVars NOT SET_
    - _Expected_Behavior: TiTiler SHALL dynamically generate and serve tiles with correct byte-range reading from COG files_
    - _Preservation: TiTiler architecture and tile serving must remain unchanged_
    - _Requirements: 1.10, 2.10, 3.3, 3.22_

  - [ ] 7.2 Add COG-specific GDAL optimizations
    - Set `GDAL_CACHEMAX=512` for 512 MB cache
    - Set `CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif,.tiff`
    - Set `GDAL_HTTP_MAX_RETRY=3`
    - Set `GDAL_HTTP_RETRY_DELAY=1`
    - Log all GDAL environment variables on TiTiler startup
    - _Bug_Condition: isBugCondition(input) where COG byte-range requests are inefficient_
    - _Expected_Behavior: COG files SHALL use HTTP range requests to fetch only required tile data efficiently_
    - _Preservation: GDAL optimization strategies must remain unchanged_
    - _Requirements: 1.24, 2.24, 3.22_

- [ ] 8. Fix cross-platform path handling

  - [ ] 8.1 Replace string path operations with pathlib.Path
    - Audit all files for string-based path operations
    - Replace with `Path` objects from `pathlib`
    - Use `.as_posix()` when passing paths to JavaScript or URLs
    - Use `.resolve()` to get absolute paths
    - Never hard-code backslashes or forward slashes
    - _Bug_Condition: isBugCondition(input) where input.pathSeparator == "\\" AND input.platform == "macOS"_
    - _Expected_Behavior: File paths SHALL resolve correctly using platform-independent path handling_
    - _Preservation: File structure and organization must remain unchanged_
    - _Requirements: 1.5, 1.25, 2.4, 2.25, 3.9_

  - [ ] 8.2 Handle case sensitivity for macOS filesystem
    - Normalize file extensions to lowercase when checking
    - Use case-insensitive path comparisons where appropriate
    - Test path resolution on both Windows and macOS
    - Document case sensitivity requirements
    - _Bug_Condition: isBugCondition(input) where case-sensitive filesystem causes asset loading failures_
    - _Expected_Behavior: All file paths SHALL resolve correctly on both Windows and macOS_
    - _Preservation: File structure must remain unchanged_
    - _Requirements: 1.25, 2.25, 3.9_

- [ ] 9. Performance optimization validation

  - [ ] 9.1 Test ultra-high-resolution imagery rendering
    - Load 5cm RGB aerial imagery GeoTIFF
    - Verify smooth rendering without lag or freezing
    - Monitor tile request efficiency
    - Verify COG byte-range requests are working
    - Profile memory usage and CPU utilization
    - _Bug_Condition: isBugCondition(input) where ultra-high-resolution data causes lag_
    - _Expected_Behavior: Ultra-high-resolution aerial imagery SHALL render smoothly without lag or freezing_
    - _Preservation: Performance optimization strategies must remain unchanged_
    - _Requirements: 1.22, 2.22, 3.22, 3.23_

  - [ ] 9.2 Test high-resolution DEM rendering
    - Load 1-2m resolution DEM GeoTIFF
    - Verify smooth rendering without lag or freezing
    - Verify hillshading and color mapping performance
    - Monitor terrain tile request efficiency
    - Profile memory usage and CPU utilization
    - _Bug_Condition: isBugCondition(input) where high-resolution DEM causes lag_
    - _Expected_Behavior: High-resolution DEM data SHALL render smoothly without lag or freezing_
    - _Preservation: Performance optimization strategies must remain unchanged_
    - _Requirements: 1.23, 2.23, 3.22, 3.23_

## Phase 3: Validation

- [ ] 10. Verify bug condition exploration tests now pass

  - [ ] 10.1 Re-run bug condition exploration tests
    - **Property 1: Expected Behavior** - Offline GIS Rendering Fixes
    - **IMPORTANT**: Re-run the SAME tests from task 1 - do NOT write new tests
    - The tests from task 1 encode the expected behavior
    - When these tests pass, it confirms the expected behavior is satisfied
    - Run bug condition exploration tests from step 1
    - **EXPECTED OUTCOME**: Tests PASS (confirms bugs are fixed)
    - Verify all 5 categories of bugs are resolved:
      - Globe rendering: CesiumJS initializes and renders 3D globe
      - Asset visualization: GeoTIFF/JPEG2000/MBTiles/DEM render correctly
      - Toolbar functionality: Icons load, buttons trigger actions
      - Comparator tool: Dropdown displays, viewers initialize, camera syncs
      - Cross-platform: macOS resolves all file paths correctly
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13, 2.14, 2.15, 2.16, 2.17, 2.18, 2.19, 2.20, 2.21, 2.22, 2.23, 2.24, 2.25_

  - [ ] 10.2 Verify preservation tests still pass
    - **Property 2: Preservation** - Core Architecture and Functionality
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all preserved functionality still works:
      - Measurement tools (distance, area, elevation profile, volume, viewshed, slope/aspect)
      - Annotation tools (point, polygon)
      - Search operations with spatial indexing
      - Layer management and visibility controls
      - Camera controls and navigation
      - Database operations and spatial queries
      - QWebChannel Python-JavaScript communication
      - Offline operation (no external network calls)
      - GDAL optimization environment variables
      - Tile caching strategies
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14, 3.15, 3.16, 3.17, 3.18, 3.19, 3.20, 3.21, 3.22, 3.23, 3.24_

- [ ] 11. Integration testing

  - [ ] 11.1 Test full application startup flow
    - Start application in server-side mode
    - Start application in client-side mode
    - Start application in unified mode
    - Verify 3D globe renders immediately in all modes
    - Verify Cesium assets load from local file system
    - Verify no external network calls are made
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.6, 3.7_

  - [ ] 11.2 Test full asset loading flow
    - Load GeoTIFF imagery and verify rendering
    - Load JPEG2000 imagery and verify rendering
    - Load MBTiles imagery and verify rendering
    - Load DEM data and verify elevation visualization
    - Verify camera flies to correct location for each asset
    - Verify layers are visible and correctly positioned
    - _Requirements: 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12_

  - [ ] 11.3 Test full toolbar interaction flow
    - Display toolbar and verify all icons load correctly
    - Click each toolbar button and verify action triggers
    - Verify checkable buttons reflect active/inactive state
    - Test visualization, measurement, annotation, navigation, and file tool groups
    - _Requirements: 2.13, 2.14, 2.15, 2.16, 2.17_

  - [ ] 11.4 Test full comparator flow
    - Click Comparator button and verify dropdown displays
    - Select two layers for comparison
    - Verify side-by-side viewers render correctly
    - Test camera synchronization with pan, zoom, rotate, tilt
    - Verify each viewer displays correct layer
    - _Requirements: 2.18, 2.19, 2.20, 2.21_

  - [ ] 11.5 Test cross-platform compatibility
    - Run application on Windows and verify all functionality
    - Run application on macOS and verify all functionality
    - Verify file paths resolve correctly on both platforms
    - Verify icons load correctly on both platforms
    - Verify Cesium assets load correctly on both platforms
    - _Requirements: 2.4, 2.25_

  - [ ] 11.6 Test performance with ultra-high-resolution data
    - Load 5cm RGB aerial imagery (large file)
    - Load 1-2m DEM data (large file)
    - Verify smooth rendering without lag or freezing
    - Monitor tile request efficiency and caching
    - Verify COG byte-range requests are working
    - _Requirements: 2.22, 2.23, 2.24_

- [ ] 12. Checkpoint - Ensure all tests pass
  - Verify all bug condition exploration tests pass (task 10.1)
  - Verify all preservation tests pass (task 10.2)
  - Verify all integration tests pass (task 11.1-11.6)
  - Review test coverage and identify any gaps
  - Document any remaining issues or edge cases
  - Ask the user if questions arise or additional testing is needed
