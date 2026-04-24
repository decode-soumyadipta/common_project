# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Measurement Tool Buttons Do Not Enable Interactive Modes
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: For deterministic bugs, scope the property to the concrete failing case(s) to ensure reproducibility
  - Test that clicking "Polygon Area" button does NOT enable polygon drawing mode on unfixed code
  - Test that clicking "Volume Cut/Fill" button does NOT enable polygon drawing mode on unfixed code
  - Test that clicking "Viewshed / LOS" button does NOT enable point selection mode on unfixed code
  - Test that clicking "Slope & Aspect" button does NOT enable polygon drawing mode on unfixed code
  - Test that status bar does NOT display real-time coordinates despite bridge signals being emitted on unfixed code
  - The test assertions should match the Expected Behavior Properties from design (interactive modes enabled, status bar displays GIS data)
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples found to understand root cause
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Measurement Tool Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for non-buggy inputs (Distance/Azimuth, Shadow Height, visualization tools, navigation tools, file operations)
  - Write property-based tests capturing observed behavior patterns from Preservation Requirements
  - Test that Distance/Azimuth tool continues to enable interactive mode correctly on unfixed code
  - Test that Shadow Height tool continues to enable interactive mode correctly on unfixed code
  - Test that visualization tools (Layer Compositor, Comparator) continue to function correctly on unfixed code
  - Test that navigation tools (Pan, Zoom, North Arrow) continue to function correctly on unfixed code
  - Test that backend measurement calculations produce identical results with identical inputs on unfixed code
  - Test that status bar widget signal handlers (on_mouse_coordinates, on_camera_changed, on_render_busy) process signals correctly on unfixed code
  - Property-based testing generates many test cases for stronger guarantees
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10_

