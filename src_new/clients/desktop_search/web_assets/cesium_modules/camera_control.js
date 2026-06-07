/**
 * camera_control.js
 * 
 * Cesium Camera Control and Manipulation
 * 
 * This module handles:
 * - flyTo operations for navigating to specific locations
 * - Camera orientation control (heading, pitch, roll)
 * - Camera orbit controls around target bounds
 * - Scene mode transitions (2D, 3D, Columbus View)
 * - Camera position synchronization
 * 
 * Requirements: 3.3, 3.5, 8.3
 */

// Camera orbit state
let cameraOrbitBounds = null;
let cameraOrbitHeading = -45.0 * (Math.PI / 180);  // Cesium.Math.toRadians(-45.0)
let cameraOrbitPitch = -35.0 * (Math.PI / 180);    // Cesium.Math.toRadians(-35.0)
let cameraOrbitRange = 1200.0;

// 3D mode pitch constraints
const MIN_3D_PITCH_RAD = -80.0 * (Math.PI / 180);   // never flatter than -80° in 3D
const DEFAULT_3D_PITCH_RAD = -35.0 * (Math.PI / 180); // default oblique view for DEM

/**
 * Fly camera to a specific location with optional orientation
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {Object} options - Flight options
 * @param {number} options.lon - Longitude in degrees
 * @param {number} options.lat - Latitude in degrees
 * @param {number} options.height - Height in meters
 * @param {number} [options.heading] - Heading in degrees (optional)
 * @param {number} [options.pitch] - Pitch in degrees (optional)
 * @param {number} [options.roll] - Roll in degrees (optional)
 * @param {number} [options.duration] - Flight duration in seconds (default: 2.0)
 * @param {Function} [options.complete] - Callback on completion
 */
export function flyToLocation(viewer, options) {
  if (!viewer || !viewer.camera) {
    return;
  }
  
  const {
    lon,
    lat,
    height,
    heading = 0,
    pitch = -35,
    roll = 0,
    duration = 2.0,
    complete
  } = options;
  
  const destination = window.Cesium.Cartesian3.fromDegrees(lon, lat, height);
  
  const orientation = {
    heading: heading * (Math.PI / 180),
    pitch: pitch * (Math.PI / 180),
    roll: roll * (Math.PI / 180)
  };
  
  viewer.camera.flyTo({
    destination: destination,
    orientation: orientation,
    duration: duration,
    complete: complete
  });
}

/**
 * Set camera orientation without changing position
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {Object} orientation - Camera orientation
 * @param {number} orientation.heading - Heading in degrees
 * @param {number} orientation.pitch - Pitch in degrees
 * @param {number} [orientation.roll] - Roll in degrees (default: 0)
 */
export function setCameraOrientation(viewer, orientation) {
  if (!viewer || !viewer.camera) {
    return;
  }
  
  const { heading, pitch, roll = 0 } = orientation;
  
  viewer.camera.setView({
    destination: viewer.camera.position.clone(),
    orientation: {
      heading: heading * (Math.PI / 180),
      pitch: pitch * (Math.PI / 180),
      roll: roll * (Math.PI / 180)
    }
  });
}

/**
 * Update camera orbit target based on bounds
 * 
 * @param {Object} bounds - Bounding box { west, south, east, north }
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 */
export function updateCameraOrbitTarget(bounds, viewer) {
  if (!bounds || !window.Cesium) {
    return;
  }
  
  const normalized = normalizeBounds(bounds);
  if (!normalized) {
    return;
  }
  
  const rect = window.Cesium.Rectangle.fromDegrees(
    normalized.west,
    normalized.south,
    normalized.east,
    normalized.north
  );
  const sphere = window.Cesium.BoundingSphere.fromRectangle3D(
    rect,
    window.Cesium.Ellipsoid.WGS84,
    0.0
  );
  
  cameraOrbitBounds = normalized;
  cameraOrbitRange = Math.max(
    compute3DFocusRange(normalized),
    sphere.radius * 1.2,
    250.0
  );
  
  if (viewer && viewer.camera) {
    if (Number.isFinite(viewer.camera.heading)) {
      cameraOrbitHeading = viewer.camera.heading;
    }
    if (Number.isFinite(viewer.camera.pitch)) {
      cameraOrbitPitch = viewer.camera.pitch;
    }
  }
}

/**
 * Apply camera orbit to current target
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {Object} activeTileBounds - Active tile bounds
 * @param {Object} lastLoadedBounds - Last loaded bounds
 * @param {string} currentSceneMode - Current scene mode ("3d", "2d", "columbus")
 * @returns {boolean} True if orbit was applied
 */
export function applyCameraOrbitTarget(viewer, activeTileBounds, lastLoadedBounds, currentSceneMode) {
  if (!viewer || currentSceneMode !== "3d") {
    return false;
  }
  
  const bounds = cameraOrbitBounds || activeTileBounds || lastLoadedBounds;
  if (!bounds) {
    return false;
  }
  
  const rect = window.Cesium.Rectangle.fromDegrees(
    bounds.west,
    bounds.south,
    bounds.east,
    bounds.north
  );
  const sphere = window.Cesium.BoundingSphere.fromRectangle3D(
    rect,
    window.Cesium.Ellipsoid.WGS84,
    0.0
  );
  const hpr = new window.Cesium.HeadingPitchRange(
    cameraOrbitHeading,
    cameraOrbitPitch,
    cameraOrbitRange
  );
  
  viewer.camera.cancelFlight();
  viewer.camera.lookAt(sphere.center, hpr);
  viewer.camera.lookAtTransform(window.Cesium.Matrix4.IDENTITY);
  
  return true;
}

