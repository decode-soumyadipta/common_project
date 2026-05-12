/**
 * event_handlers.js
 * 
 * Cesium Event Handlers
 * 
 * This module handles:
 * - Mouse click events (left, right, middle)
 * - Mouse move and hover events
 * - Measurement tool interactions
 * - Annotation placement and editing
 * - Search polygon drawing
 * - Entity picking and selection
 * 
 * Requirements: 3.3, 8.3
 */

// Measurement state
let measurementLineEntity = null;
let measurementLabelEntity = null;
let measurementPointEntities = [];
let measurementPreviewLineEntity = null;
let measurementAnchorDotEntity = null;
let measurementPreviewLabelEntity = null;
let measurementPreviewStart = null;
let measurementPreviewEnd = null;
let distanceMeasureModeEnabled = false;
let distanceMeasureAnchor = null;

// Annotation state
const annotationEntities = [];
let annotationCounter = 0;
let hoveredAnnotationEditEntity = null;
let hoveredAnnotationDeleteEntity = null;
let isAnnotationDrawing = false;
let annotationVisibilityEnabled = true;

// Click tracking
const clickedPoints = [];
let lastMapClickCartesian = null;
let lastMousePosition = null;

/**
 * Wire up click handlers for the viewer
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {Object} callbacks - Event callbacks
 * @param {Function} callbacks.onMapClick - Called on map click with (lat, lon, cartesian)
 * @param {Function} callbacks.onMeasurementUpdate - Called when measurement updates
 * @param {Function} callbacks.log - Logging function
 */
export function wireClickHandlers(viewer, callbacks = {}) {
  if (!viewer || !viewer.scene || !viewer.scene.canvas) {
    return null;
  }
  
  const { onMapClick, onMeasurementUpdate, log } = callbacks;
  
  const handler = new window.Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  
  // Track mouse down position to distinguish clicks from drags
  let mouseDownPosition = null;
  const DRAG_THRESHOLD_PIXELS = 5;
  
  handler.setInputAction(function(movement) {
    mouseDownPosition = movement.position ? {
      x: movement.position.x,
      y: movement.position.y
    } : null;
  }, window.Cesium.ScreenSpaceEventType.LEFT_DOWN);
  
  // Left click handler
  handler.setInputAction(function(movement) {
    if (!movement || !movement.position) {
      return;
    }
    
    // Check if this was a drag operation
    if (mouseDownPosition) {
      const dx = movement.position.x - mouseDownPosition.x;
      const dy = movement.position.y - mouseDownPosition.y;
      const distance = Math.sqrt(dx * dx + dy * dy);
      
      if (distance > DRAG_THRESHOLD_PIXELS) {
        // This was a drag, not a click
        mouseDownPosition = null;
        return;
      }
    }
    
    mouseDownPosition = null;
    
    // Check for annotation edit/delete icon clicks
    const picked = viewer.scene.pick(movement.position);
    if (picked && picked.id) {
      if (picked.id._annotationRole === "edit") {
        if (renameAnnotationFromEditIcon(picked.id, log)) {
          return;
        }
      }
      if (picked.id._annotationRole === "delete") {
        deleteAnnotation(viewer, picked.id, log);
        return;
      }
    }
    
    // Get cartesian position
    const cartesian = getCartesianFromViewer(viewer, movement.position);
    if (!cartesian) {
      return;
    }
    
    lastMapClickCartesian = cartesian;
    
    // Convert to lat/lon
    const cartographic = window.Cesium.Cartographic.fromCartesian(cartesian);
    const lat = window.Cesium.Math.toDegrees(cartographic.latitude);
    const lon = window.Cesium.Math.toDegrees(cartographic.longitude);
    
    // Handle measurement mode
    if (distanceMeasureModeEnabled) {
      handleMeasurementClick(viewer, cartesian, onMeasurementUpdate, log);
      return;
    }
    
    // Handle annotation drawing
    if (isAnnotationDrawing) {
      placeAnnotation(viewer, cartesian, lat, lon, log);
      return;
    }
    
    // Emit map click event
    if (onMapClick) {
      onMapClick(lat, lon, cartesian);
    }
    
    clickedPoints.push({ lat, lon, cartesian });
    
  }, window.Cesium.ScreenSpaceEventType.LEFT_CLICK);
  
  // Mouse move handler
  handler.setInputAction(function(movement) {
    if (!movement || !movement.endPosition) {
      return;
    }
    
    lastMousePosition = movement.endPosition;
    
    // Update annotation hover state
    updateAnnotationHover(viewer, movement.endPosition);
    
    // Update measurement preview
    if (distanceMeasureModeEnabled && distanceMeasureAnchor) {
      updateMeasurementPreview(viewer, movement.endPosition, onMeasurementUpdate);
    }
    
  }, window.Cesium.ScreenSpaceEventType.MOUSE_MOVE);
  
  return handler;
}

