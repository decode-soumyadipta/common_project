# QGIS Measurement UI Integration Bugfix Design

## Overview

This bugfix addresses critical UI integration issues where measurement tool buttons in the toolbar are not properly wired to activate their corresponding measurement modes, and the status bar displays static platform information instead of real-time GIS data. The backend measurement functions (distance, area, volume, viewshed, slope/aspect, shadow height) are fully implemented and functional, but the UI layer fails to properly invoke them or enable the necessary interactive modes.

The fix involves completing the toolbar action handlers to enable interactive measurement modes and ensuring the status bar properly displays real-time geographic coordinates, CRS information, elevation data, and progress indicators. The approach is minimal and surgical: wire existing components together without modifying the working backend calculation logic or the already-functional status bar widget.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug - when a user clicks a measurement tool button or views the status bar
- **Property (P)**: The desired behavior - measurement tools should activate interactive modes and status bar should display real-time GIS data
- **Preservation**: Existing functionality (visualization tools, navigation, file operations, backend calculations, status bar signal handling) that must remain unchanged
- **handle_toolbar_action**: The method in `controller.py` that routes toolbar button clicks to handler functions
- **_toolbar_measure_***: Handler methods in `controller.py` that should enable measurement modes but are incomplete
- **GISStatusBar**: The QGIS-style status bar widget in `status_bar.py` that displays coordinates, CRS, elevation, and progress
- **WebBridge**: The Qt signal bridge in `bridge.py` that emits mouseCoordinates, cameraChanged, and renderBusy signals
- **MeasurementCoordinator**: The coordinator in `measurement_coordinator.py` that manages async measurement execution
- **Interactive Mode**: A UI state where the map responds to user clicks/draws to collect measurement input (e.g., distance mode waits for two clicks)

## Bug Details

### Bug Condition

The bug manifests when a user clicks measurement tool buttons (Polygon Area, Volume Cut/Fill, Viewshed/LOS, Slope & Aspect) or when the status bar is displayed. The toolbar action handlers exist but do not enable the necessary interactive modes for users to provide measurement input.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type ToolbarActionEvent OR StatusBarDisplayEvent
  OUTPUT: boolean
  
  IF input is ToolbarActionEvent THEN
    RETURN input.action_label IN ['Polygon Area', 'Volume Cut/Fill', 'Viewshed / LOS', 'Slope & Aspect']
           AND NOT interactiveModeEnabled(input.action_label)
           AND correspondingHandlerExists(input.action_label)
  ELSE IF input is StatusBarDisplayEvent THEN
    RETURN statusBarDisplaysStaticPlatformInfo()
           AND NOT statusBarDisplaysRealtimeGISData()
  END IF
  
  RETURN FALSE
