# Offline GIS Rendering Fixes - Bugfix Design

## Overview

This design addresses 25 critical rendering and functionality bugs in the Offline 3D GIS Desktop Application that prevent proper visualization of geospatial data. The application, built with Qt5, QtWebEngine, and CesiumJS, exhibits failures across five major categories: globe/map rendering, asset visualization, toolbar functionality, comparator tool, and cross-platform compatibility. The root causes stem from incorrect CesiumJS initialization, missing asset paths, TiTiler configuration issues, icon registry failures, and Windows-to-macOS path incompatibilities.

The fix strategy employs a systematic approach: verify CesiumJS asset availability, correct WebEngine HTML loading paths, configure TiTiler with proper GDAL environment variables, fix icon registry path resolution, implement proper layer visibility and z-index management, repair comparator viewer initialization, and ensure cross-platform path handling using `pathlib.Path`.

## Glossary

- **Bug_Condition (C)**: The condition that triggers rendering or functionality failures - when CesiumJS assets are missing, paths are incorrect, or configuration is invalid
- **Property (P)**: The desired behavior - proper 3D globe rendering, correct asset visualization, functional toolbar buttons, working comparator tool
- **Preservation**: Existing architecture (qt5 + QtWebEngine + CesiumJS + TiTiler + PostGIS) and offline operation that must remain unchanged
- **CesiumJS**: Open-source JavaScript library for 3D globe rendering using WebGL, embedded in QtWebEngine
- **QtWebEngine**: Chromium-based browser engine embedded in PySide6 for rendering web content
- **TiTiler**: Dynamic tile server built on FastAPI and GDAL for serving raster tiles
- **QWebChannel**: Qt module enabling bidirectional communication between Python and JavaScript
- **IconRegistry**: Python class managing toolbar icon loading from SVG files
- **COG (Cloud Optimized GeoTIFF)**: GeoTIFF format optimized for HTTP range requests and efficient tile serving
- **Layer Visibility**: CesiumJS ImageryLayer property controlling whether a layer is displayed
- **Z-Index**: Layer stacking order determining which layers appear on top
- **Comparator**: Side-by-side layer comparison tool with synchronized camera views

## Bug Details

### Bug Condition

The bugs manifest across five categories when the application attempts to initialize the 3D globe, load geospatial assets, display toolbar buttons, or activate the comparator tool. The system exhibits multiple failure modes:

**Category 1: Globe/Map Rendering Failures**
- CesiumJS fails to initialize when assets are missing or incorrectly referenced
- QtWebEngine cannot load index.html due to incorrect path resolution
- Cross-platform path issues (Windows backslashes vs macOS forward slashes)

**Category 2: Asset Visualization Failures**
- GeoTIFF, JPEG2000, MBTiles, and DEM data focus camera correctly but render nothing
- TiTiler fails to serve tiles due to missing GDAL environment variables
- CesiumJS layers are added but remain "hidden" or "buried" due to incorrect visibility/alpha/z-index

**Category 3: Toolbar Icon and Button Failures**
- Icon registry cannot locate SVG files in client_frontend/icons directory
- Toolbar button clicks do not trigger controller actions
- Button states do not reflect active/inactive status

**Category 4: Comparator Tool Failures**
- Comparator dropdown does not display when button is clicked
- Side-by-side CesiumJS viewers fail to initialize in comparator panes
- Camera synchronization between panes does not work

**Category 5: Performance and Cross-Platform Issues**
- Ultra-high-resolution data (5cm RGB, 1-2m DEM) causes lag and freezing
- COG byte-range requests are inefficient
- macOS path resolution fails for assets built on Windows

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type ApplicationState
  OUTPUT: boolean
  
  RETURN (input.cesiumAssetsPath IS NULL OR NOT input.cesiumAssetsPath.exists())
         OR (input.htmlPath IS NULL OR NOT input.htmlPath.exists())
         OR (input.tiTilerGdalEnvVars NOT SET)
         OR (input.iconRegistryPath IS NULL OR NOT input.iconRegistryPath.exists())
         OR (input.layerVisibility == FALSE AND input.layerAlpha == 0)
         OR (input.comparatorViewersInitialized == FALSE)
         OR (input.pathSeparator == "\\" AND input.platform == "macOS")
