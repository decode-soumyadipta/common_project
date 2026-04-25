# bridge.js Refactor Plan

## Overview

`bridge.js` is a 5500-line monolithic IIFE that drives the Cesium-based offline GIS frontend.
This document describes the intended split into single-responsibility modules.

**Constraint**: No ES module bundler is available. All files are loaded via `<script>` tags.
The IIFE pattern must be preserved. Module files define functions/variables in the shared
IIFE scope — they are loaded **before** `bridge.js` so their symbols are available as
closure-captured globals.

---

## Loading Order (index.html `<script>` tags)

```html
<!-- 1. Shared state (must be first) -->
<script src="modules/state.js"></script>

<!-- 2. Pure utilities (no dependencies on other modules) -->
<script src="modules/utils.js"></script>

<!-- 3. Domain modules (depend on state + utils) -->
<script src="modules/camera.js"></script>
<script src="modules/basemap.js"></script>
<script src="modules/dem.js"></script>
<script src="modules/imagery.js"></script>
<script src="modules/comparator.js"></script>
<script src="modules/search.js"></script>
<script src="modules/measurement.js"></script>
<script src="modules/annotations.js"></script>
<script src="modules/ui.js"></script>

<!-- 4. Main orchestrator (calls into all modules) -->
<script src="bridge.js"></script>
```

---

## Module Descriptions

### `state.js` — Shared Mutable State
**Lines in bridge.js**: ~1–220 (all `let`/`const` declarations at the top of the IIFE)

All shared mutable state variables. In the future refactor these become global variables
(not wrapped in an IIFE) so all module files can read/write them.

Key variables:
- `bridge`, `viewer` — core references
- `activeImageryLayer`, `activeDemDrapeLayer`, `activeDemHillshadeLayer`
- `activeDemContext`, `activeDemTerrainSignature`, `activeDemTerrainProvider`
- `managedImageryLayers`, `globalBasemapLayer`, `fallbackBasemapLayer`
- `northPolarCapLayer`, `southPolarCapLayer`, `baseTerrainProvider`
- `clickedPoints`, `annotationEntities`, `hoveredAnnotationEditEntity`
- `measurementLineEntity`, `measurementLabelEntity`, `measurementPreviewLineEntity`
- `distanceMeasureModeEnabled`, `distanceMeasureAnchor`
- `swipeComparatorEnabled`, `comparatorModeEnabled`
- `comparatorLeftViewer`, `comparatorRightViewer`
- `comparatorCameraSyncState`, `comparatorPaneVisualState`
- `searchDrawMode`, `searchPolygonPoints`, `searchPolygonLocked`
- `searchCursorEntity`, `searchPreviewLineEntity`, `searchPreviewPolygonEntity`
- `drawnPolygons`, `drawnPolygonCounter`
- `currentSceneMode`, `activeTileBounds`, `lastLoadedBounds`
- `demVisual`, `imageryVisual`
- All `ASIA_LOCK_*` constants
- All `LOCAL_SATELLITE_*` constants
- All `DEFAULT_STARTUP_*` constants
- All `COMPARATOR_DEM_*` constants

---

### `utils.js` — Pure Utility Functions
**Lines in bridge.js**: scattered throughout, mostly ~1893–1960

Pure functions with no side effects on global state (or minimal, well-defined ones).

Functions:
- `log(level, message)` — logging bridge
- `setStatus(text)` — update DOM status element
- `emitMapClick(lon, lat)` — fire bridge event
- `emitMeasurementUpdated(meters)` — fire bridge event
- `emitLoadingProgress(percent, message)` — fire bridge event
- `buildUrlWithQuery(url, extraQuery)` — URL construction
- `normalizeBounds(bounds)` — validate/normalize bounds object
- `createRectangle(bounds)` — bounds → Cesium.Rectangle
- `rectangleFromBounds(bounds)` — alias for createRectangle
- `applyCursorStyle(element, cursorValue)` — DOM cursor helper
- `requestSceneRender()` — trigger Cesium render
- `parseDemHeightRange(options)` — extract min/max from DEM options
- `formatDistance(meters)` — human-readable distance string

---

### `camera.js` — Camera & Scene Mode
**Lines in bridge.js**: ~2219–2700, ~4732–4870

Camera management, scene mode switching, and fly-to operations.