END FUNCTION
```

### Examples

- **Polygon Area**: User clicks "Polygon Area" button → system logs "Toolbar action: Polygon Area" → handler `_toolbar_measure_polygon_area()` checks for existing polygon but does NOT enable polygon drawing mode → user cannot draw polygon → measurement fails
- **Volume Cut/Fill**: User clicks "Volume Cut/Fill" button → handler checks for polygon and DEM but does NOT enable drawing mode → user has no way to define the volume region → measurement fails
- **Viewshed/LOS**: User clicks "Viewshed / LOS" button → handler checks for clicked points but does NOT enable point selection mode → user cannot select observer point → measurement fails
- **Slope & Aspect**: User clicks "Slope & Aspect" button → handler checks for polygon but does NOT enable drawing mode → user cannot define analysis region → measurement fails
- **Status Bar**: User moves cursor over map → WebBridge emits mouseCoordinates signal → GISStatusBar widget receives signal and updates display correctly → BUT status bar was never connected to bridge signals in main_window.py → status bar shows static "GPU: Apple M2" text instead of live coordinates
- **Distance/Azimuth**: User clicks "Distance / Azimuth" button → handler `_toolbar_measure_distance()` DOES enable interactive mode correctly → user can click two points → measurement succeeds (this is the working reference implementation)

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Distance/Azimuth measurement tool must continue to work correctly (it already enables interactive mode properly)
- Shadow Height measurement tool must continue to work correctly (it already enables interactive mode properly)
- Visualization tools (Layer Compositor, Comparator) must continue to function correctly
- Navigation tools (Pan, Zoom In/Out, Zoom to Extent, North Arrow) must continue to function correctly
- File operations (Open Raster, Open DEM, Save Project, Export) must continue to function correctly
- Backend measurement calculation functions must remain unchanged (they are already correct)
- Status bar signal handling (mouseCoordinates, cameraChanged, renderBusy) must remain unchanged (already correct)
- Status bar widget implementation must remain unchanged (already correct)
- Cross-platform compatibility (Mac/Windows) must be maintained
- GPU acceleration on Windows NVIDIA must continue to work

**Scope:**
All inputs that do NOT involve the four broken measurement tools (Polygon Area, Volume Cut/Fill, Viewshed/LOS, Slope & Aspect) or status bar display should be completely unaffected by this fix. This includes:
- All working toolbar actions (Distance/Azimuth, Shadow Height, visualization, navigation, file operations)
- Backend measurement calculation logic (measure_polygon_area, compute_volume, compute_viewshed, compute_slope_aspect functions)
- WebBridge signal emission logic
- GISStatusBar widget rendering logic
- Control panel functionality
- Search functionality
- Layer loading and display

## Hypothesized Root Cause

Based on the bug description and code analysis, the most likely issues are:

1. **Missing Interactive Mode Activation**: The measurement tool handlers (`_toolbar_measure_polygon_area`, `_toolbar_measure_volume`, `_toolbar_measure_viewshed`, `_toolbar_measure_slope_aspect`) check for required input (polygon, clicked points) but do NOT enable the interactive modes that allow users to provide that input. They should follow the pattern used by `_toolbar_measure_distance()` which correctly enables distance measurement mode.

2. **Missing Polygon Drawing Mode**: Polygon Area, Volume Cut/Fill, and Slope & Aspect all require a polygon but do not enable polygon drawing mode. The search functionality already has polygon drawing (`search_draw_polygon_btn`), so the mechanism exists but is not wired to measurement tools.

3. **Missing Point Selection Mode**: Viewshed/LOS requires an observer point but does not enable a point selection mode. The code checks `self.state.clicked_points` but never enables a mode that populates this list for viewshed purposes.

4. **Status Bar Not Connected**: The GISStatusBar widget is instantiated in `main_window.py` and has correct signal handlers (`on_mouse_coordinates`, `on_camera_changed`, `on_render_busy`), but these handlers are never connected to the WebBridge signals. The connection code exists in comments but is not executed:
   ```python
   # Wire bridge signals:
   # bridge.mouseCoordinates.connect(status_bar.on_mouse_coordinates)
   ```

## Correctness Properties

Property 1: Bug Condition - Measurement Tools Enable Interactive Modes

_For any_ toolbar action where a measurement tool button is clicked (Polygon Area, Volume Cut/Fill, Viewshed/LOS, Slope & Aspect), the fixed handler function SHALL enable the appropriate interactive mode (polygon drawing or point selection) that allows the user to provide the required measurement input, and SHALL display clear instructions to the user about what to do next.

**Validates: Requirements 2.2, 2.3, 2.4, 2.5**

Property 2: Preservation - Non-Measurement Tool Behavior

_For any_ toolbar action that is NOT one of the four broken measurement tools (Polygon Area, Volume Cut/Fill, Viewshed/LOS, Slope & Aspect), the fixed code SHALL produce exactly the same behavior as the original code, preserving all existing functionality for Distance/Azimuth, Shadow Height, visualization tools, navigation tools, and file operations.

**Validates: Requirements 3.1, 3.2, 3.3, 3.7**

Property 3: Bug Condition - Status Bar Displays Real-Time GIS Data

_For any_ status bar display event where the application is running and the map is visible, the fixed status bar SHALL display real-time geographic coordinates (longitude, latitude), elevation, CRS information, map scale, heading, and render status instead of static platform information.

**Validates: Requirements 2.7, 2.8, 2.9, 2.10**

Property 4: Preservation - Status Bar Signal Handling

_For any_ WebBridge signal emission (mouseCoordinates, cameraChanged, renderBusy), the fixed code SHALL process these signals exactly as the original GISStatusBar widget implementation intended, preserving the correct signal handling logic without modification to the widget itself.

**Validates: Requirements 3.4, 3.5, 3.10**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/offline_gis_app/client_backend/desktop/controller.py`

**Function**: `_toolbar_measure_polygon_area`, `_toolbar_measure_volume`, `_toolbar_measure_slope_aspect`