/**
 * Enable distance measurement mode
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {Function} [log] - Logging function
 */
export function enableMeasurementMode(viewer, log) {
  distanceMeasureModeEnabled = true;
  distanceMeasureAnchor = null;
  
  if (log) {
    log("info", "Measurement mode enabled - click to place points");
  }
}

/**
 * Disable distance measurement mode
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {Function} [log] - Logging function
 */
export function disableMeasurementMode(viewer, log) {
  distanceMeasureModeEnabled = false;
  distanceMeasureAnchor = null;
  
  // Clear preview entities
  if (measurementPreviewLineEntity) {
    viewer.entities.remove(measurementPreviewLineEntity);
    measurementPreviewLineEntity = null;
  }
  if (measurementPreviewLabelEntity) {
    viewer.entities.remove(measurementPreviewLabelEntity);
    measurementPreviewLabelEntity = null;
  }
  
  if (log) {
    log("info", "Measurement mode disabled");
  }
}

/**
 * Clear all measurements
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {Function} [log] - Logging function
 */
export function clearMeasurements(viewer, log) {
  if (!viewer) {
    return;
  }
  
  // Clear measurement entities
  if (measurementLineEntity) {
    viewer.entities.remove(measurementLineEntity);
    measurementLineEntity = null;
  }
  if (measurementLabelEntity) {
    viewer.entities.remove(measurementLabelEntity);
    measurementLabelEntity = null;
  }
  if (measurementAnchorDotEntity) {
    viewer.entities.remove(measurementAnchorDotEntity);
    measurementAnchorDotEntity = null;
  }
  
  // Clear point entities
  for (const pointEntity of measurementPointEntities) {
    viewer.entities.remove(pointEntity);
  }
  measurementPointEntities = [];
  
  // Clear preview entities
  if (measurementPreviewLineEntity) {
    viewer.entities.remove(measurementPreviewLineEntity);
    measurementPreviewLineEntity = null;
  }
  if (measurementPreviewLabelEntity) {
    viewer.entities.remove(measurementPreviewLabelEntity);
    measurementPreviewLabelEntity = null;
  }
  
  measurementPreviewStart = null;
  measurementPreviewEnd = null;
  distanceMeasureAnchor = null;
  
  if (log) {
    log("info", "Cleared all measurements");
  }
}

/**
 * Enable annotation drawing mode
 * 
 * @param {Function} [log] - Logging function
 */
export function enableAnnotationMode(log) {
  isAnnotationDrawing = true;
  
  if (log) {
    log("info", "Annotation mode enabled - click to place markers");
  }
}

/**
 * Disable annotation drawing mode
 * 
 * @param {Function} [log] - Logging function
 */
export function disableAnnotationMode(log) {
  isAnnotationDrawing = false;
  
  if (log) {
    log("info", "Annotation mode disabled");
  }
}

/**
 * Clear all annotations
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {Function} [log] - Logging function
 */
