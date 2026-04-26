(function () {
  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: Shared Mutable State  →  future: modules/state.js
  // All let/const declarations at the top of the IIFE. These are shared via
  // closure across all logical sections. In the future refactor they become
  // global variables accessible to all module files loaded before bridge.js.
  // ═══════════════════════════════════════════════════════════════════════════

  let bridge = null;
  let viewer = null;
  let activeImageryLayer = null;
  let activeDemDrapeLayer = null;
  let activeDemHillshadeLayer = null;
  let activeDemContext = null;
  let activeDemTerrainSignature = null;
  let activeDemTerrainProvider = null;
  let activeDemDrapeUrl = null;
  let activeDemHillshadeUrl = null;
  const managedImageryLayers = new Map();
  let globalBasemapLayer = null;
  let fallbackBasemapLayer = null;
  let northPolarCapLayer = null;
  let southPolarCapLayer = null;
  let baseTerrainProvider = null;
  let baseTerrainReadyPromise = Promise.resolve(false);
  let countryBoundaryDataSource = null;
  const clickedPoints = [];
  const annotationEntities = [];
  let hoveredAnnotationEditEntity = null;
  let lastMapClickCartesian = null;
  let annotationCounter = 0;
  let measurementLineEntity = null;
  let measurementLabelEntity = null;
  let measurementPreviewLineEntity = null;
  let measurementPreviewLabelEntity = null;
  let distanceMeasureModeEnabled = false;
  let distanceMeasureAnchor = null;
  let swipeComparatorEnabled = false;
  let swipeComparatorPosition = 0.5;
  let swipeDividerElement = null;
  let swipeComparatorLeftLayerKey = null;
  let swipeComparatorRightLayerKey = null;
  let comparatorModeEnabled = false;
  let comparatorLeftViewer = null;
  let comparatorRightViewer = null;
  let comparatorLeftLayerType = null;
  let comparatorRightLayerType = null;
  let comparatorCameraSyncLock = false;
  let comparatorSyncFrameHandle = null;
  let comparatorPendingSyncSource = null;
  let comparatorActiveInputViewer = null;
  let comparatorActiveInputReleaseTimer = null;
  let comparatorDemRefreshTimer = null;
  const COMPARATOR_DEM_REFRESH_DEBOUNCE_MS = 120;
  if (!window.Cesium) {
    const statusEl = document.getElementById("status");
    if (statusEl) {
      statusEl.textContent =
        "Cesium.js not found. Run scripts/setup_cesium_assets.sh to install local Cesium assets.";
    }
    console.error("[offlineGIS] Cesium runtime not found. Local assets are missing.");
    return;
  }
  const COMPARATOR_DEM_DEFAULT_PITCH = Cesium.Math.toRadians(-35.0);
  const COMPARATOR_DEM_MIN_PITCH = Cesium.Math.toRadians(-80.0);
  const COMPARATOR_DEM_MAX_PITCH = Cesium.Math.toRadians(-15.0);
  const layerDefinitions = new Map();
  const layerVisibilityState = new Map();
  const tileErrorSeen = new Set();
  const layerErrorCounts = new Map();
  // DEM rendering uses imagery-only pipeline (colormap + hillshade on EllipsoidTerrainProvider)
  // No client-side terrain decoding — crash-proof for any raster size on macOS and Windows/NVIDIA
  const LOCAL_SATELLITE_LAYER_NAME = "LocalSatellite";
  const LOCAL_SATELLITE_TILE_ROOT = "./basemap/xyz";
  const LOCAL_SATELLITE_DEFAULT_MAX_LEVEL = 8;
  const WEB_MERCATOR_MAX_LAT_DEGREES = 85.05112878;
  const WEB_MERCATOR_SAFE_EDGE_LAT_DEGREES = 84.8;
  const LOCAL_BASEMAP_REGION_BOUNDS = {
    world: {
      west: -180.0,
      south: -WEB_MERCATOR_MAX_LAT_DEGREES,
      east: 180.0,
      north: WEB_MERCATOR_MAX_LAT_DEGREES,
    },
  };
  const DEFAULT_STARTUP_CENTER_LON = 78.0;
  const DEFAULT_STARTUP_CENTER_LAT = 22.0;
  const DEFAULT_STARTUP_HEIGHT_M = 6000000.0;   // ~6000 km — Asia fills the view
  const DEFAULT_STARTUP_HEADING = Cesium.Math.toRadians(0.0);
  const DEFAULT_STARTUP_PITCH = Cesium.Math.toRadians(-90.0);
  const AUTO_ATTACH_TERRAIN_RGB_PACK = false;
  const SHOW_COUNTRY_BOUNDARY_OVERLAY = false;

  // ── Asia camera lock ──────────────────────────────────────────────────────
  // The globe is locked to the Asia region. The camera center is clamped to
  // this rectangle and the max zoom-out distance prevents seeing other continents.
  const ASIA_LOCK_WEST  =  25.0;   // °E  (Turkey/Iran western edge)
  const ASIA_LOCK_EAST  = 180.0;   // °E  (International Date Line)
  const ASIA_LOCK_SOUTH = -12.0;   // °N  (Southern Indonesia)
  const ASIA_LOCK_NORTH =  82.0;   // °N  (Northern Russia/Arctic)
  const ASIA_LOCK_CENTER_LON = (ASIA_LOCK_WEST + ASIA_LOCK_EAST) / 2;   // ~102.5°E
  const ASIA_LOCK_CENTER_LAT = (ASIA_LOCK_SOUTH + ASIA_LOCK_NORTH) / 2; // ~35°N
  // Max altitude that still keeps Asia filling the screen (~8000 km)
  const ASIA_LOCK_MAX_ZOOM_OUT_M = 8000000.0;
  // Min altitude — 1 m (supports 3-4 cm resolution data)
  const ASIA_LOCK_MIN_ZOOM_IN_M  = 1.0;
  let _asiaCameraClampEnabled = true;
  const COUNTRY_BOUNDARY_GEOJSON_URL = "./basemap/boundaries/ne_110m_admin_0_boundary_lines_land.geojson";
  const terrainTileCache = new Map();
  // DEM rendering uses imagery-only pipeline (colormap drape + hillshade overlay on EllipsoidTerrainProvider)
  // No client-side terrain decoding — crash-proof for any raster size on macOS and Windows/NVIDIA.
  // TERRAIN_SAMPLE_SIZE is set to 65. A value of 256 creates 6.5M+ triangles and freezes the UI thread.
  // 65 is the standard optimal resolution for high-detail Cesium heightmaps without causing lag.
  const TERRAIN_SAMPLE_SIZE = 65;
  const DEM_MAX_TERRAIN_LEVEL = 14;
  const DEM_HILLSHADE_AZIMUTH = 45;
  const DEM_HILLSHADE_ALTITUDE = 45;
  const demVisual = {
    exaggeration: 2.0,
    hillshadeAlpha: 0.35,
  };
  const imageryVisual = {
    brightness: 1.0,
    contrast: 1.0,
  };
  let comparatorSelectedPane = "left";
  const comparatorPaneVisualState = {
    left: {
      imagery: {
        brightness: imageryVisual.brightness,
        contrast: imageryVisual.contrast,
      },
      dem: {
        exaggeration: demVisual.exaggeration,
        hillshadeAlpha: demVisual.hillshadeAlpha,
        colorMode: "gray",
      },
    },
    right: {
      imagery: {
        brightness: imageryVisual.brightness,
        contrast: imageryVisual.contrast,
      },
      dem: {
        exaggeration: demVisual.exaggeration,
        hillshadeAlpha: demVisual.hillshadeAlpha,
        colorMode: "gray",
      },
    },
  };
  const comparatorDemStyleRefreshVersion = {
    left: 0,
    right: 0,
  };
  const comparatorCameraSyncState = {
    left: {
      lastSourceWidthRad: NaN,
      lastSourceHeightRad: NaN,
      lastSourceCameraHeightM: NaN,
      lastSourceCenterLon: NaN,
      lastSourceCenterLat: NaN,
    },
    right: {
      lastSourceWidthRad: NaN,
      lastSourceHeightRad: NaN,
      lastSourceCameraHeightM: NaN,
      lastSourceCenterLon: NaN,
      lastSourceCenterLat: NaN,
    },
  };
  let terrainDecodeCanvas = null;
  let terrainDecodeContext = null;
  // terrainDecodeCanvas/Context retained as no-op stubs — not used in imagery-only DEM pipeline.
  let searchDrawMode = "none";
  const searchPolygonPoints = [];
  let searchPolygonLocked = false;
  let searchCursorPoint = null;
  let searchCursorEntity = null;
  let searchPreviewLineEntity = null;
  let searchPreviewPolygonEntity = null;
  let searchAreaLabelEntity = null;
  let searchCursorOverlay = null;
  let lastSearchCursorScreenPosition = null;
  let polygonVisibilityEnabled = true;
  let searchOverlayVisible = true;
  let panModeActive = false;
  let distanceScaleOverlay = null;
  const searchVertexEntities = [];
  const drawnPolygons = [];
  // Fill-volume visualisation — all tracked as entities (no GroundPrimitive)
  window._fillVolumeEntities = window._fillVolumeEntities || [];
  // _fillVolumePrimitives kept as empty stub for legacy clear calls
  window._fillVolumePrimitives = window._fillVolumePrimitives || [];
  let drawnPolygonCounter = 0;
  let aoiPanelMinimized = false;
  let annotationVisibilityEnabled = true;
  let sceneModeControlEnabled = true;
  let currentSceneMode = "3d";
  let activeTileBounds = null;
  let lastLoadedBounds = null;
  let pendingFocusAfterMorph = false;
  let pendingTerrainSceneAfterMorph = false;
  let pendingFocusBounds = null;
  let pendingFlyThroughBounds = null;
  let pendingSceneModeAfterMorph = null;
  let cameraOrbitBounds = null;
  let cameraOrbitHeading = Cesium.Math.toRadians(-45.0);
  let cameraOrbitPitch = Cesium.Math.toRadians(-35.0);
  let cameraOrbitRange = 1200.0;
  let lastEdgeScaleUpdateMs = 0;
  let has2DWheelZoomFallback = false;
  const EDGE_SCALE_UPDATE_INTERVAL_MS = 120;
  const SEARCH_PENCIL_CURSOR_IMAGE =
    "data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2220%22 height=%2220%22 viewBox=%220 0 24 24%22%3E%3Cpath fill=%22%23f4c430%22 stroke=%22%231a1a1a%22 stroke-width=%221.4%22 d=%22M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25z%22/%3E%3Cpath fill=%22%231a1a1a%22 d=%22M20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83l3.75 3.75z%22/%3E%3C/svg%3E";
  const SEARCH_PENCIL_CURSOR = `url("${SEARCH_PENCIL_CURSOR_IMAGE}") 2 18, crosshair`;
  const ANNOTATION_EDIT_ICON_IMAGE =
    "data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%2720%27 height=%2720%27 viewBox=%270 0 20 20%27%3E%3Ccircle cx=%2710%27 cy=%2710%27 r=%279%27 fill=%27rgba(255%2C255%2C255%2C0.92)%27 stroke=%27rgba(0%2C0%2C0%2C0.38)%27 stroke-width=%271.1%27/%3E%3Cpath d=%27M6.1 12.9l.5-2.2L11.8 5.5a1.3 1.3 0 011.8 0l.8.8a1.3 1.3 0 010 1.8L9.1 13.3l-2.2.5a.6.6 0 01-.8-.7z%27 fill=%27%23282f39%27/%3E%3Cpath d=%27M10.9 6.4l2.7 2.7%27 stroke=%27%23ffffff%27 stroke-width=%271%27 stroke-linecap=%27round%27/%3E%3C/svg%3E";
  const _SB_COORD_THROTTLE_MS = 33; // ~30 fps
  const _SB_RENDER_IDLE_DELAY_MS = 120;
  let _sbLastCoordEmitMs = 0;
  let _sbRenderBusy = false;
  let _sbRenderIdleTimer = null;
  
  // Tile loading progress tracking
  let _tileLoadingActive = false;
  let _tilesPending = 0;
  let _tilesLoaded = 0;
  let _tileLoadStartTime = 0;
  let _tileProgressCheckInterval = null;
  let _tileDrainTimer = null;
  const _TILE_PROGRESS_CHECK_MS = 100; // Check every 100ms

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: Utility Functions  →  future: modules/utils.js
  // Functions: log, setStatus, emitMapClick, emitMeasurementUpdated,
  //   emitLoadingProgress, buildUrlWithQuery, normalizeBounds, createRectangle,
  //   rectangleFromBounds, applyCursorStyle, requestSceneRender,
  //   parseDemHeightRange, formatDistance
  // ═══════════════════════════════════════════════════════════════════════════

  function log(level, message) {
    const fn = console[level] || console.log;
    fn("[offlineGIS]", message);
    if (bridge && bridge.js_log) {
      bridge.js_log(level, String(message));
    }
  }

  function setStatus(text) {
    const el = document.getElementById("status");
    if (el) el.textContent = text;
  }

  function emitMapClick(lon, lat) {
    if (bridge && bridge.on_map_click) {
      bridge.on_map_click(lon, lat);
    }
  }

  function emitMeasurementUpdated(meters) {
    if (bridge && bridge.on_measurement) {
      bridge.on_measurement(meters);
    }
  }

  function setRenderBusyState(busy) {
    if (!bridge || !bridge.on_render_busy) return;
    if (busy) {
      if (_sbRenderIdleTimer) {
        clearTimeout(_sbRenderIdleTimer);
        _sbRenderIdleTimer = null;
      }
      if (!_sbRenderBusy) {
        _sbRenderBusy = true;
        bridge.on_render_busy(true);
      }
      return;
    }

    if (_sbRenderIdleTimer) {
      clearTimeout(_sbRenderIdleTimer);
    }
    _sbRenderIdleTimer = setTimeout(function () {
      _sbRenderIdleTimer = null;
      if (_sbRenderBusy) {
        _sbRenderBusy = false;
        bridge.on_render_busy(false);
      }
    }, _SB_RENDER_IDLE_DELAY_MS);
  }
  
  function emitLoadingProgress(percent, message) {
    if (!bridge || !bridge.on_loading_progress) return;
    bridge.on_loading_progress(Math.round(percent), String(message || "Loading"));
  }
  
  // ── Tile loading progress via native Cesium event (accurate, zero polling) ──
  // Wired in wireStatusBarListeners() after viewer is ready.
  let _tileQueuePeak = 0;

  function startTileLoadingMonitor() {
    // No-op — progress is driven by tileLoadProgressEvent in wireStatusBarListeners
    _tileLoadingActive = true;
  }
  
  function stopTileLoadingMonitor() {
    _tileLoadingActive = false;
    _tileQueuePeak = 0;
  }

  function setSearchBusy(active, message) {
    const overlay = document.getElementById("searchBusyOverlay");
    const textEl = document.getElementById("searchBusyText");
    if (!overlay) {
      return;
    }
    const enabled = Boolean(active);
    overlay.classList.toggle("visible", enabled);
    overlay.setAttribute("aria-hidden", enabled ? "false" : "true");
    if (textEl && enabled) {
      textEl.textContent = String(message || "Searching tiles...");
    }
  }

  function requestSceneRender() {
    if (viewer && viewer.scene && typeof viewer.scene.requestRender === "function") {
      viewer.scene.requestRender();
    }
    if (comparatorLeftViewer && comparatorLeftViewer.scene) {
      comparatorLeftViewer.scene.requestRender();
    }
    if (comparatorRightViewer && comparatorRightViewer.scene) {
      comparatorRightViewer.scene.requestRender();
    }
  }

  function setComparatorWindowsVisible(visible) {
    const root = document.getElementById("comparatorWindows");
    const map = document.getElementById("cesiumContainer");
    if (!root || !map) {
      return;
    }
    const enabled = Boolean(visible);
    root.classList.toggle("active", enabled);
    root.setAttribute("aria-hidden", enabled ? "false" : "true");
    map.style.display = enabled ? "none" : "block";
  }

  function getCartesianFromViewer(targetViewer, screenPosition) {
    if (!targetViewer || !screenPosition) {
      return null;
    }
    const scene = targetViewer.scene;
    const ray = targetViewer.camera.getPickRay(screenPosition);
    let cartesian = null;
    if (ray) {
      cartesian = scene.globe.pick(ray, scene);
    }
    if (!cartesian) {
      cartesian = targetViewer.camera.pickEllipsoid(screenPosition, scene.globe.ellipsoid);
    }
    return cartesian || null;
  }

  function cartesianToLonLat(cartesian) {
    if (!cartesian) {
      return null;
    }
    const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
    if (!cartographic) {
      return null;
    }
    return {
      lon: Cesium.Math.toDegrees(cartographic.longitude),
      lat: Cesium.Math.toDegrees(cartographic.latitude),
    };
  }

  function getLonLatFromViewer(targetViewer, screenPosition) {
    return cartesianToLonLat(getCartesianFromViewer(targetViewer, screenPosition));
  }

  function getViewerCenterLonLat(targetViewer) {
    if (!targetViewer || !targetViewer.canvas) {
      return null;
    }
    const center = new Cesium.Cartesian2(
      targetViewer.canvas.clientWidth * 0.5,
      targetViewer.canvas.clientHeight * 0.5,
    );
    return getLonLatFromViewer(targetViewer, center);
  }

  function applyCrosshairScreenPosition(crosshairElement, targetViewer, screenPosition) {
    if (!crosshairElement) {
      return;
    }
    let x = 0.0;
    let y = 0.0;
    if (screenPosition && Number.isFinite(screenPosition.x) && Number.isFinite(screenPosition.y)) {
      x = Number(screenPosition.x);
      y = Number(screenPosition.y);
    } else if (targetViewer && targetViewer.canvas) {
      x = targetViewer.canvas.clientWidth * 0.5;
      y = targetViewer.canvas.clientHeight * 0.5;
    }
    crosshairElement.style.left = `${x.toFixed(2)}px`;
    crosshairElement.style.top = `${y.toFixed(2)}px`;
  }

  function updateComparatorCrosshair(lon, lat, leftScreenPosition, rightScreenPosition) {
    const leftCrosshair = document.getElementById("comparatorCrosshairLeft");
    const rightCrosshair = document.getElementById("comparatorCrosshairRight");
    const leftCoords = document.getElementById("comparatorCoordsLeft");
    const rightCoords = document.getElementById("comparatorCoordsRight");

    const hasLonLat = Number.isFinite(lon) && Number.isFinite(lat);
    applyCrosshairScreenPosition(leftCrosshair, comparatorLeftViewer, leftScreenPosition || null);
    applyCrosshairScreenPosition(rightCrosshair, comparatorRightViewer, rightScreenPosition || null);

    const text =
      hasLonLat
        ? `lon: ${Number(lon).toFixed(6)}, lat: ${Number(lat).toFixed(6)}`
        : "lon: ---, lat: ---";
    if (leftCoords) {
      leftCoords.textContent = text;
    }
    if (rightCoords) {
      rightCoords.textContent = text;
    }
  }

  function updateComparatorCenterReadout(sourceViewer) {
    if (!comparatorModeEnabled) {
      return;
    }
    const targetViewer = sourceViewer || comparatorLeftViewer;
    if (!targetViewer || !targetViewer.canvas) {
      updateComparatorCrosshair(NaN, NaN);
      return;
    }
    const center = new Cesium.Cartesian2(
      targetViewer.canvas.clientWidth * 0.5,
      targetViewer.canvas.clientHeight * 0.5,
    );
    const lonLat = getLonLatFromViewer(targetViewer, center);
    updateComparatorCrosshair(lonLat ? lonLat.lon : NaN, lonLat ? lonLat.lat : NaN, null, null);
  }

  function sceneToWindowCoordinates(targetScene, worldCartesian) {
    if (!targetScene || !worldCartesian || !Cesium.SceneTransforms) {
      return null;
    }
    if (typeof Cesium.SceneTransforms.worldToWindowCoordinates === "function") {
      return Cesium.SceneTransforms.worldToWindowCoordinates(targetScene, worldCartesian);
    }
    if (typeof Cesium.SceneTransforms.wgs84ToWindowCoordinates === "function") {
      return Cesium.SceneTransforms.wgs84ToWindowCoordinates(targetScene, worldCartesian);
    }
    return null;
  }

  function projectCartesianToViewer(targetViewer, worldCartesian) {
    if (!targetViewer || !worldCartesian) {
      return null;
    }
    const projected = sceneToWindowCoordinates(targetViewer.scene, worldCartesian);
    if (!projected || !Number.isFinite(projected.x) || !Number.isFinite(projected.y)) {
      return null;
    }
    return new Cesium.Cartesian2(Number(projected.x), Number(projected.y));
  }

  function getComparatorDemPitchRadians() {
    let pitch = Number(cameraOrbitPitch);
    if (!Number.isFinite(pitch)) {
      return COMPARATOR_DEM_DEFAULT_PITCH;
    }
    // If the source camera came from a 2D/top-down context, force a meaningful 3D tilt.
    const nearNadir = Math.abs(pitch) >= Cesium.Math.toRadians(88.0);
    if (nearNadir) {
      return COMPARATOR_DEM_DEFAULT_PITCH;
    }
    return Math.max(COMPARATOR_DEM_MIN_PITCH, Math.min(COMPARATOR_DEM_MAX_PITCH, pitch));
  }

  function setComparatorDemCameraFromRectangle(targetViewer, focusRect, sourceHeading, sourceRangeMeters) {
    if (!targetViewer || !focusRect) {
      return;
    }
    const heading = Number.isFinite(sourceHeading) ? Number(sourceHeading) : 0.0;
    const pitch = getComparatorDemPitchRadians();
    const sphere = Cesium.BoundingSphere.fromRectangle3D(focusRect, Cesium.Ellipsoid.WGS84, 0.0);
    const sourceRange = Number(sourceRangeMeters);
    const derivedRange = Math.max(sphere.radius * 1.9, 900.0);
    const range = Number.isFinite(sourceRange) && sourceRange > 50.0 ? Math.max(sourceRange, 900.0) : derivedRange;
    targetViewer.camera.lookAt(
      sphere.center,
      new Cesium.HeadingPitchRange(heading, pitch, range),
    );
    targetViewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
  }

  function focusComparatorViewerToRectangle(targetViewer, layerType, focusRect) {
    if (!targetViewer || !focusRect) {
      return;
    }
    if (layerType === "dem") {
      setComparatorDemCameraFromRectangle(targetViewer, focusRect, targetViewer.camera.heading);
      return;
    }
    targetViewer.camera.setView({ destination: focusRect });
  }

  function getComparatorLayerTypeForViewer(targetViewer) {
    if (targetViewer === comparatorLeftViewer) {
      return comparatorLeftLayerType;
    }
    if (targetViewer === comparatorRightViewer) {
      return comparatorRightLayerType;
    }
    return null;
  }

  function getComparatorPaneKeyForViewer(targetViewer) {
    if (targetViewer === comparatorLeftViewer) {
      return "left";
    }
    if (targetViewer === comparatorRightViewer) {
      return "right";
    }
    return null;
  }

  function getComparatorSyncStateForViewer(targetViewer) {
    const paneKey = getComparatorPaneKeyForViewer(targetViewer);
    if (!paneKey) {
      return null;
    }
    return comparatorCameraSyncState[paneKey] || null;
  }

  function resetComparatorCameraSyncState(reason) {
    for (const paneKey of ["left", "right"]) {
      const state = comparatorCameraSyncState[paneKey];
      if (!state) {
        continue;
      }
      state.lastSourceWidthRad = NaN;
      state.lastSourceHeightRad = NaN;
      state.lastSourceCameraHeightM = NaN;
      state.lastSourceCenterLon = NaN;
      state.lastSourceCenterLat = NaN;
    }
    log("debug", `Comparator sync state reset reason=${String(reason || "unspecified")}`);
  }

  function recordComparatorSourceRectangle(sourceViewer, sourceRectangle, context) {
    const state = getComparatorSyncStateForViewer(sourceViewer);
    if (!state || !sourceRectangle) {
      return;
    }
    const width = rectangleWidthRadians(sourceRectangle);
    const height = rectangleHeightRadians(sourceRectangle);
    const center = Cesium.Rectangle.center(sourceRectangle);
    if (!Number.isFinite(width) || !Number.isFinite(height) || !center) {
      return;
    }
    state.lastSourceWidthRad = width;
    state.lastSourceHeightRad = height;
    state.lastSourceCenterLon = Number(center.longitude);
    state.lastSourceCenterLat = Number(center.latitude);
    const cameraHeight = sourceViewer && sourceViewer.camera && sourceViewer.camera.positionCartographic && Number.isFinite(sourceViewer.camera.positionCartographic.height)
      ? Number(sourceViewer.camera.positionCartographic.height)
      : NaN;
    state.lastSourceCameraHeightM = Number.isFinite(cameraHeight) ? cameraHeight : NaN;
    const paneKey = getComparatorPaneKeyForViewer(sourceViewer) || "unknown";
    log("debug", `Comparator source rect recorded pane=${paneKey} context=${context} width=${width.toFixed(6)} height=${height.toFixed(6)} cam_h=${Number.isFinite(state.lastSourceCameraHeightM) ? state.lastSourceCameraHeightM.toFixed(2) : "n/a"} center_lon=${state.lastSourceCenterLon.toFixed(6)} center_lat=${state.lastSourceCenterLat.toFixed(6)}`);
  }

  function getComparatorDemViewer() {
    if (comparatorLeftLayerType === "dem" && comparatorLeftViewer) {
      return comparatorLeftViewer;
    }
    if (comparatorRightLayerType === "dem" && comparatorRightViewer) {
      return comparatorRightViewer;
    }
    return null;
  }

  function syncComparatorTerrainProviders() {
    const terrainProvider = viewer && viewer.terrainProvider ? viewer.terrainProvider : null;
    if (!terrainProvider) {
      return;
    }
    if (comparatorLeftViewer && comparatorLeftLayerType === "dem" && comparatorLeftViewer.terrainProvider !== terrainProvider) {
      comparatorLeftViewer.terrainProvider = terrainProvider;
    }
    if (comparatorRightViewer && comparatorRightLayerType === "dem" && comparatorRightViewer.terrainProvider !== terrainProvider) {
      comparatorRightViewer.terrainProvider = terrainProvider;
    }
  }

  function cancelComparatorCameraSyncSchedule() {
    if (comparatorSyncFrameHandle !== null) {
      window.cancelAnimationFrame(comparatorSyncFrameHandle);
      comparatorSyncFrameHandle = null;
    }
    comparatorPendingSyncSource = null;
    comparatorActiveInputViewer = null;
    if (comparatorActiveInputReleaseTimer !== null) {
      window.clearTimeout(comparatorActiveInputReleaseTimer);
      comparatorActiveInputReleaseTimer = null;
    }
  }

  function markComparatorInputViewer(sourceViewer) {
    if (!sourceViewer) {
      return;
    }
    comparatorActiveInputViewer = sourceViewer;
    if (comparatorActiveInputReleaseTimer !== null) {
      window.clearTimeout(comparatorActiveInputReleaseTimer);
      comparatorActiveInputReleaseTimer = null;
    }
    comparatorActiveInputReleaseTimer = window.setTimeout(function () {
      comparatorActiveInputReleaseTimer = null;
      comparatorActiveInputViewer = null;
      log("debug", "Comparator activeInputViewer released after inactivity window");
    }, 650);
    log("debug", `Comparator activeInputViewer set to ${sourceViewer === comparatorLeftViewer ? "LEFT" : "RIGHT"}`);
  }

  function scheduleComparatorCameraSync(sourceViewer) {
    if (comparatorModeEnabled && sourceViewer) {
      log("debug", "Comparator camera sync is disabled; scheduleComparatorCameraSync ignored");
      updateComparatorCenterReadout(sourceViewer);
    }
  }

  function lockComparatorFocusToCurrentView() {
    if (!comparatorModeEnabled || !comparatorLeftViewer || !comparatorRightViewer) {
      return;
    }
    log("debug", "Comparator camera sync is disabled; lockComparatorFocusToCurrentView ignored");
    updateComparatorCenterReadout(getComparatorDemViewer() || comparatorLeftViewer);
    requestSceneRender();
  }

  function setComparatorViewerModeByType(targetViewer, layerType) {
    if (!targetViewer || !targetViewer.scene) {
      log("debug", "setComparatorViewerModeByType: viewer or scene is null");
      return;
    }

    const isDem = String(layerType || "").toLowerCase() === "dem";

    if (!isDem) {
      // Imagery-only pane → force strict 2D flat map view.
      // Morphing to SCENE2D prevents pitch/tilt altogether.
      if (targetViewer.scene.mode !== Cesium.SceneMode.SCENE2D) {
        targetViewer.scene.morphTo2D(0.0);
        log("debug", "setComparatorViewerModeByType: imagery pane locked to 2D");
      }
      return;
    }

    // DEM pane → use global 2D/3D toggle so user controls perspective.
    const desiredMode = currentSceneMode === "2d" ? Cesium.SceneMode.SCENE2D : Cesium.SceneMode.SCENE3D;
    const currentMode = targetViewer.scene.mode;
    log("debug",
      "setComparatorViewerModeByType: DEM pane viewer=" +
      (targetViewer === comparatorLeftViewer ? "LEFT" : "RIGHT") +
      " desired=" + (desiredMode === Cesium.SceneMode.SCENE3D ? "3D" : "2D") +
      " current=" + (currentMode === Cesium.SceneMode.SCENE3D ? "3D" : "2D"));
    if (currentMode !== desiredMode) {
      if (desiredMode === Cesium.SceneMode.SCENE2D) {
        targetViewer.scene.morphTo2D(0.0);
      } else {
        targetViewer.scene.morphTo3D(0.0);
      }
    }
  }

  function rectangleWidthRadians(rectangle) {
    if (!rectangle) {
      return NaN;
    }
    let width = Number(rectangle.east) - Number(rectangle.west);
    if (!Number.isFinite(width)) {
      return NaN;
    }
    if (width < 0.0) {
      width += Cesium.Math.TWO_PI;
    }
    return Math.max(1.0e-7, Math.min(Cesium.Math.TWO_PI, width));
  }

  function rectangleHeightRadians(rectangle) {
    if (!rectangle) {
      return NaN;
    }
    const height = Number(rectangle.north) - Number(rectangle.south);
    if (!Number.isFinite(height)) {
      return NaN;
    }
    return Math.max(1.0e-7, Math.min(Cesium.Math.PI, height));
  }

  function buildRectangleFromCenter(center, widthRadians, heightRadians) {
    if (!center || !Number.isFinite(center.longitude) || !Number.isFinite(center.latitude)) {
      return null;
    }
    const halfWidth = Math.max(5.0e-8, Number(widthRadians) * 0.5);
    const halfHeight = Math.max(5.0e-8, Number(heightRadians) * 0.5);
    const south = Cesium.Math.clamp(center.latitude - halfHeight, -Cesium.Math.PI_OVER_TWO + 1.0e-6, Cesium.Math.PI_OVER_TWO - 1.0e-6);
    const north = Cesium.Math.clamp(center.latitude + halfHeight, -Cesium.Math.PI_OVER_TWO + 1.0e-6, Cesium.Math.PI_OVER_TWO - 1.0e-6);
    const west = Cesium.Math.negativePiToPi(center.longitude - halfWidth);
    const east = Cesium.Math.negativePiToPi(center.longitude + halfWidth);
    return new Cesium.Rectangle(west, south, east, north);
  }

  function resolveImagerySyncDestinationRectangle(sourceViewer, sourceRectangle, targetViewer, sourceLayerType) {
    if (!sourceRectangle) {
      return null;
    }
    if (!targetViewer || sourceLayerType !== "dem") {
      return sourceRectangle;
    }
    const targetRectangle = targetViewer.camera && targetViewer.scene
      ? targetViewer.camera.computeViewRectangle(targetViewer.scene.globe.ellipsoid)
      : null;
    if (!targetRectangle) {
      log("debug", "Comparator imagery sync: targetRectangle is null, returning source");
      return sourceRectangle;
    }

    const sourceWidth = rectangleWidthRadians(sourceRectangle);
    const sourceHeight = rectangleHeightRadians(sourceRectangle);
    const targetWidth = rectangleWidthRadians(targetRectangle);
    const targetHeight = rectangleHeightRadians(targetRectangle);
    if (!Number.isFinite(sourceWidth) || !Number.isFinite(sourceHeight) || !Number.isFinite(targetWidth) || !Number.isFinite(targetHeight)) {
      log("debug", `Comparator imagery sync: invalid dimensions src_w=${sourceWidth} src_h=${sourceHeight} tgt_w=${targetWidth} tgt_h=${targetHeight}, returning source`);
      return sourceRectangle;
    }

    const sourceState = getComparatorSyncStateForViewer(sourceViewer);
    const sourceCameraHeight = sourceViewer && sourceViewer.camera && sourceViewer.camera.positionCartographic && Number.isFinite(sourceViewer.camera.positionCartographic.height)
      ? Number(sourceViewer.camera.positionCartographic.height)
      : NaN;
    const previousSourceCameraHeight = sourceState && Number.isFinite(sourceState.lastSourceCameraHeightM)
      ? Number(sourceState.lastSourceCameraHeightM)
      : NaN;
    const rawZoomDelta = Number.isFinite(sourceCameraHeight) && Number.isFinite(previousSourceCameraHeight) && previousSourceCameraHeight > 1.0
      ? sourceCameraHeight / previousSourceCameraHeight
      : 1.0;

    // Use incremental height deltas to avoid abrupt jumps from unstable tilted DEM rectangles.
    const minZoomDelta = 0.96;
    const maxZoomDelta = 1.04;
    let zoomDelta = Cesium.Math.clamp(rawZoomDelta, minZoomDelta, maxZoomDelta);
    if (!Number.isFinite(zoomDelta) || zoomDelta <= 0.0) {
      zoomDelta = 1.0;
    }
    if (rawZoomDelta > 1.30 || rawZoomDelta < 0.70) {
      log("debug", `Comparator imagery sync SPIKE detected rawZoomDelta=${rawZoomDelta.toFixed(6)}; freezing zoomDelta=1.0`);
      zoomDelta = 1.0;
    }

    const absoluteScale = sourceWidth / targetWidth;

    log("debug", `Comparator imagery sync START: sourceWidth=${sourceWidth.toFixed(6)} sourceHeight=${sourceHeight.toFixed(6)} targetWidth=${targetWidth.toFixed(6)} targetHeight=${targetHeight.toFixed(6)} sourceCamH=${Number.isFinite(sourceCameraHeight) ? sourceCameraHeight.toFixed(2) : "n/a"} prevSourceCamH=${Number.isFinite(previousSourceCameraHeight) ? previousSourceCameraHeight.toFixed(2) : "n/a"} rawZoomDelta=${rawZoomDelta.toFixed(6)} zoomDelta=${zoomDelta.toFixed(6)} absRatio=${absoluteScale.toFixed(6)}`);

    const sourceCenterLonLat = getViewerCenterLonLat(sourceViewer);
    const sourceCenter = sourceCenterLonLat
      ? {
          longitude: Cesium.Math.toRadians(Number(sourceCenterLonLat.lon)),
          latitude: Cesium.Math.toRadians(Number(sourceCenterLonLat.lat)),
        }
      : Cesium.Rectangle.center(sourceRectangle);
    const targetCenter = Cesium.Rectangle.center(targetRectangle);
    const rawLonDelta = Cesium.Math.negativePiToPi(Number(sourceCenter.longitude) - Number(targetCenter.longitude));
    const rawLatDelta = Number(sourceCenter.latitude) - Number(targetCenter.latitude);
    const maxLonShift = targetWidth * 0.45;
    const maxLatShift = targetHeight * 0.45;
    const lonDelta = Cesium.Math.clamp(rawLonDelta, -maxLonShift, maxLonShift);
    const latDelta = Cesium.Math.clamp(rawLatDelta, -maxLatShift, maxLatShift);

    const destinationCenter = {
      longitude: Cesium.Math.negativePiToPi(Number(targetCenter.longitude) + lonDelta),
      latitude: Cesium.Math.clamp(Number(targetCenter.latitude) + latDelta, -Cesium.Math.PI_OVER_TWO + 1.0e-6, Cesium.Math.PI_OVER_TWO - 1.0e-6),
    };
    const destinationWidth = targetWidth * zoomDelta;
    const destinationHeight = targetHeight * zoomDelta;
    const resolved = buildRectangleFromCenter(destinationCenter, destinationWidth, destinationHeight);
    if (!resolved) {
      log("debug", "Comparator imagery sync: buildRectangleFromCenter failed; returning source rectangle");
      return sourceRectangle;
    }

    const resolvedWidth = rectangleWidthRadians(resolved);
    log("debug", `Comparator imagery sync RESULT: sourceCenterMode=${sourceCenterLonLat ? "screen-center" : "view-rect"} rawLonDelta=${rawLonDelta.toFixed(6)} rawLatDelta=${rawLatDelta.toFixed(6)} lonDelta=${lonDelta.toFixed(6)} latDelta=${latDelta.toFixed(6)} resolvedWidth=${resolvedWidth.toFixed(6)} targetWidth=${targetWidth.toFixed(6)}`);
    return resolved;
  }

  function syncViewerCamera(sourceViewer, targetViewer) {
    if (comparatorModeEnabled) {
      log("debug", "Comparator camera sync is disabled; syncViewerCamera ignored");
      if (sourceViewer) {
        updateComparatorCenterReadout(sourceViewer);
      }
      if (targetViewer && targetViewer.scene) {
        targetViewer.scene.requestRender();
      }
    }
  }

  function bindComparatorSyncHandlers() {
    const leftContainer = document.getElementById("comparatorLeftViewer");
    const rightContainer = document.getElementById("comparatorRightViewer");
    if (!leftContainer || !rightContainer || !comparatorLeftViewer || !comparatorRightViewer) {
      return;
    }

    comparatorLeftViewer.camera.changed.addEventListener(function () {
      if (comparatorModeEnabled) {
        updateComparatorCenterReadout(comparatorLeftViewer);
      }
    });
    comparatorRightViewer.camera.changed.addEventListener(function () {
      if (comparatorModeEnabled) {
        updateComparatorCenterReadout(comparatorRightViewer);
      }
    });

    function attachCursorBridge(container, sourceViewer) {
      container.addEventListener("wheel", function () {
        if (comparatorModeEnabled) {
          updateComparatorCenterReadout(sourceViewer);
        }
      }, { passive: true });
      container.addEventListener("mousemove", function (event) {
        if (!comparatorModeEnabled || !sourceViewer) {
          return;
        }
        const rect = container.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) {
          return;
        }
        const localX = event.clientX - rect.left;
        const localY = event.clientY - rect.top;
        const sourceScreenPosition = new Cesium.Cartesian2(localX, localY);
        const sourceCartesian = getCartesianFromViewer(sourceViewer, sourceScreenPosition);
        const sourceLonLat = sourceCartesian
          ? cartesianToLonLat(sourceCartesian)
          : getLonLatFromViewer(sourceViewer, sourceScreenPosition);

        let leftScreenPosition = null;
        let rightScreenPosition = null;
        if (sourceViewer === comparatorLeftViewer) {
          leftScreenPosition = sourceScreenPosition;
          rightScreenPosition = sourceCartesian
            ? projectCartesianToViewer(comparatorRightViewer, sourceCartesian)
            : null;
        } else {
          rightScreenPosition = sourceScreenPosition;
          leftScreenPosition = sourceCartesian
            ? projectCartesianToViewer(comparatorLeftViewer, sourceCartesian)
            : null;
        }

        updateComparatorCrosshair(
          sourceLonLat ? sourceLonLat.lon : NaN,
          sourceLonLat ? sourceLonLat.lat : NaN,
          leftScreenPosition,
          rightScreenPosition,
        );
      });
    }

    attachCursorBridge(leftContainer, comparatorLeftViewer);
    attachCursorBridge(rightContainer, comparatorRightViewer);
  }

  function rectangleFromBounds(bounds) {
    if (!bounds) {
      return undefined;
    }
    return Cesium.Rectangle.fromDegrees(bounds.west, bounds.south, bounds.east, bounds.north);
  }

  function getComparatorPaneViewer(paneKey) {
    if (paneKey === "right") {
      return comparatorRightViewer;
    }
    return comparatorLeftViewer;
  }

  function getComparatorPaneLayerType(paneKey) {
    if (paneKey === "right") {
      return comparatorRightLayerType;
    }
    return comparatorLeftLayerType;
  }

  function getComparatorPaneVisual(paneKey) {
    if (paneKey === "right") {
      return comparatorPaneVisualState.right;
    }
    return comparatorPaneVisualState.left;
  }

  function setComparatorPaneSelectionStyles(selectedPane) {
    const leftPane = document.getElementById("comparatorPaneLeft");
    const rightPane = document.getElementById("comparatorPaneRight");
    if (leftPane) {
      leftPane.classList.toggle("selected", selectedPane === "left");
    }
    if (rightPane) {
      rightPane.classList.toggle("selected", selectedPane === "right");
    }
  }

  function buildComparatorPaneSnapshot(paneKey) {
    const paneState = getComparatorPaneVisual(paneKey);
    if (!paneState) {
      return null;
    }
    const layerType = getComparatorPaneLayerType(paneKey);
    return {
      pane: paneKey,
      layer_type: layerType || "none",
      imagery: {
        brightness: Number(paneState.imagery.brightness) || 1.0,
        contrast: Number(paneState.imagery.contrast) || 1.0,
      },
      dem: {
        exaggeration: Number(paneState.dem.exaggeration) || 1.0,
        hillshade_alpha: Number(paneState.dem.hillshadeAlpha) || 0.0,
        color_mode: String(paneState.dem.colorMode || "gray"),
      },
    };
  }

  function notifyComparatorPaneState(paneKey) {
    if (!bridge || !bridge.on_comparator_pane_state) {
      return;
    }
    const snapshot = buildComparatorPaneSnapshot(paneKey);
    if (!snapshot) {
      return;
    }
    bridge.on_comparator_pane_state(JSON.stringify(snapshot));
  }

  function setSelectedComparatorPane(paneKey, notifyPanel) {
    const normalized = paneKey === "right" ? "right" : "left";
    comparatorSelectedPane = normalized;
    setComparatorPaneSelectionStyles(normalized);
    if (notifyPanel !== false) {
      notifyComparatorPaneState(normalized);
    }
  }

  function bindComparatorPaneSelectionHandlers() {
    const leftPane = document.getElementById("comparatorPaneLeft");
    const rightPane = document.getElementById("comparatorPaneRight");
    if (leftPane && !leftPane.dataset.selectionBound) {
      leftPane.dataset.selectionBound = "1";
      leftPane.addEventListener("pointerdown", function () {
        setSelectedComparatorPane("left", true);
      });
    }
    if (rightPane && !rightPane.dataset.selectionBound) {
      rightPane.dataset.selectionBound = "1";
      rightPane.addEventListener("pointerdown", function () {
        setSelectedComparatorPane("right", true);
      });
    }
  }

  function buildComparatorDemDrapeUrl(definition, demState) {
    if (definition && typeof definition.xyzUrl === "string" && definition.xyzUrl) {
      const baseQuery = definition.query && typeof definition.query === "object" ? { ...definition.query } : {};
      baseQuery.resampling = "nearest";
      baseQuery.colormap_name = String(demState.colorMode || baseQuery.colormap_name || "gray");
      return buildUrlWithQuery(definition.xyzUrl, baseQuery);
    }
    return String((definition && definition.drapeUrl) || "");
  }

  function buildComparatorDemHillshadeUrl(definition, demState) {
    if (definition && typeof definition.xyzUrl === "string" && definition.xyzUrl) {
      const sourceQuery = definition.query && typeof definition.query === "object" ? definition.query : {};
      const query = {
        algorithm: "hillshade",
        azimuth: DEM_HILLSHADE_AZIMUTH,
        angle_altitude: DEM_HILLSHADE_ALTITUDE,
        z_exaggeration: Math.max(0.1, Number(demState.exaggeration) || 1.0),
        buffer: 4,
      };
      if (Object.prototype.hasOwnProperty.call(sourceQuery, "nodata")) {
        query.nodata = sourceQuery.nodata;
      }
      return buildUrlWithQuery(definition.xyzUrl, query);
    }
    return String((definition && definition.hillshadeUrl) || "");
  }

  function logComparatorLayerStack(targetViewer, paneKey, context) {
    if (!targetViewer || !targetViewer.imageryLayers) {
      return;
    }
    const rows = [];
    for (let idx = 0; idx < targetViewer.imageryLayers.length; idx += 1) {
      const layer = targetViewer.imageryLayers.get(idx);
      const isPrimary = layer === targetViewer.__comparatorPrimaryLayer;
      const isHillshade = layer === targetViewer.__comparatorHillshadeLayer;
      const role = isPrimary ? "primary" : (isHillshade ? "hillshade" : "background");
      const alpha = Number(layer && layer.alpha);
      const show = layer && layer.show === false ? "hidden" : "shown";
      rows.push(`#${idx}:${role}:${show}:alpha=${Number.isFinite(alpha) ? alpha.toFixed(2) : "n/a"}`);
    }
    log("debug", `Comparator layer stack pane=${paneKey} context=${context} :: ${rows.join(" | ")}`);
  }

  function enforceComparatorDemLayerOrder(paneKey, targetViewer) {
    if (!targetViewer || getComparatorPaneLayerType(paneKey) !== "dem") {
      return;
    }
    const primaryLayer = targetViewer.__comparatorPrimaryLayer || null;
    const hillshadeLayer = targetViewer.__comparatorHillshadeLayer || null;

    if (primaryLayer && targetViewer.imageryLayers.indexOf(primaryLayer) >= 0) {
      primaryLayer.show = true;
      primaryLayer.alpha = 1.0;
      targetViewer.imageryLayers.raiseToTop(primaryLayer);
    }
    if (hillshadeLayer && targetViewer.imageryLayers.indexOf(hillshadeLayer) >= 0) {
      hillshadeLayer.show = true;
      targetViewer.imageryLayers.raiseToTop(hillshadeLayer);
    }
    logComparatorLayerStack(targetViewer, paneKey, "enforce-dem-z-order");
  }

  function applyComparatorPaneVisualState(paneKey) {
    const targetViewer = getComparatorPaneViewer(paneKey);
    const paneState = getComparatorPaneVisual(paneKey);
    const layerType = getComparatorPaneLayerType(paneKey);
    if (!targetViewer || !paneState || !layerType) {
      return;
    }
    if (layerType === "imagery") {
      const imageryLayer = targetViewer.__comparatorPrimaryLayer || null;
      if (imageryLayer) {
        imageryLayer.brightness = Math.max(0.2, Number(paneState.imagery.brightness) || 1.0);
        imageryLayer.contrast = Math.max(0.1, Number(paneState.imagery.contrast) || 1.0);
      }
    } else if (layerType === "dem") {
      targetViewer.scene.verticalExaggeration = Math.max(0.1, Number(paneState.dem.exaggeration) || 1.0);
      const primaryLayer = targetViewer.__comparatorPrimaryLayer || null;
      if (primaryLayer) {
        primaryLayer.alpha = 1.0;
        primaryLayer.show = true;
      }
      const hsLayer = targetViewer.__comparatorHillshadeLayer || null;
      if (hsLayer) {
        hsLayer.alpha = Math.max(0.0, Math.min(0.35, (Number(paneState.dem.hillshadeAlpha) || 0.0) * 0.45));
      }
      enforceComparatorDemLayerOrder(paneKey, targetViewer);
    }
    targetViewer.scene.requestRender();
  }

  function applyLayerDefinitionToViewer(targetViewer, definition, paneKey) {
    if (!targetViewer || !definition) {
      return;
    }
    const paneVisual = getComparatorPaneVisual(paneKey);
    const rectangle = rectangleFromBounds(definition.bounds || null);
    targetViewer.__comparatorLayerKey = String(definition.key || "");
    targetViewer.__comparatorPrimaryLayer = null;
    targetViewer.__comparatorHillshadeLayer = null;

    const fallbackBackgroundProvider = createNaturalEarthProvider();
    const fallbackBackgroundLayer = targetViewer.imageryLayers.addImageryProvider(fallbackBackgroundProvider);
    fallbackBackgroundLayer.alpha = 1.0;

    const localBackgroundProvider = new Cesium.UrlTemplateImageryProvider({
      url: `${LOCAL_SATELLITE_TILE_ROOT}/{zc}/{x}/{y}.png`,
      customTags: {
        zc: function (_p, _x, _y, level) {
          return String(Math.min(level, LOCAL_SATELLITE_DEFAULT_MAX_LEVEL));
        },
      },
      tilingScheme: new Cesium.WebMercatorTilingScheme(),
      minimumLevel: 0,
      maximumLevel: 22,
      rectangle: Cesium.Rectangle.fromDegrees(25.0, -12.0, 180.0, 82.0),
      credit: new Cesium.Credit("© OpenStreetMap contributors", false),
      enablePickFeatures: false,
    });
    // Suppress tile error logging for comparator background — 404s outside Asia are expected
    localBackgroundProvider.errorEvent.addEventListener(function (error) {
      error.retry = false;  // don't retry, just skip silently
    });
    const localBackgroundLayer = targetViewer.imageryLayers.addImageryProvider(localBackgroundProvider);
    localBackgroundLayer.alpha = 1.0;

    if (definition.type === "dem") {
      const demState = paneVisual ? paneVisual.dem : comparatorPaneVisualState.left.dem;
      const drapeUrl = buildComparatorDemDrapeUrl(definition, demState);
      const hillshadeUrl = buildComparatorDemHillshadeUrl(definition, demState);
      const demProvider = new Cesium.UrlTemplateImageryProvider({
        url: drapeUrl,
        maximumLevel: definition.maxLevel,
        minimumLevel: definition.minLevel,
        tilingScheme: new Cesium.WebMercatorTilingScheme(),
        enablePickFeatures: false,
        rectangle: rectangle,
      });
      const demLayer = targetViewer.imageryLayers.addImageryProvider(demProvider);
      demLayer.alpha = 1.0;
      targetViewer.__comparatorPrimaryLayer = demLayer;
      if (hillshadeUrl) {
        const hsProvider = new Cesium.UrlTemplateImageryProvider({
          url: hillshadeUrl,
          maximumLevel: definition.maxLevel,
          minimumLevel: definition.minLevel,
          tilingScheme: new Cesium.WebMercatorTilingScheme(),
          enablePickFeatures: false,
          rectangle: rectangle,
        });
        const hsLayer = targetViewer.imageryLayers.addImageryProvider(hsProvider);
        hsLayer.alpha = Math.max(0.0, Math.min(1.0, Number(demState.hillshadeAlpha) || 0.0));
        targetViewer.__comparatorHillshadeLayer = hsLayer;
      }
      enforceComparatorDemLayerOrder(paneKey, targetViewer);
      return;
    }

    const provider = new Cesium.UrlTemplateImageryProvider({
      url: definition.url,
      maximumLevel: definition.maxLevel,
      minimumLevel: definition.minLevel,
      tilingScheme: new Cesium.WebMercatorTilingScheme(),
      enablePickFeatures: false,
      rectangle: rectangle,
    });
    const layer = targetViewer.imageryLayers.addImageryProvider(provider);
    layer.alpha = 1.0;
    if (paneVisual) {
      layer.brightness = Math.max(0.2, Number(paneVisual.imagery.brightness) || 1.0);
      layer.contrast = Math.max(0.1, Number(paneVisual.imagery.contrast) || 1.0);
    }
    targetViewer.__comparatorPrimaryLayer = layer;
  }

  function resetComparatorViewerLayers(targetViewer) {
    if (!targetViewer) {
      return;
    }
    for (let idx = targetViewer.imageryLayers.length - 1; idx >= 0; idx -= 1) {
      const layer = targetViewer.imageryLayers.get(idx);
      targetViewer.imageryLayers.remove(layer, false);
    }
  }

  function resolveComparatorLayerKeys() {
    if (swipeComparatorLeftLayerKey && swipeComparatorRightLayerKey) {
      return [swipeComparatorLeftLayerKey, swipeComparatorRightLayerKey];
    }
    const visibleKeys = [];
    for (const [key, visible] of layerVisibilityState.entries()) {
      if (!visible) {
        continue;
      }
      if (!layerDefinitions.has(key)) {
        continue;
      }
      visibleKeys.push(key);
    }
    if (visibleKeys.length < 2) {
      return [null, null];
    }
    return [visibleKeys[0], visibleKeys[1]];
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: Comparator Mode  →  future: modules/comparator.js
  // Functions: ensureComparatorViewers, refreshComparatorLayers,
  //   setComparatorWindowsVisible, updateComparatorPolygons,
  //   scheduleComparatorDemRefresh, comparator camera sync helpers,
  //   swipe comparator setup and management
  // ═══════════════════════════════════════════════════════════════════════════

  function refreshComparatorLayers(options) {
    if (!comparatorModeEnabled || !comparatorLeftViewer || !comparatorRightViewer) {
      return;
    }
    const preserveView = Boolean(options && options.preserveView);
    const [leftKey, rightKey] = resolveComparatorLayerKeys();
    if (!leftKey || !rightKey) {
      return;
    }
    const leftDef = layerDefinitions.get(leftKey);
    const rightDef = layerDefinitions.get(rightKey);
    if (!leftDef || !rightDef) {
      return;
    }

    resetComparatorViewerLayers(comparatorLeftViewer);
    resetComparatorViewerLayers(comparatorRightViewer);
    applyLayerDefinitionToViewer(comparatorLeftViewer, leftDef, "left");
    applyLayerDefinitionToViewer(comparatorRightViewer, rightDef, "right");
    comparatorLeftLayerType = String(leftDef.type || "imagery");
    comparatorRightLayerType = String(rightDef.type || "imagery");
    setComparatorViewerModeByType(comparatorLeftViewer, comparatorLeftLayerType);
    setComparatorViewerModeByType(comparatorRightViewer, comparatorRightLayerType);
    syncComparatorTerrainProviders();
    applyComparatorPaneVisualState("left");
    applyComparatorPaneVisualState("right");

    const leftTitle = document.getElementById("comparatorTitleLeft");
    const rightTitle = document.getElementById("comparatorTitleRight");
    if (leftTitle) {
      leftTitle.textContent = leftDef.label || "Left layer";
    }
    if (rightTitle) {
      rightTitle.textContent = rightDef.label || "Right layer";
    }

    if (!preserveView && viewer && comparatorLeftViewer) {
      const leftRect = rectangleFromBounds(leftDef.bounds || null);
      const rightRect = rectangleFromBounds(rightDef.bounds || null);
      if (leftRect) {
        focusComparatorViewerToRectangle(comparatorLeftViewer, comparatorLeftLayerType, leftRect);
      }
      if (rightRect) {
        focusComparatorViewerToRectangle(comparatorRightViewer, comparatorRightLayerType, rightRect);
      }
    }
    updateComparatorCenterReadout(getComparatorDemViewer() || comparatorLeftViewer);
    setSelectedComparatorPane(comparatorSelectedPane, true);

    enforceComparatorDemLayerOrder("left", comparatorLeftViewer);
    enforceComparatorDemLayerOrder("right", comparatorRightViewer);
    const leftRectAfterRefresh = comparatorLeftViewer.camera.computeViewRectangle(comparatorLeftViewer.scene.globe.ellipsoid);
    const rightRectAfterRefresh = comparatorRightViewer.camera.computeViewRectangle(comparatorRightViewer.scene.globe.ellipsoid);
    if (leftRectAfterRefresh) {
      recordComparatorSourceRectangle(comparatorLeftViewer, leftRectAfterRefresh, "refreshComparatorLayers-left");
    }
    if (rightRectAfterRefresh) {
      recordComparatorSourceRectangle(comparatorRightViewer, rightRectAfterRefresh, "refreshComparatorLayers-right");
    }
    requestSceneRender();
  }

  function scheduleComparatorDemRefresh(paneKey) {
    if (comparatorDemRefreshTimer !== null) {
      window.clearTimeout(comparatorDemRefreshTimer);
      comparatorDemRefreshTimer = null;
    }
    const targetPane = paneKey === "right" ? "right" : "left";
    comparatorDemRefreshTimer = window.setTimeout(function () {
      comparatorDemRefreshTimer = null;
      if (!comparatorModeEnabled) {
        return;
      }
      const paneLayerType = getComparatorPaneLayerType(targetPane);
      if (paneLayerType !== "dem") {
        return;
      }

      const targetViewer = getComparatorPaneViewer(targetPane);
      const paneState = getComparatorPaneVisual(targetPane);
      const layerKey = targetPane === "right" ? swipeComparatorRightLayerKey : swipeComparatorLeftLayerKey;
      const definition = layerKey ? layerDefinitions.get(layerKey) : null;
      if (!targetViewer || !paneState || !definition || String(definition.type || "") !== "dem") {
        return;
      }
      syncComparatorTerrainProviders();

      const rectangle = rectangleFromBounds(definition.bounds || null);
      const drapeUrl = buildComparatorDemDrapeUrl(definition, paneState.dem);
      const hillshadeUrl = buildComparatorDemHillshadeUrl(definition, paneState.dem);
      const oldPrimary = targetViewer.__comparatorPrimaryLayer || null;
      const oldHillshade = targetViewer.__comparatorHillshadeLayer || null;

      let insertIndex = targetViewer.imageryLayers.length;
      if (oldPrimary) {
        const primaryIndex = targetViewer.imageryLayers.indexOf(oldPrimary);
        if (primaryIndex >= 0) {
          insertIndex = primaryIndex;
        }
      }

      const demProvider = new Cesium.UrlTemplateImageryProvider({
        url: drapeUrl,
        maximumLevel: definition.maxLevel,
        minimumLevel: definition.minLevel,
        tilingScheme: new Cesium.WebMercatorTilingScheme(),
        enablePickFeatures: false,
        rectangle: rectangle,
      });
      const newPrimary = targetViewer.imageryLayers.addImageryProvider(demProvider, insertIndex);
      newPrimary.alpha = 1.0;
      newPrimary.show = true;

      let newHillshade = null;
      if (hillshadeUrl) {
        const hillshadeProvider = new Cesium.UrlTemplateImageryProvider({
          url: hillshadeUrl,
          maximumLevel: definition.maxLevel,
          minimumLevel: definition.minLevel,
          tilingScheme: new Cesium.WebMercatorTilingScheme(),
          enablePickFeatures: false,
          rectangle: rectangle,
        });
        newHillshade = targetViewer.imageryLayers.addImageryProvider(hillshadeProvider, insertIndex + 1);
        newHillshade.show = true;
      }

      const refreshVersion = (Number(comparatorDemStyleRefreshVersion[targetPane]) || 0) + 1;
      comparatorDemStyleRefreshVersion[targetPane] = refreshVersion;
      window.setTimeout(function () {
        const latestVersion = Number(comparatorDemStyleRefreshVersion[targetPane]) || 0;
        const staleRefresh = latestVersion !== refreshVersion;
        const comparatorInactive = !comparatorModeEnabled || getComparatorPaneLayerType(targetPane) !== "dem";
        if (staleRefresh || comparatorInactive) {
          if (newHillshade && targetViewer.imageryLayers.indexOf(newHillshade) >= 0) {
            targetViewer.imageryLayers.remove(newHillshade, false);
          }
          if (targetViewer.imageryLayers.indexOf(newPrimary) >= 0) {
            targetViewer.imageryLayers.remove(newPrimary, false);
          }
          return;
        }

        targetViewer.__comparatorPrimaryLayer = newPrimary;
        targetViewer.__comparatorHillshadeLayer = newHillshade;
        applyComparatorPaneVisualState(targetPane);

        if (oldHillshade && targetViewer.imageryLayers.indexOf(oldHillshade) >= 0) {
          targetViewer.imageryLayers.remove(oldHillshade, false);
        }
        if (oldPrimary && targetViewer.imageryLayers.indexOf(oldPrimary) >= 0) {
          targetViewer.imageryLayers.remove(oldPrimary, false);
        }
        enforceComparatorDemLayerOrder(targetPane, targetViewer);
        logComparatorLayerStack(targetViewer, targetPane, "post-color-refresh");
        targetViewer.scene.requestRender();
      }, 80);
    }, COMPARATOR_DEM_REFRESH_DEBOUNCE_MS);
  }

  function setSwipeComparatorLayerKeys(leftLayerKey, rightLayerKey, leftLabel, rightLabel) {
    swipeComparatorLeftLayerKey = String(leftLayerKey || "") || null;
    swipeComparatorRightLayerKey = String(rightLayerKey || "") || null;
    if (swipeComparatorLeftLayerKey && !layerVisibilityState.has(swipeComparatorLeftLayerKey)) {
      layerVisibilityState.set(swipeComparatorLeftLayerKey, true);
    }
    if (swipeComparatorRightLayerKey && !layerVisibilityState.has(swipeComparatorRightLayerKey)) {
      layerVisibilityState.set(swipeComparatorRightLayerKey, true);
    }

    const leftTitle = document.getElementById("comparatorTitleLeft");
    const rightTitle = document.getElementById("comparatorTitleRight");
    if (leftTitle && leftLabel) {
      leftTitle.textContent = String(leftLabel);
    }
    if (rightTitle && rightLabel) {
      rightTitle.textContent = String(rightLabel);
    }
    refreshComparatorLayers();
  }

  function ensureComparatorViewers() {
    if (comparatorLeftViewer && comparatorRightViewer) {
      bindComparatorPaneSelectionHandlers();
      setComparatorPaneSelectionStyles(comparatorSelectedPane);
      return;
    }
    comparatorLeftViewer = new Cesium.Viewer("comparatorLeftViewer", {
      imageryProvider: createNaturalEarthProvider(),
      baseLayerPicker: false,
      geocoder: false,
      navigationHelpButton: false,
      sceneModePicker: false,
      homeButton: false,
      fullscreenButton: false,
      infoBox: false,
      selectionIndicator: false,
      scene3DOnly: false,
      requestRenderMode: true,
      maximumRenderTimeChange: Infinity,
      timeline: false,
      animation: false,
      terrainProvider: new Cesium.EllipsoidTerrainProvider(),
    });
    comparatorRightViewer = new Cesium.Viewer("comparatorRightViewer", {
      imageryProvider: createNaturalEarthProvider(),
      baseLayerPicker: false,
      geocoder: false,
      navigationHelpButton: false,
      sceneModePicker: false,
      homeButton: false,
      fullscreenButton: false,
      infoBox: false,
      selectionIndicator: false,
      scene3DOnly: false,
      requestRenderMode: true,
      maximumRenderTimeChange: Infinity,
      timeline: false,
      animation: false,
      terrainProvider: new Cesium.EllipsoidTerrainProvider(),
    });
    comparatorLeftViewer.scene.globe.baseColor = Cesium.Color.BLACK;
    comparatorRightViewer.scene.globe.baseColor = Cesium.Color.BLACK;
    comparatorLeftViewer.scene.backgroundColor = Cesium.Color.BLACK;
    comparatorRightViewer.scene.backgroundColor = Cesium.Color.BLACK;
    comparatorLeftViewer.scene.fxaa = false;
    comparatorRightViewer.scene.fxaa = false;
    comparatorLeftViewer.scene.mode = Cesium.SceneMode.SCENE3D;
    comparatorRightViewer.scene.mode = Cesium.SceneMode.SCENE3D;
    comparatorLeftViewer.scene.verticalExaggeration = demVisual.exaggeration;
    comparatorRightViewer.scene.verticalExaggeration = demVisual.exaggeration;
    comparatorLeftViewer.camera.percentageChanged = 0.001;
    comparatorRightViewer.camera.percentageChanged = 0.001;
    bindComparatorSyncHandlers();
    bindComparatorPaneSelectionHandlers();
    setComparatorPaneSelectionStyles(comparatorSelectedPane);
  }

  function getSwipeCandidateLayers() {
    const visibleLayers = [];
    for (const layer of managedImageryLayers.values()) {
      if (layer && layer.show) {
        visibleLayers.push(layer);
      }
    }
    if (activeDemDrapeLayer && activeDemDrapeLayer.show) {
      visibleLayers.push(activeDemDrapeLayer);
    }
    if (activeDemHillshadeLayer && activeDemHillshadeLayer.show && activeDemHillshadeLayer.alpha > 0.01) {
      visibleLayers.push(activeDemHillshadeLayer);
    }
    return visibleLayers;
  }

  function applySwipeComparatorSplit() {
    if (!viewer) {
      return;
    }
    if (comparatorModeEnabled) {
      return;
    }
    const candidates = getSwipeCandidateLayers();
    const resetLayers = Array.from(managedImageryLayers.values());
    if (activeDemDrapeLayer) {
      resetLayers.push(activeDemDrapeLayer);
    }
    if (activeDemHillshadeLayer) {
      resetLayers.push(activeDemHillshadeLayer);
    }
    for (const layer of resetLayers) {
      if (layer) {
        layer.splitDirection = Cesium.ImagerySplitDirection.NONE;
      }
    }

    if (!swipeComparatorEnabled || candidates.length === 0) {
      viewer.scene.imagerySplitPosition = 0.5;
      requestSceneRender();
      return;
    }

    if (candidates.length === 1) {
      candidates[0].splitDirection = Cesium.ImagerySplitDirection.LEFT;
    } else {
      const leftLayer = candidates[candidates.length - 1];
      const rightLayer = candidates[candidates.length - 2];
      leftLayer.splitDirection = Cesium.ImagerySplitDirection.LEFT;
      rightLayer.splitDirection = Cesium.ImagerySplitDirection.RIGHT;
    }
    viewer.scene.imagerySplitPosition = swipeComparatorPosition;
    requestSceneRender();
  }

  function updateSwipeDividerPosition() {
    if (!swipeDividerElement || !viewer || !viewer.canvas) {
      return;
    }
    const rect = viewer.canvas.getBoundingClientRect();
    swipeDividerElement.style.left = `${Math.round(rect.left + rect.width * swipeComparatorPosition)}px`;
    swipeDividerElement.style.top = `${Math.round(rect.top)}px`;
    swipeDividerElement.style.height = `${Math.round(rect.height)}px`;
  }

  function setSwipePosition(fraction) {
    const next = Number(fraction);
    if (!Number.isFinite(next)) {
      return;
    }
    swipeComparatorPosition = Math.min(0.98, Math.max(0.02, next));
    if (viewer) {
      viewer.scene.imagerySplitPosition = swipeComparatorPosition;
    }
    updateSwipeDividerPosition();
    requestSceneRender();
  }

  function ensureSwipeDivider() {
    if (swipeDividerElement || !document.body) {
      return;
    }
    const divider = document.createElement("div");
    divider.id = "swipeComparatorDivider";
    divider.style.position = "fixed";
    divider.style.width = "3px";
    divider.style.background = "#ffde59";
    divider.style.boxShadow = "0 0 0 1px rgba(0,0,0,0.35), 0 0 14px rgba(255,222,89,0.45)";
    divider.style.cursor = "ew-resize";
    divider.style.zIndex = "100001";
    divider.style.display = "none";
    divider.style.pointerEvents = "auto";
    document.body.appendChild(divider);
    swipeDividerElement = divider;

    let dragging = false;
    divider.addEventListener("mousedown", function (event) {
      event.preventDefault();
      dragging = true;
    });
    window.addEventListener("mousemove", function (event) {
      if (!dragging || !viewer || !viewer.canvas) {
        return;
      }
      const rect = viewer.canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const fraction = x / Math.max(1.0, rect.width);
      setSwipePosition(fraction);
    });
    window.addEventListener("mouseup", function () {
      dragging = false;
    });
    window.addEventListener("resize", function () {
      if (swipeComparatorEnabled) {
        updateSwipeDividerPosition();
      }
    });
  }

  function setSwipeComparatorEnabled(enabled) {
    const next = Boolean(enabled);
    swipeComparatorEnabled = next;
    comparatorModeEnabled = next;
    resetComparatorCameraSyncState(next ? "comparator-enabled" : "comparator-disabled");
    if (!next) {
      cancelComparatorCameraSyncSchedule();
    }
    if (comparatorDemRefreshTimer !== null) {
      window.clearTimeout(comparatorDemRefreshTimer);
      comparatorDemRefreshTimer = null;
    }
    const candidateCount = getSwipeCandidateLayers().length;
    ensureSwipeDivider();
    if (swipeDividerElement) {
      swipeDividerElement.style.display = "none";
    }
    if (next) {
      for (const paneKey of ["left", "right"]) {
        const paneState = getComparatorPaneVisual(paneKey);
        if (!paneState) {
          continue;
        }
        paneState.imagery.brightness = imageryVisual.brightness;
        paneState.imagery.contrast = imageryVisual.contrast;
        paneState.dem.exaggeration = demVisual.exaggeration;
        paneState.dem.hillshadeAlpha = demVisual.hillshadeAlpha;
        paneState.dem.colorMode = String(paneState.dem.colorMode || "gray");
      }
      ensureComparatorViewers();
      setSelectedComparatorPane(comparatorSelectedPane, false);
      setComparatorWindowsVisible(true);
      if (comparatorLeftViewer && comparatorRightViewer) {
        comparatorLeftViewer.resize();
        comparatorRightViewer.resize();
      }
      refreshComparatorLayers();
      const bounds = activeTileBounds || lastLoadedBounds;
      if (bounds && comparatorLeftViewer && comparatorRightViewer) {
        const rect = Cesium.Rectangle.fromDegrees(bounds.west, bounds.south, bounds.east, bounds.north);
        focusComparatorViewerToRectangle(comparatorLeftViewer, comparatorLeftLayerType, rect);
        focusComparatorViewerToRectangle(comparatorRightViewer, comparatorRightLayerType, rect);
      }
      updateComparatorCenterReadout(getComparatorDemViewer() || comparatorLeftViewer);
      notifyComparatorPaneState(comparatorSelectedPane);
      // Sync ROI polygons into comparator viewers
      updateComparatorPolygons(polygonVisibilityEnabled);
      if (candidateCount < 2) {
        setStatus("Comparator enabled. Select two visible layers to render left and right panes.");
      } else {
        setStatus("Comparator enabled. Panes are independently controllable.");
      }
    } else {
      setComparatorWindowsVisible(false);
      setStatus("Comparator disabled.");
    }
    applySwipeComparatorSplit();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: Search Cursor & Cursor Utilities  →  future: modules/search.js
  // Functions: setSearchCursorEnabled, updateSearchCursorOverlay,
  //   setMeasurementCursorEnabled, applyCursorStyle
  // ═══════════════════════════════════════════════════════════════════════════

  function applyCursorStyle(element, cursorValue) {
    if (!element || !element.style) {
      return;
    }
    if (cursorValue) {
      element.style.setProperty("cursor", cursorValue, "important");
      return;
    }
    element.style.removeProperty("cursor");
  }

  function ensureSearchCursorOverlay() {
    if (searchCursorOverlay || !document.body) {
      return;
    }
    const overlay = document.createElement("div");
    overlay.id = "searchCursorOverlay";
    overlay.setAttribute("aria-hidden", "true");
    overlay.style.position = "fixed";
    overlay.style.left = "0px";
    overlay.style.top = "0px";
    overlay.style.width = "20px";
    overlay.style.height = "20px";
    overlay.style.pointerEvents = "none";
    overlay.style.zIndex = "100000";
    overlay.style.display = "none";
    overlay.style.backgroundRepeat = "no-repeat";
    overlay.style.backgroundSize = "20px 20px";
    overlay.style.backgroundImage = `url("${SEARCH_PENCIL_CURSOR_IMAGE}")`;
    overlay.style.transform = "translate(-2px, -18px)";
    document.body.appendChild(overlay);
    searchCursorOverlay = overlay;
  }

  function updateSearchCursorOverlay(screenPosition) {
    if (!viewer || !viewer.canvas || !searchCursorOverlay || !screenPosition) {
      return;
    }
    const x = Number(screenPosition.x);
    const y = Number(screenPosition.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      return;
    }
    const rect = viewer.canvas.getBoundingClientRect();
    searchCursorOverlay.style.left = `${rect.left + x}px`;
    searchCursorOverlay.style.top = `${rect.top + y}px`;
  }

  function setSearchCursorOverlayVisible(visible) {
    if (!searchCursorOverlay) {
      return;
    }
    if (!visible || !lastSearchCursorScreenPosition) {
      searchCursorOverlay.style.display = "none";
      return;
    }
    searchCursorOverlay.style.display = "block";
    updateSearchCursorOverlay(lastSearchCursorScreenPosition);
  }

  function setSearchCursorEnabled(enabled) {
    if (!viewer || !viewer.canvas) {
      return;
    }
    ensureSearchCursorOverlay();
    const nextCursor = enabled ? (searchCursorOverlay ? "none" : SEARCH_PENCIL_CURSOR) : "";
    applyCursorStyle(viewer.canvas, nextCursor);
    const mapElement = document.getElementById("cesiumContainer");
    if (mapElement) {
      applyCursorStyle(mapElement, nextCursor);
      mapElement.classList.toggle("search-draw-cursor-active", Boolean(enabled));
    }
    if (viewer.container) {
      applyCursorStyle(viewer.container, nextCursor);
    }
    setSearchCursorOverlayVisible(Boolean(enabled));
  }

  // ── Measurement cursor — delegated to Qt/Python for smooth native rendering ──
  // Instead of a floating HTML div, we call bridge.on_measure_cursor(bool) which
  // lets Python set a QPainter-drawn QCursor directly on the QWebEngineView.
  // The <style> tag still hides the native browser cursor while active.
  let _measureCursorStyleEl = null;
  // Stubs kept so existing call sites (mouseenter/mouseleave) don't error
  let _measureCursorOverlay = null;

  function ensureMeasureCursorOverlay() { /* no-op — cursor handled by Qt */ }
  function updateMeasureCursorOverlay() { /* no-op */ }
  function setMeasureCursorOverlayVisible() { /* no-op */ }

  function setMeasurementCursorEnabled(enabled) {
    log("info", "[CURSOR_DEBUG] setMeasurementCursorEnabled called enabled=" + String(enabled) + " bridge=" + (bridge ? "ok" : "null") + " on_measure_cursor=" + (bridge && bridge.on_measure_cursor ? "ok" : "missing"));
    // Tell Python to set/unset the native Qt crosshair cursor
    if (bridge && bridge.on_measure_cursor) {
      log("info", "[CURSOR_DEBUG] calling bridge.on_measure_cursor(" + String(Boolean(enabled)) + ")");
      bridge.on_measure_cursor(Boolean(enabled));
    } else {
      log("warn", "[CURSOR_DEBUG] bridge.on_measure_cursor not available — falling back to CSS crosshair");
    }
    // No CSS cursor manipulation — Qt handles the cursor natively via setCursor()
    if (!_measureCursorStyleEl) {
      _measureCursorStyleEl = document.createElement("style");
      _measureCursorStyleEl.id = "measureCursorOverride";
      document.head.appendChild(_measureCursorStyleEl);
    }
    _measureCursorStyleEl.textContent = "";
  }

  // Legacy alias — kept for backward compatibility with existing call sites
  function _enforceMeasureCursor(active) {
    setMeasurementCursorEnabled(active);
  }
  let _measureCursorObserver = null;  // no longer used, kept to avoid reference errors
  let _measureCursorApplying = false; // no longer used, kept to avoid reference errors

  function sceneDebug(message) {
    log("info", "[SCENE_DEBUG] " + message);
  }

  function looksLikeMissingLocalAssetError(error) {
    const errorTextParts = [
      String(error || ""),
      error && error.message ? String(error.message) : "",
      error && error.stack ? String(error.stack) : "",
    ];
    const text = errorTextParts.join("\n").toLowerCase();
    return (
      text.includes("failed to fetch") ||
      text.includes("404") ||
      text.includes("not found") ||
      text.includes("err_file_not_found") ||
      text.includes("an error occurred while accessing") ||
      (text.includes("basemap/terrain") && text.includes("layer.json")) ||
      (text.includes("file://") && text.includes("layer.json"))
    );
  }

  function createSolidPolarCapDataUrl() {
    const canvas = document.createElement("canvas");
    canvas.width = 2;
    canvas.height = 2;
    const context = canvas.getContext("2d");
    if (context) {
      context.fillStyle = "#1f4f7a";
      context.fillRect(0, 0, canvas.width, canvas.height);
    }
    return canvas.toDataURL("image/png");
  }

  function detectSceneMode() {
    if (!viewer || !viewer.scene) {
      return currentSceneMode;
    }
    if (viewer.scene.mode === Cesium.SceneMode.MORPHING) {
      return "morphing";
    }
    return viewer.scene.mode === Cesium.SceneMode.SCENE2D ? "2d" : "3d";
  }

  function normalizeLongitudeDegrees(value) {
    let normalized = ((Number(value) + 540) % 360) - 180;
    if (normalized === -180) {
      normalized = 180;
    }
    return normalized;
  }

  function formatLongitudeLabel(value) {
    if (!Number.isFinite(value)) {
      return "n/a";
    }
    const lon = normalizeLongitudeDegrees(value);
    const suffix = lon >= 0 ? "E" : "W";
    const absValue = Math.abs(lon);
    const decimals = absValue >= 100 ? 0 : absValue >= 10 ? 1 : 2;
    return `${absValue.toFixed(decimals)}°${suffix}`;
  }

  function formatLatitudeLabel(value) {
    if (!Number.isFinite(value)) {
      return "n/a";
    }
    const lat = Math.max(-90, Math.min(90, Number(value)));
    const suffix = lat >= 0 ? "N" : "S";
    const absValue = Math.abs(lat);
    const decimals = absValue >= 10 ? 1 : 2;
    return `${absValue.toFixed(decimals)}°${suffix}`;
  }

  function pickCartographicAtPixel(x, y) {
    if (!viewer) {
      return null;
    }
    const screenPoint = new Cesium.Cartesian2(x, y);
    const ray = viewer.camera.getPickRay(screenPoint);
    if (ray) {
      const cartesian = viewer.scene.globe.pick(ray, viewer.scene);
      if (cartesian) {
        return Cesium.Cartographic.fromCartesian(cartesian);
      }
    }
    const ellipsoidHit = viewer.camera.pickEllipsoid(screenPoint, viewer.scene.globe.ellipsoid);
    if (ellipsoidHit) {
      return Cesium.Cartographic.fromCartesian(ellipsoidHit);
    }
    return null;
  }

  function createSvgElement(tag, attrs, textContent) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      node.setAttribute(key, String(value));
    });
    if (typeof textContent === "string") {
      node.textContent = textContent;
    }
    return node;
  }

  function clearSvg(svg) {
    while (svg && svg.firstChild) {
      svg.removeChild(svg.firstChild);
    }
  }

  function clampPixel(value, minValue, maxValue) {
    return Math.max(minValue, Math.min(maxValue, value));
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: UI Widgets (compass, scale bar, status bar)  →  future: modules/ui.js
  // Functions: updateEdgeScaleWidgets, syncSceneModeToggle,
  //   setSceneModeControlEnabled, parseDemHeightRange, createRectangle,
  //   buildUrlWithQuery
  // ═══════════════════════════════════════════════════════════════════════════

  function updateEdgeScaleWidgets() {
    if (!viewer) {
      return;
    }
    const now = performance.now();
    if (now - lastEdgeScaleUpdateMs < EDGE_SCALE_UPDATE_INTERVAL_MS) {
      return;
    }
    lastEdgeScaleUpdateMs = now;

    const topSvg = document.getElementById("edgeScaleTopSvg");
    const leftSvg = document.getElementById("edgeScaleLeftSvg");
    if (!topSvg || !leftSvg) {
      return;
    }
    if (!viewer.canvas) {
      return;
    }

    const canvasRect = viewer.canvas.getBoundingClientRect();
    if (canvasRect.width <= 0 || canvasRect.height <= 0) {
      return;
    }

    const topRect = topSvg.getBoundingClientRect();
    const leftRect = leftSvg.getBoundingClientRect();

    const topWidth = topSvg.clientWidth || 0;
    const topHeight = topSvg.clientHeight || 0;
    const leftWidth = leftSvg.clientWidth || 0;
    const leftHeight = leftSvg.clientHeight || 0;
    if (topWidth <= 0 || topHeight <= 0 || leftWidth <= 0 || leftHeight <= 0) {
      return;
    }

    topSvg.setAttribute("viewBox", `0 0 ${topWidth} ${topHeight}`);
    leftSvg.setAttribute("viewBox", `0 0 ${leftWidth} ${leftHeight}`);
    clearSvg(topSvg);
    clearSvg(leftSvg);

    const topPad = 14;
    const topTickCount = 8;
    const topAxisY = 10;
    let topValidLabels = 0;
    topSvg.appendChild(createSvgElement("line", { class: "axis", x1: topPad, y1: topAxisY, x2: topWidth - topPad, y2: topAxisY }));
    for (let i = 0; i <= topTickCount; i += 1) {
      const x = topPad + ((topWidth - topPad * 2) * i) / topTickCount;
      topSvg.appendChild(createSvgElement("line", { class: "tick", x1: x, y1: topAxisY, x2: x, y2: topAxisY + 8 }));
      const sampleX = clampPixel(topRect.left - canvasRect.left + x, 0, Math.max(0, canvasRect.width - 1));
      const sampleY = clampPixel(topRect.bottom - canvasRect.top + 2, 0, Math.max(0, canvasRect.height - 1));
      const sample = pickCartographicAtPixel(sampleX, sampleY);
      if (!sample) {
        continue;
      }
      topValidLabels += 1;
      const lonDeg = Cesium.Math.toDegrees(sample.longitude);
      topSvg.appendChild(
        createSvgElement("text", { class: "label", x: x, y: topAxisY + 21, "text-anchor": "middle" }, formatLongitudeLabel(lonDeg))
      );
    }
    if (topValidLabels < 2) {
      topSvg.appendChild(
        createSvgElement("text", { class: "label", x: topWidth / 2, y: topAxisY + 21, "text-anchor": "middle" }, "Longitude scale: n/a")
      );
    }

    const leftPad = 10;
    const leftTickCount = 8;
    const leftAxisX = leftWidth - 12;
    let leftValidLabels = 0;
    leftSvg.appendChild(createSvgElement("line", { class: "axis", x1: leftAxisX, y1: leftPad, x2: leftAxisX, y2: leftHeight - leftPad }));
    for (let i = 0; i <= leftTickCount; i += 1) {
      const y = leftPad + ((leftHeight - leftPad * 2) * i) / leftTickCount;
      leftSvg.appendChild(createSvgElement("line", { class: "tick", x1: leftAxisX - 8, y1: y, x2: leftAxisX, y2: y }));
      const sampleX = clampPixel(leftRect.right - canvasRect.left + 2, 0, Math.max(0, canvasRect.width - 1));
      const sampleY = clampPixel(leftRect.top - canvasRect.top + y, 0, Math.max(0, canvasRect.height - 1));
      const sample = pickCartographicAtPixel(sampleX, sampleY);
      if (!sample) {
        continue;
      }
      leftValidLabels += 1;
      const latDeg = Cesium.Math.toDegrees(sample.latitude);
      leftSvg.appendChild(
        createSvgElement("text", { class: "label", x: 3, y: y + 4, "text-anchor": "start" }, formatLatitudeLabel(latDeg))
      );
    }
    if (leftValidLabels < 2) {
      leftSvg.appendChild(createSvgElement("text", { class: "label", x: 3, y: leftHeight / 2, "text-anchor": "start" }, "Lat n/a"));
    }
  }

  function syncSceneModeToggle(mode) {
    // Moved to Python Qt UI
  }

  function setSceneModeControlEnabled(enabled) {
    sceneModeControlEnabled = Boolean(enabled);
    // Moved to Python Qt UI
  }

  function parseDemHeightRange(options) {
    const defaultRange = { min: -500.0, max: 9000.0 };
    const query = options && options.query ? options.query : null;
    if (!query || typeof query.rescale !== "string") {
      return defaultRange;
    }
    const parts = query.rescale.split(",").map((v) => Number(v.trim()));
    if (parts.length !== 2 || !Number.isFinite(parts[0]) || !Number.isFinite(parts[1]) || parts[1] <= parts[0]) {
      return defaultRange;
    }
    return { min: parts[0], max: parts[1] };
  }

  function createRectangle(bounds) {
    if (!bounds) return null;
    if (
      !Number.isFinite(bounds.west) ||
      !Number.isFinite(bounds.south) ||
      !Number.isFinite(bounds.east) ||
      !Number.isFinite(bounds.north)
    ) {
      return null;
    }
    return Cesium.Rectangle.fromDegrees(bounds.west, bounds.south, bounds.east, bounds.north);
  }

  function buildUrlWithQuery(url, extraQuery) {
    const splitIndex = url.indexOf("?");
    const base = splitIndex >= 0 ? url.slice(0, splitIndex) : url;
    const queryText = splitIndex >= 0 ? url.slice(splitIndex + 1) : "";
    
    // Extract existing parameters as a map to avoid double-encoding
    const existingParams = {};
    if (queryText) {
      queryText.split("&").forEach(function (pair) {
        const eqIdx = pair.indexOf("=");
        if (eqIdx > 0) {
          const key = decodeURIComponent(pair.slice(0, eqIdx));
          const value = decodeURIComponent(pair.slice(eqIdx + 1));
          existingParams[key] = value;
        }
      });
    }
    
    // Merge new parameters into existing ones
    const finalParams = Object.assign({}, existingParams, extraQuery || {});
    
    // Reconstruct query string without double-encoding
    const paramPairs = Object.entries(finalParams).map(function ([key, value]) {
      if (value === null || value === undefined) {
        return null;
      }
      if (Array.isArray(value)) {
        return value.map(function (item) {
          return encodeURIComponent(key) + "=" + encodeURIComponent(String(item));
        }).join("&");
      }
      return encodeURIComponent(key) + "=" + encodeURIComponent(String(value));
    }).filter(Boolean);
    
    const merged = paramPairs.join("&");
    return merged ? base + "?" + merged : base;
  }

  function logLayerStack() {
    if (!viewer || !viewer.imageryLayers) {
      return;
    }
    const rows = [];
    for (let idx = 0; idx < viewer.imageryLayers.length; idx += 1) {
      const layer = viewer.imageryLayers.get(idx);
      const show = layer && layer.show === false ? "HIDDEN" : "VISIBLE";
      
      // FIX: Check if alpha is a finite number, fallback to 1.0, then format.
      const rawAlpha = layer && typeof layer.alpha === "number" ? layer.alpha : 1.0;
      const alpha = (Number.isFinite(rawAlpha) ? rawAlpha : 1.0).toFixed(2);
      
      let desc = "layer#" + idx + ":" + show + ":alpha=" + alpha;
      if (layer === activeDemDrapeLayer) {
        desc += ":DEM-DRAPE";
      } else if (layer === activeDemHillshadeLayer) {
        desc += ":DEM-HILLSHADE";
      } else if (layer === globalBasemapLayer) {
        desc += ":BASEMAP";
      } else if (layer === activeImageryLayer) {
        desc += ":ACTIVE-IMAGERY";
      } else if (managedImageryLayers.has(Array.from(managedImageryLayers.entries()).find(([_, l]) => l === layer)?.[0] || "")) {
        const key = Array.from(managedImageryLayers.entries()).find(([_, l]) => l === layer)?.[0] || "unknown";
        desc += ":MANAGED-IMAGERY:" + key;
      }
      rows.push(desc);
    }
    log("debug", "Layer stack [" + viewer.imageryLayers.length + " layers]: " + rows.join(" | "));
  }

  function requestLayerStackDump() {
    logLayerStack();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: Imagery Layer Management  →  future: modules/imagery.js
  // Functions: attachTileErrorHandler, clearManagedImageryLayers,
  //   logLayerStack, setLayerVisibilityByKey, setActiveTileBounds,
  //   setLastLoadedBounds, updateBasemapBlendForCurrentMode
  // ═══════════════════════════════════════════════════════════════════════════

  function attachTileErrorHandler(provider, name) {
    layerErrorCounts.set(name, 0);
    provider.errorEvent.addEventListener(function (error) {
      error.retry = false;
      const key = `${name}:${error.level}:${error.x}:${error.y}`;
      if (tileErrorSeen.has(key)) return;
      tileErrorSeen.add(key);
      const currentCount = (layerErrorCounts.get(name) || 0) + 1;
      layerErrorCounts.set(name, currentCount);
      const msg = error && error.message ? String(error.message) : "tile request failed";
      if (currentCount === 1) {
        let templateUrl = "";
        try {
          templateUrl = String(provider && provider.url ? provider.url : "");
        } catch (_err) {
          templateUrl = "";
        }
        if (templateUrl) {
          log("warn", "Tile provider template for " + name + " => " + templateUrl);
        }
      }
      if (currentCount <= 10 || currentCount % 25 === 0) {
        log(
          "warn",
          "Tile provider error for " +
            name +
            " count=" +
            currentCount +
            " z=" +
            error.level +
            " x=" +
            error.x +
            " y=" +
            error.y +
            " msg=" +
            msg
        );
      }
    });
  }

  function clearDemTerrainMode() {
    if (!viewer) return;
    const previousDemLayerKey = activeDemContext && activeDemContext.layerKey ? activeDemContext.layerKey : null;
    if (activeDemDrapeLayer) {
      viewer.imageryLayers.remove(activeDemDrapeLayer, false);
      activeDemDrapeLayer = null;
    }
    if (activeDemHillshadeLayer) {
      viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
      activeDemHillshadeLayer = null;
    }
    activeDemContext = null;
    activeDemTerrainSignature = null;
    activeDemDrapeUrl = null;
    activeDemHillshadeUrl = null;
    if (previousDemLayerKey) {
      layerDefinitions.delete(previousDemLayerKey);
      layerVisibilityState.delete(previousDemLayerKey);
    }
    terrainTileCache.clear();
    viewer.terrainProvider = baseTerrainProvider || new Cesium.EllipsoidTerrainProvider();
    applyDefaultSceneSettings();
    if (globalBasemapLayer) {
      globalBasemapLayer.alpha = 1.0;
    }
    hideDemColorbar();
    setSceneModeControlEnabled(true);
  }

  function clearManagedImageryLayers(exceptLayerKey) {
    if (!viewer) {
      managedImageryLayers.clear();
      layerDefinitions.clear();
      layerVisibilityState.clear();
      activeImageryLayer = null;
      return;
    }
    for (const [layerKey, layer] of Array.from(managedImageryLayers.entries())) {
      if (exceptLayerKey && layerKey === exceptLayerKey) {
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
      applySwipeComparatorSplit();
      // Re-pin basemap to bottom after clearing
      updateBasemapBlendForCurrentMode();
      return;
    }
    activeImageryLayer = null;
    applySwipeComparatorSplit();
    // Re-pin basemap to bottom after clearing
    updateBasemapBlendForCurrentMode();
  }

  function setLayerVisibilityByKey(layerKey, visible) {
    if (!viewer || !layerKey) {
      return false;
    }
    layerVisibilityState.set(layerKey, Boolean(visible));

    const imageryLayer = managedImageryLayers.get(layerKey);
    if (imageryLayer) {
      const shouldShow = Boolean(visible);
      imageryLayer.show = shouldShow;
      if (shouldShow) {
        viewer.imageryLayers.raiseToTop(imageryLayer);
        activeImageryLayer = imageryLayer;
      }
      applySwipeComparatorSplit();
      if (comparatorModeEnabled) {
        refreshComparatorLayers();
      }
      requestSceneRender();
      return true;
    }

    if (activeDemContext && activeDemContext.layerKey === layerKey) {
      const shouldShow = Boolean(visible);
      activeDemContext.visible = shouldShow;
      if (activeDemDrapeLayer) {
        activeDemDrapeLayer.show = shouldShow;
      }
      if (activeDemHillshadeLayer) {
        activeDemHillshadeLayer.show = shouldShow && activeDemHillshadeLayer.alpha > 0.01;
      }
      if (shouldShow) {
        updateDemColorbar(
          parseDemHeightRange(activeDemContext.options).min,
          parseDemHeightRange(activeDemContext.options).max,
          activeDemContext.options
        );
        setSceneModeControlEnabled(true);
        setStatus("DEM layer shown.");
        log("info", "DEM layer shown key=" + layerKey);
        if (activeDemTerrainProvider && viewer.terrainProvider !== activeDemTerrainProvider) {
          _swapTerrainProviderLocked(activeDemTerrainProvider);
        }
        // Re-apply exaggeration — terrainExaggeration resets when terrain provider changes
        if (viewer && viewer.scene && viewer.scene.globe) {
          viewer.scene.globe.terrainExaggeration = Math.max(0.1, demVisual.exaggeration);
          log("debug", "DEM show: re-applied terrainExaggeration=" + demVisual.exaggeration.toFixed(2));
        }
      } else {
        hideDemColorbar();
        setSceneModeControlEnabled(true);
        setStatus("DEM layer hidden.");
        log("info", "DEM layer hidden key=" + layerKey);
        if (viewer.terrainProvider !== baseTerrainProvider) {
          _swapTerrainProviderLocked(baseTerrainProvider);
        }
      }
      if (comparatorModeEnabled) {
        refreshComparatorLayers();
      }
      requestSceneRender();
      return true;
    }

    return false;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: DEM Colorbar  →  future: modules/dem.js
  // Functions: resolveDemColorbarGradient, updateDemColorbar, hideDemColorbar
  // ═══════════════════════════════════════════════════════════════════════════

  function resolveDemColorbarGradient(colormapName) {
    const normalized = String(colormapName || "terrain").toLowerCase();
    const gradients = {
      terrain:
        "to bottom, #f7f7f7 0%, #d9d3c7 14%, #b48f6a 28%, #c7b34a 42%, #7ca860 58%, #4aa8b2 74%, #2d7bd0 88%, #173c8f 100%",
      viridis:
        "to bottom, #fde725 0%, #90d743 24%, #35b779 45%, #21918c 64%, #31688e 82%, #443a83 100%",
      turbo:
        "to bottom, #7a0403 0%, #d84f2a 18%, #f6b44f 36%, #f7f756 50%, #7bd651 66%, #2c8fe3 84%, #23135a 100%",
      slope:
        "to bottom, #fde725 0%, #90d743 24%, #35b779 45%, #21918c 64%, #31688e 82%, #443a83 100%",
      aspect:
        "to bottom, #ff0000 0%, #ffff00 16%, #00ff00 33%, #00ffff 50%, #0000ff 66%, #ff00ff 83%, #ff0000 100%",
      gray:
        "to bottom, #ffffff 0%, #cccccc 45%, #808080 72%, #202020 100%",
      greys:
        "to bottom, #ffffff 0%, #cccccc 45%, #808080 72%, #202020 100%",
    };
    return gradients[normalized] || gradients.terrain;
  }

  function updateDemColorbar(minHeight, maxHeight, options) {
    const gradient = document.getElementById("demColorbar-gradient");
    const labelHigh = document.getElementById("demColorbar-label-high");
    const labelMid = document.getElementById("demColorbar-label-mid");
    const labelLow = document.getElementById("demColorbar-label-low");
    const container = document.getElementById("demColorbar");
    if (!gradient || !labelHigh || !labelMid || !labelLow || !container) return;

    const query = options && options.query ? options.query : {};
    const algorithmName = typeof query.algorithm === "string" ? String(query.algorithm).toLowerCase() : "";
    const colormapName = typeof query.colormap_name === "string" ? query.colormap_name : "terrain";
    gradient.style.background = `linear-gradient(${resolveDemColorbarGradient(colormapName)})`;

    if (algorithmName === "slope") {
      labelHigh.textContent = "90°";
      labelMid.textContent = "45°";
      labelLow.textContent = "0°";
      container.classList.add("visible");
      return;
    }

    if (algorithmName === "aspect") {
      labelHigh.textContent = "360°";
      labelMid.textContent = "180°";
      labelLow.textContent = "0°";
      container.classList.add("visible");
      return;
    }

    const midHeight = (minHeight + maxHeight) / 2;
    labelHigh.textContent = Math.round(maxHeight).toLocaleString() + " m";
    labelMid.textContent = Math.round(midHeight).toLocaleString() + " m";
    labelLow.textContent = Math.round(minHeight).toLocaleString() + " m";

    container.classList.add("visible");
  }

  function hideDemColorbar() {
    const container = document.getElementById("demColorbar");
    if (container) {
      container.classList.remove("visible");
    }
  }

  function updateBasemapBlendForCurrentMode() {
    if (!viewer) return;
    // Ensure the basemap is always visible and at the bottom of the stack
    const basemap = globalBasemapLayer || fallbackBasemapLayer;
    if (basemap) {
      basemap.alpha = 1.0;
      basemap.show = true;
      // If it has drifted off the bottom, push it back
      if (viewer.imageryLayers.indexOf(basemap) !== 0) {
        viewer.imageryLayers.lowerToBottom(basemap);
      }
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: Camera & Scene Mode  →  future: modules/camera.js
  // Functions: applyDefaultSceneSettings, applyDemSceneSettings,
  //   tuneCameraController, configureCameraControllerForMode,
  //   _swapTerrainProviderLocked, setSceneModeInternal, detectSceneMode,
  //   syncSceneModeToggle, focusPreferredRegion, focusPreferredRegion3D,
  //   focusLoadedRegion3D, schedule3DFocusAfterMorph, startFlyThroughBounds,
  //   applyDefaultStartupFocus, _updateCompass, Asia camera lock postRender
  // ═══════════════════════════════════════════════════════════════════════════

  function applyDefaultSceneSettings() {
    if (!viewer) return;
    // Cesium 1.78: verticalExaggeration does not exist — use globe.terrainExaggeration
    viewer.scene.globe.enableLighting = true;
    viewer.scene.globe.depthTestAgainstTerrain = true;
    viewer.scene.globe.preloadAncestors = true;
    viewer.scene.globe.preloadSiblings = false;
    viewer.scene.globe.maximumScreenSpaceError = 2.0;
    viewer.scene.globe.showSkirts = true;
    viewer.scene.globe.tileCacheSize = 300;
    viewer.scene.globe.showGroundAtmosphere = false;
    viewer.scene.fog.enabled = true;
    viewer.scene.fog.density = 0.0001;
    viewer.shadows = false;
    viewer.scene.light = new Cesium.SunLight();
    viewer.scene.light.intensity = 2.0;
  }

  /**
   * Swap the terrain provider while keeping the camera locked on the current view.
   * Cesium 1.78 fires camera resets asynchronously after terrainProvider changes.
   * We lock the camera for 5 post-render frames to absorb all async resets.
   */
  function _swapTerrainProviderLocked(newProvider) {
    if (!viewer || !newProvider) return;
    if (viewer.terrainProvider === newProvider) return;

    // Snapshot current camera state
    const savedPos = viewer.camera.position.clone();
    const savedHdg = viewer.camera.heading;
    const savedPitch = viewer.camera.pitch;
    const savedRoll = viewer.camera.roll;

    log("debug", "terrainProvider swap — locking camera for 5 frames");
    viewer.terrainProvider = newProvider;

    // Re-apply camera for 5 consecutive post-render frames to beat Cesium's async reset
    let framesLeft = 5;
    const lockHandle = viewer.scene.postRender.addEventListener(function () {
      viewer.camera.setView({
        destination: savedPos,
        orientation: { heading: savedHdg, pitch: savedPitch, roll: savedRoll },
      });
      framesLeft -= 1;
      if (framesLeft <= 0) {
        lockHandle();  // self-remove
        log("debug", "terrainProvider swap — camera lock released");
      }
    });
  }

  function applyDemSceneSettings() {
    if (!viewer) return;
    // Cesium 1.78: globe.terrainExaggeration is the correct API (verticalExaggeration doesn't exist)
    // Must be re-applied every time terrain provider changes — it resets on provider swap
    viewer.scene.globe.terrainExaggeration = Math.max(0.1, demVisual.exaggeration);
    log("debug", "applyDemSceneSettings: terrainExaggeration=" + demVisual.exaggeration.toFixed(2));
    viewer.scene.globe.enableLighting = true;
    viewer.scene.globe.depthTestAgainstTerrain = true;
    viewer.scene.globe.preloadAncestors = true;
    viewer.scene.globe.preloadSiblings = false;
    viewer.scene.globe.maximumScreenSpaceError = 2.0;
    viewer.scene.globe.showSkirts = true;
    viewer.scene.globe.tileCacheSize = 300;
    viewer.scene.globe.showGroundAtmosphere = false;
    viewer.scene.fog.enabled = true;
    viewer.scene.fog.density = 0.0001;
    viewer.shadows = false;
    requestSceneRender();
  }

  function tuneCameraController() {
    if (!viewer) return;
    const controller = viewer.scene.screenSpaceCameraController;
    controller.enableCollisionDetection = true;
    controller.maximumMovementRatio = 0.075;
    controller.minimumZoomDistance = ASIA_LOCK_MIN_ZOOM_IN_M;
    controller.maximumZoomDistance = ASIA_LOCK_MAX_ZOOM_OUT_M;
    controller.maximumTiltAngle = Cesium.Math.toRadians(89.0);
    configureCameraControllerForMode(currentSceneMode);

    // ── Asia camera clamp ─────────────────────────────────────────────────
    // After every render frame, snap the camera back if it has drifted outside
    // the Asia bounding box. This prevents panning to Americas / Europe / etc.
    viewer.scene.postRender.addEventListener(function () {
      if (!_asiaCameraClampEnabled) return;
      if (!viewer || !viewer.camera) return;

      const carto = viewer.camera.positionCartographic;
      if (!carto) return;

      const lon = Cesium.Math.toDegrees(carto.longitude);
      const lat = Cesium.Math.toDegrees(carto.latitude);
      const alt = carto.height;

      // Clamp altitude
      const clampedAlt = Math.max(ASIA_LOCK_MIN_ZOOM_IN_M,
                                  Math.min(ASIA_LOCK_MAX_ZOOM_OUT_M, alt));

      // Clamp lon/lat to Asia rectangle
      const clampedLon = Math.max(ASIA_LOCK_WEST,  Math.min(ASIA_LOCK_EAST,  lon));
      const clampedLat = Math.max(ASIA_LOCK_SOUTH, Math.min(ASIA_LOCK_NORTH, lat));

      const lonDrift = Math.abs(clampedLon - lon);
      const latDrift = Math.abs(clampedLat - lat);
      const altDrift = Math.abs(clampedAlt - alt);

      // Only snap if actually out of bounds (avoid jitter on every frame)
      if (lonDrift > 0.001 || latDrift > 0.001 || altDrift > 100) {
        _asiaCameraClampEnabled = false;  // prevent re-entry during setView
        viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(clampedLon, clampedLat, clampedAlt),
          orientation: {
            heading: viewer.camera.heading,
            pitch:   viewer.camera.pitch,
            roll:    viewer.camera.roll,
          },
        });
        _asiaCameraClampEnabled = true;
      }
    });
  }

  function configureCameraControllerForMode(mode) {
    if (!viewer) {
      return;
    }
    const controller = viewer.scene.screenSpaceCameraController;
    const is2d = String(mode || "3d").toLowerCase() === "2d";
    controller.enableInputs = true;
    controller.enableTranslate = true;
    controller.enableZoom = true;
    // When panModeActive is true, force 2D-like flat drag behavior even in 3D mode
    const forceFlat = panModeActive || is2d;
    controller.enableRotate = !forceFlat;
    controller.enableTilt = !forceFlat;
    controller.enableLook = !forceFlat;
    controller.inertiaSpin = forceFlat ? 0.0 : 0.86;
    controller.inertiaTranslate = 0.86;
    controller.inertiaZoom = 0.74;
  }

  function rectangleToBounds(rectangle) {
    if (!rectangle) {
      return null;
    }
    return normalizeBounds({
      west: Cesium.Math.toDegrees(rectangle.west),
      south: Cesium.Math.toDegrees(rectangle.south),
      east: Cesium.Math.toDegrees(rectangle.east),
      north: Cesium.Math.toDegrees(rectangle.north),
    });
  }

  function isNearGlobalBounds(bounds) {
    const normalized = normalizeBounds(bounds);
    if (!normalized) {
      return false;
    }
    return (
      normalized.west <= -179.5 &&
      normalized.east >= 179.5 &&
      normalized.south <= -84.5 &&
      normalized.north >= 84.5
    );
  }

  function setActiveTileBounds(bounds) {
    const normalized = normalizeBounds(bounds);
    if (!normalized) {
      return;
    }
    activeTileBounds = normalized;
    lastLoadedBounds = normalized;
    updateCameraOrbitTarget(normalized);
  }

  function updateCameraOrbitTarget(bounds) {
    const normalized = normalizeBounds(bounds);
    if (!normalized) {
      return;
    }
    const rect = Cesium.Rectangle.fromDegrees(normalized.west, normalized.south, normalized.east, normalized.north);
    const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
    cameraOrbitBounds = normalized;
    cameraOrbitRange = Math.max(compute3DFocusRange(normalized), sphere.radius * 1.2, 250.0);
    if (viewer && viewer.camera) {
      if (Number.isFinite(viewer.camera.heading)) {
        cameraOrbitHeading = viewer.camera.heading;
      }
      if (Number.isFinite(viewer.camera.pitch)) {
        cameraOrbitPitch = viewer.camera.pitch;
      }
    }
  }

  function applyCameraOrbitTarget() {
    if (!viewer || currentSceneMode !== "3d") {
      return false;
    }
    const bounds = cameraOrbitBounds || activeTileBounds || lastLoadedBounds;
    if (!bounds) {
      return false;
    }
    const rect = Cesium.Rectangle.fromDegrees(bounds.west, bounds.south, bounds.east, bounds.north);
    const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
    const hpr = new Cesium.HeadingPitchRange(cameraOrbitHeading, cameraOrbitPitch, cameraOrbitRange);
    
    viewer.camera.cancelFlight();
    viewer.camera.lookAt(sphere.center, hpr);
    
    if (comparatorModeEnabled) {
      if (comparatorLeftViewer && comparatorLeftViewer.camera) {
        comparatorLeftViewer.camera.cancelFlight();
        comparatorLeftViewer.camera.lookAt(sphere.center, hpr);
      }
      if (comparatorRightViewer && comparatorRightViewer.camera) {
        comparatorRightViewer.camera.cancelFlight();
        comparatorRightViewer.camera.lookAt(sphere.center, hpr);
      }
    }
    
    requestSceneRender();
    return true;
  }

  function syncOrbitFromCurrentCamera(bounds) {
    if (!viewer || !viewer.camera) {
      return;
    }
    const normalized = normalizeBounds(bounds);
    if (!normalized) {
      return;
    }
    const rect = Cesium.Rectangle.fromDegrees(normalized.west, normalized.south, normalized.east, normalized.north);
    const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
    const camera = viewer.camera;
    if (Number.isFinite(camera.heading)) {
      cameraOrbitHeading = camera.heading;
    }
    if (Number.isFinite(camera.pitch)) {
      cameraOrbitPitch = camera.pitch;
    }
    if (camera.positionWC && sphere.center) {
      const distance = Cesium.Cartesian3.distance(camera.positionWC, sphere.center);
      if (Number.isFinite(distance) && distance > 1.0) {
        cameraOrbitRange = distance;
      }
    }
  }

  function resolvePreferredFocusBounds() {
    const pinnedBounds = normalizeBounds(activeTileBounds);
    if (pinnedBounds && !isNearGlobalBounds(pinnedBounds)) {
      return pinnedBounds;
    }
    if (activeDemContext && activeDemContext.options && activeDemContext.options.bounds) {
      const demBounds = normalizeBounds(activeDemContext.options.bounds);
      if (demBounds) {
        return demBounds;
      }
    }
    if (activeImageryLayer && activeImageryLayer.imageryProvider && activeImageryLayer.imageryProvider.rectangle) {
      const imageryBounds = rectangleToBounds(activeImageryLayer.imageryProvider.rectangle);
      if (imageryBounds && !isNearGlobalBounds(imageryBounds)) {
        return imageryBounds;
      }
    }
    const fallbackBounds = normalizeBounds(lastLoadedBounds);
    if (fallbackBounds && !isNearGlobalBounds(fallbackBounds)) {
      return fallbackBounds;
    }
    return null;
  }

  function focusPreferredRegion(durationSeconds) {
    const bounds = pendingFocusBounds || resolvePreferredFocusBounds();
    if (!bounds) {
      return;
    }
    setActiveTileBounds(bounds);
    focusLoadedRegion(durationSeconds);
  }

  function applyDefaultStartupFocus() {
    if (!viewer) {
      return;
    }
    viewer.camera.cancelFlight();
    viewer.camera.setView({
      destination: Cesium.Cartesian3.fromDegrees(
        DEFAULT_STARTUP_CENTER_LON,
        DEFAULT_STARTUP_CENTER_LAT,
        DEFAULT_STARTUP_HEIGHT_M
      ),
      orientation: {
        heading: DEFAULT_STARTUP_HEADING,
        pitch: DEFAULT_STARTUP_PITCH,
        roll: 0.0,
      },
    });
    cameraOrbitHeading = DEFAULT_STARTUP_HEADING;
    cameraOrbitPitch = DEFAULT_STARTUP_PITCH;
    cameraOrbitRange = DEFAULT_STARTUP_HEIGHT_M;
    viewer.scene.requestRender();
  }

  function focusPreferredRegion3D(durationSeconds) {
    const bounds = pendingFocusBounds || resolvePreferredFocusBounds();
    if (!bounds) {
      sceneDebug("focusPreferredRegion3D skipped: no bounds");
      return;
    }
    sceneDebug(
      "focusPreferredRegion3D bounds=" +
        JSON.stringify(bounds) +
        " duration=" +
        String(durationSeconds)
    );
    setActiveTileBounds(bounds);
    focusLoadedRegion3D(durationSeconds);
  }

  function schedule3DFocusAfterMorph(durationSeconds) {
    const duration = Number.isFinite(durationSeconds) ? durationSeconds : 1.0;
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () {
        sceneDebug("schedule3DFocusAfterMorph executing duration=" + String(duration));
        focusPreferredRegion3D(duration);
      });
    });
  }

  function normalizeBounds(bounds) {
    if (!bounds || typeof bounds !== "object") {
      return null;
    }
    const west = Number(bounds.west);
    const south = Number(bounds.south);
    const east = Number(bounds.east);
    const north = Number(bounds.north);
    if (!Number.isFinite(west) || !Number.isFinite(south) || !Number.isFinite(east) || !Number.isFinite(north)) {
      return null;
    }
    return { west: west, south: south, east: east, north: north };
  }

  function estimateBoundsSizeMeters(bounds) {
    const normalized = normalizeBounds(bounds);
    if (!normalized) {
      return { width: 0.0, height: 0.0, maxDimension: 0.0, diagonal: 0.0 };
    }
    const midLat = (normalized.south + normalized.north) * 0.5;
    const midLon = (normalized.west + normalized.east) * 0.5;
    const westPoint = Cesium.Cartographic.fromDegrees(normalized.west, midLat);
    const eastPoint = Cesium.Cartographic.fromDegrees(normalized.east, midLat);
    const southPoint = Cesium.Cartographic.fromDegrees(midLon, normalized.south);
    const northPoint = Cesium.Cartographic.fromDegrees(midLon, normalized.north);
    const horizontal = new Cesium.EllipsoidGeodesic(westPoint, eastPoint).surfaceDistance || 0.0;
    const vertical = new Cesium.EllipsoidGeodesic(southPoint, northPoint).surfaceDistance || 0.0;
    const width = Number.isFinite(horizontal) ? horizontal : 0.0;
    const height = Number.isFinite(vertical) ? vertical : 0.0;
    return {
      width: width,
      height: height,
      maxDimension: Math.max(width, height),
      diagonal: Math.hypot(width, height),
    };
  }

  function padBounds(bounds, paddingRatio) {
    const normalized = normalizeBounds(bounds);
    if (!normalized) {
      return null;
    }
    const ratio = Number.isFinite(paddingRatio) ? Math.max(0.0, paddingRatio) : 0.0;
    const lonSpan = Math.max(Math.abs(normalized.east - normalized.west), 0.00001);
    const latSpan = Math.max(Math.abs(normalized.north - normalized.south), 0.00001);
    const lonPad = lonSpan * ratio;
    const latPad = latSpan * ratio;
    const result = {
      west: normalized.west - lonPad,
      south: Math.max(-85.0, normalized.south - latPad),
      east: normalized.east + lonPad,
      north: Math.min(85.0, normalized.north + latPad),
    };
    return result;
  }

  function compute3DFocusRange(bounds) {
    const normalized = normalizeBounds(bounds);
    if (!normalized) {
      return 1200.0;
    }
    const rect = Cesium.Rectangle.fromDegrees(
      normalized.west,
      normalized.south,
      normalized.east,
      normalized.north
    );
    const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
    const size = estimateBoundsSizeMeters(normalized);
    const baseRange = Math.max(
      sphere.radius * 1.8,
      size.maxDimension * 1.8,
      size.diagonal * 1.25,
      75.0
    );
    return Math.min(Math.max(baseRange, 75.0), 2500000.0);
  }

  function focusLoadedRegion(durationSeconds) {
    if (!viewer) {
      return;
    }
    const boundsToUse = pendingFocusBounds || activeTileBounds || lastLoadedBounds;
    if (!boundsToUse) {
      return;
    }
    const paddedBounds = padBounds(boundsToUse, 0.04) || boundsToUse;
    const rect = Cesium.Rectangle.fromDegrees(
      paddedBounds.west,
      paddedBounds.south,
      paddedBounds.east,
      paddedBounds.north
    );
    viewer.camera.cancelFlight();
    viewer.camera.setView({ destination: rect });
    viewer.scene.requestRender();
  }

  function focusLoadedRegion3D(durationSeconds) {
    if (!viewer) {
      sceneDebug("focusLoadedRegion3D skipped: viewer unavailable");
      return;
    }
    const boundsToUse = pendingFocusBounds || activeTileBounds || lastLoadedBounds;
    if (!boundsToUse) {
      sceneDebug("focusLoadedRegion3D skipped: no bounds source");
      return;
    }
    const paddedBounds = padBounds(boundsToUse, 0.04) || boundsToUse;
    const rect = Cesium.Rectangle.fromDegrees(
      paddedBounds.west,
      paddedBounds.south,
      paddedBounds.east,
      paddedBounds.north
    );
    const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
    const range = Math.max(compute3DFocusRange(paddedBounds), sphere.radius * 1.3);
    const duration = Number.isFinite(durationSeconds) ? durationSeconds : 1.0;
    const heading = Number.isFinite(viewer.camera.heading) ? viewer.camera.heading : 0.0;
    sceneDebug(
      "focusLoadedRegion3D flyTo bounds=" +
        JSON.stringify(paddedBounds) +
        " heading=" +
        String(heading) +
        " range=" +
        String(range) +
        " duration=" +
        String(duration)
    );
    viewer.camera.cancelFlight();
    viewer.camera.flyToBoundingSphere(sphere, {
      offset: new Cesium.HeadingPitchRange(
        heading,
        Cesium.Math.toRadians(-35),
        range
      ),
      duration: duration,
    });
    viewer.scene.requestRender();
  }

  // ─────────────────────────────────────────────────────────────────────────
  //  DEM Rendering — Imagery-Only Pipeline
  //
  //  Design rationale: The previous approach used a custom TerrainProvider that
  //  decoded Terrarium-encoded PNGs frame-by-frame in the main JS thread. Cesium
  //  calls requestTileGeometry() synchronously for every visible tile, which
  //  spawned dozens of parallel Image loads + canvas operations per frame,
  //  exhausting the V8 heap and hanging/white-screening the globe. This is
  //  fundamentally incompatible with the QtWebEngine Chromium 87 environment.
  //
  //  The new approach renders DEM data as two flat EPSG:3857 imagery layers on
  //  the stable EllipsoidTerrainProvider:
  //    1. Colormap drape  — TiTiler colormap (gray/terrain) at full opacity
  //    2. Hillshade overlay — TiTiler hillshade algorithm at ~35% alpha
  //
  //  This is scientifically correct (standard GIS pseudo-color visualization),
  //  fully crash-proof for datasets of any size (2cm–5cm resolution, terabytes),
  //  and works identically on macOS and Windows/NVIDIA.
  // ─────────────────────────────────────────────────────────────────────────

  function shouldUseFetch(url) {
    const value = String(url || "").trim().toLowerCase();
    return value.startsWith("http://") || value.startsWith("https://");
  }

  async function loadJsonResource(url) {
    try {
      return await Cesium.Resource.fetchJson({ url: String(url) });
    } catch (_resourceError) {
      if (!shouldUseFetch(url)) {
        return null;
      }
      try {
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) {
          return null;
        }
        return await response.json();
      } catch (_fetchError) {
        return null;
      }
    }
  }



  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: DEM Terrain Rendering  →  future: modules/dem.js
  // Functions: OfflineCustomTerrainProvider (constructor + prototype),
  //   applyDemLayer, setDemColorMode, clearDemTerrainMode,
  //   updateDemColorbar, hideDemColorbar, resolveDemColorbarGradient,
  //   parseDemHeightRange, applyDemSceneSettings
  // ═══════════════════════════════════════════════════════════════════════════

  function applyDemLayer() {
    if (!viewer || !activeDemContext) return;
    const bounds = activeDemContext.options && activeDemContext.options.bounds ? activeDemContext.options.bounds : null;
    const rasterQuery = activeDemContext.options && activeDemContext.options.query ? activeDemContext.options.query : {};
    const minLevel = activeDemContext.options && Number.isInteger(activeDemContext.options.minzoom) ? activeDemContext.options.minzoom : 0;
    const maxLevelRaw = activeDemContext.options && Number.isInteger(activeDemContext.options.maxzoom) ? activeDemContext.options.maxzoom : 19;
    const imageryMaxLevel = Math.max(minLevel, maxLevelRaw);
    const terrainMaxLevel = Math.max(minLevel, Math.min(maxLevelRaw, DEM_MAX_TERRAIN_LEVEL));
    const rectangle = createRectangle(bounds);
    const range = parseDemHeightRange(activeDemContext.options);
    const hillshadeQuery = {
      algorithm: "hillshade",
      azimuth: DEM_HILLSHADE_AZIMUTH,
      angle_altitude: DEM_HILLSHADE_ALTITUDE,
      z_exaggeration: demVisual.exaggeration,
      buffer: 4,
    };
    if (Object.prototype.hasOwnProperty.call(rasterQuery, "nodata")) {
      hillshadeQuery.nodata = rasterQuery.nodata;
    }
    const hillshadeUrl = buildUrlWithQuery(activeDemContext.xyzUrl, hillshadeQuery);
    const drapeQuery = {
      ...rasterQuery,
      resampling: "nearest",
    };
    const drapeUrl = buildUrlWithQuery(activeDemContext.xyzUrl, drapeQuery);
    log("info", "DEM imagery-only pipeline: drape=" + drapeUrl);
    const demVisible = activeDemContext.visible !== false;
    layerDefinitions.set(activeDemContext.layerKey, {
      key: activeDemContext.layerKey,
      label: String(activeDemContext.name || activeDemContext.layerKey || "DEM"),
      type: "dem",
      xyzUrl: activeDemContext.xyzUrl,
      query: { ...rasterQuery },
      drapeUrl: drapeUrl,
      hillshadeUrl: hillshadeUrl,
      minLevel: minLevel,
      maxLevel: imageryMaxLevel,
      bounds: normalizeBounds(bounds),
      hillshadeAlpha: demVisual.hillshadeAlpha,
    });
    layerVisibilityState.set(activeDemContext.layerKey, demVisible);

    // ── 3D DEM Rendering Pipeline ──────────────────────────────────────────
    // Build the terrain provider ONLY when the DEM is first loaded or the URL changes.
    // Never rebuild for exaggeration or color mode — those are handled in-place.
    const terrainUrl = drapeUrl;
    const terrainSignatureChanged = activeDemTerrainSignature !== activeDemContext.layerKey;

    if (terrainSignatureChanged || !activeDemTerrainProvider) {
      const customTerrainProvider = new OfflineCustomTerrainProvider({
        url: terrainUrl,
        minLevel: minLevel,
        maxLevel: terrainMaxLevel,
        options: activeDemContext.options,
      });
      activeDemTerrainProvider = customTerrainProvider;
      activeDemTerrainSignature = activeDemContext.layerKey;
      log("debug", "applyDemLayer: new terrain provider built key=" + activeDemContext.layerKey);

      if (demVisible) {
        _swapTerrainProviderLocked(customTerrainProvider);
      }
    } else if (demVisible && viewer.terrainProvider !== activeDemTerrainProvider) {
      // Re-show after hide — reuse existing provider, no rebuild
      log("debug", "applyDemLayer: reusing existing terrain provider key=" + activeDemContext.layerKey);
      _swapTerrainProviderLocked(activeDemTerrainProvider);
    }

    if (!demVisible && viewer.terrainProvider !== baseTerrainProvider) {
      log("debug", "applyDemLayer: DEM hidden, restoring base terrain");
      _swapTerrainProviderLocked(baseTerrainProvider);
    }
    // ───────────────────────────────────────────────────────────────────────


    // Always clean up hillshade when drape URL changes to ensure proper layer rebuild
    const drapeUrlChanged = activeDemDrapeUrl !== drapeUrl;
    if (drapeUrlChanged && activeDemHillshadeLayer) {
      viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
      activeDemHillshadeLayer = null;
      activeDemHillshadeUrl = null;
    }

    if (!activeDemDrapeLayer || drapeUrlChanged) {
      if (activeDemDrapeLayer) {
        viewer.imageryLayers.remove(activeDemDrapeLayer, false);
        activeDemDrapeLayer = null;
      }
      const drapeProvider = new Cesium.UrlTemplateImageryProvider({
        url: drapeUrl,
        maximumLevel: imageryMaxLevel,
        minimumLevel: minLevel,
        tilingScheme: new Cesium.WebMercatorTilingScheme(),
        enablePickFeatures: false,
        rectangle: rectangle,
      });
      attachTileErrorHandler(drapeProvider, activeDemContext.name + "-drape");
      activeDemDrapeLayer = viewer.imageryLayers.addImageryProvider(drapeProvider);
      activeDemDrapeLayer.alpha = 1.0;
      activeDemDrapeLayer.show = demVisible;
      activeDemDrapeUrl = drapeUrl;
    }

    const clampedHillshadeAlpha = Math.max(0.0, Math.min(1.0, demVisual.hillshadeAlpha));
    if (clampedHillshadeAlpha > 0.01) {
      if (activeDemHillshadeLayer && activeDemHillshadeUrl !== hillshadeUrl) {
        viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
        activeDemHillshadeLayer = null;
        activeDemHillshadeUrl = null;
      }
      if (!activeDemHillshadeLayer) {
        const hillshadeProvider = new Cesium.UrlTemplateImageryProvider({
          url: hillshadeUrl,
          maximumLevel: imageryMaxLevel,
          minimumLevel: minLevel,
          tilingScheme: new Cesium.WebMercatorTilingScheme(),
          enablePickFeatures: false,
          rectangle: rectangle,
        });
        attachTileErrorHandler(hillshadeProvider, activeDemContext.name + "-hillshade");
        activeDemHillshadeLayer = viewer.imageryLayers.addImageryProvider(hillshadeProvider);
        activeDemHillshadeUrl = hillshadeUrl;
      }
      activeDemHillshadeLayer.alpha = clampedHillshadeAlpha;
      activeDemHillshadeLayer.show = demVisible;
    } else if (activeDemHillshadeLayer) {
      viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
      activeDemHillshadeLayer = null;
      activeDemHillshadeUrl = null;
    }
    applyDemSceneSettings();
    
    // Ensure proper layer stacking: RGB imagery MUST STRICTLY overlay the DEM
    // Order (top to bottom): managed imagery (RGB) > hillshade > drape > base layers
    if (activeDemDrapeLayer) {
      viewer.imageryLayers.raiseToTop(activeDemDrapeLayer);
    }
    if (activeDemHillshadeLayer) {
      viewer.imageryLayers.raiseToTop(activeDemHillshadeLayer);
    }
    for (const layer of managedImageryLayers.values()) {
      if (layer && layer.show && viewer.imageryLayers.indexOf(layer) >= 0) {
        viewer.imageryLayers.raiseToTop(layer);
      }
    }
    log("debug", "DEM layer stack: hillshade=" + (activeDemHillshadeLayer ? "yes" : "no") + " drape=" + (activeDemDrapeLayer ? "yes" : "no") + " managed=" + managedImageryLayers.size);
    updateBasemapBlendForCurrentMode();
    if (demVisible) {
      updateDemColorbar(range.min, range.max, activeDemContext.options);
      setStatus("DEM terrain active: " + activeDemContext.name);
    } else {
      hideDemColorbar();
      setStatus("DEM layer hidden.");
    }
    log(
      "info",
      "DEM activated name=" +
        activeDemContext.name +
        " min=" +
        minLevel +
        " imageryMax=" +
        imageryMaxLevel +
        " drape=" +
        drapeUrl
    );
    logLayerStack();
    if (comparatorModeEnabled) {
      refreshComparatorLayers();
    }
    requestSceneRender();
  }

  const MAX_CONCURRENT_TERRAIN_DECODES = 4;
  let activeTerrainDecodes = 0;
  const terrainDecodeQueue = [];
  terrainDecodeCanvas = document.createElement("canvas");
  terrainDecodeCanvas.width = TERRAIN_SAMPLE_SIZE;
  terrainDecodeCanvas.height = TERRAIN_SAMPLE_SIZE;
  terrainDecodeCtx = terrainDecodeCanvas.getContext("2d", { willReadFrequently: true });

  function processTerrainDecodeQueue() {
    while (terrainDecodeQueue.length > 0 && activeTerrainDecodes < MAX_CONCURRENT_TERRAIN_DECODES) {
      const task = terrainDecodeQueue.shift();
      activeTerrainDecodes++;
      task().finally(() => {
        activeTerrainDecodes--;
        processTerrainDecodeQueue();
      });
    }
  }

  function enqueueTerrainDecode(taskFn) {
    return new Promise((resolve, reject) => {
      terrainDecodeQueue.push(async () => {
        try {
          resolve(await taskFn());
        } catch (err) {
          reject(err);
        }
      });
      processTerrainDecodeQueue();
    });
  }

  function OfflineCustomTerrainProvider(options) {
    this.tilingScheme = new Cesium.WebMercatorTilingScheme();
    this.hasWaterMask = false;
    this.hasVertexNormals = false;
    this.ready = true;
    this.readyPromise = Cesium.when.resolve(true);
    this.errorEvent = new Cesium.Event();
    
    this._url = options.url;
    this._min = options.minLevel || 0;
    this._max = options.maxLevel || DEM_MAX_TERRAIN_LEVEL;
    this._rangeMin = 0;
    this._rangeMax = 0;
    
    if (options.options && options.options.query && options.options.query.rescale) {
      const parts = String(options.options.query.rescale).split(",");
      if (parts.length === 2) {
        this._rangeMin = parseFloat(parts[0]);
        this._rangeMax = parseFloat(parts[1]);
      }
    }
  }

  OfflineCustomTerrainProvider.prototype.requestTileGeometry = function (x, y, level) {
    if (level > this._max) {
      return Cesium.when.reject(new Error("Exceeded max level"));
    }
    
    const tileUrl = this._url.replace("%7Bz%7D", level).replace("%7Bx%7D", x).replace("%7By%7D", y).replace("{z}", level).replace("{x}", x).replace("{y}", y);
    
    return Cesium.when(enqueueTerrainDecode(() => {
      return new Promise((resolve, reject) => {
        const img = new Image();
        img.crossOrigin = "anonymous";
        img.onload = () => {
          terrainDecodeCtx.clearRect(0, 0, TERRAIN_SAMPLE_SIZE, TERRAIN_SAMPLE_SIZE);
          terrainDecodeCtx.drawImage(img, 0, 0, TERRAIN_SAMPLE_SIZE, TERRAIN_SAMPLE_SIZE);
          const imgData = terrainDecodeCtx.getImageData(0, 0, TERRAIN_SAMPLE_SIZE, TERRAIN_SAMPLE_SIZE);
          const data = imgData.data;
          const output = new Float32Array(TERRAIN_SAMPLE_SIZE * TERRAIN_SAMPLE_SIZE);
          
          const rMin = this._rangeMin;
          const span = this._rangeMax - rMin;
          
          for (let i = 0; i < output.length; i++) {
            const val = data[i * 4]; 
            if (data[i * 4 + 3] === 0) {
              output[i] = 0; 
            } else {
              output[i] = rMin + (val / 255.0) * span;
            }
          }
          
          img.onload = null;
          img.onerror = null;
          
          resolve(new Cesium.HeightmapTerrainData({
            buffer: output,
            width: TERRAIN_SAMPLE_SIZE,
            height: TERRAIN_SAMPLE_SIZE,
            structure: { heightScale: demVisual.exaggeration, heightOffset: 0.0, elementsPerHeight: 1, stride: 1 }
          }));
        };
        img.onerror = () => {
          img.onload = null;
          img.onerror = null;
          const output = new Float32Array(TERRAIN_SAMPLE_SIZE * TERRAIN_SAMPLE_SIZE);
          resolve(new Cesium.HeightmapTerrainData({
            buffer: output,
            width: TERRAIN_SAMPLE_SIZE,
            height: TERRAIN_SAMPLE_SIZE,
            structure: { heightScale: demVisual.exaggeration, heightOffset: 0.0, elementsPerHeight: 1, stride: 1 }
          }));
        };
        img.src = tileUrl;
      });
    }));
  };

  OfflineCustomTerrainProvider.prototype.getLevelMaximumGeometricError = function (level) {
    return 7785.0 / Math.pow(2, level);
  };
  OfflineCustomTerrainProvider.prototype.getTileDataAvailable = function (x, y, level) {
    return level <= this._max;
  };

  function setDemColorMode(colormapName) {
    if (!activeDemContext) return;
    if (!activeDemContext.options) activeDemContext.options = {};
    if (!activeDemContext.options.query) activeDemContext.options.query = {};

    const normalized = String(colormapName || "gray").toLowerCase();
    const query = activeDemContext.options.query;

    if (normalized === "slope") {
      query.algorithm = "slope";
      query.colormap_name = "viridis";
      query.rescale = "0,90";
    } else if (normalized === "aspect") {
      query.algorithm = "aspect";
      query.colormap_name = "turbo";
      query.rescale = "0,360";
    } else {
      delete query.algorithm;
      query.colormap_name = normalized;
    }

    // In-place URL swap — no terrain rebuild, no camera jump.
    if (activeDemDrapeLayer && activeDemContext) {
      const rasterQuery = activeDemContext.options.query || {};
      const drapeQuery = { ...rasterQuery, resampling: "nearest" };
      const newDrapeUrl = buildUrlWithQuery(activeDemContext.xyzUrl, drapeQuery);

      if (newDrapeUrl !== activeDemDrapeUrl) {
        const bounds = activeDemContext.options && activeDemContext.options.bounds ? activeDemContext.options.bounds : null;
        const rectangle = createRectangle(bounds);
        const minLevel = activeDemContext.options && Number.isInteger(activeDemContext.options.minzoom) ? activeDemContext.options.minzoom : 0;
        const maxLevel = activeDemContext.options && Number.isInteger(activeDemContext.options.maxzoom) ? activeDemContext.options.maxzoom : 19;

        // Snapshot camera
        const savedPos = viewer.camera.position.clone();
        const savedHdg = viewer.camera.heading;
        const savedPitch = viewer.camera.pitch;
        const savedRoll = viewer.camera.roll;

        viewer.imageryLayers.remove(activeDemDrapeLayer, false);
        activeDemDrapeLayer = null;

        const drapeProvider = new Cesium.UrlTemplateImageryProvider({
          url: newDrapeUrl,
          maximumLevel: maxLevel,
          minimumLevel: minLevel,
          tilingScheme: new Cesium.WebMercatorTilingScheme(),
          enablePickFeatures: false,
          rectangle: rectangle,
        });
        activeDemDrapeLayer = viewer.imageryLayers.addImageryProvider(drapeProvider);
        activeDemDrapeLayer.alpha = 1.0;
        activeDemDrapeLayer.show = activeDemContext.visible !== false;
        activeDemDrapeUrl = newDrapeUrl;

        // Raise hillshade and managed layers above the new drape
        if (activeDemHillshadeLayer) viewer.imageryLayers.raiseToTop(activeDemHillshadeLayer);
        for (const layer of managedImageryLayers.values()) {
          if (layer && layer.show && viewer.imageryLayers.indexOf(layer) >= 0) {
            viewer.imageryLayers.raiseToTop(layer);
          }
        }

        // Lock camera for 3 frames — imagery layer ops can trigger minor camera drift
        let framesLeft = 3;
        const lockHandle = viewer.scene.postRender.addEventListener(function () {
          viewer.camera.setView({
            destination: savedPos,
            orientation: { heading: savedHdg, pitch: savedPitch, roll: savedRoll },
          });
          framesLeft -= 1;
          if (framesLeft <= 0) lockHandle();
        });

        updateBasemapBlendForCurrentMode();
        requestSceneRender();
        log("debug", "setDemColorMode: in-place drape swap colormap=" + normalized);

        // Update colorbar gradient to match new color mode
        const range = parseDemHeightRange(activeDemContext.options);
        updateDemColorbar(range.min, range.max, activeDemContext.options);
      }
    } else {
      // No active drape layer yet — do a full apply
      applyDemLayer();
    }
  }

  function initBridge() {
    if (typeof QWebChannel === "undefined" || !window.qt || !qt.webChannelTransport) {
      setStatus("Bridge unavailable, running standalone Cesium mode.");
      log("warn", "QWebChannel transport unavailable; initializing viewer without bridge binding");
      initViewer();
      return;
    }
    new QWebChannel(qt.webChannelTransport, function (channel) {
      bridge = channel.objects.bridge;
      setStatus("Bridge connected.");
      log("info", "QWebChannel bridge connected");
      initViewer();
    });
  }

  function initViewer() {
    if (!window.Cesium) {
      setStatus("Cesium.js not found. Add local Cesium assets under web_assets/cesium.");
      log("error", "Cesium runtime not found");
      return;
    }
    const naturalEarth = createNaturalEarthProvider();
    viewer = new Cesium.Viewer("cesiumContainer", {
      imageryProvider: naturalEarth,
      baseLayerPicker: false,
      geocoder: false,
      navigationHelpButton: false,
      sceneModePicker: false,
      homeButton: false,
      fullscreenButton: false,
      infoBox: false,
      selectionIndicator: false,
      scene3DOnly: false,
      requestRenderMode: false,
      maximumRenderTimeChange: 0.0,
      timeline: false,
      animation: false,
      terrainProvider: new Cesium.EllipsoidTerrainProvider(),
      orderIndependentTranslucency: false,
      contextOptions: {
        webgl: {
          alpha: false,
          depth: true,
          stencil: false,
          antialias: true,
          powerPreference: "high-performance",
          preserveDrawingBuffer: false,
          failIfMajorPerformanceCaveat: false,
        },
      },
    });
    baseTerrainProvider = viewer.terrainProvider;
    fallbackBasemapLayer = viewer.imageryLayers.get(0);
    const devicePixelRatio = window.devicePixelRatio || 1.0;
    viewer.resolutionScale = Math.min(devicePixelRatio, 1.25);
    viewer.scene.postProcessStages.fxaa.enabled = false;
    viewer.scene.globe.baseColor = Cesium.Color.BLACK;
    viewer.scene.backgroundColor = Cesium.Color.BLACK;
    viewer.canvas.style.backgroundColor = "#000000";
    applyDefaultSceneSettings();
    tuneCameraController();
    applyDefaultStartupFocus();
    let lastErrorMessage = "";
    let lastErrorTime = 0;
    window.addEventListener("error", function (event) {
      // Ignore errors from Cesium.js itself
      if (event && event.filename && event.filename.includes("Cesium.js")) {
        return;
      }
      const msg = event && event.message ? event.message : "unknown";
      const now = Date.now();
      // Suppress duplicate errors within 1 second
      if (msg === lastErrorMessage && now - lastErrorTime < 1000) {
        return;
      }
      lastErrorMessage = msg;
      lastErrorTime = now;
      const err = event && event.error ? event.error : null;
      const stack = err && err.stack ? err.stack : "";
      log("error", "Window error: " + msg + (stack ? " | " + stack : ""));
    });
    window.addEventListener("unhandledrejection", function (event) {
      const reason = event && event.reason ? String(event.reason) : "unknown";
      log("error", "Unhandled promise rejection: " + reason);
    });

    setup2DWheelZoomFallback();
    baseTerrainReadyPromise = attachOfflineTerrainPack();
    void attachLocalSatelliteBasemap();
    if (SHOW_COUNTRY_BOUNDARY_OVERLAY) {
      void attachCountryBoundaryOverlay();
    }
    viewer.imageryLayers.layerAdded.addEventListener(function (_layer, index) {
      log("info", "Imagery layer added at index " + index);
    });
    viewer.scene.morphStart.addEventListener(function (_transitioner, oldMode, newMode) {
      sceneDebug(
        "morphStart oldMode=" +
          oldMode +
          " newMode=" +
          newMode +
          " currentSceneMode=" +
          currentSceneMode +
          " pendingSceneModeAfterMorph=" +
          String(pendingSceneModeAfterMorph)
      );
    });
    viewer.scene.morphComplete.addEventListener(function () {
      const resolvedMode = detectSceneMode();
      sceneDebug(
        "morphComplete resolvedMode=" +
          resolvedMode +
          " current(before)=" +
          currentSceneMode +
          " pendingSceneModeAfterMorph=" +
          String(pendingSceneModeAfterMorph) +
          " pendingFlyThroughBounds=" +
          String(Boolean(pendingFlyThroughBounds)) +
          " pendingFocusAfterMorph=" +
          String(pendingFocusAfterMorph)
      );
      currentSceneMode = resolvedMode === "morphing" ? currentSceneMode : resolvedMode;
      syncSceneModeToggle(currentSceneMode);
      configureCameraControllerForMode(currentSceneMode);
      if (pendingSceneModeAfterMorph) {
        const nextMode = pendingSceneModeAfterMorph;
        pendingSceneModeAfterMorph = null;
        sceneDebug("morphComplete applying queued mode=" + nextMode + " from current=" + currentSceneMode);
        if (nextMode !== currentSceneMode) {
          setSceneModeInternal(nextMode);
          return;
        }
      }
      if (pendingFlyThroughBounds && currentSceneMode === "3d") {
        const queuedBounds = pendingFlyThroughBounds;
        pendingFlyThroughBounds = null;
        pendingFocusAfterMorph = false;
        pendingTerrainSceneAfterMorph = false;
        pendingFocusBounds = null;
        startFlyThroughBounds(queuedBounds.west, queuedBounds.south, queuedBounds.east, queuedBounds.north);
        return;
      }
      if (pendingFocusAfterMorph) {
        pendingFocusAfterMorph = false;
        if (pendingTerrainSceneAfterMorph) {
          pendingTerrainSceneAfterMorph = false;
          sceneDebug("morphComplete dispatching deferred 3D focus");
          schedule3DFocusAfterMorph(1.0);
        } else {
          sceneDebug("morphComplete dispatching 2D focus");
          focusPreferredRegion(0.8);
        }
        pendingFocusBounds = null;
      }
    });
    viewer.scene.postRender.addEventListener(updateEdgeScaleWidgets);
    wireClickHandlers();
    wireStatusBarListeners();
    
    // Force a few initial renders to ensure the globe paints even in
    // constrained QtWebEngine environments.
    viewer.scene.requestRender();
    window.requestAnimationFrame(function () {
      viewer.scene.requestRender();
      window.requestAnimationFrame(function () {
        viewer.scene.requestRender();
        // After initial paint, switch to on-demand rendering for performance.
        // Use maximumRenderTimeChange=0 so any scene change triggers re-render.
        viewer.scene.requestRenderMode = true;
        viewer.scene.maximumRenderTimeChange = 0.0;
      });
    });
    setStatus("Offline Cesium initialized.");
    log("info", "Viewer initialized with local offline basemap pipeline");
  }

  function setup2DWheelZoomFallback() {
    if (!viewer || !viewer.canvas || has2DWheelZoomFallback) {
      return;
    }
    viewer.canvas.addEventListener(
      "wheel",
      function (event) {
        if (!viewer || currentSceneMode !== "2d") {
          return;
        }
        const delta = Number(event.deltaY);
        if (!Number.isFinite(delta) || delta === 0) {
          return;
        }
        event.preventDefault();
        const cartographic = viewer.camera.positionCartographic;
        const currentHeight = cartographic && Number.isFinite(cartographic.height) ? cartographic.height : 5000000.0;
        const zoomAmount = Math.max(100.0, currentHeight * 0.18);
        if (delta > 0) {
          viewer.camera.zoomOut(zoomAmount);
        } else {
          viewer.camera.zoomIn(zoomAmount);
        }
        viewer.scene.requestRender();
      },
      { passive: false }
    );
    has2DWheelZoomFallback = true;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: Basemap & OSM Tiles  →  future: modules/basemap.js
  // Functions: createNaturalEarthProvider, attachLocalSatelliteBasemap,
  //   attachOfflineFallbackBasemap, ensureFallbackBasemapLayer,
  //   updateBasemapBlendForCurrentMode, attachOfflineTerrainPack,
  //   clearPolarCapLayers, ensurePolarCapLayers
  // ═══════════════════════════════════════════════════════════════════════════

  async function attachOfflineTerrainPack() {
    if (!viewer) return false;
    return false;
  }

  async function ensureBaseTerrainReady() {
    try {
      await baseTerrainReadyPromise;
    } catch (_error) {
      // Keep runtime resilient; fallback terrain provider remains available.
    }
  }

  async function attachCountryBoundaryOverlay() {
    if (!viewer || countryBoundaryDataSource) {
      return false;
    }
    try {
      const dataSource = await Cesium.GeoJsonDataSource.load(COUNTRY_BOUNDARY_GEOJSON_URL, {
        clampToGround: false,
      });
      viewer.dataSources.add(dataSource);
      const boundaryColor = Cesium.Color.fromCssColorString("#e7edf7").withAlpha(0.72);
      dataSource.entities.values.forEach(function (entity) {
        if (!entity.polyline) {
          return;
        }
        entity.polyline.clampToGround = false;
        entity.polyline.arcType = Cesium.ArcType.GEODESIC;
        entity.polyline.width = 1.3;
        entity.polyline.material = boundaryColor;
        entity.polyline.depthFailMaterial = boundaryColor.withAlpha(0.62);
      });
      countryBoundaryDataSource = dataSource;
      viewer.scene.requestRender();
      log("info", "Offline country-boundary overlay loaded.");
      return true;
    } catch (error) {
      if (looksLikeMissingLocalAssetError(error)) {
        log("info", "No offline country-boundary overlay found.");
        return false;
      }
      log("warn", "Offline country-boundary overlay could not be loaded: " + String(error));
      return false;
    }
  }

  function createNaturalEarthProvider(rectangle) {
    return new Cesium.UrlTemplateImageryProvider({
      url: Cesium.buildModuleUrl("Assets/Textures/NaturalEarthII/{z}/{x}/{reverseY}.jpg"),
      tilingScheme: new Cesium.GeographicTilingScheme(),
      maximumLevel: 2,
      enablePickFeatures: false,
      rectangle: rectangle || undefined,
      credit: "NaturalEarthII (offline fallback)",
    });
  }

  function clearPolarCapLayers() {
    if (!viewer) return;
    if (northPolarCapLayer) {
      viewer.imageryLayers.remove(northPolarCapLayer, false);
      northPolarCapLayer = null;
    }
    if (southPolarCapLayer) {
      viewer.imageryLayers.remove(southPolarCapLayer, false);
      southPolarCapLayer = null;
    }
  }

  function ensurePolarCapLayers() {
    if (!viewer) return;
    const url = Cesium.buildModuleUrl("Assets/Textures/NaturalEarthII/{z}/{x}/{reverseY}.jpg");
    const tilingScheme = new Cesium.GeographicTilingScheme();
    const fallbackDataUrl = createSolidPolarCapDataUrl();
    if (!northPolarCapLayer) {
      let northProvider;
      try {
        northProvider = new Cesium.UrlTemplateImageryProvider({
          url: url,
          tilingScheme: tilingScheme,
          maximumLevel: 2,
          enablePickFeatures: false,
          rectangle: Cesium.Rectangle.fromDegrees(-180.0, WEB_MERCATOR_SAFE_EDGE_LAT_DEGREES, 180.0, 90.0),
          credit: "NaturalEarthII (polar fallback)",
        });
      } catch (_error) {
        northProvider = new Cesium.SingleTileImageryProvider({
          url: fallbackDataUrl,
          rectangle: Cesium.Rectangle.fromDegrees(-180.0, WEB_MERCATOR_SAFE_EDGE_LAT_DEGREES, 180.0, 90.0),
          credit: "Polar cap fallback",
        });
      }
      northPolarCapLayer = viewer.imageryLayers.addImageryProvider(northProvider, 2);
      northPolarCapLayer.alpha = 1.0;
    }
    if (!southPolarCapLayer) {
      let southProvider;
      try {
        southProvider = new Cesium.UrlTemplateImageryProvider({
          url: url,
          tilingScheme: tilingScheme,
          maximumLevel: 2,
          enablePickFeatures: false,
          rectangle: Cesium.Rectangle.fromDegrees(-180.0, -90.0, 180.0, -WEB_MERCATOR_SAFE_EDGE_LAT_DEGREES),
          credit: "NaturalEarthII (polar fallback)",
        });
      } catch (_error) {
        southProvider = new Cesium.SingleTileImageryProvider({
          url: fallbackDataUrl,
          rectangle: Cesium.Rectangle.fromDegrees(-180.0, -90.0, 180.0, -WEB_MERCATOR_SAFE_EDGE_LAT_DEGREES),
          credit: "Polar cap fallback",
        });
      }
      southPolarCapLayer = viewer.imageryLayers.addImageryProvider(southProvider, 2);
      southPolarCapLayer.alpha = 1.0;
    }
    viewer.imageryLayers.raiseToTop(northPolarCapLayer);
    viewer.imageryLayers.raiseToTop(southPolarCapLayer);
  }

  function attachOfflineFallbackBasemap(reason) {
    if (!viewer) return;
    if (globalBasemapLayer) {
      viewer.imageryLayers.remove(globalBasemapLayer, false);
      globalBasemapLayer = null;
    }
    clearPolarCapLayers();
    if (!fallbackBasemapLayer) {
      const provider = createNaturalEarthProvider();
      fallbackBasemapLayer = viewer.imageryLayers.addImageryProvider(provider, 0);
    }
    setStatus(reason || "Using offline fallback basemap.");
    log("warn", reason || "Offline XYZ basemap unavailable, using built-in fallback basemap.");
  }

  function ensureFallbackBasemapLayer() {
    if (!viewer) return;
    // If OSM basemap is already active, no fallback needed
    if (globalBasemapLayer) return;
    if (fallbackBasemapLayer) return;
    const provider = createNaturalEarthProvider();
    fallbackBasemapLayer = viewer.imageryLayers.addImageryProvider(provider, 0);
  }

  async function attachLocalSatelliteBasemap() {
    if (!viewer) return;

    // Probe zoom-0 tile using Cesium.Resource — works on file:// (fetch API does not).
    const probeUrl = `${LOCAL_SATELLITE_TILE_ROOT}/0/0/0.png`;
    let osmAvailable = false;
    try {
      const resource = new Cesium.Resource({ url: probeUrl });
      const blob = await resource.fetchBlob();
      osmAvailable = blob !== undefined && blob !== null;
    } catch (_) {
      osmAvailable = false;
    }

    if (!osmAvailable) {
      log("warn", "Local OSM tiles not found at " + probeUrl + " — using Natural Earth basemap");
      setStatus("Basemap: Natural Earth (offline)");
      return;
    }

    // OSM tiles confirmed present.
    // Remove the Natural Earth layer that was set as the initial imageryProvider.
    if (fallbackBasemapLayer) {
      viewer.imageryLayers.remove(fallbackBasemapLayer, true);
      fallbackBasemapLayer = null;
    }
    if (globalBasemapLayer) {
      viewer.imageryLayers.remove(globalBasemapLayer, true);
      globalBasemapLayer = null;
    }

    // LOCAL_SATELLITE_DEFAULT_MAX_LEVEL is the highest zoom we have tiles for (8).
    // For ultra-high-resolution data (3-4 cm, zoom 20-22) we set maximumLevel to 22
    // so Cesium keeps requesting tiles at deep zoom. The provider will serve the
    // highest available tile (zoom 8) stretched — blurry but never blank.
    // When your actual DEM/imagery layers are loaded they render on top at full res.
    const OSM_TILE_MAX_LEVEL = LOCAL_SATELLITE_DEFAULT_MAX_LEVEL;  // tiles on disk
    const OSM_DISPLAY_MAX_LEVEL = 22;                              // allow zoom to 3-4 cm

    // Build a URL template that clamps the zoom level to OSM_TILE_MAX_LEVEL.
    // Cesium's UrlTemplateImageryProvider supports a customTags map where each
    // tag is a function(imageryProvider, x, y, level) → string.
    // We use a custom {zc} tag that clamps level to the max tile we have on disk,
    // so deep-zoom requests reuse the zoom-8 tile (stretched) instead of 404-ing.
    const osmProvider = new Cesium.UrlTemplateImageryProvider({
      url: `${LOCAL_SATELLITE_TILE_ROOT}/{zc}/{x}/{y}.png`,
      customTags: {
        zc: function (_provider, _x, _y, level) {
          return String(Math.min(level, OSM_TILE_MAX_LEVEL));
        },
      },
      tilingScheme: new Cesium.WebMercatorTilingScheme(),
      minimumLevel: 0,
      maximumLevel: OSM_DISPLAY_MAX_LEVEL,
      // Restrict to Asia coverage so Cesium never requests tiles outside the downloaded area
      rectangle: Cesium.Rectangle.fromDegrees(25.0, -12.0, 180.0, 82.0),
      credit: new Cesium.Credit("© OpenStreetMap contributors", false),
      enablePickFeatures: false,
    });

    // Insert at index 0 — the absolute bottom of the layer stack
    globalBasemapLayer = viewer.imageryLayers.addImageryProvider(osmProvider, 0);
    globalBasemapLayer.alpha = 1.0;

    setStatus("Basemap: OpenStreetMap (offline)");
    log("info", "OSM basemap loaded tiles_max=" + OSM_TILE_MAX_LEVEL + " display_max=" + OSM_DISPLAY_MAX_LEVEL);
    requestSceneRender();
  }

  function readLabelText(labelEntity) {
    if (!labelEntity || !labelEntity.label || !labelEntity.label.text) {
      return "";
    }
    if (typeof labelEntity.label.text.getValue === "function") {
      return String(labelEntity.label.text.getValue(Cesium.JulianDate.now()) || "");
    }
    return String(labelEntity.label.text || "");
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: Annotations  →  future: modules/annotations.js
  // Functions: setAnnotationEditIconHoverState, renameAnnotationFromEditIcon,
  //   updateAnnotationHover, clearAnnotationEntities, setAnnotationVisibility
  // ═══════════════════════════════════════════════════════════════════════════

  function setAnnotationEditIconHoverState(editEntity, hovered) {
    if (!editEntity || !editEntity.billboard) {
      return;
    }
    editEntity.billboard.color = hovered ? Cesium.Color.WHITE.withAlpha(0.96) : Cesium.Color.WHITE.withAlpha(0.42);
  }

  function renameAnnotationFromEditIcon(editEntity) {
    if (!editEntity || editEntity._annotationRole !== "edit") {
      return false;
    }
    const labelEntity = editEntity._annotationLabelEntity || null;
    if (!labelEntity || !labelEntity.label) {
      return false;
    }
    const currentText = readLabelText(labelEntity) || "Point";
    const nextText = window.prompt("Rename point", currentText);
    if (nextText === null) {
      return true;
    }
    const cleaned = String(nextText).trim();
    if (!cleaned) {
      return true;
    }
    labelEntity.label.text = cleaned;
    setStatus("Point renamed: " + cleaned);
    requestSceneRender();
    return true;
  }

  function updateAnnotationHover(screenPosition) {
    if (!viewer || !screenPosition) {
      return;
    }
    const picked = viewer.scene.pick(screenPosition);
    const nextHover = picked && picked.id && picked.id._annotationRole === "edit" ? picked.id : null;
    if (hoveredAnnotationEditEntity === nextHover) {
      return;
    }
    if (hoveredAnnotationEditEntity) {
      setAnnotationEditIconHoverState(hoveredAnnotationEditEntity, false);
    }
    hoveredAnnotationEditEntity = nextHover;
    if (hoveredAnnotationEditEntity) {
      setAnnotationEditIconHoverState(hoveredAnnotationEditEntity, true);
    }
    requestSceneRender();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: Status Bar Bridge Emitters  →  future: modules/ui.js
  // Functions: emitMouseCoordinates, emitCameraChanged,
  //   wireStatusBarListeners, _updateCompass
  // ═══════════════════════════════════════════════════════════════════════════

  // ── Status-bar bridge emitters (QGIS-style) ──────────────────────────────
  function emitMouseCoordinates(lon, lat, screenPosition) {
    if (!bridge || !bridge.on_mouse_coordinates) return;
    const now = Date.now();
    if (now - _sbLastCoordEmitMs < _SB_COORD_THROTTLE_MS) return;
    _sbLastCoordEmitMs = now;
    
    // Sample terrain elevation ONLY when cursor is actually over DEM terrain
    let elevM = -9999;
    try {
      if (viewer && viewer.scene && viewer.scene.globe && viewer.terrainProvider && screenPosition) {
        // Check if we have actual DEM terrain (not just ellipsoid)
        const hasRealTerrain = viewer.terrainProvider && 
                               viewer.terrainProvider.constructor.name !== 'EllipsoidTerrainProvider' &&
                               !(viewer.terrainProvider instanceof Cesium.EllipsoidTerrainProvider);
        
        if (hasRealTerrain) {
          // Use scene.globe.pick to check if cursor is actually over terrain surface
          const ray = viewer.camera.getPickRay(screenPosition);
          if (ray) {
            const pickedPosition = viewer.scene.globe.pick(ray, viewer.scene);
            // Only sample elevation if we actually picked the globe surface (not ellipsoid fallback)
            if (pickedPosition) {
              const carto = Cesium.Cartographic.fromDegrees(lon, lat);
              const sampled = viewer.scene.globe.getHeight(carto);
              if (typeof sampled === "number" && Number.isFinite(sampled)) {
                elevM = sampled;
              }
            }
          }
        }
      }
    } catch (_) {}
    bridge.on_mouse_coordinates(lon, lat, elevM);
  }

  function emitCameraChanged() {
    if (!bridge || !bridge.on_camera_changed || !viewer || !viewer.camera) return;
    try {
      // Compute approximate scale denominator from camera altitude + canvas size
      const height = viewer.camera.positionCartographic.height;
      const canvas = viewer.canvas;
      const fovY = viewer.camera.frustum.fovy || 1.0472;
      const visibleMeters = 2.0 * height * Math.tan(fovY * 0.5);
      const pixelHeight = canvas.clientHeight || 1;
      const metersPerPixel = visibleMeters / pixelHeight;
      // 96 dpi screen: 1 pixel ≈ 0.000265 m physical → scale = mPx / 0.000265
      const scaleDenom = metersPerPixel / 0.000265;

      let headingDeg = Cesium.Math.toDegrees(viewer.camera.heading);
      if (headingDeg < 0) headingDeg += 360.0;
      bridge.on_camera_changed(scaleDenom, headingDeg);
    } catch (_) {}
  }

  function wireStatusBarListeners() {
    if (!viewer || !viewer.scene) return;
    // Camera moved → update scale + heading + start tile loading monitor
    viewer.camera.changed.addEventListener(function() {
      emitCameraChanged();
      _updateCompass();
      if (!_tileLoadingActive) {
        startTileLoadingMonitor();
      }
    });
    viewer.camera.moveEnd.addEventListener(function() {
      emitCameraChanged();
      _updateCompass();
      if (!_tileLoadingActive) {
        startTileLoadingMonitor();
      }
    });

    // Re-apply terrainExaggeration after every tile load batch.
    // Cesium 1.78 resets globe.terrainExaggeration when new terrain tiles are decoded.
    // Also drive the progress bar from this native event — accurate, zero polling lag.
    viewer.scene.globe.tileLoadProgressEvent.addEventListener(function (queueLength) {
      // Terrain exaggeration persistence
      if (queueLength === 0 && activeDemContext && activeDemContext.visible !== false) {
        const target = Math.max(0.1, demVisual.exaggeration);
        if (Math.abs(viewer.scene.globe.terrainExaggeration - target) > 0.001) {
          viewer.scene.globe.terrainExaggeration = target;
        }
      }

      // Real-time progress bar — driven by native tile queue length
      if (queueLength > 0) {
        _tileQueuePeak = Math.max(_tileQueuePeak, queueLength);
        const loaded = _tileQueuePeak - queueLength;
        const percent = _tileQueuePeak > 0 ? Math.min(95, Math.round((loaded / _tileQueuePeak) * 100)) : 10;
        emitLoadingProgress(percent, "Loading tiles");
        _tileLoadingActive = true;
        // Cancel any pending drain timer — queue is still active
        if (_tileQueuePeak > 0 && typeof _tileDrainTimer !== 'undefined' && _tileDrainTimer) {
          clearTimeout(_tileDrainTimer);
          _tileDrainTimer = null;
        }
      } else if (_tileLoadingActive) {
        // Queue drained — debounce the completion signal by 200 ms so a
        // rapid new-layer load doesn't cause a 100 → 0 flash on the bar.
        if (typeof _tileDrainTimer === 'undefined' || !_tileDrainTimer) {
          _tileDrainTimer = setTimeout(function () {
            _tileDrainTimer = null;
            if (!_tileLoadingActive) return;
            emitLoadingProgress(100, "Complete");
            _tileLoadingActive = false;
            _tileQueuePeak = 0;
          }, 200);
        }
      }
    });
    const compassEl = document.getElementById("compassWidget");
    if (compassEl) {
      compassEl.addEventListener("click", function () {
        if (!viewer) return;
        const bounds = activeTileBounds || lastLoadedBounds;
        if (bounds) {
          // Instant setView — no fly animation, microsecond response
          const rect = Cesium.Rectangle.fromDegrees(bounds.west, bounds.south, bounds.east, bounds.north);
          viewer.camera.cancelFlight();
          viewer.camera.setView({
            destination: rect,
            orientation: { heading: 0.0, pitch: Cesium.Math.toRadians(-90), roll: 0.0 },
          });
        } else {
          // No asset — snap North-up instantly
          viewer.camera.cancelFlight();
          viewer.camera.setView({
            destination: viewer.camera.position.clone(),
            orientation: { heading: 0.0, pitch: viewer.camera.pitch, roll: 0.0 },
          });
        }
        requestSceneRender();
        log("info", "Compass clicked: instant North-up focus");
      });
    }

    // rAF loop for fluid compass rotation — runs every frame, zero lag
    (function compassRafLoop() {
      _updateCompass();
      window.requestAnimationFrame(compassRafLoop);
    })();
  }

  function _updateCompass() {
    if (!viewer || !viewer.camera) return;
    const needle = document.getElementById("compassNeedle");
    const nLabel = document.getElementById("compassNLabel");
    if (!needle) return;
    const headingDeg = Cesium.Math.toDegrees(viewer.camera.heading);
    // Use CSS transform for GPU-accelerated rotation — smoother than setAttribute
    needle.style.transform = `rotate(${headingDeg.toFixed(2)}deg)`;
    needle.style.transformOrigin = "32px 32px";
    if (nLabel) {
      nLabel.style.transform = `rotate(${(-headingDeg).toFixed(2)}deg)`;
      nLabel.style.transformOrigin = "32px 20px";
    }
  }

  function wireClickHandlers() {
    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction(function (movement) {
      const picked = movement && movement.position ? viewer.scene.pick(movement.position) : null;
      if (picked && picked.id && picked.id._annotationRole === "edit") {
        if (renameAnnotationFromEditIcon(picked.id)) {
          return;
        }
      }

      // Try multiple picking strategies to guarantee a coordinate.
      // Strategy 1: globe.pick (works on terrain surface)
      // Strategy 2: scene.pickPosition (works on 3D tiles and terrain)
      // Strategy 3: pickEllipsoid (always works, ignores terrain height)
      let lonLat = null;
      let clickCartesian = null;

      if (movement && movement.position) {
        // Strategy 1: scene.pickPosition — uses depth buffer, most accurate at any zoom
        // This correctly handles high-resolution imagery where terrain mesh may lag
        if (viewer.scene.pickPositionSupported) {
          try {
            const depthCart = viewer.scene.pickPosition(movement.position);
            if (depthCart && Cesium.Cartesian3.magnitude(depthCart) > 1.0) {
              clickCartesian = depthCart;
            }
          } catch (_) {}
        }

        // Strategy 2: globe.pick via ray (works on terrain surface when depth unavailable)
        if (!clickCartesian) {
          const ray = viewer.camera.getPickRay(movement.position);
          if (ray) {
            clickCartesian = viewer.scene.globe.pick(ray, viewer.scene);
          }
        }

        // Strategy 3: ellipsoid fallback (always succeeds, ignores terrain height)
        if (!clickCartesian) {
          clickCartesian = viewer.camera.pickEllipsoid(
            movement.position,
            viewer.scene.globe.ellipsoid
          );
        }

        if (clickCartesian) {
          lonLat = cartesianToLonLat(clickCartesian);
          lastMapClickCartesian = Cesium.Cartesian3.clone(clickCartesian);
        }
      }

      if (!lonLat) {
        log("warn", "Click: could not resolve lon/lat from any picking strategy");
        return;
      }
      const lon = lonLat.lon;
      const lat = lonLat.lat;

      if (searchDrawMode === "polygon") {
        if (searchPolygonLocked) {
          setStatus("Polygon restored. Clear geometry to start a new polygon.");
          return;
        }
        searchPolygonPoints.push({ lon: lon, lat: lat });
        searchCursorPoint = null;
        updateSearchPolygonPreview();
        setStatus("Polygon draw: continue points, right-click or Finish to close");
        return;
      }

      if (distanceMeasureModeEnabled) {
        try {
          emitMapClick(lon, lat);
          log("info", "Distance mode click lon=" + lon.toFixed(6) + " lat=" + lat.toFixed(6));
          if (!distanceMeasureAnchor) {
            // First click: set anchor
            distanceMeasureAnchor = { lon: lon, lat: lat };
            clickedPoints.length = 0;
            clickedPoints.push([lon, lat]);
            clearMeasurementEntities();
            clearMeasurementPreviewEntities();
            setStatus("Distance tool: move cursor and click second point to finalize.");
            return;
          }

          // Second click: finalize measurement, clear anchor (stop chaining)
          const geodesic = new Cesium.EllipsoidGeodesic(
            Cesium.Cartographic.fromDegrees(distanceMeasureAnchor.lon, distanceMeasureAnchor.lat),
            Cesium.Cartographic.fromDegrees(lon, lat)
          );
          let azDegrees = Cesium.Math.toDegrees(geodesic.startHeading);
          if (azDegrees < 0) azDegrees += 360.0;
          clearMeasurementPreviewEntities();
          updateMeasurementEntities(
            distanceMeasureAnchor.lon,
            distanceMeasureAnchor.lat,
            lon,
            lat,
            geodesic.surfaceDistance,
            azDegrees
          );
          distanceMeasureAnchor = null;  // reset so next click starts fresh
          const _dist = geodesic.surfaceDistance;
          setTimeout(function() { emitMeasurementUpdated(_dist); }, 0);
          setStatus("Distance measured. Click to start a new measurement, or right-click to stop.");
          log("info", "Distance measured (m): " + geodesic.surfaceDistance.toFixed(2));
        } catch (e) {
          log("error", "Distance measurement error: " + (e.message || String(e)));
        }
        return;
      }

      clickedPoints.push([lon, lat]);
      if (clickedPoints.length > 2) clickedPoints.shift();

      // Fill-volume label expand/collapse — handled here in the persistent handler
      // to avoid creating/destroying ScreenSpaceEventHandler per analysis (macOS crash).
      if (window._fillVolumeEntities && window._fillVolumeEntities.length > 0) {
        var picked2 = viewer.scene.pick(movement.position);
        if (Cesium.defined(picked2) && Cesium.defined(picked2.id)) {
          var ent2 = picked2.id;
          if (ent2.isRegionLabel === true && ent2.detailsEntity) {
            var det = ent2.detailsEntity;
            var wasExpanded = ent2.expanded;
            det.label.show = !wasExpanded;
            ent2.expanded = !wasExpanded;
            ent2.label.text = (wasExpanded ? '\u25bc' : '\u25b2') + ' Region ' + ent2.regionId;
            requestSceneRender();
            return;
          }
        }
      }

      emitMapClick(lon, lat);
      log("debug", "Map click lon=" + lon.toFixed(6) + " lat=" + lat.toFixed(6));
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

    handler.setInputAction(function (movement) {
      if (movement && movement.endPosition) {
        lastSearchCursorScreenPosition = movement.endPosition;
        updateAnnotationHover(movement.endPosition);
      }
      if (distanceMeasureModeEnabled && distanceMeasureAnchor && searchDrawMode !== "polygon") {
        try {
          // Use pickEllipsoid as guaranteed fallback for preview over terrain
          let lonLat = getLonLatFromScreen(movement.endPosition);
          if (!lonLat && movement.endPosition) {
            const ellipsoidCart = viewer.camera.pickEllipsoid(movement.endPosition, viewer.scene.globe.ellipsoid);
            if (ellipsoidCart) lonLat = cartesianToLonLat(ellipsoidCart);
          }
          if (lonLat) {
            const geodesic = new Cesium.EllipsoidGeodesic(
              Cesium.Cartographic.fromDegrees(distanceMeasureAnchor.lon, distanceMeasureAnchor.lat),
              Cesium.Cartographic.fromDegrees(lonLat.lon, lonLat.lat)
            );
            let azDegrees = Cesium.Math.toDegrees(geodesic.startHeading);
            if (azDegrees < 0) azDegrees += 360.0;
            updateMeasurementPreview(
              distanceMeasureAnchor.lon,
              distanceMeasureAnchor.lat,
              lonLat.lon,
              lonLat.lat,
              geodesic.surfaceDistance,
              azDegrees
            );
          }
        } catch (e) {
          // Silently ignore preview errors to avoid spam
        }
      }
      
      // Always emit mouse coordinates for status bar (not just during polygon drawing)
      const lonLat = getLonLatFromScreen(movement.endPosition);
      if (lonLat) {
        emitMouseCoordinates(lonLat.lon, lonLat.lat, movement.endPosition);
      }

      // Live rubber-band line for elevation profile mode — mirrors distance tool approach
      if (window._profileModeActive && window._profileStartLon !== undefined) {
        try {
          let profileLonLat = getLonLatFromScreen(movement.endPosition);
          if (!profileLonLat && movement.endPosition) {
            const ellipsoidCart = viewer.camera.pickEllipsoid(movement.endPosition, viewer.scene.globe.ellipsoid);
            if (ellipsoidCart) profileLonLat = cartesianToLonLat(ellipsoidCart);
          }
          if (profileLonLat) {
            _updateProfilePreviewLine(
              window._profileStartLon, window._profileStartLat,
              profileLonLat.lon, profileLonLat.lat
            );
          }
        } catch (e) {
          // Silently ignore preview errors
        }
      }

      // Georeferenced cursor: project mouse onto completed profile line → emit fraction
      if (window._profileLineActive &&
          window._profileLineLon1 !== undefined && window._profileLineLon2 !== undefined) {
        try {
          let cursorLonLat = getLonLatFromScreen(movement.endPosition);
          if (!cursorLonLat && movement.endPosition) {
            const ec = viewer.camera.pickEllipsoid(movement.endPosition, viewer.scene.globe.ellipsoid);
            if (ec) cursorLonLat = cartesianToLonLat(ec);
          }
          if (cursorLonLat) {
            // Project cursor onto the geodesic line using Cartesian dot product
            // (accurate for any line length, including ultra-high-res cm-scale data)
            const p1 = Cesium.Cartesian3.fromDegrees(window._profileLineLon1, window._profileLineLat1);
            const p2 = Cesium.Cartesian3.fromDegrees(window._profileLineLon2, window._profileLineLat2);
            const pc = Cesium.Cartesian3.fromDegrees(cursorLonLat.lon, cursorLonLat.lat);
            const v  = Cesium.Cartesian3.subtract(p2, p1, new Cesium.Cartesian3());
            const w  = Cesium.Cartesian3.subtract(pc, p1, new Cesium.Cartesian3());
            const lenSq = Cesium.Cartesian3.dot(v, v);
            let frac = 0.5;
            if (lenSq > 1e-6) {
              frac = Cesium.Cartesian3.dot(w, v) / lenSq;
              frac = Math.max(0.0, Math.min(1.0, frac));
            }
            window._profileCursorFrac = frac;
            // Emit to Python so the Qt panel can draw the cursor crosshair
            if (bridge && bridge.on_profile_cursor) {
              bridge.on_profile_cursor(frac);
            }
            requestSceneRender();
          }
        } catch (e) {
          // Silently ignore
        }
      }
      
      if (searchDrawMode === "polygon") {
        updateSearchCursorOverlay(lastSearchCursorScreenPosition);
      }
      if (movement && movement.endPosition && _measureCursorOverlay && _measureCursorOverlay.style.display !== "none") {
        updateMeasureCursorOverlay(movement.endPosition);
      }
      if (searchDrawMode !== "polygon" || searchPolygonPoints.length === 0) {
        return;
      }
      // Update search polygon preview during drawing
      if (lonLat) {
        searchCursorPoint = { lon: lonLat.lon, lat: lonLat.lat };
        updateSearchPolygonPreview();
      }
    }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

    handler.setInputAction(function () {
      if (searchDrawMode === "polygon") {
        window.offlineGIS.finishSearchPolygon();
        return;
      }
      if (distanceMeasureModeEnabled) {
        setDistanceMeasureMode(false);
        log("info", "Distance measure mode ended by right-click");
      }
    }, Cesium.ScreenSpaceEventType.RIGHT_CLICK);

    viewer.canvas.addEventListener("mouseenter", function () {
      if (searchDrawMode === "polygon") {
        setSearchCursorOverlayVisible(true);
      }
      if (_measureCursorOverlay && _measureCursorStyleEl && _measureCursorStyleEl.textContent) {
        setMeasureCursorOverlayVisible(true);
      }
    });

    viewer.canvas.addEventListener("mouseleave", function () {
      setSearchCursorOverlayVisible(false);
      setMeasureCursorOverlayVisible(false);
      if (hoveredAnnotationEditEntity) {
        setAnnotationEditIconHoverState(hoveredAnnotationEditEntity, false);
        hoveredAnnotationEditEntity = null;
      }
      // Clear status bar coordinates when cursor leaves the map
      if (bridge && bridge.on_mouse_coordinates) {
        bridge.on_mouse_coordinates(0, 0, -9999);
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: Measurement Tools  →  future: modules/measurement.js
  // Functions: setDistanceMeasureMode, _enforceMeasureCursor,
  //   updateMeasurementPreview, updateMeasurementEntities,
  //   clearMeasurementEntities, clearMeasurementPreviewEntities,
  //   updateDistanceScaleOverlay, clearDistanceScaleOverlay
  // ═══════════════════════════════════════════════════════════════════════════

  function updatePolygonPreviewVisibility() {
    const visible = polygonVisibilityEnabled && searchOverlayVisible;
    if (searchCursorEntity) {
      searchCursorEntity.show = visible;
    }
    if (searchPreviewLineEntity && searchPreviewLineEntity.polyline) {
      searchPreviewLineEntity.polyline.show = visible && searchPolygonPoints.length >= 2;
    }
    if (searchPreviewPolygonEntity && searchPreviewPolygonEntity.polygon) {
      searchPreviewPolygonEntity.polygon.show = visible && searchPolygonPoints.length >= 3;
    }
    if (searchAreaLabelEntity && searchAreaLabelEntity.label) {
      searchAreaLabelEntity.label.show = visible && searchPolygonPoints.length >= 3;
    }
    if (searchPreviewLineEntity || searchPreviewPolygonEntity || searchAreaLabelEntity) {
      requestSceneRender();
    }
  }

  function setPolygonPreviewVisible(visible) {
    polygonVisibilityEnabled = Boolean(visible);
    updatePolygonPreviewVisibility();
  }

  function getLonLatFromScreen(screenPosition) {
    return getLonLatFromViewer(viewer, screenPosition);
  }

  function clearSearchEntities() {
    if (searchCursorEntity) {
      viewer.entities.remove(searchCursorEntity);
      searchCursorEntity = null;
    }
    if (searchPreviewLineEntity) {
      viewer.entities.remove(searchPreviewLineEntity);
      searchPreviewLineEntity = null;
    }
    if (searchPreviewPolygonEntity) {
      viewer.entities.remove(searchPreviewPolygonEntity);
      searchPreviewPolygonEntity = null;
    }
    if (searchAreaLabelEntity) {
      viewer.entities.remove(searchAreaLabelEntity);
      searchAreaLabelEntity = null;
    }
    // Clear vertex marker entities
    while (searchVertexEntities.length > 0) {
      const ve = searchVertexEntities.pop();
      if (ve && viewer) {
        viewer.entities.remove(ve);
      }
    }
    requestSceneRender();
  }

  function setAnnotationVisibility(visible) {
    annotationVisibilityEnabled = Boolean(visible);
    for (const entity of annotationEntities) {
      if (entity) {
        entity.show = annotationVisibilityEnabled;
      }
    }
    requestSceneRender();
  }

  function clearMeasurementEntities() {
    if (!viewer) {
      return;
    }
    try {
      if (measurementLineEntity) {
        viewer.entities.remove(measurementLineEntity);
        measurementLineEntity = null;
      }
    } catch (e) {}
    try {
      if (measurementLabelEntity) {
        viewer.entities.remove(measurementLabelEntity);
        measurementLabelEntity = null;
      }
    } catch (e) {}
    clearMeasurementPreviewEntities();
    clearDistanceScaleOverlay();
    requestSceneRender();
  }

  function clearMeasurementPreviewEntities() {
    if (!viewer) {
      return;
    }
    try {
      if (measurementPreviewLineEntity) {
        viewer.entities.remove(measurementPreviewLineEntity);
        measurementPreviewLineEntity = null;
      }
    } catch (e) {}
    try {
      if (measurementPreviewLabelEntity) {
        viewer.entities.remove(measurementPreviewLabelEntity);
        measurementPreviewLabelEntity = null;
      }
    } catch (e) {}
    requestSceneRender();
  }

  // ── Distance Scale Overlay (screen-space ruler) ──
  function ensureDistanceScaleOverlay() {
    if (distanceScaleOverlay || !document.body) {
      return;
    }
    const el = document.createElement("div");
    el.id = "distanceScaleOverlay";
    el.setAttribute("aria-hidden", "true");
    // Container is just a positioning anchor — no overflow clipping
    el.style.cssText = [
      "position:fixed",
      "pointer-events:none",
      "z-index:99999",
      "display:none",
      "overflow:visible",
    ].join(";");

    // The bar — positioned absolutely, rotated via transform on the container
    const barWrap = document.createElement("div");
    barWrap.className = "distScaleBarWrap";
    barWrap.style.cssText = [
      "position:absolute",
      "top:0",
      "left:0",
      "transform-origin:0% 50%",
      "overflow:visible",
    ].join(";");

    const bar = document.createElement("div");
    bar.className = "distScaleBar";
    bar.style.cssText = [
      "height:4px",
      "background:rgba(0,229,255,0.85)",
      "border:1px solid rgba(0,0,0,0.4)",
      "border-radius:2px",
      "box-shadow:0 1px 4px rgba(0,0,0,0.5)",
      "position:relative",
      "min-width:8px",
    ].join(";");
    barWrap.appendChild(bar);

    // Start/end ticks on the bar
    const tickStart = document.createElement("div");
    tickStart.style.cssText = "position:absolute;left:-1px;top:-4px;width:2px;height:12px;background:rgba(0,229,255,0.9);border-radius:1px;";
    bar.appendChild(tickStart);
    const tickEnd = document.createElement("div");
    tickEnd.className = "distScaleTickEnd";
    tickEnd.style.cssText = "position:absolute;right:-1px;top:-4px;width:2px;height:12px;background:rgba(0,229,255,0.9);border-radius:1px;";
    bar.appendChild(tickEnd);

    el.appendChild(barWrap);

    // Distance label — separate from bar, always horizontal, positioned at midpoint
    const distLabel = document.createElement("div");
    distLabel.className = "distScaleText";
    distLabel.style.cssText = [
      "position:fixed",
      "pointer-events:none",
      "z-index:100000",
      "display:none",
      "color:#fff",
      "font-size:12px",
      "font-weight:700",
      "font-family:'SF Mono','Menlo','Consolas',monospace",
      "text-shadow:0 1px 3px rgba(0,0,0,0.9),0 0 6px rgba(0,0,0,0.6)",
      "white-space:nowrap",
      "background:rgba(10,25,41,0.78)",
      "padding:2px 7px",
      "border-radius:4px",
      "transform:translate(-50%,-100%)",
    ].join(";");
    document.body.appendChild(distLabel);

    // Azimuth label — below midpoint, always horizontal
    const azLabel = document.createElement("div");
    azLabel.className = "distScaleAz";
    azLabel.style.cssText = [
      "position:fixed",
      "pointer-events:none",
      "z-index:100000",
      "display:none",
      "color:rgba(0,229,255,0.95)",
      "font-size:11px",
      "font-weight:600",
      "font-family:'SF Mono','Menlo','Consolas',monospace",
      "text-shadow:0 1px 2px rgba(0,0,0,0.9)",
      "white-space:nowrap",
      "transform:translate(-50%,6px)",
    ].join(";");
    document.body.appendChild(azLabel);

    document.body.appendChild(el);
    distanceScaleOverlay = el;
  }

  let _scaleOverlayLastMs = 0;
  function updateDistanceScaleOverlay(startLon, startLat, endLon, endLat, meters, azimuth) {
    const now = Date.now();
    if (now - _scaleOverlayLastMs < 33) return;  // max 30fps
    _scaleOverlayLastMs = now;
    ensureDistanceScaleOverlay();
    if (!distanceScaleOverlay || !viewer || !viewer.canvas) {
      return;
    }
    const startCart = Cesium.Cartesian3.fromDegrees(startLon, startLat);
    const endCart = Cesium.Cartesian3.fromDegrees(endLon, endLat);
    const startScreen = sceneToWindowCoordinates(viewer.scene, startCart);
    const endScreen = sceneToWindowCoordinates(viewer.scene, endCart);
    if (!startScreen || !endScreen || !Number.isFinite(startScreen.x) || !Number.isFinite(endScreen.x)) {
      distanceScaleOverlay.style.display = "none";
      _hideScaleLabels();
      return;
    }
    const canvasRect = viewer.canvas.getBoundingClientRect();
    const sx = canvasRect.left + startScreen.x;
    const sy = canvasRect.top + startScreen.y;
    const ex = canvasRect.left + endScreen.x;
    const ey = canvasRect.top + endScreen.y;
    const dx = ex - sx;
    const dy = ey - sy;
    const pixelLen = Math.sqrt(dx * dx + dy * dy);
    const angleDeg = Math.atan2(dy, dx) * (180.0 / Math.PI);

    if (pixelLen < 4.0) {
      distanceScaleOverlay.style.display = "none";
      _hideScaleLabels();
      return;
    }

    // Position the container at start point; rotate the bar wrap
    distanceScaleOverlay.style.display = "block";
    distanceScaleOverlay.style.left = sx.toFixed(1) + "px";
    distanceScaleOverlay.style.top = sy.toFixed(1) + "px";

    const barWrap = distanceScaleOverlay.querySelector(".distScaleBarWrap");
    if (barWrap) {
      barWrap.style.transform = "rotate(" + angleDeg.toFixed(2) + "deg)";
    }
    const bar = distanceScaleOverlay.querySelector(".distScaleBar");
    if (bar) {
      bar.style.width = Math.max(8, pixelLen).toFixed(1) + "px";
    }

    // Labels: always horizontal, positioned at screen midpoint
    const midX = ((sx + ex) / 2).toFixed(1);
    const midY = ((sy + ey) / 2).toFixed(1);

    const distLabel = document.querySelector(".distScaleText");
    if (distLabel) {
      const distText = meters > 1000 ? (meters / 1000.0).toFixed(2) + " km" : meters.toFixed(1) + " m";
      distLabel.textContent = "Dist: " + distText;
      distLabel.style.left = midX + "px";
      distLabel.style.top = midY + "px";
      distLabel.style.display = "block";
    }
    const azLabel = document.querySelector(".distScaleAz");
    if (azLabel) {
      const azText = azimuth !== undefined ? "Az: " + azimuth.toFixed(1) + "°" : "";
      azLabel.textContent = azText;
      azLabel.style.left = midX + "px";
      azLabel.style.top = midY + "px";
      azLabel.style.display = azText ? "block" : "none";
    }
  }

  function _hideScaleLabels() {
    const distLabel = document.querySelector(".distScaleText");
    if (distLabel) distLabel.style.display = "none";
    const azLabel = document.querySelector(".distScaleAz");
    if (azLabel) azLabel.style.display = "none";
  }

  function clearDistanceScaleOverlay() {
    // Hide immediately
    if (distanceScaleOverlay) {
      distanceScaleOverlay.style.display = "none";
    }
    _hideScaleLabels();
    // Fully remove all DOM elements — use querySelectorAll to catch duplicates
    const existing = document.getElementById("distanceScaleOverlay");
    if (existing) existing.remove();
    document.querySelectorAll(".distScaleText").forEach(function(el) { el.remove(); });
    document.querySelectorAll(".distScaleAz").forEach(function(el) { el.remove(); });
    distanceScaleOverlay = null;
    // NOTE: do NOT call clearMeasurementEntities here — that would cause infinite recursion.
    // clearMeasurementEntities already calls clearDistanceScaleOverlay, not the other way.
  }

  function _clearFillVolumeEntities() {
    if (!viewer) return;
    var ents = window._fillVolumeEntities || [];
    for (var i = 0; i < ents.length; i++) {
      var ent = ents[i];
      try {
        if (!ent) continue;
        if (viewer.entities.contains(ent)) {
          viewer.entities.remove(ent);
        }
      } catch (_) {}
    }
    window._fillVolumeEntities = [];
    window._fillVolumePrimitives = [];
  }

  // Profile rubber-band preview — recreates entity on every mouse move (same as distance tool)
  function _updateProfilePreviewLine(startLon, startLat, endLon, endLat) {
    if (!viewer) return;
    if (window._profilePreviewEntity) {
      try { viewer.entities.remove(window._profilePreviewEntity); } catch (_) {}
      window._profilePreviewEntity = null;
    }
    try {
      window._profilePreviewEntity = viewer.entities.add({
        polyline: {
          positions: [
            Cesium.Cartesian3.fromDegrees(startLon, startLat),
            Cesium.Cartesian3.fromDegrees(endLon, endLat),
          ],
          width: 1.5,
          arcType: Cesium.ArcType.GEODESIC,
          material: Cesium.Color.fromCssColorString("#00e5ff").withAlpha(0.7),
          depthFailMaterial: Cesium.Color.fromCssColorString("#00e5ff").withAlpha(0.3),
        },
      });
      requestSceneRender();
    } catch (_) {}
  }

  function updateMeasurementPreview(startLon, startLat, endLon, endLat, meters, azimuth) {
    if (!viewer) {
      return;
    }
    try {
      clearMeasurementPreviewEntities();
      const start = Cesium.Cartesian3.fromDegrees(startLon, startLat);
      const end = Cesium.Cartesian3.fromDegrees(endLon, endLat);

      measurementPreviewLineEntity = viewer.entities.add({
        polyline: {
          positions: [start, end],
          width: 1.5,
          arcType: Cesium.ArcType.GEODESIC,
          material: Cesium.Color.fromCssColorString("#00e5ff").withAlpha(0.7),
          depthFailMaterial: Cesium.Color.fromCssColorString("#00e5ff").withAlpha(0.3),
        },
      });

      // Update the screen-space scale bar overlay
      updateDistanceScaleOverlay(startLon, startLat, endLon, endLat, meters, azimuth);
      requestSceneRender();
    } catch (e) {
      // Silently ignore preview errors
    }
  }

  function setDistanceMeasureMode(enabled) {
    distanceMeasureModeEnabled = Boolean(enabled);
    distanceMeasureAnchor = null;
    
    const container = document.getElementById("cesiumContainer");
    if (distanceMeasureModeEnabled) {
      if (container) container.classList.add("measure-distance-cursor-active");
      _enforceMeasureCursor(true);
    } else {
      if (container) container.classList.remove("measure-distance-cursor-active");
      _enforceMeasureCursor(false);
    }
    
    if (distanceMeasureModeEnabled && searchDrawMode === "polygon") {
      searchDrawMode = "none";
      searchOverlayVisible = false;
      setSearchCursorEnabled(false);
      updatePolygonPreviewVisibility();
    }
    clearMeasurementPreviewEntities();
    clearDistanceScaleOverlay();
    if (distanceMeasureModeEnabled) {
      setMeasurementCursorEnabled(true);
      clickedPoints.length = 0;
      setStatus("Distance tool: click first point, move to preview, click second point to measure. Right-click to stop.");
      return;
    }
    // Turning off — clear ALL measurement marks (line, label, preview, overlay)
    clearMeasurementEntities();
    setMeasurementCursorEnabled(false);
    setStatus("Distance tool disabled.");
  }

  function setPanMode(enabled) {
    panModeActive = Boolean(enabled);
    if (panModeActive) {
      if (distanceMeasureModeEnabled) {
        setDistanceMeasureMode(false);
      }
      if (searchDrawMode === "polygon") {
        searchDrawMode = "none";
        searchOverlayVisible = false;
        setSearchCursorEnabled(false);
        updatePolygonPreviewVisibility();
      }
      clearDistanceScaleOverlay();
      // Force 2D-like flat drag: disable rotate/tilt/look
      configureCameraControllerForMode(currentSceneMode);
      setStatus("Pan mode enabled — drag to translate view.");
      log("info", "Pan mode activated (2D-like drag)");
    } else {
      // Restore normal 3D interaction controls
      configureCameraControllerForMode(currentSceneMode);
      setStatus("Pan mode disabled — 3D navigation restored.");
      log("info", "Pan mode deactivated (3D navigation restored)");
    }
    requestSceneRender();
  }

  function updateMeasurementEntities(startLon, startLat, endLon, endLat, meters, azimuth) {
    if (!viewer) {
      return;
    }
    try {
      clearMeasurementEntities();
    } catch (e) {
      log("error", "clearMeasurementEntities failed: " + e.message);
    }
    
    try {
      const start = Cesium.Cartesian3.fromDegrees(startLon, startLat);
      const end = Cesium.Cartesian3.fromDegrees(endLon, endLat);
      const labelLon = (startLon + endLon) / 2.0;
      const labelLat = (startLat + endLat) / 2.0;

      let distText = meters > 1000 ? (meters / 1000.0).toFixed(2) + " km" : meters.toFixed(1) + " m";
      let azText = azimuth !== undefined ? azimuth.toFixed(1) + "°" : "";
      const labelText = "Dist: " + distText + (azText ? "   Az: " + azText : "");

      measurementLineEntity = viewer.entities.add({
        polyline: {
          positions: [start, end],
          width: 1.5,
          arcType: Cesium.ArcType.GEODESIC,
          material: Cesium.Color.fromCssColorString("#00e5ff"),
          depthFailMaterial: Cesium.Color.fromCssColorString("#00e5ff").withAlpha(0.5),
        },
      });

      measurementLabelEntity = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(labelLon, labelLat),
        label: {
          text: labelText,
          font: "bold 13px 'Segoe UI', 'Arial', sans-serif",
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          showBackground: true,
          backgroundColor: Cesium.Color.fromCssColorString("#0a1929").withAlpha(0.82),
          backgroundPadding: new Cesium.Cartesian2(8, 5),
          horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          pixelOffset: new Cesium.Cartesian2(0, -14),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          scale: 1.0,
        },
      });
      requestSceneRender();
    } catch (e) {
      log("error", "updateMeasurementEntities failed: " + e.message);
    }
  }

  function clearAnnotationEntities() {
    if (!viewer) {
      return;
    }
    hoveredAnnotationEditEntity = null;
    while (annotationEntities.length > 0) {
      const entity = annotationEntities.pop();
      if (entity) {
        viewer.entities.remove(entity);
      }
    }
    requestSceneRender();
  }

  function zoomBy(factor) {
    if (!viewer || !viewer.camera) {
      return;
    }
    const camera = viewer.camera;
    const altitude = Cesium.Cartographic.fromCartesian(camera.positionWC).height;
    const amount = Math.max(5.0, Math.abs(altitude * (factor - 1.0)));
    if (factor < 1.0) {
      camera.zoomIn(amount);
    } else {
      camera.zoomOut(amount);
    }
    requestSceneRender();
  }

  function resetNorthUp() {
    if (!viewer || !viewer.camera) {
      return;
    }
    const camera = viewer.camera;
    camera.cancelFlight();

    // Reset heading to north (0.0) while preserving current position and pitch
    camera.flyTo({
      destination: camera.position,
      orientation: {
        heading: 0.0,
        pitch: camera.pitch,
        roll: camera.roll,
      },
      duration: 0.85,
    });
    requestSceneRender();
  }

  function zoomToExtent() {
    if (!viewer) {
      return;
    }
    const bounds = activeTileBounds || lastLoadedBounds;
    if (!bounds) {
      return;
    }
    if (currentSceneMode === "3d" || currentSceneMode === "morphing") {
      focusLoadedRegion3D(1.2);
    } else {
      focusLoadedRegion(0.8);
    }
  }

  function getSearchPreviewPoints() {
    return searchCursorPoint ? searchPolygonPoints.concat([searchCursorPoint]) : searchPolygonPoints.slice();
  }

  function getSearchPreviewCartesianPoints() {
    return getSearchPreviewPoints().map((p) => Cesium.Cartesian3.fromDegrees(p.lon, p.lat));
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: Search Polygon & AOI  →  future: modules/search.js
  // Functions: ensureSearchPreviewEntities, updateSearchPolygonPreview,
  //   finalizeSearchPolygon, toggleDrawnPolygonVisibility,
  //   toggleAllDrawnPolygonsVisibility, updatePolygonPreviewVisibility,
  //   setPolygonPreviewVisible, setSearchCursorEnabled,
  //   updateSearchCursorOverlay, emitSearchGeometry
  // ═══════════════════════════════════════════════════════════════════════════

  function ensureSearchPreviewEntities() {
    if (!viewer) {
      return;
    }

    if (!searchPreviewLineEntity) {
      searchPreviewLineEntity = viewer.entities.add({
        polyline: {
          positions: new Cesium.CallbackProperty(() => {
            const points = getSearchPreviewPoints();
            if (points.length < 2) {
              return [];
            }
            const positions = points.map((p) => Cesium.Cartesian3.fromDegrees(p.lon, p.lat));
            if (!searchCursorPoint && points.length >= 3) {
              positions.push(positions[0]);
            }
            return positions;
          }, false),
          width: 2.5,
          material: Cesium.Color.CYAN,
          clampToGround: true,
          // Always render on top — never occluded by terrain or imagery
          depthFailMaterial: Cesium.Color.CYAN.withAlpha(0.6),
          show: new Cesium.CallbackProperty(
            () => polygonVisibilityEnabled && searchOverlayVisible && getSearchPreviewPoints().length >= 2,
            false,
          ),
        },
      });
    }

    if (!searchPreviewPolygonEntity) {
      searchPreviewPolygonEntity = viewer.entities.add({
        polygon: {
          hierarchy: new Cesium.CallbackProperty(() => {
            const positions = getSearchPreviewCartesianPoints();
            if (positions.length < 3) {
              return null;
            }
            return new Cesium.PolygonHierarchy(positions);
          }, false),
          material: Cesium.Color.CYAN.withAlpha(0.25),
          fill: true,
          outline: true,
          outlineColor: Cesium.Color.CYAN,
          outlineWidth: 2,
          perPositionHeight: false,
          // Use height reference instead of classificationType for Cesium 1.78 compatibility
          height: 0,
          extrudedHeight: 0,
          show: new Cesium.CallbackProperty(
            () => polygonVisibilityEnabled && searchOverlayVisible && getSearchPreviewPoints().length >= 3,
            false,
          ),
        },
      });
    }

    if (!searchCursorEntity) {
      searchCursorEntity = viewer.entities.add({
        position: new Cesium.CallbackProperty(() => {
          if (!searchCursorPoint) {
            return Cesium.Cartesian3.fromDegrees(0, 0);
          }
          return Cesium.Cartesian3.fromDegrees(searchCursorPoint.lon, searchCursorPoint.lat);
        }, false),
        point: {
          pixelSize: 8,
          color: Cesium.Color.YELLOW,
          outlineColor: Cesium.Color.BLACK.withAlpha(0.7),
          outlineWidth: 1,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        show: new Cesium.CallbackProperty(
          () => polygonVisibilityEnabled && searchOverlayVisible && Boolean(searchCursorPoint),
          false,
        ),
      });
    }

    if (!searchAreaLabelEntity) {
      searchAreaLabelEntity = viewer.entities.add({
        position: new Cesium.CallbackProperty(() => {
          const points = getSearchPreviewPoints();
          const center = polygonLabelPosition(points);
          if (!center) {
            return Cesium.Cartesian3.fromDegrees(0, 0);
          }
          return Cesium.Cartesian3.fromDegrees(center.lon, center.lat);
        }, false),
        label: {
          text: new Cesium.CallbackProperty(() => {
            const points = getSearchPreviewPoints();
            if (points.length < 3) {
              return "";
            }
            const areaSquareMeters = computePolygonAreaSquareMeters(points);
            if (!Number.isFinite(areaSquareMeters) || areaSquareMeters <= 0) {
              return "";
            }
            return "Area " + formatArea(areaSquareMeters);
          }, false),
          font: "13px 'Segoe UI', sans-serif",
          fillColor: Cesium.Color.WHITE,
          showBackground: true,
          backgroundColor: Cesium.Color.BLACK.withAlpha(0.82),
          backgroundPadding: new Cesium.Cartesian2(8, 4),
          style: Cesium.LabelStyle.FILL,
          horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
          verticalOrigin: Cesium.VerticalOrigin.CENTER,
          pixelOffset: new Cesium.Cartesian2(0, 0),
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          scale: 0.8,
          show: new Cesium.CallbackProperty(
            () => polygonVisibilityEnabled && searchOverlayVisible && getSearchPreviewPoints().length >= 3,
            false,
          ),
        },
      });
    }
  }

  function syncSearchVertexEntities() {
    if (!viewer) {
      return;
    }
    // Remove excess vertex entities
    while (searchVertexEntities.length > searchPolygonPoints.length) {
      const ve = searchVertexEntities.pop();
      if (ve) {
        viewer.entities.remove(ve);
      }
    }
    // Create or update vertex entities for each polygon point
    for (let i = 0; i < searchPolygonPoints.length; i++) {
      const pt = searchPolygonPoints[i];
      if (i < searchVertexEntities.length) {
        // Update position of existing entity
        searchVertexEntities[i].position = Cesium.Cartesian3.fromDegrees(pt.lon, pt.lat);
        searchVertexEntities[i].show = polygonVisibilityEnabled && searchOverlayVisible;
      } else {
        // Create new vertex entity
        const ve = viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(pt.lon, pt.lat),
          point: {
            pixelSize: 9,
            color: Cesium.Color.fromCssColorString("#f4c430"),
            outlineColor: Cesium.Color.fromCssColorString("#1a1a1a"),
            outlineWidth: 1.5,
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
          show: polygonVisibilityEnabled && searchOverlayVisible,
        });
        searchVertexEntities.push(ve);
      }
    }
  }

  function updateSearchPolygonPreview() {
    ensureSearchPreviewEntities();
    syncSearchVertexEntities();
    requestSceneRender();
  }

  function finalizeSearchPolygon() {
    if (searchPolygonPoints.length < 3) {
      log("warn", "Polygon draw requires at least 3 points");
      return;
    }
    searchCursorPoint = null;
    if (searchPreviewLineEntity && searchPreviewLineEntity.polyline) {
      searchPreviewLineEntity.polyline.material = Cesium.Color.fromCssColorString("#31d18d");
      // Detach from searchOverlayVisible — drawn polygon stays visible independently
      searchPreviewLineEntity.polyline.show = true;
      searchPreviewLineEntity.polyline.depthFailMaterial = Cesium.Color.fromCssColorString("#31d18d").withAlpha(0.6);
    }
    if (searchPreviewPolygonEntity && searchPreviewPolygonEntity.polygon) {
      searchPreviewPolygonEntity.polygon.material = Cesium.Color.fromCssColorString("#31d18d").withAlpha(0.28);
      // Detach from searchOverlayVisible — drawn polygon stays visible independently
      searchPreviewPolygonEntity.polygon.show = true;
    }
    if (searchAreaLabelEntity && searchAreaLabelEntity.label) {
      searchAreaLabelEntity.label.show = true;
    }
    for (const ve of searchVertexEntities) {
      if (ve) ve.show = true;
    }
    updateSearchPolygonPreview();

    // Save drawn polygon for multi-polygon management
    drawnPolygonCounter += 1;
    const polyRecord = {
      id: drawnPolygonCounter,
      label: "Polygon " + drawnPolygonCounter,
      points: searchPolygonPoints.slice(),
      lineEntity: searchPreviewLineEntity,
      polygonEntity: searchPreviewPolygonEntity,
      areaLabelEntity: searchAreaLabelEntity,
      vertexEntities: searchVertexEntities.slice(),
      visible: true,  // always visible until explicitly hidden via checkbox
    };
    drawnPolygons.push(polyRecord);

    // Sync to comparator viewers immediately
    if (comparatorModeEnabled) {
      updateComparatorPolygons(true);
    }

    const polygonPayload = { points: searchPolygonPoints.slice() };
    searchDrawMode = "none";
    searchPolygonLocked = true;
    searchOverlayVisible = true;
    setSearchCursorEnabled(false);
    // Removed DOM update for polygonToggleControl
    // Update AOI panel
    updateAoiPanel(searchPolygonPoints);
    setStatus("Search polygon ready");
    window.requestAnimationFrame(function () {
      emitSearchGeometry("polygon", polygonPayload);
    });
    requestSceneRender();
  }

  function computePolygonAreaSquareMeters(points) {
    if (!Array.isArray(points) || points.length < 3) {
      return 0.0;
    }
    const center = polygonLabelPosition(points);
    if (!center) {
      return 0.0;
    }

    const origin = Cesium.Cartesian3.fromDegrees(center.lon, center.lat, 0.0);
    const enuTransform = Cesium.Transforms.eastNorthUpToFixedFrame(origin);
    const worldToLocal = Cesium.Matrix4.inverseTransformation(enuTransform, new Cesium.Matrix4());

    const localPoints = points.map((point) => {
      const cartesian = Cesium.Cartesian3.fromDegrees(point.lon, point.lat, 0.0);
      const local = Cesium.Matrix4.multiplyByPoint(worldToLocal, cartesian, new Cesium.Cartesian3());
      return { x: local.x, y: local.y };
    });

    let twiceArea = 0.0;
    for (let i = 0; i < localPoints.length; i += 1) {
      const current = localPoints[i];
      const next = localPoints[(i + 1) % localPoints.length];
      twiceArea += current.x * next.y - next.x * current.y;
    }

    return Math.abs(twiceArea) * 0.5;
  }

  function polygonLabelPosition(points) {
    if (!Array.isArray(points) || points.length === 0) {
      return null;
    }
    const positions = points.map((p) => Cesium.Cartesian3.fromDegrees(p.lon, p.lat));
    if (!positions.length) {
      return null;
    }
    const sphere = Cesium.BoundingSphere.fromPoints(positions);
    const cartographic = Cesium.Cartographic.fromCartesian(sphere.center);
    if (!cartographic) {
      return { lon: points[0].lon, lat: points[0].lat };
    }
    return {
      lon: Cesium.Math.toDegrees(cartographic.longitude),
      lat: Cesium.Math.toDegrees(cartographic.latitude),
    };
  }

  function formatArea(squareMeters) {
    if (!Number.isFinite(squareMeters) || squareMeters <= 0) {
      return "0 m\u00b2";
    }
    if (squareMeters >= 1_000_000) {
      return (squareMeters / 1_000_000).toFixed(2) + " km\u00b2";
    }
    return Math.round(squareMeters) + " m\u00b2";
  }

  // ── AOI Polygon Panel & Dropdown Management ──
  function updateAoiPanel(points) {
    if (!Array.isArray(points) || points.length < 3) {
      if (bridge && bridge.on_aoi_stats_updated) {
        bridge.on_aoi_stats_updated(0, "0 m\u00b2");
      }
      return;
    }
    const area = computePolygonAreaSquareMeters(points);
    const areaText = formatArea(area);
    if (bridge && bridge.on_aoi_stats_updated) {
      bridge.on_aoi_stats_updated(points.length, areaText);
    }
  }

  function toggleAoiPanelMinimize() {
    aoiPanelMinimized = !aoiPanelMinimized;
  }

  function updatePolygonDropdownUI() {
    if (bridge && bridge.on_polygon_list_updated) {
      const payload = drawnPolygons.map(poly => ({
        id: poly.id,
        label: poly.label,
        points_count: poly.points.length,
        visible: poly.visible
      }));
      bridge.on_polygon_list_updated(JSON.stringify(payload));
    }
  }

  function toggleDrawnPolygonVisibility(polyId, visible) {
    for (const poly of drawnPolygons) {
      if (poly.id !== polyId) {
        continue;
      }
      poly.visible = Boolean(visible);
      if (poly.lineEntity) poly.lineEntity.show = poly.visible;
      if (poly.polygonEntity) poly.polygonEntity.show = poly.visible;
      if (poly.areaLabelEntity) poly.areaLabelEntity.show = poly.visible;
      for (const ve of poly.vertexEntities || []) {
        if (ve) ve.show = poly.visible;
      }
    }
    requestSceneRender();
  }

  function toggleAllDrawnPolygonsVisibility(visible) {
    const isVisible = Boolean(visible);
    for (const poly of drawnPolygons) {
      poly.visible = isVisible;
      if (poly.lineEntity) poly.lineEntity.show = isVisible;
      if (poly.polygonEntity) poly.polygonEntity.show = isVisible;
      if (poly.areaLabelEntity) poly.areaLabelEntity.show = isVisible;
      for (const ve of poly.vertexEntities || []) {
        if (ve) ve.show = isVisible;
      }
    }
    requestSceneRender();
  }

  const comparatorPolygonEntities = { left: [], right: [] };

  function updateComparatorPolygons(visible) {
    if (!comparatorModeEnabled || !comparatorLeftViewer || !comparatorRightViewer) {
      return;
    }
    for (const ent of comparatorPolygonEntities.left) {
      comparatorLeftViewer.entities.remove(ent);
    }
    for (const ent of comparatorPolygonEntities.right) {
      comparatorRightViewer.entities.remove(ent);
    }
    comparatorPolygonEntities.left = [];
    comparatorPolygonEntities.right = [];

    if (!visible) {
      return;
    }

    const addPolyToViewers = (pts, color, isDrawn) => {
      if (!pts || pts.length < 3) return;
      const degreesArray = pts.reduce((acc, p) => { acc.push(p.lon, p.lat); return acc; }, []);
      const positions = Cesium.Cartesian3.fromDegreesArray(degreesArray);
      const polylinePositions = Cesium.Cartesian3.fromDegreesArray(degreesArray.concat([pts[0].lon, pts[0].lat]));
      
      const polylineDesc = {
        positions: polylinePositions,
        width: isDrawn ? 3.0 : 2.0,
        material: color,
        clampToGround: true
      };
      const polygonDesc = {
        hierarchy: positions,
        material: color.withAlpha(0.2),
        classificationType: Cesium.ClassificationType.TERRAIN
      };
      comparatorPolygonEntities.left.push(comparatorLeftViewer.entities.add({ polyline: polylineDesc, polygon: polygonDesc }));
      comparatorPolygonEntities.right.push(comparatorRightViewer.entities.add({ polyline: polylineDesc, polygon: polygonDesc }));
    };

    for (const poly of drawnPolygons) {
      addPolyToViewers(poly.points, Cesium.Color.YELLOW, true);
    }
    if (searchPolygonPoints && searchPolygonPoints.length >= 3) {
      addPolyToViewers(searchPolygonPoints, Cesium.Color.CYAN, false);
    }
  }

  function emitSearchGeometry(type, payload) {
    if (bridge && bridge.on_search_geometry) {
      bridge.on_search_geometry(type, JSON.stringify(payload));
    }
  }

  function setSceneModeInternal(mode) {
    if (!viewer) return;
    const normalized = String(mode || "3d").toLowerCase() === "2d" ? "2d" : "3d";
    let actualMode = detectSceneMode();
    sceneDebug(
      "setSceneModeInternal enter requested=" +
        mode +
        " normalized=" +
        normalized +
        " actualMode=" +
        actualMode +
        " currentSceneMode=" +
        currentSceneMode +
        " pendingSceneModeAfterMorph=" +
        String(pendingSceneModeAfterMorph)
    );
    if (actualMode === "morphing") {
      sceneDebug("setSceneModeInternal scene is morphing; forcing completeMorph before queueing");
      try {
        viewer.scene.completeMorph();
      } catch (_err) {
        // Ignore completeMorph failures and continue with queueing below.
      }
      actualMode = detectSceneMode();
      sceneDebug("setSceneModeInternal after completeMorph actualMode=" + actualMode);
    }
    if (actualMode === "morphing") {
      pendingSceneModeAfterMorph = normalized;
      syncSceneModeToggle(normalized);
      sceneDebug("setSceneModeInternal queued mode while morphing queued=" + normalized);
      return;
    }
    if (actualMode !== currentSceneMode) {
      currentSceneMode = actualMode;
      syncSceneModeToggle(actualMode);
      sceneDebug("setSceneModeInternal synced currentSceneMode to actualMode=" + actualMode);
    }
    pendingSceneModeAfterMorph = null;
    const preferredBounds = resolvePreferredFocusBounds();
    if (preferredBounds) {
      setActiveTileBounds(preferredBounds);
    }
    if (normalized === currentSceneMode) {
      sceneDebug("setSceneModeInternal no-op branch normalized matches current=" + normalized);
      configureCameraControllerForMode(normalized);
      syncSceneModeToggle(normalized);
      requestSceneRender();
      return;
    }
    pendingFocusBounds = preferredBounds;
    pendingFocusAfterMorph = Boolean(preferredBounds);
    pendingTerrainSceneAfterMorph = normalized === "3d" && Boolean(preferredBounds);
    configureCameraControllerForMode(normalized);
    if (normalized === "2d") {
      sceneDebug("setSceneModeInternal morphTo2D begin pendingFocus=" + String(pendingFocusAfterMorph));
      // Instant morph (0-duration) to avoid lag and frame drops
      viewer.scene.morphTo2D(0.0);
      currentSceneMode = "2d";
      syncSceneModeToggle("2d");
      if (comparatorModeEnabled) {
        setComparatorViewerModeByType(comparatorLeftViewer, null);
        setComparatorViewerModeByType(comparatorRightViewer, null);
      }
      updateBasemapBlendForCurrentMode();
      // Force immediate re-render after instant morph
      requestSceneRender();
      window.requestAnimationFrame(requestSceneRender);
      setStatus("2D map mode active.");
      log("info", "Scene mode switched to 2D from 3D");
      return;
    }
    sceneDebug("setSceneModeInternal morphTo3D begin pendingFocus=" + String(pendingFocusAfterMorph));
    // Instant morph (0-duration) to avoid lag and frame drops
    viewer.scene.morphTo3D(0.0);
    currentSceneMode = "3d";
    syncSceneModeToggle("3d");
    if (comparatorModeEnabled) {
      setComparatorViewerModeByType(comparatorLeftViewer, null);
      setComparatorViewerModeByType(comparatorRightViewer, null);
    }
    updateBasemapBlendForCurrentMode();

    // After morphTo3D, re-attach terrain provider and focus on active asset.
    // morphTo3D(0) resets the terrain provider — we must restore it.
    window.requestAnimationFrame(function () {
      if (activeDemTerrainProvider && activeDemContext && activeDemContext.visible !== false) {
        if (viewer.terrainProvider !== activeDemTerrainProvider) {
          _swapTerrainProviderLocked(activeDemTerrainProvider);
        }
        viewer.scene.globe.terrainExaggeration = Math.max(0.1, demVisual.exaggeration);
      }
      // Focus on active asset after morph
      const bounds = activeTileBounds || lastLoadedBounds;
      if (bounds) {
        schedule3DFocusAfterMorph(1.0);
      }
      requestSceneRender();
    });

    requestSceneRender();
    setStatus("3D globe mode active.");
    log("info", "Scene mode switched to 3D from 2D");
  }

  function startFlyThroughBounds(west, south, east, north) {
    if (!viewer) return;
    const targetBounds = { west: west, south: south, east: east, north: north };
    setActiveTileBounds(targetBounds);
    const modeNow = detectSceneMode();
    sceneDebug("startFlyThroughBounds modeNow=" + modeNow + " currentSceneMode=" + currentSceneMode);
    if (modeNow !== "3d") {
      pendingFlyThroughBounds = targetBounds;
      setSceneModeInternal("3d");
      setStatus("Switching to 3D globe...");
      sceneDebug("startFlyThroughBounds queued fly-through until 3d morph completes");
      return;
    }

    const rect = Cesium.Rectangle.fromDegrees(west, south, east, north);
    const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
    const nearRange = Math.max(compute3DFocusRange(lastLoadedBounds), sphere.radius * 1.4);
    const farRange = Math.min(Math.max(nearRange * 3.25, 280.0), 4500000.0);

    viewer.camera.cancelFlight();
    viewer.camera.flyToBoundingSphere(sphere, {
      offset: new Cesium.HeadingPitchRange(
        Cesium.Math.toRadians(-45),
        Cesium.Math.toRadians(-55),
        farRange
      ),
      duration: 2.6,
      complete: function () {
        viewer.camera.flyToBoundingSphere(sphere, {
          offset: new Cesium.HeadingPitchRange(
            Cesium.Math.toRadians(30),
            Cesium.Math.toRadians(-26),
            nearRange
          ),
          duration: 3.2,
        });
      },
    });
    setStatus("Fly-through started.");
    sceneDebug("startFlyThroughBounds flight started in 3d");
    log("info", "Fly-through started for selected bounds");
  }

  window.offlineGIS = {
    flyTo: function (lon, lat, height) {
      if (!viewer) return;
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(lon, lat, height || 8000),
        duration: 2.0,
      });
      log("info", "Fly-to lon=" + lon + " lat=" + lat);
    },
    flyToBounds: function (west, south, east, north) {
      if (!viewer) return;
      setActiveTileBounds({ west: west, south: south, east: east, north: north });
      const rect = Cesium.Rectangle.fromDegrees(west, south, east, north);
      viewer.camera.flyTo({
        destination: rect,
        duration: 2.2,
      });
      log("info", "Fly-to bounds west=" + west + " south=" + south + " east=" + east + " north=" + north);
    },
    focusBounds: function (west, south, east, north) {
      if (!viewer) return;
      // Add 10% padding so assets don't touch the viewport edges
      const padLon = (east - west) * 0.10;
      const padLat = (north - south) * 0.10;
      const paddedWest  = Math.max(-180, west  - padLon);
      const paddedEast  = Math.min( 180, east  + padLon);
      const paddedSouth = Math.max( -90, south - padLat);
      const paddedNorth = Math.min(  90, north + padLat);
      setActiveTileBounds({ west: west, south: south, east: east, north: north });
      const rect = Cesium.Rectangle.fromDegrees(paddedWest, paddedSouth, paddedEast, paddedNorth);
      viewer.camera.cancelFlight();
      viewer.camera.flyTo({
        destination: rect,
        orientation: { heading: 0.0, pitch: Cesium.Math.toRadians(-90), roll: 0.0 },
        duration: 1.2,
      });
      requestSceneRender();
      log("debug", "Focus bounds (fit) west=" + west + " south=" + south + " east=" + east + " north=" + north);
    },
    flyThroughBounds: function (west, south, east, north) {
      startFlyThroughBounds(west, south, east, north);
    },
    addTileLayer: async function (name, xyzUrl, kind, options) {
      if (!viewer) return;
      await ensureBaseTerrainReady();
      log(
        "info",
        "addTileLayer request name=" +
          String(name || "") +
          " kind=" +
          String(kind || "") +
          " xyz=" +
          String(xyzUrl || "") +
          " options=" +
          JSON.stringify(options || {})
      );
      const layerKey =
        options && typeof options.layer_key === "string" && options.layer_key
          ? options.layer_key
          : "imagery:" + String(name || "layer");
      const replaceExisting = !(options && options.replace_existing === false);
      const isDem =
        (options && options.is_dem === true) ||
        String(kind || "").toLowerCase() === "dem" ||
        String(name || "").toLowerCase().includes("dem");
      if (isDem) {
        window.offlineGIS.addDemLayer(name, xyzUrl, options || {});
        return;
      }
      if (replaceExisting) {
        // Always fully clear DEM terrain so imagery renders flat on the ellipsoid.
        // Imagery is a 2D product and should not drape over DEM elevation.
        clearDemTerrainMode();
        clearManagedImageryLayers();
      }
      setSceneModeControlEnabled(true);
      let providerUrl = xyzUrl;
      const extraQuery = options && options.query ? options.query : {};
      const qp = new URLSearchParams();
      Object.entries(extraQuery).forEach(([k, v]) => {
        if (v === null || v === undefined) return;
        if (Array.isArray(v)) {
          v.forEach((item) => qp.append(k, String(item)));
          return;
        }
        qp.set(k, String(v));
      });
      const qpText = qp.toString();
      if (qpText) providerUrl += (providerUrl.includes("?") ? "&" : "?") + qpText;
      log("debug", "Imagery URL construction baseUrl=" + xyzUrl + " finalUrl=" + providerUrl);
      const bounds = options && options.bounds ? options.bounds : null;
      const normalizedBounds = normalizeBounds(bounds);
      if (normalizedBounds) {
        setActiveTileBounds(normalizedBounds);
      }
      let rectangle;
      if (normalizedBounds) {
        rectangle = Cesium.Rectangle.fromDegrees(
          normalizedBounds.west,
          normalizedBounds.south,
          normalizedBounds.east,
          normalizedBounds.north
        );
      }
      const minLevel = options && Number.isInteger(options.minzoom) ? options.minzoom : 0;
      const maxLevel = options && Number.isInteger(options.maxzoom) ? options.maxzoom : 19;
      const existingLayer = managedImageryLayers.get(layerKey);
      if (existingLayer) {
        existingLayer.show = true;
        viewer.imageryLayers.raiseToTop(existingLayer);
        activeImageryLayer = existingLayer;
        layerVisibilityState.set(layerKey, true);
        applySwipeComparatorSplit();
        if (comparatorModeEnabled) {
          refreshComparatorLayers();
        }
        updateBasemapBlendForCurrentMode();
        setStatus("Layer shown: " + name);
        log("info", "Layer shown key=" + layerKey + " name=" + name);
        requestSceneRender();
        return;
      }
      const provider = new Cesium.UrlTemplateImageryProvider({
        url: providerUrl,
        maximumLevel: maxLevel,
        minimumLevel: minLevel,
        tilingScheme: new Cesium.WebMercatorTilingScheme(),
        enablePickFeatures: false,
        rectangle: rectangle,
      });
      log(
        "debug",
        "Imagery provider template URL: " + providerUrl
      );
      log(
        "info",
        "Imagery provider configured name=" +
          String(name || "") +
          " min=" +
          minLevel +
          " max=" +
          maxLevel +
          " rectangle=" +
          JSON.stringify(normalizedBounds || null) +
          " url=" +
          providerUrl
      );
      // Attach ready handler to detect initialization issues
      if (provider.readyPromise && typeof provider.readyPromise.then === "function") {
        provider.readyPromise.then(
          function () {
            log("debug", "Provider ready name=" + name + " tilesLoaded=" + (provider.getTileCredits ? "yes" : "no"));
          },
          function (err) {
            log("warn", "Provider ready failed name=" + name + " error=" + String(err));
          }
        );
      }
      attachTileErrorHandler(provider, name);
      activeImageryLayer = viewer.imageryLayers.addImageryProvider(provider);
      managedImageryLayers.set(layerKey, activeImageryLayer);
      viewer.imageryLayers.raiseToTop(activeImageryLayer);
      activeImageryLayer.alpha = 1.0;
      activeImageryLayer.show = true;
      layerDefinitions.set(layerKey, {
        key: layerKey,
        label: String(name || layerKey),
        type: "imagery",
        url: providerUrl,
        minLevel: minLevel,
        maxLevel: maxLevel,
        bounds: normalizedBounds,
      });
      layerVisibilityState.set(layerKey, true);
      applySwipeComparatorSplit();
      if (comparatorModeEnabled) {
        refreshComparatorLayers();
      }
      updateBasemapBlendForCurrentMode();
      logLayerStack();
      setStatus("Layer added: " + name);
      log(
        "info",
        "Layer added name=" +
          name +
          " key=" +
          layerKey +
          " kind=" +
          kind +
          " url=" +
          providerUrl +
          " min=" +
          minLevel +
          " max=" +
          maxLevel
      );
      // Start tile loading progress monitor
      startTileLoadingMonitor();
    },
    addDemLayer: function (name, xyzUrl, options) {
      if (!viewer) return;
      log(
        "info",
        "addDemLayer request name=" +
          String(name || "") +
          " xyz=" +
          String(xyzUrl || "") +
          " options=" +
          JSON.stringify(options || {})
      );
      const replaceExisting = !(options && options.replace_existing === false);
      const layerKey =
        options && typeof options.layer_key === "string" && options.layer_key
          ? options.layer_key
          : "dem:" + String(name || "layer");
      if (replaceExisting) {
        clearManagedImageryLayers();
      }
      setSceneModeInternal("3d");
      setSceneModeControlEnabled(true);
      syncSceneModeToggle("3d");
      const normalizedBounds = normalizeBounds(options && options.bounds ? options.bounds : null);
      if (normalizedBounds) {
        setActiveTileBounds(normalizedBounds);
      }
      activeDemContext = {
        layerKey: layerKey,
        name: name,
        xyzUrl: xyzUrl,
        options: options || {},
        visible: true,
      };
      layerVisibilityState.set(layerKey, true);
      applyDemLayer();
    },
    setSceneMode: function (mode) {
      sceneDebug(
        "window.setSceneMode requested=" +
          mode +
          " sceneModeControlEnabled=" +
          String(sceneModeControlEnabled) +
          " activeDemContext=" +
          String(Boolean(activeDemContext)) +
          " detectSceneMode=" +
          detectSceneMode() +
          " currentSceneMode=" +
          currentSceneMode
      );
      setSceneModeInternal(mode);
    },
    setSceneModeControlEnabled: function (enabled) {
      setSceneModeControlEnabled(Boolean(enabled));
    },
    setSearchBusy: function (active, message) {
      setSearchBusy(active, message);
    },
    setDemColorMode: function (colormapName) {
      const normalized = String(colormapName || "gray").toLowerCase() === "terrain" ? "terrain" : "gray";
      if (comparatorModeEnabled) {
        const paneState = getComparatorPaneVisual(comparatorSelectedPane);
        if (!paneState) {
          return;
        }
        paneState.dem.colorMode = normalized;
        if (getComparatorPaneLayerType(comparatorSelectedPane) === "dem") {
          scheduleComparatorDemRefresh(comparatorSelectedPane);
        }
        notifyComparatorPaneState(comparatorSelectedPane);
        requestSceneRender();
        return;
      }
      setDemColorMode(normalized);
    },
    setSwipeComparatorLayers: function (leftLayerKey, rightLayerKey, leftLabel, rightLabel) {
      setSwipeComparatorLayerKeys(leftLayerKey, rightLayerKey, leftLabel, rightLabel);
    },
    setComparatorLayers: function (leftLayerKey, rightLayerKey, leftLabel, rightLabel) {
      setSwipeComparatorLayerKeys(leftLayerKey, rightLayerKey, leftLabel, rightLabel);
    },
    setLayerVisibility: function (layerKey, visible) {
      const applied = setLayerVisibilityByKey(String(layerKey || ""), Boolean(visible));
      if (!applied) {
        log("warn", "Layer visibility update ignored key=" + String(layerKey));
      }
    },
    setPolygonVisibility: function (polyId, visible) {
      toggleDrawnPolygonVisibility(polyId, visible);
    },
    setSearchPolygonVisibility: function (visible) {
      polygonVisibilityEnabled = Boolean(visible);
      updatePolygonPreviewVisibility();
      toggleAllDrawnPolygonsVisibility(visible);
      updateComparatorPolygons(visible);
      log("debug", "All polygons visibility set to " + String(visible));
    },
    flyThroughBounds: function (west, south, east, north) {
      startFlyThroughBounds(west, south, east, north);
    },
    setDemProperties: function (exaggeration, hillshadeAlpha) {
      const nextExaggeration = Math.max(0.1, Number(exaggeration) || 1.0);
      const nextHillshadeAlpha = Math.max(0.0, Math.min(1.0, Number(hillshadeAlpha) || 0.0));

      if (comparatorModeEnabled) {
        if (comparatorDemRefreshTimer !== null) {
          window.clearTimeout(comparatorDemRefreshTimer);
          comparatorDemRefreshTimer = null;
        }
        const paneState = getComparatorPaneVisual(comparatorSelectedPane);
        if (!paneState) return;
        
        const comparatorExaggChanged = paneState.dem.exaggeration !== nextExaggeration;
        paneState.dem.exaggeration = nextExaggeration;
        paneState.dem.hillshadeAlpha = nextHillshadeAlpha;
        
        applyComparatorPaneVisualState(comparatorSelectedPane);
        notifyComparatorPaneState(comparatorSelectedPane);
        
        if (comparatorExaggChanged) {
          if (comparatorDemRefreshTimer !== null) {
            window.clearTimeout(comparatorDemRefreshTimer);
          }
          comparatorDemRefreshTimer = window.setTimeout(() => {
            scheduleComparatorDemRefresh(comparatorSelectedPane);
          }, 500);
        }
        
        requestSceneRender();
        return;
      }

      const exaggerationChanged = demVisual.exaggeration !== nextExaggeration;
      demVisual.exaggeration = nextExaggeration;
      demVisual.hillshadeAlpha = nextHillshadeAlpha;
      
      if (activeDemHillshadeLayer) {
        activeDemHillshadeLayer.alpha = demVisual.hillshadeAlpha;
      }

      if (exaggerationChanged && viewer && viewer.scene && viewer.scene.globe) {
        // Cesium 1.78: globe.terrainExaggeration scales terrain heights in-place.
        // No terrain provider rebuild needed — zero camera jump, instant visual update.
        viewer.scene.globe.terrainExaggeration = Math.max(0.1, nextExaggeration);
        log("debug", "DEM exaggeration applied in-place value=" + nextExaggeration.toFixed(2));
      }

      requestSceneRender();
    },
    setImageryProperties: function (brightness, contrast) {
      if (!viewer) return;
      const nextBrightness = Math.max(0.2, brightness);
      const nextContrast = Math.max(0.1, contrast);

      if (comparatorModeEnabled) {
        const paneState = getComparatorPaneVisual(comparatorSelectedPane);
        if (!paneState) {
          return;
        }
        paneState.imagery.brightness = nextBrightness;
        paneState.imagery.contrast = nextContrast;
        applyComparatorPaneVisualState(comparatorSelectedPane);
        notifyComparatorPaneState(comparatorSelectedPane);
        log(
          "debug",
          "Comparator imagery properties pane=" +
            comparatorSelectedPane +
            " brightness=" +
            nextBrightness +
            " contrast=" +
            nextContrast
        );
        requestSceneRender();
        return;
      }

      imageryVisual.brightness = nextBrightness;
      imageryVisual.contrast = nextContrast;
      const visibleManagedLayers = Array.from(managedImageryLayers.values()).filter((layer) => layer && layer.show);
      if (visibleManagedLayers.length > 0) {
        for (const layer of visibleManagedLayers) {
          layer.brightness = nextBrightness;
          layer.contrast = nextContrast;
        }
        log("debug", "Set imagery brightness=" + brightness + " contrast=" + contrast + " layers=" + visibleManagedLayers.length);
        requestSceneRender();
        return;
      }
      const layer = activeImageryLayer || viewer.imageryLayers.get(0);
      if (!layer) return;
      layer.brightness = nextBrightness;
      layer.contrast = nextContrast;
      requestSceneRender();
      log("debug", "Set imagery brightness=" + brightness + " contrast=" + contrast);
    },
    rotateCamera: function (degrees) {
      if (!viewer) return;
      // Camera rotation is not applicable in 2D mode
      if (currentSceneMode === "2d") {
        log("debug", "rotateCamera: ignored in 2D mode");
        return;
      }
      log("debug", "rotateCamera: degrees=" + degrees + " comparatorMode=" + comparatorModeEnabled);
      const targetBounds = cameraOrbitBounds || activeTileBounds || lastLoadedBounds;
      if (targetBounds) {
        log("debug", "rotateCamera: targetBounds found, syncing orbit");
        syncOrbitFromCurrentCamera(targetBounds);
        cameraOrbitHeading += Cesium.Math.toRadians(degrees);
        log("debug", "rotateCamera: cameraOrbitHeading updated, calling applyCameraOrbitTarget");
        applyCameraOrbitTarget();
      } else {
        log("debug", "rotateCamera: no targetBounds, rotating main viewer directly");
        viewer.camera.rotateRight(Cesium.Math.toRadians(degrees));
      }
      if (comparatorModeEnabled && comparatorLeftViewer && comparatorRightViewer) {
        comparatorLeftViewer.camera.rotateRight(Cesium.Math.toRadians(degrees));
        comparatorRightViewer.camera.rotateRight(Cesium.Math.toRadians(degrees));
      }
      requestSceneRender();
      log("debug", "Rotate camera degrees=" + degrees);
    },
    setPitch: function (degrees) {
      if (!viewer) return;
      // Pitch tilt is not applicable in 2D mode
      if (currentSceneMode === "2d") {
        log("debug", "setPitch: ignored in 2D mode");
        return;
      }
      log("debug", "setPitch: degrees=" + degrees);
      const targetBounds = cameraOrbitBounds || activeTileBounds || lastLoadedBounds;
      if (targetBounds) {
        log("debug", "setPitch: targetBounds found, syncing orbit");
        syncOrbitFromCurrentCamera(targetBounds);
      }
      cameraOrbitPitch = Cesium.Math.toRadians(degrees);
      log("debug", "setPitch: cameraOrbitPitch set to radians=" + cameraOrbitPitch);
      
      if (!applyCameraOrbitTarget()) {
        log("debug", "setPitch: applyCameraOrbitTarget returned false, setting main viewer camera");
        const camera = viewer.camera;
        const orientation = {
            heading: camera.heading,
            pitch: cameraOrbitPitch,
            roll: camera.roll,
        };
        camera.setView({
          destination: camera.position,
          orientation: orientation,
        });
        
        if (comparatorModeEnabled) {
          if (comparatorLeftViewer && comparatorLeftViewer.camera) {
            comparatorLeftViewer.camera.setView({
              destination: comparatorLeftViewer.camera.position,
              orientation: orientation,
            });
          }
          if (comparatorRightViewer && comparatorRightViewer.camera) {
            comparatorRightViewer.camera.setView({
              destination: comparatorRightViewer.camera.position,
              orientation: orientation,
            });
          }
        }
      }
      requestSceneRender();
      log("debug", "Set pitch degrees=" + degrees);
    },
    addAnnotation: function (text, lon, lat) {
      if (!viewer) return;
      annotationCounter += 1;
      const annotationId = "annotation-" + String(annotationCounter);
      const pointName = String(text || "Point").trim() || "Point";
      let anchorPosition = null;
      if (lastMapClickCartesian) {
        const lastLonLat = cartesianToLonLat(lastMapClickCartesian);
        if (lastLonLat) {
          const lonDiff = Math.abs(Number(lastLonLat.lon) - Number(lon));
          const latDiff = Math.abs(Number(lastLonLat.lat) - Number(lat));
          if (lonDiff <= 0.00002 && latDiff <= 0.00002) {
            anchorPosition = Cesium.Cartesian3.clone(lastMapClickCartesian);
          }
        }
      }
      if (!anchorPosition) {
        const cartographic = Cesium.Cartographic.fromDegrees(Number(lon), Number(lat));
        const sampledHeight = viewer.scene && viewer.scene.globe ? viewer.scene.globe.getHeight(cartographic) : null;
        const height = Number.isFinite(sampledHeight) ? Number(sampledHeight) : 0.0;
        anchorPosition = Cesium.Cartesian3.fromDegrees(Number(lon), Number(lat), height);
      }
      lastMapClickCartesian = null;
      const anchorEntity = viewer.entities.add({
        position: anchorPosition,
        point: {
          pixelSize: 10,
          color: Cesium.Color.fromCssColorString("#f2c94c"),
          outlineColor: Cesium.Color.fromCssColorString("#1d1d1d"),
          outlineWidth: 1,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      anchorEntity.show = annotationVisibilityEnabled;
      anchorEntity._annotationId = annotationId;
      anchorEntity._annotationRole = "anchor";

      const labelEntity = viewer.entities.add({
        position: anchorPosition,
        label: {
          text: pointName,
          fillColor: Cesium.Color.WHITE,
          showBackground: true,
          backgroundColor: Cesium.Color.BLACK.withAlpha(0.62),
          outlineColor: Cesium.Color.BLACK.withAlpha(0.9),
          outlineWidth: 2,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          font: "500 12px 'Segoe UI', 'Helvetica Neue', sans-serif",
          pixelOffset: new Cesium.Cartesian2(12, -8),
          horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1800000.0, 0.45),
          translucencyByDistance: new Cesium.NearFarScalar(3000.0, 1.0, 2400000.0, 0.62),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      labelEntity.show = annotationVisibilityEnabled;
      labelEntity._annotationId = annotationId;
      labelEntity._annotationRole = "label";

      const editEntity = viewer.entities.add({
        position: anchorPosition,
        billboard: {
          image: ANNOTATION_EDIT_ICON_IMAGE,
          width: 17,
          height: 17,
          color: Cesium.Color.WHITE.withAlpha(0.42),
          pixelOffset: new Cesium.Cartesian2(12, -26),
          horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1700000.0, 0.62),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      editEntity.show = annotationVisibilityEnabled;
      editEntity._annotationId = annotationId;
      editEntity._annotationRole = "edit";
      editEntity._annotationAnchorEntity = anchorEntity;
      editEntity._annotationLabelEntity = labelEntity;

      annotationEntities.push(anchorEntity);
      annotationEntities.push(labelEntity);
      annotationEntities.push(editEntity);
      requestSceneRender();
      window.requestAnimationFrame(requestSceneRender);
      log("info", "Annotation added lon=" + lon + " lat=" + lat);
    },
    clearAnnotations: function () {
      clearAnnotationEntities();
      log("info", "Annotations cleared");
    },
    setAnnotationVisibility: function (visible) {
      setAnnotationVisibility(Boolean(visible));
    },
    clearMeasurements: function () {
      setDistanceMeasureMode(false);
      clickedPoints.length = 0;
      clearMeasurementEntities();
      clearMeasurementPreviewEntities();
      clearDistanceScaleOverlay();
      _clearFillVolumeEntities();
      window._fillVolumePrimitives = [];
      log("info", "Measurement overlays cleared");
    },
    clearMeasurementEntities: function () {
      clearMeasurementEntities();
      log("debug", "Measurement entities cleared");
    },
    clearOverlays: function () {
      clickedPoints.length = 0;
      setDistanceMeasureMode(false);
      clearMeasurementEntities();
      clearMeasurementPreviewEntities();
      clearDistanceScaleOverlay();
      clearAnnotationEntities();
      clearSearchEntities();
      _clearFillVolumeEntities();
      window._fillVolumePrimitives = [];
      searchPolygonPoints.length = 0;
      searchPolygonLocked = false;
      searchCursorPoint = null;
      searchOverlayVisible = true;
      emitSearchGeometry("none", {});
      setStatus("All overlays cleared");
      log("info", "All overlays cleared");
      requestSceneRender();
    },
    zoomIn: function () {
      zoomBy(0.7);
      log("debug", "Zoom in");
    },
    zoomOut: function () {
      zoomBy(1.3);
      log("debug", "Zoom out");
    },
    zoomToExtent: function () {
      zoomToExtent();
      log("debug", "Zoom to extent");
    },
    resetNorthUp: function () {
      resetNorthUp();
      log("debug", "North-up orientation reset");
    },
    setSwipeComparator: function (enabled) {
      setSwipeComparatorEnabled(Boolean(enabled));
      log("debug", "Comparator=" + String(Boolean(enabled)));
    },
    setLayerAlpha: function (layerKey, alpha) {
      if (!viewer || !viewer.imageryLayers) return;
      const numAlpha = Math.max(0.0, Math.min(1.0, Number(alpha) || 0.0));
      
      const layer = managedImageryLayers.get(layerKey);
      if (layer) {
        layer.alpha = numAlpha;
      } else if (activeDemContext && activeDemContext.layerKey === layerKey) {
        if (activeDemDrapeLayer) {
            activeDemDrapeLayer.alpha = numAlpha;
        }
      }
      requestSceneRender();
    },
    setComparator: function (enabled) {
      setSwipeComparatorEnabled(Boolean(enabled));
      log("debug", "Comparator=" + String(Boolean(enabled)));
    },
    requestComparatorPaneState: function () {
      notifyComparatorPaneState(comparatorSelectedPane);
    },
    setSwipePosition: function (fraction) {
      setSwipePosition(Number(fraction));
      log("debug", "Comparator position=" + String(fraction));
    },
    setComparatorPosition: function (fraction) {
      setSwipePosition(Number(fraction));
      log("debug", "Comparator position=" + String(fraction));
    },
    setDistanceMeasureMode: function (enabled) {
      setDistanceMeasureMode(Boolean(enabled));
      log("info", "Distance measure mode=" + String(Boolean(enabled)));
    },
    setMeasurementCursor: function (enabled) {
      log("info", "[CURSOR_DEBUG] setMeasurementCursor API called enabled=" + String(Boolean(enabled)));
      setMeasurementCursorEnabled(Boolean(enabled));
    },
    drawProfileLine: function (lon1, lat1, lon2, lat2) {
      if (!viewer) return;
      // Clear profile mode flag and preview line
      window._profileModeActive = false;
      if (window._profilePreviewEntity) {
        try { viewer.entities.remove(window._profilePreviewEntity); } catch (_) {}
        window._profilePreviewEntity = null;
      }
      // Remove any previous profile line and markers
      if (window._profileLineEntity) {
        try { viewer.entities.remove(window._profileLineEntity); } catch (_) {}
        window._profileLineEntity = null;
      }
      if (window._profileStartEntity) {
        try { viewer.entities.remove(window._profileStartEntity); } catch (_) {}
        window._profileStartEntity = null;
      }
      if (window._profileEndEntity) {
        try { viewer.entities.remove(window._profileEndEntity); } catch (_) {}
        window._profileEndEntity = null;
      }
      const cyan = Cesium.Color.fromCssColorString("#00e5ff");
      window._profileLineEntity = viewer.entities.add({
        polyline: {
          positions: [
            Cesium.Cartesian3.fromDegrees(Number(lon1), Number(lat1)),
            Cesium.Cartesian3.fromDegrees(Number(lon2), Number(lat2)),
          ],
          width: 2.5,
          arcType: Cesium.ArcType.GEODESIC,
          material: cyan,
          depthFailMaterial: cyan.withAlpha(0.5),
        },
      });
      // Start/end point markers
      window._profileStartEntity = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(Number(lon1), Number(lat1)),
        point: { pixelSize: 8, color: cyan, outlineColor: Cesium.Color.BLACK, outlineWidth: 1, disableDepthTestDistance: Number.POSITIVE_INFINITY },
      });
      window._profileEndEntity = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(Number(lon2), Number(lat2)),
        point: { pixelSize: 8, color: cyan, outlineColor: Cesium.Color.BLACK, outlineWidth: 1, disableDepthTestDistance: Number.POSITIVE_INFINITY },
      });
      requestSceneRender();
      log("debug", "Profile line drawn lon1=" + lon1 + " lat1=" + lat1 + " lon2=" + lon2 + " lat2=" + lat2);
      // Store endpoints for georeferenced cursor projection
      window._profileLineLon1 = Number(lon1);
      window._profileLineLat1 = Number(lat1);
      window._profileLineLon2 = Number(lon2);
      window._profileLineLat2 = Number(lat2);
      window._profileLineActive = true;
      // Create the moving cursor point on the globe (dull yellow, starts at midpoint)
      if (window._profileCursorGlobeEntity) {
        try { viewer.entities.remove(window._profileCursorGlobeEntity); } catch (_) {}
        window._profileCursorGlobeEntity = null;
      }
      const yellow = Cesium.Color.fromCssColorString("#c8a800").withAlpha(0.88);
      // Pre-compute the geodesic for accurate interpolation along the great-circle arc
      const _geodesicForCursor = new Cesium.EllipsoidGeodesic(
        Cesium.Cartographic.fromDegrees(Number(lon1), Number(lat1)),
        Cesium.Cartographic.fromDegrees(Number(lon2), Number(lat2))
      );
      window._profileCursorGlobeEntity = viewer.entities.add({
        position: new Cesium.CallbackProperty(function () {
          if (!window._profileLineActive) {
            return Cesium.Cartesian3.fromDegrees(Number(lon1), Number(lat1));
          }
          const f = (typeof window._profileCursorFrac === "number")
            ? Math.max(0.0, Math.min(1.0, window._profileCursorFrac))
            : 0.5;
          // Interpolate along the true geodesic arc — pixel-accurate for any resolution
          const interp = _geodesicForCursor.interpolateUsingFraction(f);
          return Cesium.Cartesian3.fromRadians(interp.longitude, interp.latitude);
        }, false),
        point: {
          pixelSize: 10,
          color: yellow,
          outlineColor: Cesium.Color.fromCssColorString("#3a2800"),
          outlineWidth: 1.5,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      window._profileCursorFrac = 0.5;
    },
    drawProfileStartMarker: function (lon, lat) {
      if (!viewer) return;
      // Remove previous start marker if any
      if (window._profileStartEntity) {
        try { viewer.entities.remove(window._profileStartEntity); } catch (_) {}
        window._profileStartEntity = null;
      }
      // Clear any stale preview line
      if (window._profilePreviewEntity) {
        try { viewer.entities.remove(window._profilePreviewEntity); } catch (_) {}
        window._profilePreviewEntity = null;
      }
      // Clear the previous completed profile line and end marker
      if (window._profileLineEntity) {
        try { viewer.entities.remove(window._profileLineEntity); } catch (_) {}
        window._profileLineEntity = null;
      }
      if (window._profileEndEntity) {
        try { viewer.entities.remove(window._profileEndEntity); } catch (_) {}
        window._profileEndEntity = null;
      }
      const cyan = Cesium.Color.fromCssColorString("#00e5ff");
      window._profileStartEntity = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(Number(lon), Number(lat)),
        point: { pixelSize: 9, color: cyan, outlineColor: Cesium.Color.BLACK, outlineWidth: 1.5, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        label: {
          text: "A",
          font: "bold 11px sans-serif",
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          pixelOffset: new Cesium.Cartesian2(10, -10),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      // Store start coords — preview line is recreated on every mouse move
      window._profileStartLon = Number(lon);
      window._profileStartLat = Number(lat);
      window._profileModeActive = true;
      requestSceneRender();
      log("debug", "Profile start marker placed lon=" + lon + " lat=" + lat);
    },
    clearProfilePreview: function () {
      window._profileModeActive = false;
      window._profileStartLon = undefined;
      window._profileStartLat = undefined;
      if (window._profilePreviewEntity) {
        try { viewer.entities.remove(window._profilePreviewEntity); } catch (_) {}
        window._profilePreviewEntity = null;
      }
      if (window._profileStartEntity) {
        try { viewer.entities.remove(window._profileStartEntity); } catch (_) {}
        window._profileStartEntity = null;
      }
      requestSceneRender();
    },
    clearProfileLine: function () {
      window._profileModeActive = false;
      window._profileLineActive = false;
      window._profileLineLon1 = undefined;
      window._profileLineLat1 = undefined;
      window._profileLineLon2 = undefined;
      window._profileLineLat2 = undefined;
      window._profileCursorFrac = undefined;
      for (const key of ["_profilePreviewEntity", "_profileStartEntity", "_profileEndEntity", "_profileLineEntity", "_profileCursorGlobeEntity"]) {
        if (window[key]) {
          try { viewer.entities.remove(window[key]); } catch (_) {}
          window[key] = null;
        }
      }
      requestSceneRender();
      log("debug", "Profile line cleared from globe");
    },
    setPanMode: function (enabled) {
      setPanMode(Boolean(enabled));
      log("info", "Pan mode=" + String(Boolean(enabled)));
    },    setSearchDrawMode: function (mode) {
      if (mode !== "polygon") {
        searchDrawMode = "none";
        searchOverlayVisible = false;
        setSearchCursorEnabled(false);
        updatePolygonPreviewVisibility();
        // Removed DOM update
        setStatus("Search draw disabled");
        requestSceneRender();
        return;
      }
      searchDrawMode = "polygon";
      searchOverlayVisible = true;
      polygonVisibilityEnabled = true;
      searchCursorPoint = null;
      setPolygonPreviewVisible(true);
      setSearchCursorEnabled(!searchPolygonLocked);
      // Removed DOM update
      if (searchPolygonLocked) {
        setStatus("Polygon restored. Clear geometry to start a new polygon.");
      } else {
        setStatus("Polygon draw: click points, right-click or Finish to close");
      }
      requestSceneRender();
    },
    finishSearchPolygon: function () {
      finalizeSearchPolygon();
    },
    clearSearchGeometry: function () {
      searchDrawMode = "none";
      searchPolygonLocked = false;
      searchCursorPoint = null;
      searchPolygonPoints.length = 0;
      searchOverlayVisible = true;
      polygonVisibilityEnabled = true;
      clearSearchEntities();
      emitSearchGeometry("none", {});
      setPolygonPreviewVisible(true);
      setSearchCursorEnabled(false);
      // Removed DOM update
      setStatus("Search geometry cleared");
      requestSceneRender();
    },
    setPolygonPreviewVisible: function (visible) {
      setPolygonPreviewVisible(Boolean(visible));
    },
    clearFillVolumes: function () {
      _clearFillVolumeEntities();
      window._fillVolumePrimitives = [];
      requestSceneRender();
      log("debug", "Fill volume overlays cleared");
    },
    drawFillVolumes: function (regionsJson) {
      _clearFillVolumeEntities();
      var regions;
      try { regions = JSON.parse(regionsJson); } catch (e) { log("error", "drawFillVolumes: bad JSON"); return; }
      if (!Array.isArray(regions) || regions.length === 0) {
        log("debug", "drawFillVolumes: no regions to draw");
        return;
      }

      log("info", "Starting to draw " + regions.length + " fill volume regions");

      var distinctColors = [
        [255,  80,  40, 200],
        [ 40, 120, 255, 200],
        [ 40, 220, 100, 200],
        [255, 200,  40, 200],
        [180,  40, 255, 200],
        [255, 100, 180, 200],
        [ 40, 220, 220, 200],
        [255, 140,  40, 200],
      ];

      function getRegionColor(index) {
        var rgba = distinctColors[index % distinctColors.length];
        return new Cesium.Color(rgba[0]/255, rgba[1]/255, rgba[2]/255, rgba[3]/255);
      }

      var labelEntities = [];

      for (var ri = 0; ri < regions.length; ri++) {
        var r = regions[ri];
        var regionId = r.id || r.region_id || (ri + 1);

        if (!r.outline || r.outline.length < 3) {
          log("warn", "Region " + regionId + " has invalid outline, skipping");
          continue;
        }

        var fillColour = getRegionColor(ri);

        // Pure entity polygon — no GroundPrimitive, no GPU lifecycle, safe on macOS Metal + Windows NVIDIA.
        // No height — Cesium drapes on globe surface. arcType RHUMB gives pixel-accurate
        // edges for small sub-km polygons (avoids geodesic subdivision artifacts).
        var positions = r.outline.map(function(p) {
          return Cesium.Cartesian3.fromDegrees(p.lon, p.lat);
        });

        // Use the region's rim elevation + small offset so the flat polygon
        // sits just above the terrain surface and is never occluded at any zoom level.
        var polyHeight = (typeof r.rim_elevation_m === 'number' && isFinite(r.rim_elevation_m))
          ? r.rim_elevation_m + 2.0
          : 2.0;

        var regionEnt = viewer.entities.add({
          id: 'fill-region-ent-' + regionId,
          polygon: {
            hierarchy: new Cesium.PolygonHierarchy(positions),
            material: fillColour,
            height: polyHeight,
            arcType: Cesium.ArcType.RHUMB,
            outline: false,
            fill: true,
          },
        });
        window._fillVolumeEntities.push(regionEnt);

        var volStr = r.fill_volume_m3 >= 1000000000
          ? (r.fill_volume_m3 / 1000000000).toFixed(3) + " km\u00b3"
          : r.fill_volume_m3 >= 1000000
          ? (r.fill_volume_m3 / 1000000).toFixed(3) + " Mm\u00b3"
          : r.fill_volume_m3.toFixed(3) + " m\u00b3";
        var areaStr = r.area_m2 >= 10000
          ? (r.area_m2 / 10000).toFixed(2) + " ha"
          : r.area_m2.toFixed(0) + " m\u00b2";

        labelEntities.push({
          position: Cesium.Cartesian3.fromDegrees(r.centroid_lon, r.centroid_lat, polyHeight + 5.0),
          regionId: regionId,
          volStr: volStr,
          areaStr: areaStr,
          maxDepth: r.max_depth_m,
          meanDepth: r.mean_depth_m,
        });
      }

      for (var li = 0; li < labelEntities.length; li++) {
        var labelData = labelEntities[li];

        var labelEnt = viewer.entities.add({
          id: 'fill-label-' + labelData.regionId,
          position: labelData.position,
          label: {
            text: "\u25bc Region " + labelData.regionId,
            font: "bold 13px 'Segoe UI', Arial, sans-serif",
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            fillColor: Cesium.Color.WHITE,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2.5,
            showBackground: true,
            backgroundColor: Cesium.Color.BLACK.withAlpha(0.85),
            backgroundPadding: new Cesium.Cartesian2(8, 5),
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            verticalOrigin: Cesium.VerticalOrigin.TOP,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            pixelOffset: new Cesium.Cartesian2(0, -15),
            scale: 1.0,
          },
        });
        labelEnt.regionId = labelData.regionId;
        labelEnt.volume = labelData.volStr;
        labelEnt.area = labelData.areaStr;
        labelEnt.maxDepth = labelData.maxDepth.toFixed(2) + ' m';
        labelEnt.meanDepth = labelData.meanDepth.toFixed(2) + ' m';
        labelEnt.expanded = false;
        labelEnt.isRegionLabel = true;
        window._fillVolumeEntities.push(labelEnt);

        var detailsEnt = viewer.entities.add({
          id: 'fill-details-' + labelData.regionId,
          position: labelData.position,
          label: {
            text:
              'Volume: ' + labelData.volStr + '\n' +
              'Area: ' + labelData.areaStr + '\n' +
              'Max Depth: ' + labelData.maxDepth.toFixed(2) + ' m\n' +
              'Mean Depth: ' + labelData.meanDepth.toFixed(2) + ' m',
            font: "12px 'Segoe UI', Arial, sans-serif",
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            fillColor: Cesium.Color.WHITE,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
            showBackground: true,
            backgroundColor: Cesium.Color.fromCssColorString('#1a1a1a').withAlpha(0.92),
            backgroundPadding: new Cesium.Cartesian2(10, 6),
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            verticalOrigin: Cesium.VerticalOrigin.TOP,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            pixelOffset: new Cesium.Cartesian2(0, 15),
            scale: 0.95,
            show: false,
          },
        });
        detailsEnt.parentRegionId = labelData.regionId;
        detailsEnt.isDetails = true;
        window._fillVolumeEntities.push(detailsEnt);
        labelEnt.detailsEntity = detailsEnt;
      }

      requestSceneRender();
      log("info", "Fill volumes drawn: " + regions.length + " regions");
    },
  };

  document.addEventListener("DOMContentLoaded", initBridge);
})();