**Specific Changes**:
1. **Enable Polygon Drawing Mode**: Before checking for polygon existence, enable polygon drawing mode using the existing search polygon mechanism:
   - Call `self.set_search_draw_mode(enabled=True)` to enable drawing
   - Set a flag to indicate measurement context (not search context)
   - Display user instructions: "Draw a polygon on the map, then click Finish to calculate [measurement type]"
   - When polygon is finished, automatically trigger the measurement calculation
   - Alternative: Create a dedicated measurement polygon mode separate from search polygon mode

2. **Add Polygon Completion Handler**: Connect the polygon finish event to automatically trigger the measurement:
   - When user clicks "Finish" or completes polygon, check if in measurement mode
   - If in measurement mode, call the appropriate measurement function
   - Clear the measurement mode flag after calculation

3. **Handle Mode Conflicts**: Ensure polygon drawing mode disables conflicting modes:
   - Disable distance measurement mode
   - Disable point annotation mode
   - Disable pan mode
   - Follow the pattern used in `_toolbar_measure_distance()`

**File**: `src/offline_gis_app/client_backend/desktop/controller.py`

**Function**: `_toolbar_measure_viewshed`

**Specific Changes**:
1. **Enable Point Selection Mode**: Before checking for clicked points, enable a point selection mode:
   - Set `self._viewshed_mode_enabled = True` flag
   - Display user instructions: "Click on the map to select observer point for viewshed analysis"
   - When point is clicked, automatically trigger viewshed calculation
   - Clear the mode flag after calculation

2. **Add Click Handler Logic**: In the `on_map_click` handler, check for viewshed mode:
   - If `self._viewshed_mode_enabled` is True, store the clicked point
   - Automatically call `_toolbar_measure_viewshed()` to perform calculation
   - Clear the mode flag

3. **Handle Mode Conflicts**: Ensure viewshed mode disables conflicting modes:
   - Disable distance measurement mode
   - Disable polygon drawing mode
   - Disable point annotation mode
   - Follow the pattern used in `_toolbar_measure_distance()`

**File**: `src/offline_gis_app/client_backend/desktop/main_window.py`

**Location**: `__init__` method, after GISStatusBar instantiation (around line 420)

**Specific Changes**:
1. **Connect Status Bar Signals**: The status bar widget is already instantiated and the bridge signals are already being emitted. Simply connect them:
   ```python
   # ── QGIS-style status bar ────────────────────────────────────────
   self.gis_status_bar = GISStatusBar(self)
   self.setStatusBar(self.gis_status_bar)
   # Connect bridge signals to status bar handlers
   self.bridge.mouseCoordinates.connect(self.gis_status_bar.on_mouse_coordinates)
   self.bridge.cameraChanged.connect(self.gis_status_bar.on_camera_changed)
   self.bridge.renderBusy.connect(self.gis_status_bar.on_render_busy)
   ```

2. **Verify Signal Emission**: Ensure WebBridge signals are being emitted from JavaScript:
   - Check that `bridge.on_mouse_coordinates(lon, lat, elevation)` is called from CesiumJS
   - Check that `bridge.on_camera_changed(scale, heading)` is called on camera move
   - Check that `bridge.on_render_busy(busy)` is called during rendering
   - These should already be working based on the bridge implementation

**File**: `src/offline_gis_app/client_backend/desktop/controller.py`

**Function**: `__init__`

**Specific Changes**:
1. **Add Measurement Mode Flags**: Initialize flags for tracking measurement modes:
   ```python
   self._polygon_area_mode_enabled = False
   self._volume_mode_enabled = False
   self._slope_aspect_mode_enabled = False
   self._viewshed_mode_enabled = False
   ```

2. **Add Measurement Context Flag**: Track whether polygon drawing is for search or measurement:
   ```python
   self._polygon_drawing_context = "none"  # "none", "search", "measurement"
   ```

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that simulate clicking measurement tool buttons and verify that interactive modes are NOT enabled on unfixed code, then verify they ARE enabled on fixed code.

