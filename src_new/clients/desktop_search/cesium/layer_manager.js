/**
 * layer_manager.js
 * 
 * Cesium ImageryLayer Management
 * 
 * This module handles:
 * - Adding and removing imagery layers
 * - Layer visibility control
 * - Layer ordering and z-index management
 * - DEM (Digital Elevation Model) layer management
 * - Layer opacity and visual properties
 * 
 * Requirements: 3.3, 3.5, 8.3
 */

// Managed imagery layers registry
const managedImageryLayers = new Map();
const layerDefinitions = new Map();
const layerVisibilityState = new Map();

// Active layers
let activeImageryLayer = null;
let activeDemDrapeLayer = null;
let activeDemHillshadeLayer = null;
let activeDemContext = null;

/**
 * Add an imagery layer to the viewer
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {Object} options - Layer options
 * @param {string} options.layerKey - Unique identifier for the layer
 * @param {string} options.url - Tile URL template
 * @param {string} [options.name] - Display name for the layer
 * @param {number} [options.alpha] - Layer opacity (0-1, default: 1.0)
 * @param {boolean} [options.show] - Initial visibility (default: true)
 * @param {number} [options.minzoom] - Minimum zoom level (default: 0)
 * @param {number} [options.maxzoom] - Maximum zoom level (default: 19)
 * @param {Function} [options.log] - Logging function
 * @returns {Cesium.ImageryLayer|null} Created imagery layer or null on failure
 */
export function addImageryLayer(viewer, options) {
  if (!viewer || !options || !options.layerKey || !options.url) {
    return null;
  }
  
  const {
    layerKey,
    url,
    name = layerKey,
    alpha = 1.0,
    show = true,
    minzoom = 0,
    maxzoom = 26,
    log
  } = options;
  
  // Check if layer already exists
  const existingLayer = managedImageryLayers.get(layerKey);
  if (existingLayer) {
    existingLayer.show = true;
    if (log) {
      log("info", "Layer already exists, showing: " + layerKey);
    }
    return existingLayer;
  }
  
  // Create imagery provider
  const provider = new window.Cesium.UrlTemplateImageryProvider({
    url: url,
    minimumLevel: minzoom,
    maximumLevel: maxzoom,
    tilingScheme: new window.Cesium.WebMercatorTilingScheme(),
    rectangle: window.Cesium.Rectangle.MAX_VALUE
  });
  
  // Add layer to viewer
  const layer = viewer.imageryLayers.addImageryProvider(provider);
  layer.alpha = alpha;
  layer.show = show;
  layer._layerKey = layerKey;
  layer._layerName = name;
  
  // Register layer
  managedImageryLayers.set(layerKey, layer);
  layerDefinitions.set(layerKey, { url, name, minzoom, maxzoom });
  layerVisibilityState.set(layerKey, show);
  
  activeImageryLayer = layer;
  
  if (log) {
    log("info", "Added imagery layer: " + layerKey + " at index " + viewer.imageryLayers.indexOf(layer));
  }
  
  return layer;
}

/**
 * Remove an imagery layer from the viewer
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {string} layerKey - Layer identifier
 * @param {Function} [log] - Logging function
 * @returns {boolean} True if layer was removed
 */
export function removeLayer(viewer, layerKey, log) {
  if (!viewer || !layerKey) {
    return false;
  }
  
  // Handle DEM layer keys (may have :hillshade suffix)
  const key = layerKey.replace(":hillshade", "");
  
  // Remove main layer
  const mainLayer = managedImageryLayers.get(key);
  if (mainLayer) {
    viewer.imageryLayers.remove(mainLayer, false);
    managedImageryLayers.delete(key);
    layerDefinitions.delete(key);
    layerVisibilityState.delete(key);
  }
  
  // Remove hillshade layer if exists
  const hillshadeKey = key + ":hillshade";
  const hillshadeLayer = managedImageryLayers.get(hillshadeKey);
  if (hillshadeLayer) {
    viewer.imageryLayers.remove(hillshadeLayer, false);
    managedImageryLayers.delete(hillshadeKey);
    layerDefinitions.delete(hillshadeKey);
    layerVisibilityState.delete(hillshadeKey);
  }
  
  if (log) {
    log("info", "Removed layer: " + layerKey);
  }
  
  return true;
}