END FUNCTION
```

### Examples

**Example 1: Blank Globe on Startup**
- **Trigger**: Application starts in any mode (server/client/unified)
- **Current Behavior**: Displays "Waiting for local Cesium assets..." indefinitely, blank WebView
- **Expected Behavior**: 3D globe renders immediately with base terrain at default coordinates
- **Root Cause**: CesiumJS assets not found at `./cesium/` path, or HTML file not loaded

**Example 2: GeoTIFF Loads But Doesn't Render**
- **Trigger**: User loads 5cm aerial imagery GeoTIFF
- **Current Behavior**: Camera flies to correct location, but only black boundaries visible
- **Expected Behavior**: High-resolution imagery draped on globe at correct geographic location
- **Root Cause**: TiTiler not serving tiles (missing GDAL env vars), or layer visibility/alpha set incorrectly

**Example 3: Toolbar Buttons Show Wrong Icons**
- **Trigger**: Application displays main toolbar
- **Current Behavior**: Icons do not match button functions, or placeholder icons shown
- **Expected Behavior**: QGIS-sourced SVG icons clearly represent each button's function
- **Root Cause**: IconRegistry cannot resolve path to client_frontend/icons directory

**Example 4: Comparator Button Does Nothing**
- **Trigger**: User clicks Comparator toolbar button
- **Current Behavior**: No dropdown appears, button does not activate
- **Expected Behavior**: Dropdown displays with available layers for selection
- **Root Cause**: Comparator viewer initialization fails, or layer options not populated

**Example 5: macOS Path Resolution Fails**
- **Trigger**: Application runs on macOS after being built on Windows
- **Current Behavior**: Cannot locate web assets, icons, or Cesium files
- **Expected Behavior**: All file paths resolve correctly using platform-independent handling
- **Root Cause**: Hard-coded Windows backslash paths, case-sensitive filesystem issues

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- PySide6 (Qt6) framework for UI must continue to work exactly as before
- CesiumJS embedded via QtWebEngine for 3D globe rendering must remain unchanged
- TiTiler for dynamic tile generation must continue to operate
- PostgreSQL + PostGIS for metadata catalog must remain unchanged
- QWebChannel for Python-JavaScript communication must continue to function
- Offline operation without any internet connection must be preserved
- Current file/folder structure must remain intact
- Support for GeoTIFF, JPEG2000, MBTiles formats must continue
- Measurement tools (distance, area, elevation profile, volume, viewshed, slope/aspect) must work as before
- Annotation tools (point, polygon) must continue to function
- Search operations with spatial indexing must remain unchanged
- GDAL optimization environment variables must continue to be used
- Tile caching strategies must remain efficient
- Multi-threading with QThreadPool must continue to work

**Scope:**
All inputs that do NOT involve the 25 identified bug conditions should be completely unaffected by this fix. This includes:
- Existing measurement and analysis workflows
- Database operations and spatial queries
- Layer management and visibility controls (when working correctly)
- Camera controls and navigation (when working correctly)
- File upload and metadata extraction
- Search functionality and result display

## Hypothesized Root Cause

Based on the bug description and code analysis, the most likely issues are:

### 1. **CesiumJS Asset Path Resolution**
The application fails to locate CesiumJS assets due to incorrect path construction in `main_window.py`:
- `base_path` calculation uses relative path traversal that may fail in packaged applications
- Fallback path logic may not cover all deployment scenarios
- `CESIUM_BASE_URL` in index.html may point to incorrect location

### 2. **TiTiler GDAL Configuration**
TiTiler fails to serve tiles efficiently because critical GDAL environment variables are not set:
- `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR` prevents costly directory listing
- `GDAL_HTTP_MERGE_CONSECUTIVE_RANGES=YES` optimizes byte-range requests
- These are set in `titiler_manager.py` but may not propagate correctly

### 3. **CesiumJS Layer Visibility Management**
Layers are added to CesiumJS but remain invisible due to incorrect property settings:
- `ImageryLayer.show` property may be set to `false`
- `ImageryLayer.alpha` may be set to `0.0`
- Layer z-index may place new layers behind existing layers
- `bridge.js` may not properly configure layer properties when adding

### 4. **Icon Registry Path Resolution**
IconRegistry fails to locate SVG files because path construction is incorrect:
- `ICON_DIR` uses relative path that may not resolve in all contexts
- Cross-platform path separators not handled correctly
- SVG files may not be included in packaged application

### 5. **Comparator Viewer Initialization**
Comparator tool fails because CesiumJS viewer instances are not properly created:
- `comparatorLeftViewer` and `comparatorRightViewer` may not be initialized
- DOM elements `#comparatorLeftViewer` and `#comparatorRightViewer` may not exist
- Camera synchronization logic may have race conditions

