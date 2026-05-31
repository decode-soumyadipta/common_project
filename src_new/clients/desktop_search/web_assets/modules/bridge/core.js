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
    if (viewer && viewer.scene) {
      viewer.scene.requestRender();
    }
  };
  const setComparatorWindowsVisible = bridgeUtils.setComparatorWindowsVisible || function () {};
  const ensureRubberBandLine = bridgeUtils.ensureRubberBandLine || function () { return null; };
  const clearRubberBandLine = bridgeUtils.clearRubberBandLine || function () {};
  const normalizeBounds = bridgeUtils.normalizeBounds || function (bounds) {
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
    const query = options && options.query ? options.query : null;
    if (!query || typeof query.rescale !== "string") {
      return defaultRange;
    }
    const parts = query.rescale.split(",").map((value) => Number(value.trim()));
    if (parts.length !== 2 || !Number.isFinite(parts[0]) || !Number.isFinite(parts[1]) || parts[1] <= parts[0]) {
      return defaultRange;
    }
    return { min: parts[0], max: parts[1] };
  };

  function getActiveDemColorMode() {
    return String((activeDemContext && activeDemContext.colorMode) || demVisual.colorMode || "terrain").toLowerCase();
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

  var flyThroughCursorCartesian = null;

  function liftFlyThroughPoint(cartesian) {
    if (!cartesian) {
      return null;
    }
    const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
    const terrainHeight = viewer && viewer.scene && viewer.scene.globe
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
      baseHeight
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
        bridge.on_fly_through_playback_progress(Number(progress));
      } catch (_) {}
    }
  }

  function buildFlyThroughPlaybackPlan() {
    if (flyThroughPoints.length < 2) {
      return null;
    }

    const speedFactor = Math.max(0.5, Math.min(3.0, Number(flyThroughSpeedMultiplier) || 1.0));
    const segments = [];
    let totalDurationMs = 0;

    for (let index = 0; index < flyThroughPoints.length - 1; index += 1) {
      const p1 = flyThroughPoints[index];
      const p2 = flyThroughPoints[index + 1];
      if (!p1 || !p2) {
        continue;
      }

      const carto1 = Cesium.Cartographic.fromCartesian(p1);
      const carto2 = Cesium.Cartographic.fromCartesian(p2);
      const startPos = Cesium.Cartesian3.fromRadians(
        carto1.longitude,
        carto1.latitude,
        carto1.height + 900
      );
      const endPos = Cesium.Cartesian3.fromRadians(
        carto2.longitude,
        carto2.latitude,
        carto2.height + 900
      );
      const distance = Cesium.Cartesian3.distance(p1, p2);
      const durationMs = Math.max(350, (distance / (100 * speedFactor)) * 1000);
      segments.push({
        startPos: startPos,
        endPos: endPos,
        heading: new Cesium.EllipsoidGeodesic(carto1, carto2).startHeading,
        durationMs: durationMs,
      });
      totalDurationMs += durationMs;
    }

    return segments.length
      ? { segments: segments, totalDurationMs: totalDurationMs }
      : null;
  }

  function getFlyThroughStateForProgress(progress, plan) {
    const normalized = Math.max(0, Math.min(1, Number(progress) || 0));
    const playbackPlan = plan || buildFlyThroughPlaybackPlan();
    if (!playbackPlan || playbackPlan.segments.length === 0) {
      return null;
    }

    const totalDurationMs = Math.max(1, playbackPlan.totalDurationMs);
    const targetMs = normalized * totalDurationMs;
    let segmentStartMs = 0;

    for (let index = 0; index < playbackPlan.segments.length; index += 1) {
      const segment = playbackPlan.segments[index];
      const segmentEndMs = segmentStartMs + segment.durationMs;
      const isLastSegment = index === playbackPlan.segments.length - 1;
      if (targetMs <= segmentEndMs || isLastSegment) {
        const localProgress = segment.durationMs > 0
          ? Math.max(0, Math.min(1, (targetMs - segmentStartMs) / segment.durationMs))
          : 1.0;
        return {
          startPos: segment.startPos,
          endPos: segment.endPos,
          heading: segment.heading,
          localProgress: localProgress,
          progress: normalized,
          totalDurationMs: totalDurationMs,
        };
      }
      segmentStartMs = segmentEndMs;
    }

    return null;
  }

  function applyFlyThroughCameraState(state) {
    if (!viewer || !viewer.camera || !state) {
      return;
    }

    const easedProgress = Cesium.EasingFunction.QUADRATIC_IN_OUT(state.localProgress);
    const destination = Cesium.Cartesian3.lerp(
      state.startPos,
      state.endPos,
      easedProgress,
      new Cesium.Cartesian3()
    );

    viewer.camera.setView({
      destination: destination,
      orientation: {
        heading: state.heading,
        pitch: Cesium.Math.toRadians(flyThroughPlaybackPitchDegrees),
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
    flyThroughSpeedMultiplier = Math.max(0.5, Math.min(3.0, nextSpeed));
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

    const restoreView = function () {
      if (viewer && viewer.scene && viewer.scene.screenSpaceCameraController) {
        viewer.scene.screenSpaceCameraController.enableInputs = true;
      }
      if (flyThroughOriginalView && viewer && viewer.camera) {
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

    if (flyThroughOriginalView && viewer && viewer.camera) {
      viewer.camera.flyTo({
        destination: flyThroughOriginalView.destination,
        orientation: flyThroughOriginalView.orientation,
        duration: Math.max(0.4, 2.5 / Math.max(0.5, Math.min(3.0, Number(flyThroughSpeedMultiplier) || 1.0))),
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
      var cartesian = null;
      if (viewer.scene.pickPositionSupported) {
        try {
          cartesian = viewer.scene.pickPosition(mousePos);
        } catch (_) {}
      }
      if (!cartesian) {
        var ray = viewer.camera.getPickRay(mousePos);
        if (ray) {
          cartesian = viewer.scene.globe.pick(ray, viewer.scene);
        }
      }
      if (!cartesian) {
        cartesian = viewer.camera.pickEllipsoid(mousePos, viewer.scene.globe.ellipsoid);
      }
      if (cartesian) {
        var carto = Cesium.Cartographic.fromCartesian(cartesian);
        var terrainHeight = viewer.scene.globe.getHeight(carto);
        var height = (terrainHeight !== undefined && terrainHeight !== null)
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
        width: 2,
        color: "#00e5ff",
        alpha: 0.85,
        clampToGround: true,
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
        width: 2,
        material: Cesium.Color.fromCssColorString("#00e5ff").withAlpha(0.85),
        arcType: Cesium.ArcType.GEODESIC,
        clampToGround: true,
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
  // TERRAIN_SAMPLE_SIZE is set to 65 for smoother LOD transitions and finer detail.
  // 65 increases terrain fidelity while keeping decode cost manageable on desktop GPUs.
  const TERRAIN_SAMPLE_SIZE = 65;
  const DEM_MAX_TERRAIN_LEVEL = 14;
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
    exaggeration: 1.0,
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
  let searchCursorEntity = null;
  let searchPreviewLineEntity = null;
  let searchPreviewPolygonEntity = null;
  let searchAreaLabelEntity = null;
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
          return searchPreviewLineEntity;
        },
        setSearchPreviewLineEntity: function (value) {
          searchPreviewLineEntity = value;
        },
        getSearchPreviewPolygonEntity: function () {
          return searchPreviewPolygonEntity;
        },
        setSearchPreviewPolygonEntity: function (value) {
          searchPreviewPolygonEntity = value;
        },
        getSearchAreaLabelEntity: function () {
          return searchAreaLabelEntity;
        },
        setSearchAreaLabelEntity: function (value) {
          searchAreaLabelEntity = value;
        },
        getSearchCursorEntity: function () {
          return searchCursorEntity;
        },
        setSearchCursorEntity: function (value) {
          searchCursorEntity = value;
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
          searchDrawMode = value;
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
      height: cartographic.height
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

  function updateComparatorCenterReadout(sourceViewer, paneIdx) {
    if (!comparatorModeEnabled) {
      return;
    }
    var idx = (typeof paneIdx === "number") ? paneIdx : comparatorViewers.indexOf(sourceViewer);
    var targetViewer = sourceViewer || comparatorViewers[0];
    if (!targetViewer || !targetViewer.canvas) {
      return;
    }
    var center = new Cesium.Cartesian2(
      targetViewer.canvas.clientWidth * 0.5,
      targetViewer.canvas.clientHeight * 0.5,
    );
    var lonLat = getLonLatFromViewer(targetViewer, center);
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
    const cameraHeight = sourceViewer && sourceViewer.camera && sourceViewer.camera.positionCartographic && Number.isFinite(sourceViewer.camera.positionCartographic.height)
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
        if (!targetViewer) return;
        const layerKey = targetViewer.__comparatorLayerKey || null;
        const definition = layerKey ? layerDefinitions.get(layerKey) : null;
        const layerType = definition ? (definition.layerType || definition.type) : null;
        const isDem = String(layerType || "").toLowerCase() === "dem";
        
        if (isDem) {
           if (activeDemTerrainProvider && targetViewer.terrainProvider !== activeDemTerrainProvider) {
             targetViewer.terrainProvider = activeDemTerrainProvider;
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
        focusComparatorViewerToRectangle(targetViewer, layerType, focusRect);
      }
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
      focusComparatorViewerToRectangle(targetViewer, layerType, focusRect);
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
        log("debug", "Comparator camera sync is disabled; syncViewerCamera ignored"); // Logging for debugging
      if (sourceViewer) {
        updateComparatorCenterReadout(sourceViewer);
      }
      if (targetViewer && targetViewer.scene) {
        targetViewer.scene.requestRender();
      }
    }
  }

  function bindComparatorSyncHandlers() {
    // Wire camera-change and mousemove for all active comparator panes.
    // Uses comparatorViewers[] array — works for 2, 3, or 4 panes.
    var _numActive = comparatorViewers.filter(Boolean).length;
    for (var _bi = 0; _bi < _numActive; _bi++) {
      (function(idx) {
        var v = comparatorViewers[idx];
        if (!v) return;
        var container = document.getElementById("comparatorViewer" + idx);
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

        // Mousemove → project geo position to all other panes' crosshairs.
        // Keep the update rate close to the display refresh rate.
        let lastMouseMoveTime = 0;
        const MOUSE_MOVE_THROTTLE_MS = 16;
        container.addEventListener("mousemove", function (event) {
          if (!comparatorModeEnabled || !v) return;
          
          // Throttle mouse move processing
          const now = Date.now();
          if (now - lastMouseMoveTime < MOUSE_MOVE_THROTTLE_MS) return;
          lastMouseMoveTime = now;
          
          var rect = container.getBoundingClientRect();
          if (rect.width <= 0 || rect.height <= 0) return;
          var localX = event.clientX - rect.left;
          var localY = event.clientY - rect.top;
          var srcPos = new Cesium.Cartesian2(localX, localY);
          var srcCartesian = getCartesianFromViewer(v, srcPos);
          var srcLonLat = srcCartesian
            ? cartesianToLonLat(srcCartesian)
            : getLonLatFromViewer(v, srcPos);
          var projectedCartesian = srcCartesian || (srcLonLat
            ? Cesium.Cartesian3.fromDegrees(Number(srcLonLat.lon), Number(srcLonLat.lat))
            : null);

          // Update crosshair on every pane
          var _total = comparatorViewers.filter(Boolean).length;
          for (var _pi = 0; _pi < _total; _pi++) {
            var targetV = comparatorViewers[_pi];
            var crosshair = document.querySelector("#comparatorPane" + _pi + " .comparatorCrosshair");
            if (!crosshair) continue;

            var screenPos;
            if (_pi === idx) {
              screenPos = srcPos;
            } else if (projectedCartesian && targetV) {
              screenPos = projectCartesianToViewer(targetV, projectedCartesian);
            } else {
              screenPos = null;
            }

            applyCrosshairScreenPosition(crosshair, targetV, screenPos);
          }

          if (srcLonLat) {
            emitMouseCoordinates(srcLonLat.lon, srcLonLat.lat);
          }
        });
      })(_bi);
    }
    bindComparatorPaneSelectionHandlers();
    setComparatorPaneSelectionStyles(comparatorSelectedPane);
  }

  function getComparatorPaneViewer(paneKey) {
    var idx = resolveComparatorPaneIndex(paneKey);
    return (Array.isArray(comparatorViewers) && comparatorViewers[idx]) || null;
  }

  function getComparatorPaneLayerType(paneKey) {
    var idx = resolveComparatorPaneIndex(paneKey);
    var v = Array.isArray(comparatorViewers) ? comparatorViewers[idx] : null;
    if (!v) return null;
    var key = v.__comparatorLayerKey || null;
    if (!key) return null;
    var def = layerDefinitions.get(key);
    return (def && def.type) ? String(def.type) : null;
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
    var _numActive = comparatorViewers.filter(Boolean).length;
    var selectedIndex = resolveComparatorPaneIndex(selectedPane);
    for (var _ssi = 0; _ssi < 4; _ssi++) {
      var pane = document.getElementById("comparatorPane" + _ssi);
      if (!pane) continue;
      var isSelected = (_ssi === selectedIndex) && (_ssi < _numActive);
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
    var _numActive = comparatorViewers.filter(Boolean).length;
    for (var _si = 0; _si < _numActive; _si++) {
      (function(idx) {
        var pane = document.getElementById("comparatorPane" + idx);
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

    const localBackgroundProvider = new Cesium.UrlTemplateImageryProvider({
      url: `${LOCAL_SATELLITE_TILE_ROOT}/{z}/{x}/{y}.png`,
      tilingScheme: new Cesium.WebMercatorTilingScheme(),
      minimumLevel: 0,
      maximumLevel: 10,  // OSM tiles available up to zoom level 10
      credit: new Cesium.Credit("© OpenStreetMap contributors", false),
      enablePickFeatures: false,
    });
    // Suppress tile error logging for comparator background — 404s for missing tiles are expected
    localBackgroundProvider.errorEvent.addEventListener(function (error) {
      error.retry = false;  // don't retry, just skip silently
    });
    const localBackgroundLayer = targetViewer.imageryLayers.addImageryProvider(localBackgroundProvider);
    localBackgroundLayer.alpha = 1.0;
    localBackgroundLayer.show = false;
    targetViewer.__defaultEarthLayer = localBackgroundLayer;

    if (!targetViewer.__osmBasemapLayer) {
      try {
        const osmProvider = new Cesium.UrlTemplateImageryProvider({
          url: `${LOCAL_SATELLITE_TILE_ROOT}/{z}/{x}/{y}.png`,
          tilingScheme: new Cesium.WebMercatorTilingScheme(),
          minimumLevel: 0,
          maximumLevel: 10,
          credit: new Cesium.Credit("© OpenStreetMap contributors", false),
          enablePickFeatures: false,
          tileWidth: 256,
          tileHeight: 256,
        });
        osmProvider.errorEvent.addEventListener(function (error) {
          error.retry = false;
        });
        targetViewer.__osmBasemapLayer = targetViewer.imageryLayers.addImageryProvider(osmProvider, 0);
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

      // Apply tilted 3D camera after a short delay to let morphTo3D settle.
      // On Windows/ANGLE the scene mode transition is async — we need to wait
      // at least one frame before lookAt works correctly.
      if (rectangle) {
        var _demRect = rectangle;
        var _demViewer = targetViewer;
        var _demPaneKey = paneKey;
        function _applyDemCamera() {
          if (!_demViewer || !_demViewer.scene) return;
          var pitch = getComparatorDemPitchRadians();
          var sphere = Cesium.BoundingSphere.fromRectangle3D(_demRect, Cesium.Ellipsoid.WGS84, 0.0);
          var range = Math.max(sphere.radius * 1.9, 900.0);
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

    // Re-enforce 2D after a short delay — Windows/ANGLE can revert the mode
    var _imgViewer = targetViewer;
    var _imgPaneKey = paneKey;
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
    if (swipeComparatorLeftLayerKey && swipeComparatorRightLayerKey) {
      return [swipeComparatorLeftLayerKey, swipeComparatorRightLayerKey];
    }
    const visibleKeys = [];
    for (const [key, visible] of layerVisibilityState.entries()) {
      if (!visible || !layerDefinitions.has(key)) continue;
      visibleKeys.push(key);
    }
    return visibleKeys.slice(0, 4);
  }

  // ═══════════════════════════════════════════════════════════════════════════