/**
 * Set layer visibility
 * 
 * @param {string} layerKey - Layer identifier
 * @param {boolean} visible - Visibility state
 * @param {Function} [log] - Logging function
 */
export function setLayerVisibility(layerKey, visible, log) {
  const imageryLayer = managedImageryLayers.get(layerKey);
  if (imageryLayer) {
    const shouldShow = Boolean(visible);
    imageryLayer.show = shouldShow;
    layerVisibilityState.set(layerKey, shouldShow);
    
    if (log) {
      log("debug", "Set layer visibility: " + layerKey + " = " + shouldShow);
    }
  }
}

/**
 * Set layer opacity (alpha)
 * 
 * @param {string} layerKey - Layer identifier
 * @param {number} alpha - Opacity value (0-1)
 * @param {Function} [log] - Logging function
 */
export function setLayerAlpha(layerKey, alpha, log) {
  const layer = managedImageryLayers.get(layerKey);
  if (layer) {
    const numAlpha = Math.max(0.0, Math.min(1.0, Number(alpha) || 0.0));
    layer.alpha = numAlpha;
    
    if (log) {
      log("debug", "Set layer alpha: " + layerKey + " = " + numAlpha);
    }
  }
}

/**
 * Clear all managed imagery layers
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {string} [exceptLayerKey] - Layer to preserve (optional)
 * @param {Function} [log] - Logging function
 */
export function clearManagedImageryLayers(viewer, exceptLayerKey, log) {
  if (!viewer) {
    managedImageryLayers.clear();
    layerDefinitions.clear();
    layerVisibilityState.clear();
    return;
  }
  
  for (const [layerKey, layer] of Array.from(managedImageryLayers.entries())) {
    if (exceptLayerKey && layerKey === exceptLayerKey) {
      continue;
    }
    
    // DEM drape and hillshade layers should only be removed via clearDemTerrainMode
    if (activeDemContext && activeDemContext.layerKey === layerKey) {
      if (log) {
        log("debug", "clearManagedImageryLayers: Preserving DEM layer " + layerKey);
      }
      continue;
    }
    
    if (layer) {
      viewer.imageryLayers.remove(layer, false);
    }
    managedImageryLayers.delete(layerKey);
    layerDefinitions.delete(layerKey);
    layerVisibilityState.delete(layerKey);
  }
  
  if (exceptLayerKey) {
    activeImageryLayer = managedImageryLayers.get(exceptLayerKey) || null;
  }
}

/**
 * Get all managed imagery layers
 * 
 * @returns {Map} Map of layer keys to Cesium.ImageryLayer instances
 */
export function getManagedLayers() {
  return new Map(managedImageryLayers);
}

/**
 * Get layer by key
 * 
 * @param {string} layerKey - Layer identifier
 * @returns {Cesium.ImageryLayer|null} Layer instance or null
 */
export function getLayerByKey(layerKey) {
  return managedImageryLayers.get(layerKey) || null;
}

/**
 * Check if layer exists
 * 
 * @param {string} layerKey - Layer identifier
 * @returns {boolean} True if layer exists
 */
export function hasLayer(layerKey) {
  return managedImageryLayers.has(layerKey);
}

/**
 * Get layer visibility state
 * 
 * @param {string} layerKey - Layer identifier
 * @returns {boolean} Visibility state
 */
export function getLayerVisibility(layerKey) {
  return layerVisibilityState.get(layerKey) || false;
}

/**
 * Enforce layer display order
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {Array<string>} layerOrder - Array of layer keys in desired order (bottom to top)
 * @param {Function} [log] - Logging function
 */
