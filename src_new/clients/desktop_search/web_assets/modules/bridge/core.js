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
  // Reserved for future hillshade rebuild throttling.
  // Stores original DEM rescale range from server (before any color mode switch)
  let _demOriginalRescale = null;
  // Stores the last UI display order for layers (set by enforceLayerDisplayOrder OR reorderLayersEventDriven)
  // so it can be re-applied after any drape swap without a Python round-trip.
  let _lastKnownLayerOrder = null;
  // Stable camera range used for pitch/rotate so rapid slider events don't compute
  // a live distance from a mid-flight camera position (which causes jump artifacts).
  let _cameraOrbitRange = null;
  let lastMousePosition = null;
  const managedImageryLayers = new Map();
  const vectorLayerSources = new Map();
  let northPolarCapLayer = null;
  let southPolarCapLayer = null;
  let defaultEarthLayer = null;  // Default Earth imagery when OSM is hidden
  let osmBasemapLayer = null;    // OSM tile layer (lazy-loaded)
  let countryBoundaryDataSource = null;
  const clickedPoints = [];
  const annotationEntities = [];
  let hoveredAnnotationEditEntity = null;
    let hoveredAnnotationDeleteEntity = null;
  let lastMapClickCartesian = null;
  window._currentBasemapVisibility = false; // Match Python backend default

  let annotationCounter = 0;
  let measurementLineEntity = null;
  let measurementLabelEntity = null;
  let measurementPointEntities = [];
  let measurementPreviewLineEntity = null;
  let measurementAnchorDotEntity = null;
  let measurementPreviewLabelEntity = null;
  let measurementPreviewStart = null;
  let measurementPreviewEnd = null;
  let lineDrawModeEnabled = false;
  let lineDrawStart = null;
  let lineDrawPreviewLineEntity = null;
  let lineDrawPreviewStart = null;
  let lineDrawPreviewEnd = null;
  let distanceMeasureModeEnabled = false;
  let distanceMeasureAnchor = null;
  let swipeComparatorEnabled = false;
  let swipeComparatorPosition = 0.5;
  let swipeDividerElement = null;
  let swipeComparatorLeftLayerKey = null;
  let swipeComparatorRightLayerKey = null;
  let swipeComparatorExplicitKeys = [];   // Full ordered list of selected layer keys (N-pane support)
  let comparatorModeEnabled = false;
  window.OfflineGISRuntime = window.OfflineGISRuntime || {};
  Object.defineProperty(window.OfflineGISRuntime, "comparatorModeEnabled", {
    get: function () { return comparatorModeEnabled; },
    set: function (val) {
      comparatorModeEnabled = val;
      console.log("[offlineGIS] runtime.comparatorModeEnabled set to:", val);
    },
    configurable: true
  });
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
  const COMPARATOR_DEM_REFRESH_DEBOUNCE_MS = 32;
  let flyThroughModeEnabled = false;
  const flyThroughPoints = [];
  let flyThroughPreviewLineEntity = null;
  let flyThroughPathEntity = null;
  let flyThroughIsPlaying = false;
  let flyThroughStopRequested = false;
  let flyThroughOriginalView = null;
  let flyThroughPreviewEnd = null;
  let flyThroughSpeedMultiplier = 1.0;
  let flyThroughPlaybackProgress = 0.0;
  let flyThroughPlaybackPitchDegrees = -42.0;
  let flyThroughPlaybackHeightMeters = 900.0;
  let flyThroughPlaybackLastTimestamp = 0;
  let flyThroughPlaybackFrameHandle = null;
  let flyThroughPlaybackSegmentIndex = 0;
  let flyThroughPlaybackSegmentStartMs = 0;
  let flyThroughPlaybackPausedElapsedMs = 0;
  let flyThroughPlaybackPaused = false;
  const runtime = (window.OfflineGISRuntime = window.OfflineGISRuntime || {});
  const bridgeUtils = window.OfflineGISUtils || {};
  const log = bridgeUtils.log || function (level, message) {
    const fn = console[level] || console.log;
    fn("[offlineGIS]", message);
  };
  const setStatus = bridgeUtils.setStatus || function (text) {
    const el = document.getElementById("status");
    if (el) el.textContent = text;
  };
  const emitMapClick = bridgeUtils.emitMapClick || function () {};
  const emitMeasurementUpdated = bridgeUtils.emitMeasurementUpdated || function () {};
  const emitLoadingProgress = bridgeUtils.emitLoadingProgress || function () {};
  const requestSceneRender = bridgeUtils.requestSceneRender || function () {
    // Fallback: directly trigger a render frame if viewer is available
    if (viewer?.scene) {
      viewer.scene.requestRender();
    }
  };
  const setComparatorWindowsVisible = bridgeUtils.setComparatorWindowsVisible || function () {};
  const ensureRubberBandLine = bridgeUtils.ensureRubberBandLine || function () { return null; };
  const clearRubberBandLine = bridgeUtils.clearRubberBandLine || function () {};
  const normalizeBounds = bridgeUtils.normalizeBounds || function (bounds) {
    if (!bounds) {
      return null;
    }
    if (Array.isArray(bounds) && bounds.length === 4) {
      const west = Number(bounds[0]);
      const south = Number(bounds[1]);
      const east = Number(bounds[2]);
      const north = Number(bounds[3]);
      if (Number.isFinite(west) && Number.isFinite(south) && Number.isFinite(east) && Number.isFinite(north)) {
        return { west: west, south: south, east: east, north: north };
      }
    }
    if (typeof bounds === "object") {
      const west = Number(bounds.west);
      const south = Number(bounds.south);
      const east = Number(bounds.east);
      const north = Number(bounds.north);
      if (Number.isFinite(west) && Number.isFinite(south) && Number.isFinite(east) && Number.isFinite(north)) {
        return { west: west, south: south, east: east, north: north };
      }
    }
    return null;
  };
  const cursorControls = window.OfflineGISCursorControls || {};
  const setSearchCursorEnabled = cursorControls.setSearchCursorEnabled || function () {};
  const updateSearchCursorOverlay = cursorControls.updateSearchCursorOverlay || function () {};
  const setSearchCursorOverlayVisible = cursorControls.setSearchCursorOverlayVisible || function () {};
  const setMeasurementCursorEnabled = cursorControls.setMeasurementCursorEnabled || function () {};
  const _enforceMeasureCursor = cursorControls._enforceMeasureCursor || setMeasurementCursorEnabled;
  const ensureMeasureCursorOverlay = cursorControls.ensureMeasureCursorOverlay || function () {};
  const updateMeasureCursorOverlay = cursorControls.updateMeasureCursorOverlay || function () {};
  const setMeasureCursorOverlayVisible = cursorControls.setMeasureCursorOverlayVisible || function () {};
  const emitSearchGeometry =
    (window.OfflineGISModules &&
      window.OfflineGISModules.search &&
      window.OfflineGISModules.search.geometry &&
      window.OfflineGISModules.search.geometry.emitSearchGeometry) ||
    function () {};
  const createRectangle = bridgeUtils.createRectangle || function (bounds) {
    const normalized = normalizeBounds(bounds);
    return normalized ? Cesium.Rectangle.fromDegrees(normalized.west, normalized.south, normalized.east, normalized.north) : null;
  };
  const rectangleFromBounds = bridgeUtils.rectangleFromBounds || createRectangle;
  const applyCursorStyle = bridgeUtils.applyCursorStyle || function (element, cursorValue) {
    if (!element || !element.style) {
      return;
    }
    if (cursorValue) {
      element.style.setProperty("cursor", cursorValue, "important");
      return;
    }
    element.style.removeProperty("cursor");
  };
  const parseDemHeightRange = bridgeUtils.parseDemHeightRange || function (options) {
    const defaultRange = { min: -500.0, max: 9000.0 };
    const query = options?.query ? options.query : null;
    if (!query || typeof query.rescale !== "string") {
      return defaultRange;
    }
    const parts = query.rescale.split(",").map((value) => Number(value.trim()));
    if (parts.length !== 2 || !Number.isFinite(parts[0]) || !Number.isFinite(parts[1]) || parts[1] <= parts[0]) {
      return defaultRange;
    }
    return { min: parts[0], max: parts[1] };
  };

  const getDemTerrainHeightFallback = function () {
    if (typeof activeDemContext !== "undefined" && activeDemContext?.options && activeDemContext.options.query) {
      const rescale = activeDemContext.options.query.rescale;
      if (typeof rescale === "string") {
        const parts = rescale.split(",").map(Number);
        if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
          return (parts[0] + parts[1]) * 0.5;
        }
      } else if (Array.isArray(rescale) && rescale.length > 0) {
        const parts = String(rescale[0]).split(",").map(Number);
        if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
          return (parts[0] + parts[1]) * 0.5;
        }
      }
    }
    return 0.0;
  };

  function getActiveDemColorMode() {
    return String((activeDemContext?.colorMode) || demVisual.colorMode || "terrain").toLowerCase();
  }

  function getDemRescaleRangeForColorMode(colorMode) {
    const normalized = String(colorMode || "terrain").toLowerCase();
    if (normalized === "slope") {
      return { min: 0.0, max: 90.0 };
    }
    if (normalized === "aspect") {
      return { min: 0.0, max: 360.0 };
    }
    if (_demOriginalRescale) {
      const parts = String(_demOriginalRescale).split(",").map((value) => Number(value.trim()));
      if (parts.length === 2 && Number.isFinite(parts[0]) && Number.isFinite(parts[1]) && parts[1] > parts[0]) {
        return { min: parts[0], max: parts[1] };
      }
    }
    return { min: -500.0, max: 9000.0 };
  }

  let flyThroughCursorCartesian = null;

  function liftFlyThroughPoint(cartesian) {
    if (!cartesian) {
      return null;
    }
    const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
    const terrainHeight = viewer?.scene && viewer.scene.globe
      ? viewer.scene.globe.getHeight(cartographic)
      : null;
    const baseHeight = Number.isFinite(terrainHeight)
      ? Number(terrainHeight)
      : Number.isFinite(cartographic.height)
        ? Number(cartographic.height)
        : 0.0;
    return Cesium.Cartesian3.fromRadians(
      cartographic.longitude,
      cartographic.latitude,
      baseHeight + 0.1
    );
  }

  function notifyFlyThroughPlaybackState(state) {
    if (bridge && typeof bridge.on_fly_through_playback_state === "function") {
      try {
        bridge.on_fly_through_playback_state(String(state));
      } catch (_) {}
    }
  }

  function cancelFlyThroughPlaybackFrame() {
    if (flyThroughPlaybackFrameHandle !== null) {
      window.cancelAnimationFrame(flyThroughPlaybackFrameHandle);
      flyThroughPlaybackFrameHandle = null;
    }
  }

  function notifyFlyThroughPlaybackProgress(progress) {
    if (bridge && typeof bridge.on_fly_through_playback_progress === "function") {
      try {
        const val = Number(progress);
        if (Number.isFinite(val)) {
          bridge.on_fly_through_playback_progress(val);
        }
      } catch (_) {}
    }
  }

  function buildFlyThroughPlaybackPlan() {
    if (flyThroughPoints.length < 2) {
      return null;
    }

    const speedFactor = Math.max(0.1, Math.min(5.0, Number(flyThroughSpeedMultiplier) || 1.0));
    const distances = [0];
    let totalDist = 0;

    for (let index = 0; index < flyThroughPoints.length - 1; index += 1) {
      const p1 = flyThroughPoints[index];
      const p2 = flyThroughPoints[index + 1];
      if (!p1 || !p2) {
        distances.push(totalDist);
        continue;
      }

      const carto1 = Cesium.Cartographic.fromCartesian(p1);
      const carto2 = Cesium.Cartographic.fromCartesian(p2);
      const geodesic = new Cesium.EllipsoidGeodesic(carto1, carto2);
      totalDist += geodesic.surfaceDistance;
      distances.push(totalDist);
    }

    // Generate normalized strictly increasing time parameters [0.0, 1.0]
    const times = distances.map(function (d) {
      return totalDist > 0 ? d / totalDist : 0.0;
    });
    for (let i = 1; i < times.length; i++) {
      if (times[i] <= times[i - 1]) {
        times[i] = times[i - 1] + 0.0001;
      }
    }
    times[times.length - 1] = 1.0;

    const pointsFiltered = flyThroughPoints.filter(Boolean);
    const spline = {
      times: times,
      points: pointsFiltered,
      evaluate: function(normalized) {
        const t = Cesium.Math.clamp(normalized, 0.0, 1.0);
        if (pointsFiltered.length === 0) return null;
        if (pointsFiltered.length === 1) return pointsFiltered[0].clone();
        
        let idx = 0;
        while (idx < times.length - 2 && times[idx + 1] < t) {
          idx++;
        }
        const t0 = times[idx];
        const t1 = times[idx + 1];
        const u = (t1 - t0) > 1e-5 ? (t - t0) / (t1 - t0) : 0.0;
        
        const p0 = pointsFiltered[idx];
        const p1 = pointsFiltered[idx + 1];
        
        return Cesium.Cartesian3.lerp(p0, p1, u, new Cesium.Cartesian3());
      }
    };

    const totalDurationMs = Math.max(1000, (totalDist / (18 * speedFactor)) * 1000);

    return {
      spline: spline,
      totalDurationMs: totalDurationMs,
      totalDist: totalDist,
    };
  }

  function getFlyThroughStateForProgress(progress, plan) {
    const normalized = Math.max(0, Math.min(1, Number(progress) || 0));
    const playbackPlan = plan || buildFlyThroughPlaybackPlan();
    if (!playbackPlan || !playbackPlan.spline) {
      return null;
    }

    const spline = playbackPlan.spline;
    const totalDurationMs = playbackPlan.totalDurationMs;

    let groundPos = null;
    try {
      groundPos = spline.evaluate(normalized);
    } catch (e) {
      log("error", "Spline evaluation failed: " + e.message);
      return null;
    }

    // Calculate heading using local direction vector at normalized time
    const dt = 0.01;
    const tMinus = Math.max(0, normalized - dt);
    const tPlus = Math.min(1, normalized + dt);

    const pMinus = spline.evaluate(tMinus);
    const pPlus = spline.evaluate(tPlus);
    const direction = Cesium.Cartesian3.subtract(pPlus, pMinus, new Cesium.Cartesian3());

    let rawHeading = 0.0;
    if (Cesium.Cartesian3.magnitude(direction) > 1e-4) {
      const enuMatrix = Cesium.Transforms.eastNorthUpToFixedFrame(groundPos);
      const east = Cesium.Matrix4.getColumn(enuMatrix, 0, new Cesium.Cartesian3());
      const north = Cesium.Matrix4.getColumn(enuMatrix, 1, new Cesium.Cartesian3());
      const localDirectionX = Cesium.Cartesian3.dot(direction, east);
      const localDirectionY = Cesium.Cartesian3.dot(direction, north);

      if (Math.abs(localDirectionX) > 1e-7 || Math.abs(localDirectionY) > 1e-7) {
        rawHeading = Math.atan2(localDirectionX, localDirectionY);
      } else {
        rawHeading = window._flyThroughLastHeading !== undefined && window._flyThroughLastHeading !== null
          ? window._flyThroughLastHeading
          : 0.0;
      }
    } else {
      rawHeading = window._flyThroughLastHeading !== undefined && window._flyThroughLastHeading !== null
        ? window._flyThroughLastHeading
        : 0.0;
    }

    return {
      groundPos: groundPos,
      rawHeading: rawHeading,
      progress: normalized,
      localProgress: normalized,
      totalDurationMs: totalDurationMs,
    };
  }

  function applyFlyThroughCameraState(state) {
    if (!viewer || !viewer.camera || !state) {
      return;
    }

    const groundPos = state.groundPos;
    const groundCarto = Cesium.Cartographic.fromCartesian(groundPos);
    if (!groundCarto) {
      return;
    }

    const terrainHeight = viewer.scene.globe.getHeight(groundCarto);
    const heightOffset = Math.max(1.0, Math.min(2000.0, Number(flyThroughPlaybackHeightMeters) || 900.0));

    let finalHeight = groundCarto.height + heightOffset;
    const safetyHeight = (Number.isFinite(terrainHeight) ? terrainHeight : 0.0) + 20.0; // Clear at least 20m above terrain

    if (Number.isFinite(terrainHeight)) {
      const targetHeight = terrainHeight + heightOffset;
      if (window._flyThroughLastAdjustedHeight === undefined || window._flyThroughLastAdjustedHeight === null) {
        window._flyThroughLastAdjustedHeight = targetHeight;
      } else {
        // Dynamic low-pass filter: ascend quickly to prevent terrain collisions, descend slowly for flight stability
        const isAscending = targetHeight > window._flyThroughLastAdjustedHeight;
        const alpha = isAscending ? 0.12 : 0.03;
        window._flyThroughLastAdjustedHeight = window._flyThroughLastAdjustedHeight * (1.0 - alpha) + targetHeight * alpha;
      }
      finalHeight = Math.max(window._flyThroughLastAdjustedHeight, safetyHeight);
    } else {
      window._flyThroughLastAdjustedHeight = null;
    }

    // Smooth heading with wrap-around interpolation
    const currentHeading = state.rawHeading;
    if (window._flyThroughLastHeading === undefined || window._flyThroughLastHeading === null) {
      window._flyThroughLastHeading = currentHeading;
    } else {
      let diff = currentHeading - window._flyThroughLastHeading;
      diff = Math.atan2(Math.sin(diff), Math.cos(diff));
      const headingAlpha = 0.10; // smooth turnaround factor
      window._flyThroughLastHeading = window._flyThroughLastHeading + diff * headingAlpha;
    }

    // Smooth pitch with low-pass filter
    const targetPitch = Cesium.Math.toRadians(flyThroughPlaybackPitchDegrees);
    if (window._flyThroughLastPitch === undefined || window._flyThroughLastPitch === null) {
      window._flyThroughLastPitch = targetPitch;
    } else {
      const pitchAlpha = 0.10; // smooth pitch factor
      window._flyThroughLastPitch = window._flyThroughLastPitch * (1.0 - pitchAlpha) + targetPitch * pitchAlpha;
    }

    const destination = Cesium.Cartesian3.fromRadians(
      groundCarto.longitude,
      groundCarto.latitude,
      finalHeight
    );

    viewer.camera.setView({
      destination: destination,
      orientation: {
        heading: window._flyThroughLastHeading,
        pitch: window._flyThroughLastPitch,
        roll: 0.0,
      },
    });
  }

  function syncFlyThroughPlaybackToProgress(progress, requestRender) {
    const normalized = Math.max(0, Math.min(1, Number(progress) || 0));
    flyThroughPlaybackProgress = normalized;
    const state = getFlyThroughStateForProgress(normalized);
    if (state) {
      applyFlyThroughCameraState(state);
    }
    flyThroughPlaybackLastTimestamp = performance.now();
    notifyFlyThroughPlaybackProgress(normalized);
    if (requestRender !== false) {
      requestSceneRender();
    }
    return state;
  }

  function setFlyThroughSpeed(value) {
    const nextSpeed = Number(value);
    if (!Number.isFinite(nextSpeed) || nextSpeed <= 0) {
      return;
    }
    flyThroughSpeedMultiplier = Math.max(0.1, Math.min(5.0, nextSpeed));
    if (flyThroughPoints.length >= 2) {
      syncFlyThroughPlaybackToProgress(flyThroughPlaybackProgress, true);
    }
  }

  function setFlyThroughPlaybackProgress(value) {
    if (flyThroughPoints.length < 2) {
      return;
    }
    const normalized = Math.max(0, Math.min(0.999, Number(value) || 0));
    syncFlyThroughPlaybackToProgress(normalized, true);
  }

  function setFlyThroughPitch(value) {
    const nextPitch = Number(value);
    if (!Number.isFinite(nextPitch)) {
      return;
    }
    flyThroughPlaybackPitchDegrees = Math.max(-80.0, Math.min(-10.0, nextPitch));
    if (flyThroughPoints.length >= 2) {
      syncFlyThroughPlaybackToProgress(flyThroughPlaybackProgress, true);
    }
  }

  function setFlyThroughHeight(value) {
    const nextHeight = Number(value);
    if (!Number.isFinite(nextHeight)) {
      return;
    }
    flyThroughPlaybackHeightMeters = Math.max(50.0, Math.min(10000.0, nextHeight));
    if (flyThroughPoints.length >= 2) {
      syncFlyThroughPlaybackToProgress(flyThroughPlaybackProgress, true);
    }
  }

  function applyFlyThroughPlaybackFrame(timestamp) {
    if (!flyThroughIsPlaying || flyThroughStopRequested) {
      cancelFlyThroughPlaybackFrame();
      return;
    }

    const playbackPlan = buildFlyThroughPlaybackPlan();
    if (!playbackPlan) {
      finishFlyThroughPlayback();
      return;
    }

    if (!flyThroughPlaybackLastTimestamp) {
      flyThroughPlaybackLastTimestamp = timestamp;
    }

    const deltaMs = Math.max(0, timestamp - flyThroughPlaybackLastTimestamp);
    flyThroughPlaybackLastTimestamp = timestamp;
    const totalDurationMs = Math.max(1, playbackPlan.totalDurationMs);
    flyThroughPlaybackProgress = Math.max(0, flyThroughPlaybackProgress + (deltaMs / totalDurationMs));

    if (flyThroughPlaybackProgress >= 1.0) {
      flyThroughPlaybackProgress = 1.0;
      notifyFlyThroughPlaybackProgress(1.0);
      finishFlyThroughPlayback();
      return;
    }

    const state = getFlyThroughStateForProgress(flyThroughPlaybackProgress, playbackPlan);
    if (!state) {
      finishFlyThroughPlayback();
      return;
    }

    applyFlyThroughCameraState(state);
    notifyFlyThroughPlaybackProgress(flyThroughPlaybackProgress);
    requestSceneRender();
    flyThroughPlaybackFrameHandle = window.requestAnimationFrame(applyFlyThroughPlaybackFrame);
  }

  function startFlyThroughAnimation() {
    if (flyThroughPoints.length < 2 || flyThroughIsPlaying) {
      return;
    }

    flyThroughStopRequested = false;
    flyThroughModeEnabled = false;
    flyThroughIsPlaying = true;
    flyThroughPlaybackPaused = false;
    flyThroughPlaybackProgress = 0.0;
    flyThroughPlaybackLastTimestamp = 0;
    window._flyThroughLastAdjustedHeight = null;
    window._flyThroughLastHeading = null;
    window._flyThroughLastPitch = null;

    if (!flyThroughOriginalView) {
      flyThroughOriginalView = {
        destination: viewer.camera.position.clone(),
        orientation: {
          heading: viewer.camera.heading,
          pitch: viewer.camera.pitch,
          roll: viewer.camera.roll,
        },
        fov: viewer.camera.frustum.fov,
      };
    }

    if (flyThroughPreviewLineEntity) {
      viewer.entities.remove(flyThroughPreviewLineEntity);
      flyThroughPreviewLineEntity = null;
    }
    flyThroughPreviewEnd = null;

    viewer.scene.screenSpaceCameraController.enableInputs = false;
    viewer.camera.frustum.fov = Cesium.Math.toRadians(80.0);
    notifyFlyThroughPlaybackState("playing");
    syncFlyThroughPlaybackToProgress(0.0, true);
    cancelFlyThroughPlaybackFrame();
    flyThroughPlaybackFrameHandle = window.requestAnimationFrame(applyFlyThroughPlaybackFrame);
    setStatus("Starting fly through...");
  }

  function pauseFlyThroughAnimation() {
    if (!flyThroughIsPlaying) {
      return;
    }
    flyThroughPlaybackPaused = true;
    flyThroughIsPlaying = false;
    cancelFlyThroughPlaybackFrame();
    window._flyThroughLastAdjustedHeight = null;
    window._flyThroughLastHeading = null;
    window._flyThroughLastPitch = null;
    notifyFlyThroughPlaybackState("paused");
    setStatus("Fly through paused.");
  }

  function toggleFlyThroughPlayback() {
    if (flyThroughIsPlaying) {
      pauseFlyThroughAnimation();
      return;
    }
    if (flyThroughPoints.length < 2) {
      setStatus("Draw at least 2 points for a fly through.");
      return;
    }
    if (flyThroughPlaybackPaused) {
      flyThroughPlaybackPaused = false;
      flyThroughIsPlaying = true;
      flyThroughPlaybackLastTimestamp = performance.now();
      notifyFlyThroughPlaybackState("playing");
      cancelFlyThroughPlaybackFrame();
      flyThroughPlaybackFrameHandle = window.requestAnimationFrame(applyFlyThroughPlaybackFrame);
      return;
    }
    startFlyThroughAnimation();
  }

  function finishFlyThroughPlayback() {
    cancelFlyThroughPlaybackFrame();
    flyThroughIsPlaying = false;
    flyThroughPlaybackPaused = false;
    flyThroughPlaybackProgress = 0.0;
    flyThroughPlaybackLastTimestamp = 0;
    flyThroughStopRequested = false;
    window._flyThroughLastAdjustedHeight = null;
    window._flyThroughLastHeading = null;
    window._flyThroughLastPitch = null;

    const restoreView = function () {
      if (viewer?.scene && viewer.scene.screenSpaceCameraController) {
        viewer.scene.screenSpaceCameraController.enableInputs = true;
      }
      if (flyThroughOriginalView && viewer?.camera) {
        try {
          viewer.camera.setView({
            destination: flyThroughOriginalView.destination,
            orientation: flyThroughOriginalView.orientation,
          });
          viewer.camera.frustum.fov = flyThroughOriginalView.fov;
        } catch (_) {}
      }
      flyThroughOriginalView = null;
      flyThroughPoints.length = 0;
      if (flyThroughPathEntity) {
        viewer.entities.remove(flyThroughPathEntity);
        flyThroughPathEntity = null;
      }
      setStatus("Fly through complete.");
      notifyFlyThroughPlaybackState("ended");
      notifyFlyThroughPlaybackProgress(0.0);
      requestSceneRender();
    };

    if (flyThroughOriginalView && viewer?.camera) {
      viewer.camera.flyTo({
        destination: flyThroughOriginalView.destination,
        orientation: flyThroughOriginalView.orientation,
        duration: Math.max(0.4, 2.5 / Math.max(0.1, Math.min(5.0, Number(flyThroughSpeedMultiplier) || 1.0))),
        complete: restoreView,
        cancel: restoreView,
      });
      return;
    }

    restoreView();
  }

  function updateFlyThroughPreview(mousePos) {
    if (!flyThroughModeEnabled) return;

    if (mousePos) {
      // Use depth pick when available for stable terrain clamping.
      let cartesian = null;
      if (viewer.scene.pickPositionSupported) {
        try {
          cartesian = viewer.scene.pickPosition(mousePos);
        } catch (_) {}
      }
      if (!cartesian) {
        let ray = viewer.camera.getPickRay(mousePos);
        if (ray) {
          cartesian = viewer.scene.globe.pick(ray, viewer.scene);
        }
      }
      if (!cartesian) {
        cartesian = viewer.camera.pickEllipsoid(mousePos, viewer.scene.globe.ellipsoid);
      }
      if (cartesian) {
        let carto = Cesium.Cartographic.fromCartesian(cartesian);
        let terrainHeight = viewer.scene.globe.getHeight(carto);
        let height = (terrainHeight !== undefined && terrainHeight !== null)
          ? terrainHeight
          : carto.height;
        flyThroughCursorCartesian = Cesium.Cartesian3.fromRadians(
          carto.longitude,
          carto.latitude,
          Number.isFinite(height) ? height : 0
        );
        flyThroughPreviewEnd = flyThroughCursorCartesian;
      }
    } else {
      flyThroughPreviewEnd = null;
    }

    if (flyThroughPoints.length === 0) {
      return;
    }

    flyThroughPreviewLineEntity = ensureRubberBandLine(
      "fly-through-preview",
      function () {
        if (!flyThroughPoints.length) {
          return [];
        }
        const lifted = flyThroughPoints.map(liftFlyThroughPoint).filter(Boolean);
        if (flyThroughPreviewEnd) {
          const endPoint = liftFlyThroughPoint(flyThroughPreviewEnd);
          if (endPoint) {
            lifted.push(endPoint);
          }
        }
        return lifted;
      },
        {
          width: 1.2,
          color: "#00e5ff",
          alpha: 1.0,
          clampToGround: false,
        }
    );
    requestSceneRender();
  }

  function reapplyLayerOrderIfKnown() {
    if (!_lastKnownLayerOrder || _lastKnownLayerOrder.length === 0) {
      return;
    }
    if (window.offlineGIS && typeof window.offlineGIS.enforceLayerDisplayOrder === "function") {
      window.offlineGIS.enforceLayerDisplayOrder(_lastKnownLayerOrder);
    }
  }

  function finishFlyThroughPath() {
    if (flyThroughPoints.length < 2) {
      setStatus("Draw at least 2 points for a fly through.");
      return;
    }
    flyThroughModeEnabled = false;
    if (flyThroughPreviewLineEntity) {
      viewer.entities.remove(flyThroughPreviewLineEntity);
      flyThroughPreviewLineEntity = null;
    }
    flyThroughPreviewEnd = null;
    if (flyThroughPathEntity) viewer.entities.remove(flyThroughPathEntity);

    flyThroughPathEntity = viewer.entities.add({
      polyline: {
        positions: flyThroughPoints.map(liftFlyThroughPoint).filter(Boolean),
        width: 0.8,
        material: Cesium.Color.fromCssColorString("#00e5ff"),
        depthFailMaterial: Cesium.Color.fromCssColorString("#00e5ff"),
        arcType: Cesium.ArcType.GEODESIC,
        clampToGround: false,
      }
    });
  }

  // Debounce timers for visual properties
  let _demPropertiesDebounceTimer = null;
  let _imageryPropertiesDebounceTimer = null;
  const VISUAL_UPDATE_DEBOUNCE_MS = 16; // ~1 frame at 60fps
  const buildUrlWithQuery = bridgeUtils.buildUrlWithQuery || function (url, extraQuery) {
    const splitIndex = url.indexOf("?");
    const base = splitIndex >= 0 ? url.slice(0, splitIndex) : url;
    const queryText = splitIndex >= 0 ? url.slice(splitIndex + 1) : "";
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
    const finalParams = Object.assign({}, existingParams, extraQuery || {});
    const encodeValue = function (key, value) {
      if (key === "url") {
        return encodeURIComponent(value)
          .replace(/%3A/gi, ":")
          .replace(/%2F/gi, "/")
          .replace(/%40/gi, "@");
      }
      return encodeURIComponent(value);
    };
    const paramPairs = Object.entries(finalParams)
      .map(function ([key, value]) {
        if (value === null || value === undefined) {
          return null;
        }
        if (Array.isArray(value)) {
          return value.map(function (item) {
            return encodeURIComponent(key) + "=" + encodeValue(key, String(item));
          }).join("&");
        }
        return encodeURIComponent(key) + "=" + encodeValue(key, String(value));
      })
      .filter(Boolean);
    const merged = paramPairs.join("&");
    return merged ? base + "?" + merged : base;
  };
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
  // 3D mode pitch constraints: clear separation from 2D (which is always -90°)
  const MIN_3D_PITCH_RAD = Cesium.Math.toRadians(-80.0);   // never flatter than -80° in 3D
  const DEFAULT_3D_PITCH_RAD = Cesium.Math.toRadians(-35.0); // default oblique view for DEM
  const layerDefinitions = new Map();
  const layerVisibilityState = new Map();
  const managedPointCloudLayers = new Map();
  const tileErrorSeen = new Set();
  const layerErrorCounts = new Map();
  // DEM rendering uses imagery-only pipeline (colormap + hillshade on EllipsoidTerrainProvider)
  // No client-side terrain decoding — crash-proof for any raster size on macOS and Windows/NVIDIA
  const LOCAL_SATELLITE_TILE_ROOT = "./basemap/xyz";
  const DEFAULT_STARTUP_CENTER_LON = 78.0;  // India center longitude
  const DEFAULT_STARTUP_CENTER_LAT = 22.0;  // India center latitude
  const DEFAULT_STARTUP_HEIGHT_M = 6000000.0;   // ~6000 km — shows full India + surrounding region (better for tile visibility)
  const DEFAULT_STARTUP_HEADING = Cesium.Math.toRadians(0.0);
  const DEFAULT_STARTUP_PITCH = Cesium.Math.toRadians(-89.0);
  const WEB_MERCATOR_SAFE_EDGE_LAT_DEGREES = 85.05112878;
  const COUNTRY_BOUNDARY_GEOJSON_URL = "./data/countries.geojson";
  const SHOW_COUNTRY_BOUNDARY_OVERLAY = false;
  // DEM rendering uses imagery-only pipeline (colormap drape + hillshade overlay on EllipsoidTerrainProvider)
  // No client-side terrain decoding — crash-proof for any raster size on macOS and Windows/NVIDIA.
  // TERRAIN_SAMPLE_SIZE: 129 = 2^7+1 (valid heightmap grid size). Higher values give a
  // finer vertex mesh per tile — eliminates zig-zag/slanting edge artifacts and provides
  // smoother elevation at borders. Decode cost is O(N^2) so 129 vs 65 is 4× more work
  // per tile but still well within desktop GPU budget for the 3–4 cm/pixel DEM dataset.
  const TERRAIN_SAMPLE_SIZE = 129;
  const DEM_MAX_TERRAIN_LEVEL = 16;
  const DEM_HILLSHADE_AZIMUTH = 45;
  const DEM_HILLSHADE_ALTITUDE = 45;
  function createComparatorPaneVisualState() {
    return {
      imagery: {
        brightness: imageryVisual.brightness,
        contrast: imageryVisual.contrast,
      },
      dem: {
        exaggeration: demVisual.exaggeration,
        hillshadeAlpha: demVisual.hillshadeAlpha,
        colorMode: "gray",
      },
    };
  }
  function createComparatorCameraSyncState() {
    return {
      lastSourceWidthRad: NaN,
      lastSourceHeightRad: NaN,
      lastSourceCameraHeightM: NaN,
      lastSourceCenterLon: NaN,
      lastSourceCenterLat: NaN,
    };
  }
  function resolveComparatorPaneIndex(paneKey) {
    if (paneKey === "right") {
      return 1;
    }
    if (paneKey === "left" || paneKey === null || paneKey === undefined || paneKey === "") {
      return 0;
    }
    if (typeof paneKey === "number" && Number.isFinite(paneKey)) {
      return Math.max(0, Math.floor(paneKey));
    }
    const normalized = String(paneKey);
    const paneMatch = normalized.match(/^pane(\d+)$/i);
    if (paneMatch) {
      return Math.max(0, Number(paneMatch[1]) || 0);
    }
    const parsed = Number(normalized);
    if (Number.isInteger(parsed) && parsed >= 0) {
      return parsed;
    }
    return 0;
  }
  function getComparatorPaneKeyForIndex(index) {
    const normalized = Math.max(0, Number(index) || 0);
    if (normalized === 0) {
      return "left";
    }
    if (normalized === 1) {
      return "right";
    }
    return "pane" + normalized;
  }
  const demVisual = {
    exaggeration: 0.6,
    hillshadeAlpha: 0.0,
    colorMode: "terrain",
  };
  const imageryVisual = {
    brightness: 1.0,
    contrast: 1.0,
  };
  let comparatorSelectedPane = "left";
  const comparatorPaneVisualState = {
    left: createComparatorPaneVisualState(),
    right: createComparatorPaneVisualState(),
  };
  const comparatorDemStyleRefreshVersion = {
    left: 0,
    right: 0,
  };
  const comparatorCameraSyncState = {
    left: createComparatorCameraSyncState(),
    right: createComparatorCameraSyncState(),
  };
  let searchDrawMode = "none";
  const searchPolygonPoints = [];
  let searchPolygonLocked = false;
  let searchCursorPoint = null;
  let searchRectangleStartPoint = null;
  let searchRectangleCurrentPoint = null;
  let searchRectangleLocked = false;
  window.searchCursorEntity = null;
  window.searchPreviewLineEntity = null;
  window.searchPreviewPolygonEntity = null;
  window.searchAreaLabelEntity = null;
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
  const searchPolygonControllerFactory =
    window.OfflineGISSearchPolygonController &&
    window.OfflineGISSearchPolygonController.createSearchPolygonController;
  const searchPolygonController = searchPolygonControllerFactory
    ? searchPolygonControllerFactory({
        getViewer: function () {
          return viewer;
        },
        getBridge: function () {
          return bridge;
        },
        getCesium: function () {
          return Cesium;
        },
        getSearchPolygonPoints: function () {
          return searchPolygonPoints;
        },
        getSearchCursorPoint: function () {
          return searchCursorPoint;
        },
        getSearchOverlayVisible: function () {
          return searchOverlayVisible;
        },
        getPolygonVisibilityEnabled: function () {
          return polygonVisibilityEnabled;
        },
        getSearchPreviewLineEntity: function () {
          return window.searchPreviewLineEntity;
        },
        setSearchPreviewLineEntity: function (value) {
          window.searchPreviewLineEntity = value;
        },
        getSearchPreviewPolygonEntity: function () {
          return window.searchPreviewPolygonEntity;
        },
        setSearchPreviewPolygonEntity: function (value) {
          window.searchPreviewPolygonEntity = value;
        },
        getSearchAreaLabelEntity: function () {
          return window.searchAreaLabelEntity;
        },
        setSearchAreaLabelEntity: function (value) {
          window.searchAreaLabelEntity = value;
        },
        getSearchCursorEntity: function () {
          return window.searchCursorEntity;
        },
        setSearchCursorEntity: function (value) {
          window.searchCursorEntity = value;
        },
        getSearchVertexEntities: function () {
          return searchVertexEntities;
        },
        setSearchVertexEntities: function () {},
        getDrawnPolygons: function () {
          return drawnPolygons;
        },
        setDrawnPolygons: function () {},
        getComparatorModeEnabled: function () {
          return comparatorModeEnabled;
        },
        getComparatorLeftViewer: function () {
          return comparatorLeftViewer;
        },
        getComparatorRightViewer: function () {
          return comparatorRightViewer;
        },
        getComparatorPolygonEntities: function () {
          return comparatorPolygonEntities;
        },
        getSearchDrawMode: function () {
          return searchDrawMode;
        },
        getSearchOverlayVisible: function () {
          return typeof window._offlineGISSearchOverlayVisible === "boolean"
            ? window._offlineGISSearchOverlayVisible
            : searchOverlayVisible;
        },
        setSearchDrawMode: function (value) {
          const prev = searchDrawMode;
          searchDrawMode = value;
          // BUG FIX: When starting a new polygon draw, always reset the locked state
          // and clear stale points. Previously the locked flag from a finalized polygon
          // would persist into the new draw session, causing Escape to silently fail and
          // new click-points to stack on top of the old polygon's ghost points.
          if (value === "polygon" && prev !== "polygon") {
            searchPolygonLocked = false;
            searchPolygonPoints.length = 0;
            searchCursorPoint = null;
          }
        },
        setSearchCursorPoint: function (value) {
          searchCursorPoint = value;
        },
        setSearchPolygonLocked: function (value) {
          searchPolygonLocked = value;
        },
        setSearchOverlayVisible: function (value) {
          searchOverlayVisible = Boolean(value);
          window._offlineGISSearchOverlayVisible = searchOverlayVisible;
          // Enforce visibility immediately for any existing drawn polygons
          try {
            for (let i = 0; i < drawnPolygons.length; i += 1) {
              const poly = drawnPolygons[i];
              if (!poly || poly._isAnnotationPoly) continue;
              const shouldShow = Boolean(poly.visible) && searchOverlayVisible;
              if (poly.lineEntity) poly.lineEntity.show = shouldShow;
              if (poly.polygonEntity) poly.polygonEntity.show = shouldShow;
              if (poly.areaLabelEntity) poly.areaLabelEntity.show = shouldShow;
            }
          } catch (e) {
            // ignore errors while enforcing visibility
          }
          if (window.offlineGIS && typeof window.offlineGIS.syncSearchResultMarkerVisibility === "function") {
            try {
              window.offlineGIS.syncSearchResultMarkerVisibility();
            } catch (_) {}
          }
          requestSceneRender();
        },
        getAoiPanelMinimized: function () {
          return aoiPanelMinimized;
        },
        setAoiPanelMinimized: function (value) {
          aoiPanelMinimized = value;
        },
        requestSceneRender: requestSceneRender,
        setSearchCursorEnabled: setSearchCursorEnabled,
        updateComparatorPolygons: function (value) {
          updateComparatorPolygons(value);
        },
        incrementDrawnPolygonCounter: function () {
          drawnPolygonCounter += 1;
        },
        getDrawnPolygonCounter: function () {
          return drawnPolygonCounter;
        },
        getIsAnnotationDrawing: function () {
          return isAnnotationDrawing;
        },
        getAnnotationVisibilityEnabled: function () {
          return annotationVisibilityEnabled;
        },
        emitSearchGeometry: function (type, payload) {
          if (offlineGIS.on_search_geometry) {
            offlineGIS.on_search_geometry(type, payload);
          }
        },
        setStatus: setStatus,
        log: log,
      })
    : null;
  let isAnnotationDrawing = false;
  let annotationVisibilityEnabled = true;
  let sceneModeControlEnabled = true;
  let currentSceneMode = "3d";
  let isInteracting = false;
  let scenePerfDefaults = null;
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
  const EDGE_SCALE_UPDATE_INTERVAL_MS = 120;
  const EDGE_SCALE_UPDATE_INTERVAL_2D_MS = 320;
  const ANNOTATION_DELETE_ICON_IMAGE = "data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%2720%27 height=%2720%27 viewBox=%270 0 20 20%27%3E%3Ccircle cx=%2710%27 cy=%2710%27 r=%279%27 fill=%27rgba(220%2C50%2C50%2C0.92)%27 stroke=%27rgba(0%2C0%2C0%2C0.38)%27 stroke-width=%271.1%27/%3E%3Cpath d=%27M6 6L14 14M14 6L6 14%27 stroke=%27%23ffffff%27 stroke-width=%272%27 stroke-linecap=%27round%27/%3E%3C/svg%3E";
  const ANNOTATION_EDIT_ICON_IMAGE =
    "data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%2720%27 height=%2720%27 viewBox=%270 0 20 20%27%3E%3Ccircle cx=%2710%27 cy=%2710%27 r=%279%27 fill=%27rgba(255%2C255%2C255%2C0.92)%27 stroke=%27rgba(0%2C0%2C0%2C0.38)%27 stroke-width=%271.1%27/%3E%3Cpath d=%27M6.1 12.9l.5-2.2L11.8 5.5a1.3 1.3 0 011.8 0l.8.8a1.3 1.3 0 010 1.8L9.1 13.3l-2.2.5a.6.6 0 01-.8-.7z%27 fill=%27%23282f39%27/%3E%3Cpath d=%27M10.9 6.4l2.7 2.7%27 stroke=%27%23ffffff%27 stroke-width=%271%27 stroke-linecap=%27round%27/%3E%3C/svg%3E";
  const _SB_COORD_THROTTLE_MS = 50; // Faster coordinate updates (20 fps) - reduced from 100ms
  const _SB_CAMERA_THROTTLE_MS = 100; // Throttle camera change events to reduce overhead (~10 fps)
  const _SB_RENDER_IDLE_DELAY_MS = 120;
  let _sbLastCoordEmitMs = 0;
  let _sbLastCameraEmitMs = 0;
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

  // ── Tile loading progress via native Cesium event (accurate, zero polling) ──
  // Wired in wireStatusBarListeners() after viewer is ready.
  let _tileQueuePeak = 0;

  function startTileLoadingMonitor() {
    // No-op — progress is driven by tileLoadProgressEvent in wireStatusBarListeners
    _tileLoadingActive = true;
  }
  
  // stopTileLoadingMonitor removed — monitor resets via tileLoadProgressEvent directly

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