export function clearAnnotations(viewer, log) {
  if (!viewer) {
    return;
  }
  
  for (const entity of annotationEntities) {
    if (entity) {
      viewer.entities.remove(entity);
    }
  }
  annotationEntities.length = 0;
  annotationCounter = 0;
  
  if (log) {
    log("info", "Cleared all annotations");
  }
}

/**
 * Set annotation visibility
 * 
 * @param {boolean} visible - Visibility state
 */
export function setAnnotationVisibility(visible) {
  annotationVisibilityEnabled = Boolean(visible);
  
  for (const entity of annotationEntities) {
    if (entity) {
      entity.show = annotationVisibilityEnabled;
    }
  }
}

/**
 * Add a marker annotation at a specific location
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {Object} options - Marker options
 * @param {number} options.lat - Latitude in degrees
 * @param {number} options.lon - Longitude in degrees
 * @param {string} [options.text] - Marker text
 * @param {string} [options.color] - Marker color (CSS color string)
 * @param {Function} [options.log] - Logging function
 * @returns {Object} Created annotation entities { anchor, label, edit, delete }
 */
export function addMarker(viewer, options) {
  if (!viewer || !options) {
    return null;
  }
  
  const { lat, lon, text = "Point", color = "#ff0000", log } = options;
  
  const cartesian = window.Cesium.Cartesian3.fromDegrees(lon, lat);
  
  return placeAnnotation(viewer, cartesian, lat, lon, log, text, color);
}

// ─────────────────────────────────────────────────────────────────────────
// Internal Helper Functions
// ─────────────────────────────────────────────────────────────────────────

/**
 * Get cartesian position from screen coordinates
 */
function getCartesianFromViewer(viewer, screenPosition) {
  if (!viewer || !screenPosition) {
    return null;
  }
  
  const scene = viewer.scene;
  const ray = viewer.camera.getPickRay(screenPosition);
  let cartesian = null;
  
  if (ray) {
    cartesian = scene.globe.pick(ray, scene);
  }
  
  if (!cartesian) {
    cartesian = viewer.camera.pickEllipsoid(screenPosition, scene.globe.ellipsoid);
  }
  
  return cartesian || null;
}

/**
 * Handle measurement click
 */
function handleMeasurementClick(viewer, cartesian, onMeasurementUpdate, log) {
  if (!distanceMeasureAnchor) {
    // First click - set anchor
    distanceMeasureAnchor = cartesian;
    measurementPreviewStart = cartesian;
    
    // Create anchor dot
    measurementAnchorDotEntity = viewer.entities.add({
      position: cartesian,
      point: {
        pixelSize: 8,
        color: window.Cesium.Color.YELLOW,
        outlineColor: window.Cesium.Color.BLACK,
        outlineWidth: 2,
        heightReference: window.Cesium.HeightReference.CLAMP_TO_GROUND
      }
    });
    
    if (log) {
      log("info", "Measurement anchor set - click again to measure distance");
    }
  } else {
    // Second click - complete measurement
    const distance = window.Cesium.Cartesian3.distance(distanceMeasureAnchor, cartesian);
    const distanceKm = (distance / 1000).toFixed(2);
    
    // Create measurement line
    if (measurementLineEntity) {
      viewer.entities.remove(measurementLineEntity);
    }
    measurementLineEntity = viewer.entities.add({
      polyline: {
        positions: [distanceMeasureAnchor, cartesian],
        width: 3,
        material: window.Cesium.Color.YELLOW,
        clampToGround: true
      }
    });
    
    // Create measurement label
    const midpoint = window.Cesium.Cartesian3.midpoint(
      distanceMeasureAnchor,
      cartesian,
      new window.Cesium.Cartesian3()
    );
    
    if (measurementLabelEntity) {
      viewer.entities.remove(measurementLabelEntity);
    }
    measurementLabelEntity = viewer.entities.add({
      position: midpoint,
      label: {
        text: distanceKm + " km",
        font: "bold 16px sans-serif",
        fillColor: window.Cesium.Color.WHITE,
        outlineColor: window.Cesium.Color.BLACK,
        outlineWidth: 2,
        showBackground: true,
        backgroundColor: window.Cesium.Color.BLACK.withAlpha(0.7),
        pixelOffset: new window.Cesium.Cartesian2(0, -20),
        heightReference: window.Cesium.HeightReference.CLAMP_TO_GROUND
      }
    });
    
    // Clear preview
    if (measurementPreviewLineEntity) {
      viewer.entities.remove(measurementPreviewLineEntity);
      measurementPreviewLineEntity = null;
    }
    if (measurementPreviewLabelEntity) {
      viewer.entities.remove(measurementPreviewLabelEntity);
      measurementPreviewLabelEntity = null;
    }
    
    // Reset anchor for next measurement
    distanceMeasureAnchor = null;
    measurementPreviewStart = null;
    
    if (onMeasurementUpdate) {
      onMeasurementUpdate(distance, distanceKm);
    }
    
    if (log) {
      log("info", "Measurement complete: " + distanceKm + " km");
    }
  }
}