**Test Cases**:
1. **Polygon Area Mode Test**: Click "Polygon Area" button on unfixed code → verify polygon drawing mode is NOT enabled → verify user cannot draw polygon (will fail on unfixed code)
2. **Volume Mode Test**: Click "Volume Cut/Fill" button on unfixed code → verify polygon drawing mode is NOT enabled (will fail on unfixed code)
3. **Viewshed Mode Test**: Click "Viewshed / LOS" button on unfixed code → verify point selection mode is NOT enabled (will fail on unfixed code)
4. **Slope Aspect Mode Test**: Click "Slope & Aspect" button on unfixed code → verify polygon drawing mode is NOT enabled (will fail on unfixed code)
5. **Status Bar Connection Test**: Move cursor over map on unfixed code → verify status bar does NOT update with coordinates → verify it shows static platform info (will fail on unfixed code)
6. **Distance Mode Reference Test**: Click "Distance / Azimuth" button on unfixed code → verify distance mode IS enabled → verify user can click two points (should pass on unfixed code - this is the working reference)

**Expected Counterexamples**:
- Polygon Area, Volume, Slope & Aspect buttons do not enable polygon drawing mode
- Viewshed button does not enable point selection mode
- Status bar does not display real-time coordinates despite bridge signals being emitted
- Possible causes: missing mode activation calls, missing signal connections, incorrect handler logic

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  IF input is ToolbarActionEvent THEN
    result := handleToolbarAction_fixed(input.action_label)
    ASSERT interactiveModeEnabled(input.action_label)
    ASSERT userInstructionsDisplayed(input.action_label)
  ELSE IF input is StatusBarDisplayEvent THEN
    result := displayStatusBar_fixed()
    ASSERT statusBarDisplaysRealtimeCoordinates()
    ASSERT statusBarDisplaysCRS()
    ASSERT statusBarDisplaysElevation()
  END IF
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  IF input is ToolbarActionEvent THEN
    ASSERT handleToolbarAction_original(input) = handleToolbarAction_fixed(input)
  ELSE IF input is BackendCalculationEvent THEN
    ASSERT measurementBackend_original(input) = measurementBackend_fixed(input)
  ELSE IF input is StatusBarSignalEvent THEN
    ASSERT statusBarWidget_original(input) = statusBarWidget_fixed(input)
  END IF
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for working toolbar actions and backend calculations, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Distance Tool Preservation**: Verify Distance/Azimuth tool continues to work exactly as before (enable mode, collect two points, calculate)
2. **Shadow Height Preservation**: Verify Shadow Height tool continues to work exactly as before
3. **Visualization Tools Preservation**: Verify Layer Compositor and Comparator continue to work correctly
4. **Navigation Tools Preservation**: Verify Pan, Zoom, North Arrow continue to work correctly
5. **Backend Calculation Preservation**: Verify measure_polygon_area(), compute_volume(), compute_viewshed(), compute_slope_aspect() produce identical results with identical inputs
6. **Status Bar Widget Preservation**: Verify GISStatusBar.on_mouse_coordinates(), on_camera_changed(), on_render_busy() methods produce identical display updates with identical signal inputs

### Unit Tests

- Test that clicking "Polygon Area" button enables polygon drawing mode
- Test that clicking "Volume Cut/Fill" button enables polygon drawing mode and checks for DEM
- Test that clicking "Viewshed / LOS" button enables point selection mode
- Test that clicking "Slope & Aspect" button enables polygon drawing mode and checks for DEM
- Test that completing a polygon in measurement mode triggers the appropriate calculation
- Test that clicking a point in viewshed mode triggers viewshed calculation
- Test that status bar signal connections are established on initialization
- Test that status bar updates when mouseCoordinates signal is emitted
- Test that mode conflicts are handled (e.g., enabling polygon mode disables distance mode)
- Test that user instructions are displayed when measurement modes are enabled

### Property-Based Tests

- Generate random toolbar action sequences and verify that measurement tools always enable appropriate modes
- Generate random coordinate streams and verify status bar always displays them correctly
- Generate random measurement inputs (polygons, points) and verify backend calculations produce consistent results
- Test that all non-measurement toolbar actions continue to work across many scenarios
- Test that status bar handles edge cases (coordinates at poles, date line crossing, missing elevation data)

### Integration Tests

- Test full measurement workflow: click button → draw polygon → finish → see result in panel
- Test full viewshed workflow: click button → click observer point → see result in panel
- Test status bar integration: move cursor → see coordinates update → zoom → see scale update
- Test mode switching: enable distance mode → enable polygon mode → verify distance mode disabled
- Test cross-platform: verify measurements work on Mac and Windows
- Test with real DEM data: verify elevation-dependent measurements use GDAL correctly