### 6. **Cross-Platform Path Handling**
macOS fails to load assets because Windows-style paths are hard-coded:
- Backslash separators (`\`) instead of forward slashes (`/`)
- Case-sensitive filesystem on macOS vs case-insensitive on Windows
- Absolute vs relative path resolution differences

### 7. **QtWebEngine HTML Loading**
WebView displays blank because HTML file path is incorrectly constructed:
- `QUrl.fromLocalFile()` may not handle all path formats correctly
- Query string cache-busting may interfere with loading
- File permissions may prevent access

### 8. **Toolbar Action Wiring**
Toolbar buttons don't trigger actions because signal-slot connections are incorrect:
- `_on_toolbar_action_triggered` may not be properly connected
- Action labels may not match controller method names
- Checkable button state management may have logic errors

## Correctness Properties

Property 1: Bug Condition - Globe Rendering and Asset Visualization

_For any_ application state where CesiumJS assets exist, HTML paths are correct, TiTiler is configured with GDAL environment variables, and layer properties are set correctly (isBugCondition returns false for rendering issues), the fixed application SHALL render the 3D globe immediately on startup, display loaded GeoTIFF/JPEG2000/MBTiles/DEM data correctly draped on the globe at the correct geographic location, and serve tiles efficiently from TiTiler.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12**

Property 2: Bug Condition - Toolbar and Comparator Functionality

_For any_ application state where icon registry paths are correct, toolbar actions are properly wired, and comparator viewers are initialized (isBugCondition returns false for UI issues), the fixed application SHALL display correct QGIS-sourced icons on toolbar buttons, trigger corresponding controller actions when buttons are clicked, display the comparator dropdown with available layers, render side-by-side CesiumJS viewers, and synchronize camera movements between panes.

**Validates: Requirements 2.13, 2.14, 2.15, 2.16, 2.17, 2.18, 2.19, 2.20, 2.21**

Property 3: Bug Condition - Performance and Cross-Platform Compatibility

_For any_ application state where COG files are accessed with HTTP range requests, GDAL optimizations are enabled, and paths use platform-independent resolution (isBugCondition returns false for performance/platform issues), the fixed application SHALL render ultra-high-resolution data (5cm RGB, 1-2m DEM) smoothly without lag, use efficient byte-range requests for tile data, and resolve all file paths correctly on both Windows and macOS.

**Validates: Requirements 2.22, 2.23, 2.24, 2.25**

Property 4: Preservation - Core Architecture and Offline Operation

_For any_ input that does NOT involve the 25 identified bug conditions (isBugCondition returns false), the fixed code SHALL produce exactly the same behavior as the original code, preserving PySide6 UI framework, CesiumJS rendering, TiTiler tile serving, PostgreSQL + PostGIS metadata catalog, QWebChannel communication, offline operation, file structure, data format support, measurement tools, annotation tools, search operations, and performance optimizations.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14, 3.15, 3.16, 3.17, 3.18, 3.19, 3.20, 3.21, 3.22, 3.23, 3.24**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct, the following file-by-file modifications are required:

#### **File 1**: `src/offline_gis_app/client_backend/desktop/main_window.py`

**Function**: `__init__` (lines 90-180)

**Specific Changes**:

1. **Fix CesiumJS Asset Path Resolution**:
   - Replace relative path traversal with robust path resolution
   - Add multiple fallback paths for different deployment scenarios
   - Verify path exists before constructing QUrl
   
   ```python
   # Current problematic code (lines 175-180):
   base_path = Path(__file__).resolve().parents[2] / "client_frontend" / "web_assets" / "index.html"
   if not base_path.exists():
       base_path = Path(__file__).resolve().parents[3] / "src" / "offline_gis_app" / "client_frontend" / "web_assets" / "index.html"
   
   # Fixed code:
   # Try multiple paths in order of likelihood
   possible_paths = [
       Path(__file__).resolve().parents[2] / "client_frontend" / "web_assets" / "index.html",
       Path(__file__).resolve().parents[3] / "src" / "offline_gis_app" / "client_frontend" / "web_assets" / "index.html",
       Path(__file__).resolve().parent.parent.parent / "client_frontend" / "web_assets" / "index.html",
       Path.cwd() / "src" / "offline_gis_app" / "client_frontend" / "web_assets" / "index.html",
   ]
   
   base_path = None
   for path in possible_paths:
       if path.exists():
           base_path = path
           break
   
   if base_path is None:
       self.panel.log("ERROR: Cannot locate index.html. Check installation.")
       return
   ```

2. **Verify Cesium Assets Directory**:
   - Check that `./cesium/` directory exists relative to index.html
   - Log warning if Cesium assets are missing
   
   ```python
   cesium_dir = base_path.parent / "cesium"
   if not cesium_dir.exists():
       self.panel.log("WARNING: Cesium assets not found. Run scripts/setup_cesium_assets.sh")
   ```

3. **Fix QUrl Construction**:
   - Use `as_posix()` for cross-platform compatibility
   - Ensure file:// protocol is correctly formatted
   
   ```python
   # Use as_posix() to ensure forward slashes on all platforms
   html_url = QUrl.fromLocalFile(str(base_path.resolve().as_posix()))
   ```

#### **File 2**: `src/offline_gis_app/client_frontend/web_assets/bridge.js`

**Function**: CesiumJS viewer initialization (lines 1-100)

**Specific Changes**:

1. **Fix Layer Visibility on Add**:
   - Ensure `ImageryLayer.show` is set to `true`
   - Set `ImageryLayer.alpha` to appropriate value (1.0 for imagery, 0.35 for hillshade)
   - Manage z-index to ensure new layers appear on top
   
   ```javascript
   // Add after layer creation in addImageryLayer function:
   imageryLayer.show = true;
   imageryLayer.alpha = 1.0; // or appropriate value for layer type
   
   // Move layer to top of stack
   viewer.imageryLayers.raiseToTop(imageryLayer);
   ```

2. **Fix DEM Terrain Provider Configuration**:
   - Ensure terrain provider is correctly assigned to viewer
   - Verify terrain tiles are being requested
   
   ```javascript
   // When setting DEM terrain:
   viewer.terrainProvider = new Cesium.CesiumTerrainProvider({
       url: demTileUrl,
       requestVertexNormals: true,
       requestWaterMask: false
   });
   
   // Force terrain update
   viewer.scene.globe.terrainProvider = viewer.terrainProvider;
   ```

3. **Fix Comparator Viewer Initialization**:
   - Ensure DOM elements exist before creating viewers
   - Initialize viewers with proper configuration
   - Set up camera synchronization listeners
   
   ```javascript
   // Check DOM elements exist:
   const leftContainer = document.getElementById('comparatorLeftViewer');
   const rightContainer = document.getElementById('comparatorRightViewer');
   
   if (!leftContainer || !rightContainer) {
       console.error('[offlineGIS] Comparator DOM elements not found');
       return false;
   }
   
   // Initialize viewers:
   comparatorLeftViewer = new Cesium.Viewer('comparatorLeftViewer', {
       imageryProvider: false,
       baseLayerPicker: false,
       terrainProvider: new Cesium.EllipsoidTerrainProvider()
   });
   
   comparatorRightViewer = new Cesium.Viewer('comparatorRightViewer', {
       imageryProvider: false,
       baseLayerPicker: false,
       terrainProvider: new Cesium.EllipsoidTerrainProvider()
   });
   ```

#### **File 3**: `src/offline_gis_app/client_backend/desktop/icon_registry.py`

**Function**: `IconRegistry` class (lines 30-150)

**Specific Changes**:

1. **Fix Icon Directory Path Resolution**:
   - Use absolute path resolution with multiple fallbacks
   - Handle packaged application scenarios
   
   ```python
   # Current code (line 30):
   ICON_DIR = Path(__file__).resolve().parents[2] / "client_frontend" / "icons"
   
   # Fixed code:
   def _get_icon_dir() -> Path:
       """Resolve icon directory with multiple fallback paths."""
       possible_paths = [
           Path(__file__).resolve().parents[2] / "client_frontend" / "icons",
           Path(__file__).resolve().parents[3] / "src" / "offline_gis_app" / "client_frontend" / "icons",
           Path.cwd() / "src" / "offline_gis_app" / "client_frontend" / "icons",
       ]
       
       for path in possible_paths:
           if path.exists() and path.is_dir():
               return path
       
       # Return first path as fallback (will trigger placeholder icons)
       return possible_paths[0]
   
   ICON_DIR = _get_icon_dir()
   ```

2. **Add Logging for Missing Icons**:
   - Log which icons are missing to help debugging
   
   ```python
   @classmethod
   def get(cls, tool_name: str, size: int = DEFAULT_ICON_SIZE, color: Optional[str] = None) -> QIcon:
       # ... existing code ...
       
       if not path.exists():
           logging.getLogger("desktop.icon_registry").warning(
               "Icon file not found: %s (tool: %s)", path, tool_name
           )
           icon = cls._make_placeholder(tool_name[:2].upper(), size)
           cls._cache[cache_key] = icon
           return icon
   ```

#### **File 4**: `src/offline_gis_app/client_backend/desktop/titiler_manager.py`

**Function**: `_start_process` (lines 30-60)

**Specific Changes**:

1. **Verify GDAL Environment Variables Are Set**:
   - Add logging to confirm environment variables are applied
   - Verify TiTiler process inherits environment
   
   ```python
   def _start_process(self) -> None:
       # ... existing code ...
       
       env = os.environ.copy()
       env["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"
       env["GDAL_HTTP_MERGE_CONSECUTIVE_RANGES"] = "YES"
       
       # Add logging:
       self._logger.info(
           "Starting TiTiler with GDAL env: GDAL_DISABLE_READDIR_ON_OPEN=%s, GDAL_HTTP_MERGE_CONSECUTIVE_RANGES=%s",
           env["GDAL_DISABLE_READDIR_ON_OPEN"],
           env["GDAL_HTTP_MERGE_CONSECUTIVE_RANGES"]
       )
       
       # ... rest of existing code ...
   ```

2. **Add COG-Specific Optimizations**:
   - Set additional GDAL environment variables for COG performance
   
   ```python
   env["GDAL_CACHEMAX"] = "512"  # 512 MB cache
   env["CPL_VSIL_CURL_ALLOWED_EXTENSIONS"] = ".tif,.tiff"
   env["GDAL_HTTP_MAX_RETRY"] = "3"
   env["GDAL_HTTP_RETRY_DELAY"] = "1"
   ```

#### **File 5**: `src/offline_gis_app/client_backend/desktop/controller.py`

**Function**: `_load_asset_layer` (lines 800-1000, need to read full function)

**Specific Changes**:

1. **Fix Layer Visibility After Add**:
   - Explicitly set layer visibility to true after adding
   - Verify layer is in viewer's imagery layers collection
   
   ```python
   # After calling bridge.js addLayer:
   self._run_js_call("setLayerVisibility", layer_key, True)
   self._run_js_call("setLayerAlpha", layer_key, 1.0)
   ```

2. **Fix DEM Layer Configuration**:
   - Ensure DEM layers use terrain provider, not imagery layer
   - Set proper hillshade and exaggeration values
   
   ```python
   if self._is_dem_asset(asset):
       # Use terrain provider for DEM
       self._run_js_call("setTerrainProvider", tile_url)
       self._run_js_call("setDemExaggeration", 2.0)
       self._run_js_call("setDemHillshadeAlpha", 0.35)
   ```

#### **File 6**: `src/offline_gis_app/client_frontend/web_assets/index.html`

**Function**: HTML structure (lines 1-100)

**Specific Changes**:

1. **Verify Cesium Asset Path**:
   - Ensure `CESIUM_BASE_URL` points to correct relative path
   - Add error handling for missing Cesium.js
   
   ```html
   <script>
     window.CESIUM_BASE_URL = "./cesium/";
     
     // Verify Cesium loads
     window.addEventListener('error', function(e) {
       if (e.filename && e.filename.includes('Cesium.js')) {
         console.error('Failed to load Cesium.js. Check that cesium/ directory exists.');
         document.getElementById('status').textContent = 
           'ERROR: Cesium.js not found. Run scripts/setup_cesium_assets.sh';
       }
     }, true);
   </script>
   ```

2. **Ensure Comparator DOM Elements Exist**:
   - Verify `#comparatorLeftViewer` and `#comparatorRightViewer` divs are present
   - Add proper styling for visibility
   
   ```html
   <!-- Verify these elements exist in comparatorWindows div: -->
   <div class="comparatorViewer" id="comparatorLeftViewer"></div>
   <div class="comparatorViewer" id="comparatorRightViewer"></div>
   ```

#### **File 7**: Cross-Platform Path Handling (Multiple Files)

**Specific Changes**:

1. **Use `pathlib.Path` Consistently**:
   - Replace all string path operations with `Path` objects
   - Use `.as_posix()` when passing paths to JavaScript or URLs
   - Use `.resolve()` to get absolute paths

2. **Handle Case Sensitivity**:
   - Normalize file extensions to lowercase when checking
   - Use case-insensitive path comparisons where appropriate

3. **Fix Path Separators**:
   - Never hard-code backslashes or forward slashes
   - Let `pathlib` handle platform-specific separators

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bugs on unfixed code, then verify the fixes work correctly and preserve existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bugs BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that attempt to initialize the application, load assets, click toolbar buttons, and activate the comparator tool. Run these tests on the UNFIXED code to observe failures and understand the root causes.

**Test Cases**:

1. **Globe Rendering Test**: Start application and verify 3D globe renders (will fail on unfixed code)
   - Expected failure: Blank WebView or "Waiting for local Cesium assets..." message
   - Confirms: CesiumJS asset path or HTML loading issue

2. **GeoTIFF Visualization Test**: Load 5cm aerial imagery GeoTIFF and verify it renders on globe (will fail on unfixed code)
   - Expected failure: Camera flies to location but no imagery visible
   - Confirms: TiTiler configuration or layer visibility issue

3. **Toolbar Icon Test**: Display toolbar and verify icons match button functions (will fail on unfixed code)
   - Expected failure: Placeholder icons or mismatched icons
   - Confirms: Icon registry path resolution issue

4. **Comparator Activation Test**: Click Comparator button and verify dropdown appears (will fail on unfixed code)
   - Expected failure: No dropdown, button does not activate
   - Confirms: Comparator viewer initialization issue

5. **macOS Path Test**: Run application on macOS and verify assets load (will fail on unfixed code if built on Windows)
   - Expected failure: Cannot locate web assets, icons, or Cesium files
   - Confirms: Cross-platform path handling issue

**Expected Counterexamples**:
- CesiumJS viewer does not initialize due to missing assets or incorrect paths
- Layers are added to viewer but remain invisible due to incorrect visibility/alpha settings
- Toolbar buttons show placeholder icons due to icon registry path resolution failure
- Comparator viewers are not created due to missing DOM elements or initialization errors
- macOS cannot resolve file paths due to hard-coded Windows separators

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed application produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := application_fixed(input)
  ASSERT expectedBehavior(result)
END FOR
```

**Test Cases**:

1. **Globe Renders on Startup**: Start application in all modes (server/client/unified) and verify 3D globe renders immediately
2. **GeoTIFF Renders Correctly**: Load GeoTIFF and verify imagery is visible and correctly positioned
3. **JPEG2000 Renders Correctly**: Load JPEG2000 and verify imagery is visible and correctly positioned
4. **MBTiles Renders Correctly**: Load MBTiles and verify tiles are visible and correctly positioned
5. **DEM Renders Correctly**: Load DEM and verify elevation visualization with hillshading
6. **Toolbar Icons Display Correctly**: Verify all toolbar buttons show appropriate QGIS-sourced icons
7. **Toolbar Buttons Trigger Actions**: Click each toolbar button and verify corresponding action executes
8. **Comparator Dropdown Displays**: Click Comparator button and verify dropdown with layer options appears
9. **Comparator Viewers Render**: Select layers and verify side-by-side viewers display correctly
10. **Comparator Camera Syncs**: Move camera in one pane and verify other pane follows
11. **macOS Paths Resolve**: Run on macOS and verify all assets load correctly
12. **High-Resolution Performance**: Load 5cm RGB and 1-2m DEM and verify smooth rendering without lag

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed application produces the same result as the original application.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT application_original(input) = application_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for measurement tools, annotation tools, search operations, and other functionality, then write property-based tests capturing that behavior.

**Test Cases**:

1. **Measurement Tools Preservation**: Verify distance, area, elevation profile, volume, viewshed, and slope/aspect calculations produce identical results
2. **Annotation Tools Preservation**: Verify point and polygon annotations work identically
3. **Search Operations Preservation**: Verify coordinate search and polygon search produce identical results
4. **Layer Management Preservation**: Verify layer visibility toggles and context switching work identically
5. **Camera Controls Preservation**: Verify pan, zoom, rotate, and tilt controls work identically
6. **File Upload Preservation**: Verify file selection and metadata extraction work identically
7. **Database Operations Preservation**: Verify PostgreSQL queries and PostGIS spatial operations work identically
8. **QWebChannel Communication Preservation**: Verify Python-JavaScript message passing works identically
9. **Offline Operation Preservation**: Verify no external network calls are made
10. **Performance Optimization Preservation**: Verify GDAL environment variables and caching strategies work identically

### Unit Tests

- Test CesiumJS asset path resolution with multiple deployment scenarios
- Test icon registry path resolution with multiple fallback paths
- Test TiTiler GDAL environment variable propagation
- Test layer visibility and alpha property setting
- Test comparator viewer initialization and DOM element creation
- Test cross-platform path handling with Windows and macOS paths
- Test QUrl construction with various file path formats
- Test toolbar action signal-slot connections

### Property-Based Tests

- Generate random file paths and verify cross-platform resolution works correctly
- Generate random layer configurations and verify visibility/alpha settings are correct
- Generate random toolbar button sequences and verify actions trigger correctly
- Generate random asset metadata and verify rendering works correctly
- Generate random camera positions and verify comparator synchronization works correctly

### Integration Tests

- Test full application startup flow with globe rendering
- Test full asset loading flow from file selection to visualization
- Test full toolbar interaction flow from button click to action execution
- Test full comparator flow from activation to layer comparison
- Test full cross-platform flow on both Windows and macOS
- Test full performance flow with ultra-high-resolution data