/**
 * Update measurement preview line
 */
function updateMeasurementPreview(viewer, screenPosition, onMeasurementUpdate) {
  if (!distanceMeasureAnchor) {
    return;
  }
  
  const cartesian = getCartesianFromViewer(viewer, screenPosition);
  if (!cartesian) {
    return;
  }
  
  measurementPreviewEnd = cartesian;
  
  // Create or update preview line
  if (!measurementPreviewLineEntity) {
    measurementPreviewLineEntity = viewer.entities.add({
      polyline: {
        positions: new window.Cesium.CallbackProperty(function() {
          if (measurementPreviewStart && measurementPreviewEnd) {
            return [measurementPreviewStart, measurementPreviewEnd];
          }
          return [];
        }, false),
        width: 2,
        material: window.Cesium.Color.YELLOW.withAlpha(0.6),
        clampToGround: true
      }
    });
  }
  
  // Calculate distance
  const distance = window.Cesium.Cartesian3.distance(distanceMeasureAnchor, cartesian);
  const distanceKm = (distance / 1000).toFixed(2);
  
  // Create or update preview label
  const midpoint = window.Cesium.Cartesian3.midpoint(
    distanceMeasureAnchor,
    cartesian,
    new window.Cesium.Cartesian3()
  );
  
  if (!measurementPreviewLabelEntity) {
    measurementPreviewLabelEntity = viewer.entities.add({
      position: new window.Cesium.CallbackProperty(function() {
        if (measurementPreviewStart && measurementPreviewEnd) {
          return window.Cesium.Cartesian3.midpoint(
            measurementPreviewStart,
            measurementPreviewEnd,
            new window.Cesium.Cartesian3()
          );
        }
        return midpoint;
      }, false),
      label: {
        text: new window.Cesium.CallbackProperty(function() {
          if (measurementPreviewStart && measurementPreviewEnd) {
            const d = window.Cesium.Cartesian3.distance(measurementPreviewStart, measurementPreviewEnd);
            return (d / 1000).toFixed(2) + " km";
          }
          return "0.00 km";
        }, false),
        font: "14px sans-serif",
        fillColor: window.Cesium.Color.YELLOW,
        outlineColor: window.Cesium.Color.BLACK,
        outlineWidth: 2,
        pixelOffset: new window.Cesium.Cartesian2(0, -20),
        heightReference: window.Cesium.HeightReference.CLAMP_TO_GROUND
      }
    });
  }
}

/**
 * Place an annotation marker
 */