- [x] 3. Fix for measurement tool UI integration and status bar connection

  - [x] 3.1 Connect status bar signals in main_window.py
    - Open `src/offline_gis_app/client_backend/desktop/main_window.py`
    - Locate the status bar initialization section (around line 420)
    - The signal connections are already present (lines 423-425):
      ```python
      self.bridge.mouseCoordinates.connect(self.gis_status_bar.on_mouse_coordinates)
      self.bridge.cameraChanged.connect(self.gis_status_bar.on_camera_changed)
      self.bridge.renderBusy.connect(self.gis_status_bar.on_render_busy)
      ```
    - Verify these connections are active and not commented out
    - Verify WebBridge signals are being emitted from JavaScript (check bridge.js)
    - _Bug_Condition: isBugCondition(StatusBarDisplayEvent) where statusBarDisplaysStaticPlatformInfo() AND NOT statusBarDisplaysRealtimeGISData()_
    - _Expected_Behavior: Status bar SHALL display real-time geographic coordinates, elevation, CRS, scale, heading, and render status_
    - _Preservation: Status bar widget implementation and signal handling logic remain unchanged_
    - _Requirements: 2.7, 2.8, 2.9, 2.10, 3.4, 3.5, 3.10_

  - [x] 3.2 Add measurement mode flags to controller initialization
    - Open `src/offline_gis_app/client_backend/desktop/controller.py`
    - Locate the `__init__` method
    - Add measurement mode flags after existing mode flags (around line 100):
      ```python
      self._polygon_area_mode_enabled = False
      self._volume_mode_enabled = False
      self._slope_aspect_mode_enabled = False
      self._viewshed_mode_enabled = False
      self._polygon_drawing_context = "none"  # "none", "search", "measurement"
      ```
    - _Bug_Condition: isBugCondition(ToolbarActionEvent) where action_label IN ['Polygon Area', 'Volume Cut/Fill', 'Viewshed / LOS', 'Slope & Aspect'] AND NOT interactiveModeEnabled(action_label)_
    - _Expected_Behavior: Measurement tools SHALL enable appropriate interactive modes (polygon drawing or point selection)_
    - _Preservation: Existing mode flags and initialization logic remain unchanged_
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3_

  - [x] 3.3 Implement polygon drawing mode for Polygon Area measurement
    - Open `src/offline_gis_app/client_backend/desktop/controller.py`
    - Locate the `_toolbar_measure_polygon_area` method
    - Before checking for polygon existence, enable polygon drawing mode:
      ```python
      if not self.state.search_polygon_points:
          self._polygon_drawing_context = "measurement"
          self._polygon_area_mode_enabled = True
          self.set_search_draw_mode(enabled=True)
          self.panel.log("Draw a polygon on the map, then click Finish to calculate area.")
          return
      ```
    - When polygon is finished, automatically trigger area calculation
    - Clear the measurement mode flag after calculation
    - Follow the pattern used in `_toolbar_measure_distance()` for mode handling
    - _Bug_Condition: User clicks "Polygon Area" button AND polygon drawing mode is NOT enabled_
    - _Expected_Behavior: System SHALL enable polygon drawing mode and display user instructions_
    - _Preservation: Backend measure_polygon_area() function remains unchanged_
    - _Requirements: 2.2, 2.11, 2.12, 3.1, 3.7_

  - [x] 3.4 Implement polygon drawing mode for Volume Cut/Fill measurement
    - Open `src/offline_gis_app/client_backend/desktop/controller.py`
    - Locate the `_toolbar_measure_volume` method
    - Before checking for polygon existence, enable polygon drawing mode:
      ```python
      if not self.state.search_polygon_points:
          self._polygon_drawing_context = "measurement"
          self._volume_mode_enabled = True
          self.set_search_draw_mode(enabled=True)
          self.panel.log("Draw a polygon on the map, then click Finish to calculate volume.")
          return
      ```
    - Check for active DEM layer before enabling mode
    - When polygon is finished, automatically trigger volume calculation
    - Clear the measurement mode flag after calculation
    - _Bug_Condition: User clicks "Volume Cut/Fill" button AND polygon drawing mode is NOT enabled_
    - _Expected_Behavior: System SHALL enable polygon drawing mode and display user instructions_
    - _Preservation: Backend compute_volume() function remains unchanged_
    - _Requirements: 2.3, 2.11, 2.12, 3.1, 3.7_

  - [x] 3.5 Implement polygon drawing mode for Slope & Aspect measurement
    - Open `src/offline_gis_app/client_backend/desktop/controller.py`
    - Locate the `_toolbar_measure_slope_aspect` method
    - Before checking for polygon existence, enable polygon drawing mode:
      ```python
      if not self.state.search_polygon_points:
          self._polygon_drawing_context = "measurement"
          self._slope_aspect_mode_enabled = True
          self.set_search_draw_mode(enabled=True)
          self.panel.log("Draw a polygon on the map, then click Finish to calculate slope & aspect.")
          return
      ```
    - Check for active DEM layer before enabling mode
    - When polygon is finished, automatically trigger slope/aspect calculation
    - Clear the measurement mode flag after calculation
    - _Bug_Condition: User clicks "Slope & Aspect" button AND polygon drawing mode is NOT enabled_
    - _Expected_Behavior: System SHALL enable polygon drawing mode and display user instructions_
    - _Preservation: Backend compute_slope_aspect() function remains unchanged_
    - _Requirements: 2.5, 2.11, 2.12, 3.1, 3.7_

  - [x] 3.6 Implement point selection mode for Viewshed/LOS measurement
    - Open `src/offline_gis_app/client_backend/desktop/controller.py`
    - Locate the `_toolbar_measure_viewshed` method
    - Before checking for clicked points, enable point selection mode:
      ```python
      if not self.state.clicked_points:
          self._viewshed_mode_enabled = True
          self.panel.log("Click on the map to select observer point for viewshed analysis.")
          return
      ```
    - Check for active DEM layer before enabling mode
    - In the `on_map_click` handler, check for viewshed mode and store clicked point
    - Automatically trigger viewshed calculation when point is clicked
    - Clear the mode flag after calculation
    - _Bug_Condition: User clicks "Viewshed / LOS" button AND point selection mode is NOT enabled_
    - _Expected_Behavior: System SHALL enable point selection mode and display user instructions_
    - _Preservation: Backend compute_viewshed() function remains unchanged_
    - _Requirements: 2.4, 2.11, 2.12, 3.1, 3.7_

  - [x] 3.7 Add polygon completion handler for measurement context
    - Open `src/offline_gis_app/client_backend/desktop/controller.py`
    - Locate the `finish_search_polygon` method or polygon completion logic
    - Add check for measurement context:
      ```python
      if self._polygon_drawing_context == "measurement":
          if self._polygon_area_mode_enabled:
              self._toolbar_measure_polygon_area()
          elif self._volume_mode_enabled:
              self._toolbar_measure_volume()
          elif self._slope_aspect_mode_enabled:
              self._toolbar_measure_slope_aspect()
          self._polygon_drawing_context = "none"
      ```
    - Ensure polygon drawing mode is disabled after measurement
    - _Bug_Condition: User finishes polygon in measurement mode AND measurement is NOT triggered_
    - _Expected_Behavior: System SHALL automatically trigger appropriate measurement calculation_
    - _Preservation: Search polygon functionality remains unchanged_
    - _Requirements: 2.2, 2.3, 2.5, 2.11, 3.1_

  - [x] 3.8 Handle mode conflicts for measurement tools
    - Open `src/offline_gis_app/client_backend/desktop/controller.py`
    - In each measurement mode activation, disable conflicting modes:
      - Disable distance measurement mode
      - Disable point annotation mode
      - Disable shadow height mode
      - Disable pan mode (if necessary)
    - Follow the pattern used in `_toolbar_measure_distance()` for mode conflict handling
    - Ensure only one interactive mode is active at a time
    - _Bug_Condition: Multiple interactive modes are enabled simultaneously_
    - _Expected_Behavior: System SHALL disable conflicting modes when enabling a new mode_
    - _Preservation: Existing mode conflict handling for Distance/Azimuth and Shadow Height remains unchanged_
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3_

  - [x] 3.9 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Measurement Tool Buttons Enable Interactive Modes
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - Verify that clicking "Polygon Area" button enables polygon drawing mode
    - Verify that clicking "Volume Cut/Fill" button enables polygon drawing mode
    - Verify that clicking "Viewshed / LOS" button enables point selection mode
    - Verify that clicking "Slope & Aspect" button enables polygon drawing mode
    - Verify that status bar displays real-time coordinates when cursor moves
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.7, 2.8, 2.9, 2.10_

  - [x] 3.10 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Measurement Tool Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - Verify Distance/Azimuth tool continues to work correctly
    - Verify Shadow Height tool continues to work correctly
    - Verify visualization tools continue to function correctly
    - Verify navigation tools continue to function correctly
    - Verify backend measurement calculations produce identical results
    - Verify status bar widget signal handlers process signals correctly
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint - Ensure all tests pass
  - Run all bug condition exploration tests - verify they pass
  - Run all preservation tests - verify they pass
  - Test full measurement workflows manually:
    - Click "Polygon Area" → draw polygon → finish → see result in panel
    - Click "Volume Cut/Fill" → draw polygon → finish → see result in panel
    - Click "Viewshed / LOS" → click observer point → see result in panel
    - Click "Slope & Aspect" → draw polygon → finish → see result in panel
  - Test status bar integration:
    - Move cursor over map → see coordinates update in real-time
    - Zoom camera → see scale update
    - Rotate camera → see heading update
  - Test mode switching:
    - Enable distance mode → enable polygon mode → verify distance mode disabled
    - Enable polygon area mode → enable viewshed mode → verify polygon mode disabled
  - Ensure all tests pass, ask the user if questions arise
