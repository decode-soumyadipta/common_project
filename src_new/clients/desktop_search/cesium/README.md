# Cesium Module Documentation

This directory contains modularized CesiumJS integration code extracted from the original monolithic `bridge.js` file.

## Module Structure

### viewer_init.js
**Purpose**: Cesium Viewer initialization and offline configuration

**Key Features**:
- Air-gapped viewer instantiation (disables Cesium Ion, Bing Maps, terrain providers)
- WebGL context loss recovery for long-running desktop applications
- GPU detection and adaptive performance tuning (NVIDIA vs Intel)
- Local file:// protocol compatibility patches
- Offline terrain provider configuration

**Main Functions**:
- `initializeViewer(containerId, options)` - Initialize Cesium viewer with air-gap compliance
- `getDefaultStartupPosition()` - Get default camera position (centered on India)

**Requirements**: 3.3, 3.5, 3.6, 8.3, 8.4, 16.3

---

### camera_control.js
**Purpose**: Camera manipulation and navigation

**Key Features**:
- flyTo operations for location navigation
- Camera orientation control (heading, pitch, roll)
- Camera orbit controls around target bounds
- Scene mode transitions (2D, 3D, Columbus View)
- Camera position synchronization

**Main Functions**:
- `flyToLocation(viewer, options)` - Fly camera to specific location
- `setCameraOrientation(viewer, orientation)` - Set camera orientation
- `updateCameraOrbitTarget(bounds, viewer)` - Update orbit target
- `setPitch(viewer, degrees)` - Set camera pitch
- `setHeading(viewer, degrees)` - Set camera heading
- `resetCameraToDefault(viewer, defaultPosition)` - Reset to default view

**Requirements**: 3.3, 3.5, 8.3

---

### layer_manager.js
**Purpose**: ImageryLayer management and control

**Key Features**:
- Add/remove imagery layers
- Layer visibility control
- Layer ordering and z-index management
- DEM (Digital Elevation Model) layer management
- Layer opacity and visual properties

**Main Functions**:
- `addImageryLayer(viewer, options)` - Add imagery layer
- `removeLayer(viewer, layerKey, log)` - Remove layer
- `setLayerVisibility(layerKey, visible, log)` - Toggle layer visibility
- `setLayerAlpha(layerKey, alpha, log)` - Set layer opacity
- `clearManagedImageryLayers(viewer, exceptLayerKey, log)` - Clear all layers
- `enforceLayerDisplayOrder(viewer, layerOrder, log)` - Set layer z-order
- `clearDemTerrainMode(viewer, log)` - Clear DEM terrain layers

**Requirements**: 3.3, 3.5, 8.3

---

### event_handlers.js
**Purpose**: User interaction and event handling

**Key Features**:
- Mouse click events (left, right, middle)
- Mouse move and hover events
- Distance measurement tool
- Annotation placement and editing
- Search polygon drawing
- Entity picking and selection

**Main Functions**:
- `wireClickHandlers(viewer, callbacks)` - Setup event handlers
- `enableMeasurementMode(viewer, log)` - Enable distance measurement
- `disableMeasurementMode(viewer, log)` - Disable measurement
- `clearMeasurements(viewer, log)` - Clear all measurements
- `enableAnnotationMode(log)` - Enable annotation drawing
- `disableAnnotationMode(log)` - Disable annotation drawing
- `clearAnnotations(viewer, log)` - Clear all annotations
- `addMarker(viewer, options)` - Add marker annotation

**Requirements**: 3.3, 8.3

---

### index.js
**Purpose**: Module aggregation and API surface preservation

**Key Features**:
- Re-exports all public functions from sub-modules
- Maintains original API surface for backward compatibility
- Single entry point for all Cesium functionality

**Usage**:
```javascript
import {
  initializeViewer,
  flyToLocation,
  addImageryLayer,
  wireClickHandlers
} from './cesium/index.js';
```

---

## Air-Gap Compliance

All modules are designed for air-gapped LAN deployment:

1. **No External Network Requests**:
   - Cesium Ion disabled
   - Bing Maps disabled
   - External terrain providers disabled
   - All assets loaded from local file system

2. **Offline Configuration**:
   - `imageryProvider: false` - No default basemap
   - `terrainProvider: EllipsoidTerrainProvider` - Local ellipsoid terrain
   - `baseLayerPicker: false` - Prevents external provider UI
   - `geocoder: false` - Prevents external geocoding API calls

3. **Local Asset Loading**:
   - All CesiumJS assets served from `web_assets/cesium/`
   - No CDN dependencies
   - File:// protocol compatibility patches applied

---

## Migration from bridge.js

The original `bridge.js` file (~9000+ lines) has been split into focused modules:

| Original Section | New Module | Lines |
|-----------------|------------|-------|
| Viewer initialization | viewer_init.js | ~400 |
| Camera controls | camera_control.js | ~350 |
| Layer management | layer_manager.js | ~450 |
| Event handlers | event_handlers.js | ~700 |
| **Total** | **4 modules** | **~1900** |

**Benefits**:
- Easier navigation and debugging
- Clear separation of concerns
- Improved testability
- Better code reusability
- Maintained backward compatibility via index.js

---

## Testing

Unit tests for these modules should be created in:
```
src_new/tests/unit/cesium/
├── test_viewer_init.js
├── test_camera_control.js
├── test_layer_manager.js
└── test_event_handlers.js
```

Integration tests should verify:
- Viewer initialization in air-gapped mode
- Camera navigation and orientation
- Layer add/remove/visibility operations
- Event handler registration and callbacks
- Measurement and annotation tools

---

## Future Enhancements

Potential improvements for future iterations:

1. **TypeScript Migration**: Add type definitions for better IDE support
2. **State Management**: Extract shared state into a dedicated state manager
3. **Event Bus**: Implement event bus for decoupled communication
4. **Configuration**: Externalize constants to configuration files
5. **Performance Monitoring**: Add performance metrics and logging
6. **Error Handling**: Enhance error recovery and user feedback

---

## Related Files

- Original source: `src/client_desktop/frontend/bridge.js`
- Python bridge: `src_new/clients/desktop_search/bridge/`
- Web assets: `src_new/clients/desktop_search/web_assets/`
- Design document: `.kiro/specs/geospatial-microservices-refactor/design.md`