Functions:
- `applyDefaultSceneSettings()` — configure globe/fog/lighting defaults
- `applyDemSceneSettings()` — configure scene for DEM rendering
- `tuneCameraController()` — set zoom limits, Asia clamp postRender listener
- `configureCameraControllerForMode(mode)` — 2D vs 3D input controls
- `_swapTerrainProviderLocked(newProvider)` — swap terrain with camera lock
- `setSceneModeInternal(mode)` — morph 2D↔3D with pending state machine
- `detectSceneMode()` — read current Cesium scene mode
- `syncSceneModeToggle(mode)` — sync UI toggle (no-op, moved to Python)
- `focusPreferredRegion(durationSeconds)` — fly to best available bounds
- `focusPreferredRegion3D(durationSeconds)` — 3D-specific fly-to
- `focusLoadedRegion(durationSeconds)` — fly to activeTileBounds (2D)
- `focusLoadedRegion3D(durationSeconds)` — fly to activeTileBounds (3D)
- `schedule3DFocusAfterMorph(durationSeconds)` — deferred 3D focus
- `startFlyThroughBounds(west, south, east, north)` — cinematic fly-through
- `applyDefaultStartupFocus()` — initial Asia view on startup
- `_updateCompass()` — rotate compass needle DOM element
- Asia camera lock postRender listener (inside `tuneCameraController`)

---

### `basemap.js` — Basemap & OSM Tiles
**Lines in bridge.js**: ~3295–3510

Basemap provider creation and attachment.

Functions:
- `createNaturalEarthProvider(rectangle)` — NaturalEarth fallback provider
- `attachLocalSatelliteBasemap()` — probe and attach offline OSM XYZ tiles
- `attachOfflineFallbackBasemap(reason)` — fall back to NaturalEarth
- `ensureFallbackBasemapLayer()` — ensure at least one basemap exists
- `updateBasemapBlendForCurrentMode()` — pin basemap to bottom of stack
- `attachOfflineTerrainPack()` — attach offline terrain (currently no-op)
- `clearPolarCapLayers()` — remove polar cap imagery layers
- `ensurePolarCapLayers()` — add NaturalEarth polar cap layers

---

### `dem.js` — DEM Terrain Rendering
**Lines in bridge.js**: ~2739–3100

DEM imagery-only pipeline (colormap drape + hillshade on EllipsoidTerrainProvider).

Functions/classes:
- `OfflineCustomTerrainProvider(options)` — constructor
- `OfflineCustomTerrainProvider.prototype.requestTileGeometry` — decode heightmap
- `OfflineCustomTerrainProvider.prototype.getLevelMaximumGeometricError`
- `OfflineCustomTerrainProvider.prototype.getTileDataAvailable`
- `applyDemLayer()` — build and attach DEM imagery layers + terrain provider
- `setDemColorMode(colormapName)` — in-place colormap swap
- `clearDemTerrainMode()` — remove DEM layers, restore base terrain
- `updateDemColorbar(minHeight, maxHeight, options)` — update colorbar DOM
- `hideDemColorbar()` — hide colorbar DOM element
- `resolveDemColorbarGradient(colormapName)` — CSS gradient string for colormap
- `parseDemHeightRange(options)` — extract height range from DEM options
- `applyDemSceneSettings()` — configure scene for DEM (also in camera.js)

---

### `imagery.js` — Imagery Layer Management
**Lines in bridge.js**: ~1992–2215

Imagery layer lifecycle and visibility management.

Functions:
- `clearManagedImageryLayers(exceptLayerKey)` — remove all managed layers
- `logLayerStack()` — debug dump of imagery layer stack
- `setLayerVisibilityByKey(layerKey, visible)` — show/hide a layer by key
- `setActiveTileBounds(bounds)` — update activeTileBounds + orbit target
- `attachTileErrorHandler(provider, name)` — suppress/log tile 404s
- `updateBasemapBlendForCurrentMode()` — (shared with basemap.js)

---

### `comparator.js` — Comparator Mode
**Lines in bridge.js**: ~400–1590

Side-by-side layer comparison (swipe and dual-viewer modes).

Functions:
- `ensureComparatorViewers()` — create left/right Cesium.Viewer instances
- `refreshComparatorLayers(options)` — rebuild layers in both panes
- `setComparatorWindowsVisible(visible)` — show/hide comparator DOM
- `updateComparatorPolygons(visible)` — sync ROI polygons to comparator viewers
- `scheduleComparatorDemRefresh(paneKey)` — debounced DEM color refresh
- `setSwipeComparatorEnabled(enabled)` — enable/disable comparator mode
- `applySwipeComparatorSplit()` — apply split direction to imagery layers
- `bindComparatorSyncHandlers()` — wire camera/cursor sync event listeners
- `syncComparatorTerrainProviders()` — copy terrain provider to DEM panes
- `applyComparatorPaneVisualState(paneKey)` — apply brightness/exaggeration
- `applyLayerDefinitionToViewer(targetViewer, definition, paneKey)` — load layer
- `setSelectedComparatorPane(paneKey, notifyPanel)` — select active pane
- `notifyComparatorPaneState(paneKey)` — emit pane state to Python bridge
- `buildComparatorPaneSnapshot(paneKey)` — serialize pane state to JSON

---

### `search.js` — Search Polygon & AOI
**Lines in bridge.js**: ~4332–4730