function placeAnnotation(viewer, cartesian, lat, lon, log, text = null, color = "#ff0000") {
  annotationCounter++;
  const annotationId = "annotation_" + annotationCounter;
  const annotationText = text || window.prompt("Enter annotation text:", "Point " + annotationCounter) || "Point " + annotationCounter;
  
  // Create anchor point
  const anchorEntity = viewer.entities.add({
    position: cartesian,
    point: {
      pixelSize: 10,
      color: window.Cesium.Color.fromCssColorString(color),
      outlineColor: window.Cesium.Color.WHITE,
      outlineWidth: 2,
      heightReference: window.Cesium.HeightReference.CLAMP_TO_GROUND
    }
  });
  anchorEntity._annotationId = annotationId;
  anchorEntity._annotationRole = "anchor";
  
  // Create label
  const labelEntity = viewer.entities.add({
    position: cartesian,
    label: {
      text: annotationText,
      font: "bold 14px sans-serif",
      fillColor: window.Cesium.Color.WHITE,
      outlineColor: window.Cesium.Color.BLACK,
      outlineWidth: 2,
      showBackground: true,
      backgroundColor: window.Cesium.Color.fromCssColorString(color).withAlpha(0.8),
      pixelOffset: new window.Cesium.Cartesian2(0, -30),
      heightReference: window.Cesium.HeightReference.CLAMP_TO_GROUND
    }
  });
  labelEntity._annotationId = annotationId;
  labelEntity._annotationRole = "label";
  
  // Create edit icon
  const editEntity = viewer.entities.add({
    position: cartesian,
    billboard: {
      image: getAnnotationEditIconImage(),
      width: 20,
      height: 20,
      pixelOffset: new window.Cesium.Cartesian2(25, -30),
      color: window.Cesium.Color.WHITE.withAlpha(0.42),
      heightReference: window.Cesium.HeightReference.CLAMP_TO_GROUND
    }
  });
  editEntity._annotationId = annotationId;
  editEntity._annotationRole = "edit";
  editEntity._annotationLabelEntity = labelEntity;
  
  // Create delete icon
  const deleteEntity = viewer.entities.add({
    position: cartesian,
    billboard: {
      image: getAnnotationDeleteIconImage(),
      width: 20,
      height: 20,
      pixelOffset: new window.Cesium.Cartesian2(50, -30),
      color: window.Cesium.Color.WHITE.withAlpha(0.62),
      heightReference: window.Cesium.HeightReference.CLAMP_TO_GROUND
    }
  });
  deleteEntity._annotationId = annotationId;
  deleteEntity._annotationRole = "delete";
  deleteEntity._annotationAnchorEntity = anchorEntity;
  deleteEntity._annotationLabelEntity = labelEntity;
  deleteEntity._annotationEditEntity = editEntity;
  
  // Register entities
  annotationEntities.push(anchorEntity, labelEntity, editEntity, deleteEntity);
  
  if (log) {
    log("info", "Placed annotation: " + annotationText + " at (" + lat.toFixed(4) + ", " + lon.toFixed(4) + ")");
  }
  
  return { anchor: anchorEntity, label: labelEntity, edit: editEntity, delete: deleteEntity };
}

/**
 * Delete an annotation
 */
function deleteAnnotation(viewer, deleteEntity, log) {
  const delTargets = [
    deleteEntity._annotationAnchorEntity,
    deleteEntity._annotationLabelEntity,
    deleteEntity._annotationEditEntity,
    deleteEntity
  ];
  
  for (const target of delTargets) {
    const idx = annotationEntities.indexOf(target);
    if (idx > -1) {
      annotationEntities.splice(idx, 1);
    }
    if (target) {
      viewer.entities.remove(target);
    }
  }
  
  if (log) {
    log("info", "Deleted annotation id=" + (deleteEntity._annotationId || "?"));
  }
}

/**
 * Rename annotation from edit icon
 */
function renameAnnotationFromEditIcon(editEntity, log) {
  if (!editEntity || editEntity._annotationRole !== "edit") {
    return false;
  }
  
  const labelEntity = editEntity._annotationLabelEntity || null;
  if (!labelEntity || !labelEntity.label) {
    return false;
  }
  
  const currentText = labelEntity.label.text.getValue() || "Point";
  const nextText = window.prompt("Rename annotation", currentText);
  
  if (nextText === null) {
    return true;
  }
  
  if (nextText && nextText.trim()) {
    labelEntity.label.text = nextText.trim();
    if (log) {
      log("info", "Renamed annotation to: " + nextText.trim());
    }
  }
  
  return true;
}