/**
 * Sync orbit parameters from current camera position
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {Object} bounds - Bounding box
 */
export function syncOrbitFromCurrentCamera(viewer, bounds) {
  if (!viewer || !viewer.camera || !bounds) {
    return;
  }
  
  const rect = window.Cesium.Rectangle.fromDegrees(
    bounds.west,
    bounds.south,
    bounds.east,
    bounds.north
  );
  const sphere = window.Cesium.BoundingSphere.fromRectangle3D(
    rect,
    window.Cesium.Ellipsoid.WGS84,
    0.0
  );
  
  const camera = viewer.camera;
  if (Number.isFinite(camera.heading)) {
    cameraOrbitHeading = camera.heading;
  }
  if (Number.isFinite(camera.pitch)) {
    cameraOrbitPitch = camera.pitch;
  }
  if (camera.positionWC && sphere.center) {
    const distance = window.Cesium.Cartesian3.distance(camera.positionWC, sphere.center);
    if (Number.isFinite(distance) && distance > 1.0) {
      cameraOrbitRange = distance;
    }
  }
}

/**
 * Set camera pitch (tilt angle)
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {number} degrees - Pitch in degrees (-90 to 0)
 */
export function setPitch(viewer, degrees) {
  if (!viewer || !viewer.camera) {
    return;
  }
  
  cameraOrbitPitch = degrees * (Math.PI / 180);
  
  // Clamp to 3D constraints
  if (cameraOrbitPitch < MIN_3D_PITCH_RAD) {
    cameraOrbitPitch = MIN_3D_PITCH_RAD;
  }
  
  // Apply pitch around the center of the screen
  const canvas = viewer.canvas;
  const center = new window.Cesium.Cartesian2(
    canvas.clientWidth / 2,
    canvas.clientHeight / 2
  );
  
  const ray = viewer.camera.getPickRay(center);
  let target = null;
  
  if (ray) {
    target = viewer.scene.globe.pick(ray, viewer.scene);
  }
  
  if (target) {
    const distance = window.Cesium.Cartesian3.distance(viewer.camera.position, target);
    viewer.camera.lookAt(
      target,
      new window.Cesium.HeadingPitchRange(viewer.camera.heading, cameraOrbitPitch, distance)
    );
    viewer.camera.lookAtTransform(window.Cesium.Matrix4.IDENTITY);
  } else {
    viewer.camera.setView({
      destination: viewer.camera.position.clone(),
      orientation: {
        heading: viewer.camera.heading,
        pitch: cameraOrbitPitch,
        roll: viewer.camera.roll
      }
    });
  }
}

/**
 * Set camera heading (rotation angle)
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {number} degrees - Heading in degrees (0-360)
 */
export function setHeading(viewer, degrees) {
  if (!viewer || !viewer.camera) {
    return;
  }
  
  cameraOrbitHeading = degrees * (Math.PI / 180);
  
  viewer.camera.setView({
    destination: viewer.camera.position.clone(),
    orientation: {
      heading: cameraOrbitHeading,
      pitch: viewer.camera.pitch,
      roll: viewer.camera.roll
    }
  });
}

/**
 * Get current camera orbit parameters
 * 
 * @returns {Object} Orbit parameters { heading, pitch, range, bounds }
 */
export function getCameraOrbitParams() {
  return {
    heading: cameraOrbitHeading * (180 / Math.PI),  // Convert to degrees
    pitch: cameraOrbitPitch * (180 / Math.PI),
    range: cameraOrbitRange,
    bounds: cameraOrbitBounds
  };
}

/**
 * Reset camera to default startup position
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {Object} defaultPosition - Default position { lon, lat, height, heading, pitch }
 */
export function resetCameraToDefault(viewer, defaultPosition) {
  if (!viewer || !viewer.camera) {
    return;
  }
  
  const { lon, lat, height, heading, pitch } = defaultPosition;
  
  viewer.camera.flyTo({
    destination: window.Cesium.Cartesian3.fromDegrees(lon, lat, height),
    orientation: {
      heading: heading * (Math.PI / 180),
      pitch: pitch * (Math.PI / 180),
      roll: 0.0
    },
    duration: 2.0
  });
  
  cameraOrbitHeading = heading * (Math.PI / 180);
  cameraOrbitPitch = pitch * (Math.PI / 180);
  cameraOrbitRange = height;
}

// ─────────────────────────────────────────────────────────────────────────
// Helper Functions
// ─────────────────────────────────────────────────────────────────────────

/**
 * Normalize bounds object
 * 
 * @param {Object} bounds - Bounds { west, south, east, north }
 * @returns {Object|null} Normalized bounds or null if invalid
 */
function normalizeBounds(bounds) {
  if (!bounds || typeof bounds !== "object") {
    return null;
  }
  const west = Number(bounds.west);
  const south = Number(bounds.south);
  const east = Number(bounds.east);
  const north = Number(bounds.north);
  if (!Number.isFinite(west) || !Number.isFinite(south) || 
      !Number.isFinite(east) || !Number.isFinite(north)) {
    return null;
  }
  return { west, south, east, north };
}

/**
 * Compute 3D focus range for bounds
 * 
 * @param {Object} bounds - Bounds { west, south, east, north }
 * @returns {number} Focus range in meters
 */
function compute3DFocusRange(bounds) {
  if (!bounds || !window.Cesium) {
    return 1000.0;
  }
  
  const rect = window.Cesium.Rectangle.fromDegrees(
    bounds.west,
    bounds.south,
    bounds.east,
    bounds.north
  );
  const sphere = window.Cesium.BoundingSphere.fromRectangle3D(
    rect,
    window.Cesium.Ellipsoid.WGS84,
    0.0
  );
  
  return sphere.radius * 2.5;
}
