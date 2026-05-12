/**
 * index.js
 * 
 * Cesium Module Index - Re-exports all public functions
 * 
 * This module preserves the original API surface by re-exporting all public
 * functions from the modularized cesium/ directory.
 * 
 * Requirements: 3.3, 3.5, 3.6, 8.3, 8.4, 16.3
 */

// Viewer Initialization
export {
  initializeViewer,
  getDefaultStartupPosition
} from './viewer_init.js';

// Camera Control
export {
  flyToLocation,
  setCameraOrientation,
  updateCameraOrbitTarget,
  applyCameraOrbitTarget,
  syncOrbitFromCurrentCamera,
  setPitch,
  setHeading,
  getCameraOrbitParams,
  resetCameraToDefault
} from './camera_control.js';

// Layer Management
export {
  addImageryLayer,
  removeLayer,
  setLayerVisibility,
  setLayerAlpha,
  clearManagedImageryLayers,
  getManagedLayers,
  getLayerByKey,
  hasLayer,
  getLayerVisibility,
  enforceLayerDisplayOrder,
  raiseLayerToTop,
  lowerLayerToBottom,
  getActiveImageryLayer,
  setActiveImageryLayer,
  clearDemTerrainMode,
  getLayerCount,
  getAllLayerKeys,
  logLayerStack
} from './layer_manager.js';

// Event Handlers
export {
  wireClickHandlers,
  enableMeasurementMode,
  disableMeasurementMode,
  clearMeasurements,
  enableAnnotationMode,
  disableAnnotationMode,
  clearAnnotations,
  setAnnotationVisibility,
  addMarker
} from './event_handlers.js';