Polygon drawing, AOI management, and search geometry emission.

Functions:
- `ensureSearchPreviewEntities()` — create Cesium entities for polygon preview
- `updateSearchPolygonPreview()` — refresh preview during drawing
- `finalizeSearchPolygon()` — lock polygon and emit to Python bridge
- `toggleDrawnPolygonVisibility(polyId, visible)` — show/hide one polygon
- `toggleAllDrawnPolygonsVisibility(visible)` — show/hide all polygons
- `updatePolygonPreviewVisibility()` — sync visibility flags to entities
- `setPolygonPreviewVisible(visible)` — set polygonVisibilityEnabled flag
- `setSearchCursorEnabled(enabled)` — apply pencil cursor to canvas
- `updateSearchCursorOverlay(screenPosition)` — move pencil cursor overlay
- `emitSearchGeometry(type, payload)` — fire bridge.on_search_geometry

---

### `measurement.js` — Distance/Azimuth Measurement
**Lines in bridge.js**: ~3860–4270

Distance measurement tool with screen-space scale bar overlay.

Functions:
- `setDistanceMeasureMode(enabled)` — enable/disable distance tool
- `_enforceMeasureCursor(active)` — MutationObserver to keep crosshair cursor
- `updateMeasurementPreview(...)` — live preview line during cursor move
- `updateMeasurementEntities(...)` — finalized measurement line + label
- `clearMeasurementEntities()` — remove all measurement Cesium entities
- `clearMeasurementPreviewEntities()` — remove preview entities only
- `updateDistanceScaleOverlay(...)` — position/size the screen-space ruler
- `clearDistanceScaleOverlay()` — hide the ruler overlay

---

### `annotations.js` — Annotation Tools
**Lines in bridge.js**: ~3519–3570

Point annotation management.

Functions:
- `clearAnnotationEntities()` — remove all annotation Cesium entities
- `setAnnotationVisibility(visible)` — show/hide all annotations
- `renameAnnotationFromEditIcon(editEntity)` — prompt-based rename
- `updateAnnotationHover(screenPosition)` — highlight hovered edit icon
- `setAnnotationEditIconHoverState(editEntity, hovered)` — dim/brighten icon

---

### `ui.js` — UI Widgets
**Lines in bridge.js**: ~1793–1895, ~3569–3710

Status bar, compass, scale widgets, and bridge emitters.

Functions:
- `wireStatusBarListeners()` — wire camera/tile events to status bar
- `_updateCompass()` — rotate compass needle (also referenced in camera.js)
- `emitMouseCoordinates(lon, lat, screenPosition)` — throttled coord emit
- `emitCameraChanged()` — emit scale denominator + heading to Python
- `updateEdgeScaleWidgets()` — draw lon/lat tick marks on SVG rulers
- `setSearchBusy(active, message)` — show/hide search busy overlay
- `setMeasurementCursorEnabled(enabled)` — apply crosshair cursor
- `setSceneModeControlEnabled(enabled)` — enable/disable scene mode toggle
- `syncSceneModeToggle(mode)` — sync toggle state (no-op, moved to Python)

---

## Implementation Notes

### Why not split now?

The file is working correctly in production. The risk of introducing subtle bugs
(wrong variable scope, missing closure references, load-order issues) outweighs
the benefit of splitting at this time.

### Safe split strategy (when ready)

1. Create each module file as a plain JS file (no IIFE, no `"use strict"` wrapper).
   Functions defined at the top level become globals accessible to all scripts.

2. Move the `let`/`const` state declarations from `bridge.js` into `state.js` as
   top-level `var` declarations (or `let` if the target environment supports it).

3. Move function groups into their respective module files, removing them from `bridge.js`.

4. Add `<script>` tags to `index.html` in the order shown above.

5. Test each module in isolation by commenting out the others and verifying the
   remaining functionality still works.

### Dependency graph

```
state.js
  └── utils.js
        ├── camera.js
        ├── basemap.js
        ├── dem.js (depends on camera.js for applyDemSceneSettings)
        ├── imagery.js (depends on basemap.js for updateBasemapBlendForCurrentMode)
        ├── comparator.js (depends on imagery.js, dem.js, basemap.js)
        ├── search.js
        ├── measurement.js
        ├── annotations.js
        └── ui.js (depends on camera.js for _updateCompass)
```

### Shared functions (appear in multiple modules)

- `updateBasemapBlendForCurrentMode` — used by imagery.js and basemap.js
- `_updateCompass` — used by ui.js and camera.js (wireStatusBarListeners)
- `parseDemHeightRange` — used by dem.js and utils.js
- `applyDemSceneSettings` — used by dem.js and camera.js

Resolution: keep these in the lowest-level module that owns them and import
(or call) from higher-level modules. In the no-bundler environment, load order
ensures availability.