export function enforceLayerDisplayOrder(viewer, layerOrder, log) {
  if (!viewer || !layerOrder || !Array.isArray(layerOrder)) {
    return;
  }
  
  // Apply order from bottom to top
  for (let i = 0; i < layerOrder.length; i++) {
    const layerKey = layerOrder[i];
    const layer = managedImageryLayers.get(layerKey);
    
    if (layer && viewer.imageryLayers.contains(layer)) {
      const currentIndex = viewer.imageryLayers.indexOf(layer);
      const targetIndex = i;
      
      if (currentIndex !== targetIndex) {
        // Move layer to target index
        viewer.imageryLayers.remove(layer, false);
        viewer.imageryLayers.add(layer, targetIndex);
      }
    }
  }
  
  if (log) {
    log("debug", "Enforced layer display order: " + layerOrder.join(", "));
  }
}

/**
 * Raise layer to top of stack
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {string} layerKey - Layer identifier
 * @param {Function} [log] - Logging function
 */
export function raiseLayerToTop(viewer, layerKey, log) {
  if (!viewer || !layerKey) {
    return;
  }
  
  const layer = managedImageryLayers.get(layerKey);
  if (layer && viewer.imageryLayers.contains(layer)) {
    viewer.imageryLayers.raiseToTop(layer);
    
    if (log) {
      log("debug", "Raised layer to top: " + layerKey);
    }
  }
}

/**
 * Lower layer to bottom of stack
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {string} layerKey - Layer identifier
 * @param {Function} [log] - Logging function
 */
export function lowerLayerToBottom(viewer, layerKey, log) {
  if (!viewer || !layerKey) {
    return;
  }
  
  const layer = managedImageryLayers.get(layerKey);
  if (layer && viewer.imageryLayers.contains(layer)) {
    viewer.imageryLayers.lowerToBottom(layer);
    
    if (log) {
      log("debug", "Lowered layer to bottom: " + layerKey);
    }
  }
}

/**
 * Get active imagery layer
 * 
 * @returns {Cesium.ImageryLayer|null} Active layer or null
 */
export function getActiveImageryLayer() {
  return activeImageryLayer;
}

/**
 * Set active imagery layer
 * 
 * @param {Cesium.ImageryLayer} layer - Layer to set as active
 */
export function setActiveImageryLayer(layer) {
  activeImageryLayer = layer;
}

/**
 * Clear DEM terrain mode
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {Function} [log] - Logging function
 */
export function clearDemTerrainMode(viewer, log) {
  if (!viewer) {
    return;
  }
  
  const previousDemLayerKey = activeDemContext ? activeDemContext.layerKey : null;
  
  // Remove DEM drape layer
  if (activeDemDrapeLayer) {
    viewer.imageryLayers.remove(activeDemDrapeLayer, false);
    
    if (previousDemLayerKey) {
      managedImageryLayers.delete(previousDemLayerKey);
    }
    
    activeDemDrapeLayer = null;
  }
  
  // Remove DEM hillshade layer
  if (activeDemHillshadeLayer) {
    viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
    
    if (previousDemLayerKey) {
      managedImageryLayers.delete(previousDemLayerKey + ":hillshade");
    }
    
    activeDemHillshadeLayer = null;
  }
  
  activeDemContext = null;
  
  if (log) {
    log("info", "Cleared DEM terrain mode");
  }
}

/**
 * Get layer count
 * 
 * @returns {number} Number of managed layers
 */
export function getLayerCount() {
  return managedImageryLayers.size;
}

/**
 * Get all layer keys
 * 
 * @returns {Array<string>} Array of layer keys
 */
export function getAllLayerKeys() {
  return Array.from(managedImageryLayers.keys());
}

/**
 * Log current layer stack for debugging
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {Function} log - Logging function
 */
export function logLayerStack(viewer, log) {
  if (!viewer || !log) {
    return;
  }
  
  log("debug", "=== Layer Stack (bottom to top) ===");
  
  for (let i = 0; i < viewer.imageryLayers.length; i++) {
    const layer = viewer.imageryLayers.get(i);
    const layerKey = layer._layerKey || "unknown";
    const layerName = layer._layerName || "unnamed";
    const alpha = layer.alpha.toFixed(2);
    const show = layer.show;
    
    log("debug", `  [${i}] ${layerKey} (${layerName}): alpha=${alpha}, show=${show}`);
  }
  
  log("debug", "=== End Layer Stack ===");
}