// TODO: Refactor this function to reduce its Cognitive Complexity from 22 to the 15 allowed.
  function getCartesianFromViewer(targetViewer, screenPosition) {
    if (!targetViewer || !screenPosition || !targetViewer.scene) {
      return null;
    }
    const scene = targetViewer.scene;
    let cartesian = null;
    try {
      // 1. globe.pick — most accurate, works when terrain tiles are loaded
      if (scene.globe) {
        const ray = targetViewer.camera.getPickRay(screenPosition);
        if (ray) {
          cartesian = scene.globe.pick(ray, scene);
        }
      }
      // 2. pickPosition — works for rendered geometry (DEMs, entities)
      if (!cartesian && scene.pickPositionSupported) {
        try {
          const depthCart = scene.pickPosition(screenPosition);
          if (depthCart && Cesium.Cartesian3.magnitude(depthCart) > 1.0) {
            cartesian = depthCart;
          }
        } catch (_) {}
      }
      // 3. pickEllipsoid — always succeeds if the screen point is over the globe.
      // This is the critical fallback for DEM panes in 3D mode where globe.pick
      // returns null when terrain tiles haven't loaded at that pixel.
      if (!cartesian) {
        const ellipsoid = scene.globe ? scene.globe.ellipsoid : Cesium.Ellipsoid.WGS84;
        cartesian = targetViewer.camera.pickEllipsoid(screenPosition, ellipsoid);
      }
      // 4. Re-project 2D map-space Cartesian back to globe Cartesian if needed
      if (cartesian && scene.mode === Cesium.SceneMode.SCENE2D) {
        const projection = scene.mapProjection;
        if (projection) {
          const carto = projection.unproject(cartesian);
          const ellipsoid = scene.globe ? scene.globe.ellipsoid : Cesium.Ellipsoid.WGS84;
          cartesian = Cesium.Cartographic.toCartesian(carto, ellipsoid);
        }
      }
    } catch (err) {
      log("debug", "getCartesianFromViewer error: " + err.message);
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
      height: cartographic.height
    };
  }

  function sampleTerrainHeightsForPath(coords, isClosed = false, samplesPerSegment = 10) {
    if (!viewer || !viewer.scene || !viewer.scene.globe || !coords || coords.length < 2) {
      return coords || [];
    }
    const ellipsoid = viewer.scene.globe.ellipsoid || Cesium.Ellipsoid.WGS84;
    
    // Convert all input coordinates to Cartographic
    const cartographics = coords.map(function(c) {
      try {
        return Cesium.Cartographic.fromCartesian(c, ellipsoid);
      } catch (e) {
        return null;
      }
    }).filter(Boolean);

    if (cartographics.length < 2) {
      return coords;
    }

    if (isClosed && cartographics.length >= 3) {
      cartographics.push(cartographics[0]);
    }

    const points = [];
    for (let segment = 0; segment < cartographics.length - 1; segment++) {
      const start = cartographics[segment];
      const end = cartographics[segment + 1];
      if (!start || !end) continue;
      
      const count = segment === cartographics.length - 2 ? samplesPerSegment : samplesPerSegment - 1;
      for (let i = 0; i <= count; i++) {
        const t = i / samplesPerSegment;
        const lon = start.longitude + (end.longitude - start.longitude) * t;
        const lat = start.latitude + (end.latitude - start.latitude) * t;
        const carto = new Cesium.Cartographic(lon, lat);
        
        const terrainHeight = viewer.scene.globe.getHeight(carto);
        const height = (typeof terrainHeight === "number" && Number.isFinite(terrainHeight)) ? terrainHeight : 0.0;
        
        // Lift slightly above ground to prevent depth culling/z-fighting
        const cartesian = Cesium.Cartesian3.fromRadians(lon, lat, height + 0.15);
        points.push(cartesian);
      }
    }
    return points;
  }

  // Expose helper on offlineGIS runtime
  window.offlineGIS.sampleTerrainHeightsForPath = sampleTerrainHeightsForPath;

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
    if (screenPosition && Number.isFinite(screenPosition.x) && Number.isFinite(screenPosition.y)) {
      // Position the overlay crosshair at exact pixel coords within the pane.
      // The ::before/::after pseudo-elements extend -20px in each direction around this point.
      crosshairElement.style.left = screenPosition.x.toFixed(1) + "px";
      crosshairElement.style.top  = screenPosition.y.toFixed(1) + "px";
      crosshairElement.style.display = "block";
    } else {
      crosshairElement.style.display = "none";
    }
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

  function updateComparatorCenterReadout(sourceViewer, paneIdx) {
    if (!comparatorModeEnabled) {
      return;
    }
    let idx = (typeof paneIdx === "number") ? paneIdx : comparatorViewers.indexOf(sourceViewer);
    let targetViewer = sourceViewer || comparatorViewers[0];
    if (!targetViewer || !targetViewer.canvas) {
      return;
    }
    let center = new Cesium.Cartesian2(
      targetViewer.canvas.clientWidth * 0.5,
      targetViewer.canvas.clientHeight * 0.5,
    );
    let lonLat = getLonLatFromViewer(targetViewer, center);
    if (lonLat) {
      emitMouseCoordinates(lonLat.lon, lonLat.lat);
    }
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
// TODO: Refactor this function to reduce its Cognitive Complexity from 48 to the 15 allowed.

  function projectCartesianToViewer(targetViewer, worldCartesian) {
    if (!targetViewer || !worldCartesian) {
      return null;
    }
    try {
      if (isNaN(worldCartesian.x) || isNaN(worldCartesian.y) || isNaN(worldCartesian.z)) {
        return null;
      }
      let carto = null;
      let cartesianToProject = worldCartesian;
      if (targetViewer.scene) {
        const ellipsoid = targetViewer.scene.globe ? targetViewer.scene.globe.ellipsoid : Cesium.Ellipsoid.WGS84;
        carto = Cesium.Cartographic.fromCartesian(worldCartesian, ellipsoid);
        if (carto && !isNaN(carto.longitude) && !isNaN(carto.latitude)) {
          let height = 0.0;
          const hasTerrain = targetViewer.terrainProvider &&
                             targetViewer.terrainProvider.constructor &&
                             targetViewer.terrainProvider.constructor.name !== "EllipsoidTerrainProvider";

          if (targetViewer.scene.mode !== Cesium.SceneMode.SCENE2D && targetViewer.scene.globe) {
            if (hasTerrain) {
              const terrainHeight = targetViewer.scene.globe.getHeight(carto);
              if (typeof terrainHeight === "number" && !isNaN(terrainHeight)) {
                // Clamp to terrain surface + 10m offset so the point is always
                // above the terrain mesh and visible to SceneTransforms.
                height = terrainHeight + 10.0;
              } else {
                // Terrain tiles not loaded yet for this position — use a generous
                // above-ellipsoid offset so the point isn't occluded by terrain.
                height = 100.0;
              }
            }
            // S4165: else branch (height = 0.0) is redundant — height is already 0.0
          }
          carto.height = height;
          const projectedCart = Cesium.Cartographic.toCartesian(carto, ellipsoid);
          if (projectedCart && !isNaN(projectedCart.x) && !isNaN(projectedCart.y) && !isNaN(projectedCart.z)) {
            cartesianToProject = projectedCart;
          }
        }
      }

      // Primary: use Cesium's SceneTransforms (works perfectly in 2D/Columbus/3D views)
      let projected = null;
      try {
        projected = sceneToWindowCoordinates(targetViewer.scene, cartesianToProject);
      } catch (e) {}

      if (projected && Number.isFinite(projected.x) && Number.isFinite(projected.y) && !isNaN(projected.x) && !isNaN(projected.y)) {
        // Validate the projected pixel is within (or near) the canvas bounds
        const cw = targetViewer.canvas.clientWidth;
        const ch = targetViewer.canvas.clientHeight;
        if (projected.x >= -cw && projected.x <= 2 * cw && projected.y >= -ch && projected.y <= 2 * ch) {
          return new Cesium.Cartesian2(Number(projected.x), Number(projected.y));
        }
      }

      // Fallback: direct camera viewProjection matrix projection.
      // Works on tilted 3D DEM scenes where SceneTransforms returns null.
      try {
        const camera = targetViewer.camera;
        const scene = targetViewer.scene;
        if (!camera || !scene) return null;
        const cw = targetViewer.canvas.clientWidth;
        const ch = targetViewer.canvas.clientHeight;
        if (cw <= 0 || ch <= 0) return null;

        const viewProj = Cesium.Matrix4.multiply(
          camera.frustum.projectionMatrix,
          camera.viewMatrix,
          new Cesium.Matrix4()
        );

        let clipInputVec;
        if (scene.mode === Cesium.SceneMode.SCENE2D && carto) {
          const projection = scene.mapProjection;
          if (projection) {
            const projectedCoord = projection.project(carto);
            clipInputVec = new Cesium.Cartesian4(projectedCoord.x, projectedCoord.y, 0.0, 1.0);
          } else {
            clipInputVec = new Cesium.Cartesian4(cartesianToProject.x, cartesianToProject.y, cartesianToProject.z, 1.0);
          }
        } else {
          clipInputVec = new Cesium.Cartesian4(cartesianToProject.x, cartesianToProject.y, cartesianToProject.z, 1.0);
        }

        const clip = Cesium.Matrix4.multiplyByVector(viewProj, clipInputVec, new Cesium.Cartesian4());

        if (clip.w <= 0.0) return null;   // behind camera

        const ndcX = clip.x / clip.w;
        const ndcY = clip.y / clip.w;
        if (Number.isFinite(ndcX) && Number.isFinite(ndcY) && !isNaN(ndcX) && !isNaN(ndcY)) {
          const screenX = (ndcX + 1.0) * 0.5 * cw;
          const screenY = (1.0 - ndcY) * 0.5 * ch;
          return new Cesium.Cartesian2(screenX, screenY);
        }
      } catch (err) {
        return null;
      }
    } catch (err) {}
    return null;
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
    // Also clamp: if pitch is very shallow (near 0°) use the default tilt
    const tooShallow = Math.abs(pitch) < Cesium.Math.toRadians(10.0);
    if (tooShallow) {
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
    const centerLon = (focusRect.west + focusRect.east) * 0.5;
    const centerLat = (focusRect.south + focusRect.north) * 0.5;
    const centerCarto = new Cesium.Cartographic(centerLon, centerLat);
    let terrainHeight = undefined;
    if (targetViewer.scene.globe && typeof targetViewer.scene.globe.getHeight === "function") {
      const h = targetViewer.scene.globe.getHeight(centerCarto);
      if (typeof h === "number" && Number.isFinite(h)) {
        terrainHeight = h;
      }
    }
    if (terrainHeight === undefined || terrainHeight === null || isNaN(terrainHeight)) {
      terrainHeight = typeof getDemTerrainHeightFallback === "function"
          ? getDemTerrainHeightFallback()
          : 0.0;
    }
    if (targetViewer.scene.globe && typeof targetViewer.scene.globe.terrainExaggeration === "number") {
      terrainHeight *= targetViewer.scene.globe.terrainExaggeration;
    }
    const sphere = Cesium.BoundingSphere.fromRectangle3D(focusRect, Cesium.Ellipsoid.WGS84, terrainHeight);
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
    const is2d = targetViewer.scene && targetViewer.scene.mode === Cesium.SceneMode.SCENE2D;
    if (layerType === "dem" && !is2d) {
      setComparatorDemCameraFromRectangle(targetViewer, focusRect, targetViewer.camera.heading);
      return;
    }
    targetViewer.camera.setView({ destination: focusRect });
    if (targetViewer.scene) {
      targetViewer.scene.requestRender();
    }
  }

  // getComparatorLayerTypeForViewer removed — callers use comparatorLeftLayerType/comparatorRightLayerType directly

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
    const cameraHeight = sourceViewer?.camera && sourceViewer.camera.positionCartographic && Number.isFinite(sourceViewer.camera.positionCartographic.height)
      ? Number(sourceViewer.camera.positionCartographic.height)
      : NaN;
    state.lastSourceCameraHeightM = Number.isFinite(cameraHeight) ? cameraHeight : NaN;
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
    if (typeof comparatorViewers !== "undefined" && Array.isArray(comparatorViewers)) {
      comparatorViewers.forEach(targetViewer => {
        if (!targetViewer || !targetViewer.scene) return;
        const is2d = targetViewer.scene.mode === Cesium.SceneMode.SCENE2D;
        const layerKey = targetViewer.__comparatorLayerKey || null;
        const definition = layerKey ? layerDefinitions.get(layerKey) : null;
        const layerType = definition ? (definition.layerType || definition.type) : null;
        const isDem = String(layerType || "").toLowerCase() === "dem";
        if (isDem && !is2d) {
           const signatureChanged = targetViewer.__customTerrainSignature !== layerKey;
           if (signatureChanged || !targetViewer.__customTerrainProvider) {
             log("info", "DEM_RENDER: Building NEW terrain provider for comparator pane=" + targetViewer.__comparatorPaneKey + " key=" + layerKey);
             const terrainQuery = {
               ...definition.query,
               resampling: "bilinear",
             };
             delete terrainQuery.colormap_name;
             delete terrainQuery.colormap;
             delete terrainQuery.algorithm;
             const terrainUrl = buildUrlWithQuery(definition.xyzUrl, terrainQuery);

             const customTerrainProvider = new OfflineCustomTerrainProvider({
               url: terrainUrl,
               minLevel: definition.minLevel,
               maxLevel: definition.maxLevel || DEM_MAX_TERRAIN_LEVEL,
               options: {
                 query: definition.query,
                 bounds: definition.bounds
               }
             });
             targetViewer.__customTerrainProvider = customTerrainProvider;
             targetViewer.__customTerrainSignature = layerKey;
           }
           if (targetViewer.terrainProvider !== targetViewer.__customTerrainProvider) {
             targetViewer.terrainProvider = targetViewer.__customTerrainProvider;
           }
        } else {
           if (targetViewer.terrainProvider && targetViewer.terrainProvider.constructor && targetViewer.terrainProvider.constructor.name !== "EllipsoidTerrainProvider") {
             targetViewer.terrainProvider = new Cesium.EllipsoidTerrainProvider();
           }
        }
      });
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

  // markComparatorInputViewer removed — comparatorActiveInputViewer is unused in active code

  // scheduleComparatorCameraSync removed — updateComparatorCenterReadout called directly
  // lockComparatorFocusToCurrentView removed — no callers

  function setComparatorViewerModeByType(targetViewer, layerType) {
    if (!targetViewer || !targetViewer.scene) {
      return;
    }

    const layerKey = targetViewer.__comparatorLayerKey || null;
    const definition = layerKey ? layerDefinitions.get(layerKey) : null;
    const resolvedLayerType = layerType || (definition ? (definition.layerType || definition.type) : null);
    const isDem = String(resolvedLayerType || "").toLowerCase() === "dem";
    const focusRect = definition ? rectangleFromBounds(definition.bounds || null) : null;

    if (!isDem) {
      // Imagery-only pane → force strict 2D flat map view.
      // Morphing to SCENE2D prevents pitch/tilt altogether.
      if (targetViewer.scene.mode !== Cesium.SceneMode.SCENE2D) {
        targetViewer.scene.morphTo2D(0.0);
      }
      if (focusRect) {
        focusComparatorViewerToRectangle(targetViewer, resolvedLayerType, focusRect);
      }
      syncComparatorTerrainProviders();
      return;
    }

    // DEM pane → use global 2D/3D toggle so user controls perspective.
      const desiredMode = currentSceneMode === "2d" ? Cesium.SceneMode.SCENE2D : Cesium.SceneMode.SCENE3D; // Adjusted for user preference
    const currentMode = targetViewer.scene.mode;
    if (currentMode !== desiredMode) {
      if (desiredMode === Cesium.SceneMode.SCENE2D) {
        targetViewer.scene.morphTo2D(0.0);
      } else {
        targetViewer.scene.morphTo3D(0.0);
      }
    }
    if (focusRect) {
      focusComparatorViewerToRectangle(targetViewer, resolvedLayerType, focusRect);
    }
    syncComparatorTerrainProviders();
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
    const sourceCameraHeight = sourceViewer?.camera && sourceViewer.camera.positionCartographic && Number.isFinite(sourceViewer.camera.positionCartographic.height)
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
        log("debug", "Comparator camera sync is disabled; syncViewerCamera ignored"); // Logging for debugging
      if (sourceViewer) {
        updateComparatorCenterReadout(sourceViewer);
      }
      if (targetViewer?.scene) {
        targetViewer.scene.requestRender();
      }
    }
  }

  function bindComparatorSyncHandlers() {
    // Wire camera-change and mousemove for all active comparator panes.
    // Uses comparatorViewers[] array — works for 2, 3, or 4 panes.
    let _numActive = comparatorViewers.filter(Boolean).length;
    for (let _bi = 0; _bi < _numActive; _bi++) {
      (function(idx) {
        let v = comparatorViewers[idx];
        if (!v) return;
        let container = document.getElementById("comparatorViewer" + idx);
        if (!container) return;

        // Camera change → update coords readout for this pane
        v.camera.changed.addEventListener(function () {
          if (comparatorModeEnabled) {
            updateComparatorCenterReadout(v, idx);
          }
        });

        // Wheel → update coords
        container.addEventListener("wheel", function () {
          if (comparatorModeEnabled) updateComparatorCenterReadout(v, idx);
        }, { passive: true });

        // Clean up previous DOM listeners
        if (v.__comparatorMouseMoveListener) {
          container.removeEventListener("mousemove", v.__comparatorMouseMoveListener);
          v.__comparatorMouseMoveListener = null;
        }
        if (v.__comparatorMouseLeaveListener) {
          container.removeEventListener("mouseleave", v.__comparatorMouseLeaveListener);
          v.__comparatorMouseLeaveListener = null;
        }

        let lastMouseMoveTime = 0;
// TODO: Refactor this function to reduce its Cognitive Complexity from 16 to the 15 allowed.
        const MOUSE_MOVE_THROTTLE_MS = 16;

        const mouseMoveListener = function (event) {
          const isEnabled = window.OfflineGISRuntime && window.OfflineGISRuntime.comparatorModeEnabled;
          if (!isEnabled || !v || !v.canvas) return;

          const rect = v.canvas.getBoundingClientRect();
          const x = event.clientX - rect.left;
          const y = event.clientY - rect.top;
          const srcPos = new Cesium.Cartesian2(x, y);

          // Throttle mouse move processing
          const now = Date.now();
          if (now - lastMouseMoveTime < MOUSE_MOVE_THROTTLE_MS) return;
          lastMouseMoveTime = now;

          let srcCartesian = getCartesianFromViewer(v, srcPos);
          let srcLonLat = srcCartesian ? cartesianToLonLat(srcCartesian) : null;

          let projectedCartesian = srcCartesian || (srcLonLat
            ? Cesium.Cartesian3.fromDegrees(Number(srcLonLat.lon), Number(srcLonLat.lat))
            : null);

          // Update crosshair on every pane EXCEPT the source pane.
          // The source pane uses the native OS crosshair cursor (set via CSS cursor:crosshair),
          // so drawing an overlay there would create a double-cursor effect.
          let _total = comparatorViewers.filter(Boolean).length;
          for (let _pi = 0; _pi < _total; _pi++) {
            if (_pi === idx) {
              // Source pane: always hide overlay — native cursor handles this pane
              let srcCrosshair = document.querySelector("#comparatorPane" + _pi + " .comparatorCrosshair");
              if (srcCrosshair) srcCrosshair.style.display = "none";
              continue;
            }

            let targetV = comparatorViewers[_pi];
            let crosshair = document.querySelector("#comparatorPane" + _pi + " .comparatorCrosshair");
            if (!crosshair || !targetV) continue;

            // Project the geo-coordinate into the target pane's screen space
            let screenPos = projectedCartesian ? projectCartesianToViewer(targetV, projectedCartesian) : null;
            applyCrosshairScreenPosition(crosshair, targetV, screenPos);
          }

          if (srcLonLat) {
            emitMouseCoordinates(srcLonLat.lon, srcLonLat.lat);
          }
        };

        const mouseLeaveListener = function () {
          // Hide overlay crosshairs in all panes when mouse leaves
          let _total = comparatorViewers.filter(Boolean).length;
          for (let _pi = 0; _pi < _total; _pi++) {
            let crosshair = document.querySelector("#comparatorPane" + _pi + " .comparatorCrosshair");
            if (crosshair) {
              crosshair.style.display = "none";
            }
          }
        };

        container.addEventListener("mousemove", mouseMoveListener);
        container.addEventListener("mouseleave", mouseLeaveListener);
        v.__comparatorMouseMoveListener = mouseMoveListener;
        v.__comparatorMouseLeaveListener = mouseLeaveListener;
      })(_bi);
    }
    bindComparatorPaneSelectionHandlers();
    setComparatorPaneSelectionStyles(comparatorSelectedPane);
  }

  function getComparatorPaneViewer(paneKey) {
    let idx = resolveComparatorPaneIndex(paneKey);
    return (Array.isArray(comparatorViewers) && comparatorViewers[idx]) || null;
  }

  function getComparatorPaneLayerType(paneKey) {
    let idx = resolveComparatorPaneIndex(paneKey);
    let v = Array.isArray(comparatorViewers) ? comparatorViewers[idx] : null;
    if (!v) return null;
    let key = v.__comparatorLayerKey || null;
    if (!key) return null;
    let def = layerDefinitions.get(key);
    return (def?.type) ? String(def.type) : null;
  }

  function getComparatorPaneVisual(paneKey) {
    const paneIndex = resolveComparatorPaneIndex(paneKey);
    const storageKey = getComparatorPaneKeyForIndex(paneIndex);
    if (!comparatorPaneVisualState[storageKey]) {
      comparatorPaneVisualState[storageKey] = createComparatorPaneVisualState();
    }
    return comparatorPaneVisualState[storageKey];
  }

  function setComparatorPaneSelectionStyles(selectedPane) {
    let _numActive = comparatorViewers.filter(Boolean).length;
    let selectedIndex = resolveComparatorPaneIndex(selectedPane);
    for (let _ssi = 0; _ssi < 4; _ssi++) {
      let pane = document.getElementById("comparatorPane" + _ssi);
      if (!pane) continue;
      let isSelected = (_ssi === selectedIndex) && (_ssi < _numActive);
      pane.classList.toggle("selected", isSelected);
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
    const normalized = getComparatorPaneKeyForIndex(resolveComparatorPaneIndex(paneKey));
    comparatorSelectedPane = normalized;
    setComparatorPaneSelectionStyles(normalized);
    if (notifyPanel !== false) {
      notifyComparatorPaneState(normalized);
    }
  }

  function bindComparatorPaneSelectionHandlers() {
    let _numActive = comparatorViewers.filter(Boolean).length;
    for (let _si = 0; _si < _numActive; _si++) {
      (function(idx) {
        let pane = document.getElementById("comparatorPane" + idx);
        if (!pane || pane.dataset.selectionBound) return;
        pane.dataset.selectionBound = "1";
        pane.addEventListener("pointerdown", function () {
          setSelectedComparatorPane(String(idx), true);
        });
      })(_si);
    }
  }

  function buildComparatorDemDrapeUrl(definition, demState) {
    if (definition && typeof definition.xyzUrl === "string" && definition.xyzUrl) {
      const baseQuery = definition.query && typeof definition.query === "object" ? { ...definition.query } : {};
      baseQuery.resampling = "bilinear";
      baseQuery.colormap_name = String(demState.colorMode || baseQuery.colormap_name || "gray");
      return buildUrlWithQuery(definition.xyzUrl, baseQuery);
    }
    return String((definition?.drapeUrl) || "");
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
    return String((definition?.hillshadeUrl) || "");
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
      const alpha = Number(layer?.alpha);
      const show = layer?.show === false ? "hidden" : "shown";
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
        // Use the pane's hillshadeAlpha directly (0.0 - 1.0) so the main slider
        // is the single source of truth and behaves consistently across panes.
        hsLayer.alpha = Math.max(0.0, Math.min(1.0, Number(paneState.dem.hillshadeAlpha) || 0.0));
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
    targetViewer.__comparatorPaneKey = String(paneKey || "left");
    targetViewer.__comparatorLayerKey = String(definition.key || "");
    targetViewer.__comparatorPrimaryLayer = null;
    targetViewer.__comparatorHillshadeLayer = null;

    const localBackgroundProvider = new Cesium.TileMapServiceImageryProvider({
      url: Cesium.buildModuleUrl("Assets/Textures/NaturalEarthII"),
    });
    const localBackgroundLayer = targetViewer.imageryLayers.addImageryProvider(localBackgroundProvider);
    localBackgroundLayer.alpha = 1.0;
    localBackgroundLayer.show = true;
    targetViewer.__defaultEarthLayer = localBackgroundLayer;

    if (!targetViewer.__osmBasemapLayer) {
      try {
        const osmProvider = OfflineGISUtils.createIntelligentOsmProvider(Cesium, {
          url: `${LOCAL_SATELLITE_TILE_ROOT}/{z}/{x}/{y}.png`,
          tilingScheme: new Cesium.WebMercatorTilingScheme(),
          rectangle: Cesium.Rectangle.fromDegrees(60.0, 5.0, 105.0, 55.0),
          credit: new Cesium.Credit("© OpenStreetMap contributors", false),
          enablePickFeatures: false,
          tileWidth: 256,
          tileHeight: 256,
        });
        osmProvider.errorEvent.addEventListener(function (error) {
          error.retry = false;
        });
        targetViewer.__osmBasemapLayer = targetViewer.imageryLayers.addImageryProvider(osmProvider, 1);
        targetViewer.__osmBasemapLayer.alpha = 1.0;
        targetViewer.__osmBasemapLayer.show = false;
      } catch (e) {
        log("debug", "Comparator OSM preload skipped: " + e);
      }
    }

    if (definition.type === "dem") {
      const demState = paneVisual ? paneVisual.dem : comparatorPaneVisualState.left.dem;
      const drapeUrl = buildComparatorDemDrapeUrl(definition, demState);
      const hillshadeUrl = buildComparatorDemHillshadeUrl(definition, demState);

      // Force 3D globe mode for DEM panes — must happen BEFORE adding layers
      // so Cesium initialises the 3D scene graph correctly on Windows/ANGLE.
      log("debug", "COMP_DEM pane=" + paneKey + " forcing SCENE3D for DEM viewer");
      if (targetViewer.scene && targetViewer.scene.mode !== Cesium.SceneMode.SCENE3D) {
        targetViewer.scene.morphTo3D(0.0);
        log("debug", "COMP_DEM pane=" + paneKey + " morphTo3D issued");
      } else {
        log("debug", "COMP_DEM pane=" + paneKey + " already SCENE3D mode=" + targetViewer.scene.mode);
      }

      const demProvider = new Cesium.UrlTemplateImageryProvider({
        url: drapeUrl,
        maximumLevel: definition.maxLevel || definition.maxzoom || 26,
        minimumLevel: definition.minLevel || definition.minzoom || 0,
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
          maximumLevel: definition.maxLevel || definition.maxzoom || 26,
          minimumLevel: definition.minLevel || definition.minzoom || 0,
          tilingScheme: new Cesium.WebMercatorTilingScheme(),
          enablePickFeatures: false,
          rectangle: rectangle,
        });
        const hsLayer = targetViewer.imageryLayers.addImageryProvider(hsProvider);
        hsLayer.alpha = Math.max(0.0, Math.min(1.0, Number(demState.hillshadeAlpha) || 0.0));
        targetViewer.__comparatorHillshadeLayer = hsLayer;
      }
      enforceComparatorDemLayerOrder(paneKey, targetViewer);

      // Apply tilted 3D camera after a short delay to let morphTo3D settle.
      // On Windows/ANGLE the scene mode transition is async — we need to wait
      // at least one frame before lookAt works correctly.
      if (rectangle) {
        let _demRect = rectangle;
        let _demViewer = targetViewer;
        let _demPaneKey = paneKey;
        function _applyDemCamera() {
          if (!_demViewer || !_demViewer.scene) return;
          let pitch = getComparatorDemPitchRadians();
          let centerLon = (_demRect.west + _demRect.east) * 0.5;
          let centerLat = (_demRect.south + _demRect.north) * 0.5;
          let centerCarto = new Cesium.Cartographic(centerLon, centerLat);
          let terrainHeight = undefined;
          if (_demViewer.scene.globe && typeof _demViewer.scene.globe.getHeight === "function") {
            const h = _demViewer.scene.globe.getHeight(centerCarto);
            if (typeof h === "number" && Number.isFinite(h)) {
              terrainHeight = h;
            }
          }
          if (terrainHeight === undefined || terrainHeight === null || isNaN(terrainHeight)) {
            terrainHeight = typeof getDemTerrainHeightFallback === "function"
                ? getDemTerrainHeightFallback()
                : 0.0;
          }
          if (_demViewer.scene.globe && typeof _demViewer.scene.globe.terrainExaggeration === "number") {
            terrainHeight *= _demViewer.scene.globe.terrainExaggeration;
          }
          let sphere = Cesium.BoundingSphere.fromRectangle3D(_demRect, Cesium.Ellipsoid.WGS84, terrainHeight);
          let range = Math.max(sphere.radius * 1.9, 900.0);
          log("debug", "COMP_DEM pane=" + _demPaneKey +
            " applying camera pitch=" + Cesium.Math.toDegrees(pitch).toFixed(1) +
            "° range=" + range.toFixed(0) + "m" +
            " sceneMode=" + _demViewer.scene.mode);
          try {
            _demViewer.camera.lookAt(
              sphere.center,
              new Cesium.HeadingPitchRange(0.0, pitch, range)
            );
            _demViewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
          } catch(e) {
            log("warn", "COMP_DEM pane=" + _demPaneKey + " lookAt failed: " + e);
          }
          _demViewer.scene.requestRender();
        }
        setTimeout(_applyDemCamera, 50);
        setTimeout(_applyDemCamera, 300);
        setTimeout(_applyDemCamera, 700);
      }

      if (targetViewer.scene) {
        targetViewer.scene.requestRender();
      }
      return;
    }

    // Imagery pane — always force strict 2D flat map, no tilt ever
    log("debug", "COMP_IMAGERY pane=" + paneKey + " forcing SCENE2D for imagery viewer sceneMode=" + targetViewer.scene.mode);
    if (targetViewer.scene && targetViewer.scene.mode !== Cesium.SceneMode.SCENE2D) {
      targetViewer.scene.morphTo2D(0.0);
      log("debug", "COMP_IMAGERY pane=" + paneKey + " morphTo2D issued");
    }

    const provider = new Cesium.UrlTemplateImageryProvider({
      url: definition.url,
      maximumLevel: definition.maxLevel || definition.maxzoom || 26,
      minimumLevel: definition.minLevel || definition.minzoom || 0,
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

    // Re-enforce 2D after a short delay — Windows/ANGLE can revert the mode
    let _imgViewer = targetViewer;
    let _imgPaneKey = paneKey;
    function _enforce2D() {
      if (!_imgViewer || !_imgViewer.scene) return;
      if (_imgViewer.scene.mode !== Cesium.SceneMode.SCENE2D) {
        log("debug", "COMP_IMAGERY pane=" + _imgPaneKey + " re-enforcing SCENE2D");
        _imgViewer.scene.morphTo2D(0.0);
      }
      if (_imgViewer.scene) _imgViewer.scene.requestRender();
    }
    setTimeout(_enforce2D, 80);
    setTimeout(_enforce2D, 400);
  }

  function resetComparatorViewerLayers(targetViewer) {
    if (!targetViewer) {
      return;
    }
    for (let idx = targetViewer.imageryLayers.length - 1; idx >= 0; idx -= 1) {
      const layer = targetViewer.imageryLayers.get(idx);
      if (layer === targetViewer.__osmBasemapLayer || layer === targetViewer.__defaultEarthLayer) {
        continue;
      }
      targetViewer.imageryLayers.remove(layer, false);
    }
  }

  function resolveComparatorLayerKeys() {
    // Prefer the explicitly selected keys (set via setComparatorLayers).
    // This guarantees pane count == 2.
    if (swipeComparatorExplicitKeys?.length >= 2) {
      return swipeComparatorExplicitKeys.slice(0, 2);
    }
    // Legacy fallback: use left/right pair if only those two are available
    if (swipeComparatorLeftLayerKey && swipeComparatorRightLayerKey) {
      return [swipeComparatorLeftLayerKey, swipeComparatorRightLayerKey];
    }
    const visibleKeys = [];
    for (const [key, visible] of layerVisibilityState.entries()) {
      if (!visible || !layerDefinitions.has(key)) continue;
      visibleKeys.push(key);
    }
    return visibleKeys.slice(0, 2);
  }

  function syncAnnotationsToPython() {
    if (typeof bridge === "undefined" || !bridge || typeof bridge.on_annotations_sync !== "function") {
      return;
    }
    
    function readLabelText(labelEntity) {
      if (!labelEntity || !labelEntity.label) return "";
      const textVal = labelEntity.label.text;
      if (!textVal) return "";
      if (typeof textVal.getValue === "function") {
        return String(textVal.getValue(Cesium.JulianDate.now()) || "");
      }
      return String(textVal || "");
    }

    // Group all entities in annotationEntities by _annotationId
    const groups = {};
    if (typeof annotationEntities !== "undefined" && Array.isArray(annotationEntities)) {
      for (const ent of annotationEntities) {
        if (ent?._annotationId) {
          const id = ent._annotationId;
          if (!groups[id]) {
            groups[id] = {};
          }
          const role = ent._annotationRole;
          if (role === "anchor" || role === "icon" || role === "text-label" || role === "line") {
            groups[id].main = ent;
          } else if (role === "label") {
            groups[id].label = ent;
          }
        }
      }
    }
    
    const points = [];
    const lines = [];
    const icons = [];
    const texts = [];
    
    for (const id in groups) {
      const g = groups[id];
      const mainEnt = g.main;
      const labelEnt = g.label;
      if (!mainEnt) continue;
      
      // Get position with height
      let lon = 0.0;
      let lat = 0.0;
      let height = 0.0;
      if (mainEnt.position) {
        const cartesian = mainEnt.position.getValue(Cesium.JulianDate.now());
        if (cartesian) {
          const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
          if (cartographic) {
            lon = Cesium.Math.toDegrees(cartographic.longitude);
            lat = Cesium.Math.toDegrees(cartographic.latitude);
            height = cartographic.height || 0.0;
          }
        }
      }
      
      // Get label text
      let text = "";
      if (labelEnt) {
        text = readLabelText(labelEnt);
      } else if (mainEnt._annotationRole === "text-label") {
        text = readLabelText(mainEnt);
      }
      
      if (id.startsWith("annotation-")) {
        // Point annotation
        points.push({
          lon: lon,
          lat: lat,
          height: height,
          text: text || "Point"
        });
      } else if (id.startsWith("icon-annotation-")) {
        // Icon annotation
        const iconName = mainEnt._iconName || "marker";
        icons.push({
          lon: lon,
          lat: lat,
          height: height,
          icon: iconName,
          text: text || ""
        });
      } else if (id.startsWith("text-label-")) {
        // Text-only label
        texts.push({
          lon: lon,
          lat: lat,
          height: height,
          text: text || "Label"
        });
      } else if (id.startsWith("line-annotation-")) {
        // Line annotation — emit [lon, lat, height] triples
        const coords = [];
        if (mainEnt.polyline && mainEnt.polyline.positions) {
          const positions = mainEnt.polyline.positions.getValue(Cesium.JulianDate.now());
          if (positions?.length) {
            for (const pos of positions) {
              const carto = Cesium.Cartographic.fromCartesian(pos);
              if (carto) {
                coords.push([Cesium.Math.toDegrees(carto.longitude), Cesium.Math.toDegrees(carto.latitude), carto.height || 0.0]);
              }
            }
          }
        }
        lines.push({
          coords: coords,
          label: text || "Line"
        });
      }
    }
    
    // Also parse drawnPolygons for annotation polygons
    const polygons = [];
    if (typeof drawnPolygons !== "undefined" && Array.isArray(drawnPolygons)) {
      for (const poly of drawnPolygons) {
        if (poly?._isAnnotationPoly) {
          const coords = (poly.points || []).map(function (p) {
            let h = 0.0;
            if (p.cartesian) {
              const carto = Cesium.Cartographic.fromCartesian(p.cartesian);
              if (carto) {
                h = carto.height || 0.0;
              }
            } else if (typeof p.height === "number") {
              h = p.height;
            }
            return [p.lon, p.lat, h];
          });
          polygons.push({
            coords: coords,
            label: poly.label || ("Polygon " + poly.id)
          });
        }
      }
    }
    
    const payload = {
      points: points,
      lines: lines,
      icons: icons,
      texts: texts,
      polygons: polygons
    };
    
    bridge.on_annotations_sync(JSON.stringify(payload));
  }
  
  window.syncAnnotationsToPython = syncAnnotationsToPython;

  window.offlineGIS = window.offlineGIS || {};
  Object.assign(window.offlineGIS, {
    resetAnnotationCounter: function () {
      annotationCounter = 0;
    },
    resetDrawnPolygonCounter: function () {
      drawnPolygonCounter = 0;
    },
    getDemTerrainHeightFallback: getDemTerrainHeightFallback
  });

  // ═══════════════════════════════════════════════════════════════════════════