/**
 * Update annotation hover state
 */
function updateAnnotationHover(viewer, screenPosition) {
  if (!viewer || !screenPosition) {
    return;
  }
  
  const picked = viewer.scene.pick(screenPosition);
  const nextHover = picked && picked.id && picked.id._annotationRole === "edit" ? picked.id : null;
  
  if (hoveredAnnotationEditEntity !== nextHover) {
    if (hoveredAnnotationEditEntity) {
      setAnnotationEditIconHoverState(hoveredAnnotationEditEntity, false);
    }
    hoveredAnnotationEditEntity = nextHover;
    if (hoveredAnnotationEditEntity) {
      setAnnotationEditIconHoverState(hoveredAnnotationEditEntity, true);
    }
  }
  
  const nextDelHover = picked && picked.id && picked.id._annotationRole === "delete" ? picked.id : null;
  if (hoveredAnnotationDeleteEntity !== nextDelHover) {
    if (hoveredAnnotationDeleteEntity) {
      setAnnotationDeleteIconHoverState(hoveredAnnotationDeleteEntity, false);
    }
    hoveredAnnotationDeleteEntity = nextDelHover;
    if (hoveredAnnotationDeleteEntity) {
      setAnnotationDeleteIconHoverState(hoveredAnnotationDeleteEntity, true);
    }
  }
}

/**
 * Set annotation edit icon hover state
 */
function setAnnotationEditIconHoverState(editEntity, hovered) {
  if (!editEntity || !editEntity.billboard) {
    return;
  }
  editEntity.billboard.color = hovered 
    ? window.Cesium.Color.WHITE.withAlpha(0.96) 
    : window.Cesium.Color.WHITE.withAlpha(0.42);
}

/**
 * Set annotation delete icon hover state
 */
function setAnnotationDeleteIconHoverState(deleteEntity, hovered) {
  if (!deleteEntity || !deleteEntity.billboard) {
    return;
  }
  deleteEntity.billboard.color = hovered 
    ? window.Cesium.Color.WHITE.withAlpha(0.96) 
    : window.Cesium.Color.WHITE.withAlpha(0.62);
}

/**
 * Get annotation edit icon image (SVG data URL)
 */
function getAnnotationEditIconImage() {
  return "data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%2720%27 height=%2720%27 viewBox=%270 0 20 20%27%3E%3Ccircle cx=%2710%27 cy=%2710%27 r=%279%27 fill=%27rgba(255%2C255%2C255%2C0.92)%27 stroke=%27rgba(0%2C0%2C0%2C0.38)%27 stroke-width=%271.1%27/%3E%3Cpath d=%27M6.1 12.9l.5-2.2L11.8 5.5a1.3 1.3 0 011.8 0l.8.8a1.3 1.3 0 010 1.8L9.1 13.3l-2.2.5a.6.6 0 01-.8-.7z%27 fill=%27%23282f39%27/%3E%3Cpath d=%27M10.9 6.4l2.7 2.7%27 stroke=%27%23ffffff%27 stroke-width=%271%27 stroke-linecap=%27round%27/%3E%3C/svg%3E";
}

/**
 * Get annotation delete icon image (SVG data URL)
 */
function getAnnotationDeleteIconImage() {
  return "data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%2720%27 height=%2720%27 viewBox=%270 0 20 20%27%3E%3Ccircle cx=%2710%27 cy=%2710%27 r=%279%27 fill=%27rgba(220%2C50%2C50%2C0.92)%27 stroke=%27rgba(0%2C0%2C0%2C0.38)%27 stroke-width=%271.1%27/%3E%3Cpath d=%27M6 6L14 14M14 6L6 14%27 stroke=%27%23ffffff%27 stroke-width=%272%27 stroke-linecap=%27round%27/%3E%3C/svg%3E";
}
