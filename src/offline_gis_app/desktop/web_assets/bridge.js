(function () {
  let bridge = null;
  let viewer = null;
  let activeImageryLayer = null;
  let activeDemDrapeLayer = null;
  let activeDemHillshadeLayer = null;
  let activeDemContext = null;
  let activeDemTerrainSignature = null;
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
  let comparatorCameraSyncLock = false;
  const layerDefinitions = new Map();
  const layerVisibilityState = new Map();
  const tileErrorSeen = new Set();
  const layerErrorCounts = new Map();
  const TERRAIN_SAMPLE_SIZE = 33;
  const DEM_MAX_TERRAIN_LEVEL = 14;
  const MAX_TERRAIN_CACHE_ITEMS = 512;
  const LOCAL_SATELLITE_LAYER_NAME = "LocalSatellite";
  const LOCAL_SATELLITE_TILE_ROOT = "./basemap/xyz";
  const LOCAL_SATELLITE_METADATA_URL = "./basemap/xyz/metadata.json";
  const LOCAL_SATELLITE_DEFAULT_MAX_LEVEL = 7;
  const WEB_MERCATOR_MAX_LAT_DEGREES = 85.05112878;
  const WEB_MERCATOR_SAFE_EDGE_LAT_DEGREES = 84.8;
  const LOCAL_BASEMAP_REGION_BOUNDS = {
    world: {
      west: -180.0,
      south: -WEB_MERCATOR_MAX_LAT_DEGREES,
      east: 180.0,
      north: WEB_MERCATOR_MAX_LAT_DEGREES,
    },
    asia: {
      west: 25.0,
      south: -12.0,
      east: 180.0,
      north: 82.0,
    },
  };
  const LOCAL_TERRAIN_RGB_ROOT = "./basemap/terrain-rgb";
  const LOCAL_TERRAIN_RGB_METADATA_URL = "./basemap/terrain-rgb/metadata.json";
  const AUTO_ATTACH_TERRAIN_RGB_PACK = false;
  const SHOW_COUNTRY_BOUNDARY_OVERLAY = false;
  const COUNTRY_BOUNDARY_GEOJSON_URL = "./basemap/boundaries/ne_110m_admin_0_boundary_lines_land.geojson";
  const terrainTileCache = new Map();
  const demVisual = {
    exaggeration: 2.0,
    hillshadeAlpha: 0.35,
    azimuth: 45,
    altitude: 45,
  };
  let terrainDecodeCanvas = null;
  let terrainDecodeContext = null;
  let searchDrawMode = "none";
  const searchPolygonPoints = [];
  let searchCursorPoint = null;
  const searchVertexEntities = [];
  let searchCursorEntity = null;
  let searchPreviewLineEntity = null;
  let searchPreviewPolygonEntity = null;
  let searchAreaLabelEntity = null;
  let searchCursorOverlay = null;
  let lastSearchCursorScreenPosition = null;
  let polygonVisibilityEnabled = true;
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

  function applyCrosshairScreenPosition(crosshairElement, targetViewer, worldCartesian) {
    if (!crosshairElement) {
      return;
    }
    let leftPx = 0.0;
    let topPx = 0.0;
    if (targetViewer && worldCartesian) {
      const projected = Cesium.SceneTransforms.wgs84ToWindowCoordinates(targetViewer.scene, worldCartesian);
      if (projected && Number.isFinite(projected.x) && Number.isFinite(projected.y)) {
        leftPx = Number(projected.x);
        topPx = Number(projected.y);
      } else {
        leftPx = targetViewer.canvas.clientWidth * 0.5;
        topPx = targetViewer.canvas.clientHeight * 0.5;
      }
    }
    crosshairElement.style.left = `${leftPx.toFixed(2)}px`;
    crosshairElement.style.top = `${topPx.toFixed(2)}px`;
  }

  function updateComparatorCrosshair(lon, lat) {
    const leftCrosshair = document.getElementById("comparatorCrosshairLeft");
    const rightCrosshair = document.getElementById("comparatorCrosshairRight");
    const leftCoords = document.getElementById("comparatorCoordsLeft");
    const rightCoords = document.getElementById("comparatorCoordsRight");

    const hasLonLat = Number.isFinite(lon) && Number.isFinite(lat);
    const worldCartesian = hasLonLat ? Cesium.Cartesian3.fromDegrees(Number(lon), Number(lat), 0.0) : null;
    applyCrosshairScreenPosition(leftCrosshair, comparatorLeftViewer, worldCartesian);
    applyCrosshairScreenPosition(rightCrosshair, comparatorRightViewer, worldCartesian);

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

  function syncViewerCamera(sourceViewer, targetViewer) {
    if (!sourceViewer || !targetViewer || comparatorCameraSyncLock) {
      return;
    }
    comparatorCameraSyncLock = true;
    try {
      const sourceCamera = sourceViewer.camera;
      targetViewer.camera.setView({
        destination: sourceCamera.positionWC,
        orientation: {
          direction: sourceCamera.directionWC,
          up: sourceCamera.upWC,
        },
      });
      targetViewer.scene.requestRender();
    } finally {
      comparatorCameraSyncLock = false;
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
        syncViewerCamera(comparatorLeftViewer, comparatorRightViewer);
      }
    });
    comparatorRightViewer.camera.changed.addEventListener(function () {
      if (comparatorModeEnabled) {
        syncViewerCamera(comparatorRightViewer, comparatorLeftViewer);
      }
    });

    function attachCursorBridge(container, sourceViewer) {
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
        const lonLat = getLonLatFromViewer(sourceViewer, new Cesium.Cartesian2(localX, localY));
        updateComparatorCrosshair(lonLat ? lonLat.lon : NaN, lonLat ? lonLat.lat : NaN);
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

  function applyLayerDefinitionToViewer(targetViewer, definition) {
    if (!targetViewer || !definition) {
      return;
    }
    const rectangle = rectangleFromBounds(definition.bounds || null);
    if (definition.type === "dem") {
      const demProvider = new Cesium.UrlTemplateImageryProvider({
        url: definition.drapeUrl,
        maximumLevel: definition.maxLevel,
        minimumLevel: definition.minLevel,
        tilingScheme: new Cesium.WebMercatorTilingScheme(),
        enablePickFeatures: false,
        rectangle: rectangle,
      });
      const demLayer = targetViewer.imageryLayers.addImageryProvider(demProvider);
      demLayer.alpha = 1.0;
      if (definition.hillshadeUrl) {
        const hsProvider = new Cesium.UrlTemplateImageryProvider({
          url: definition.hillshadeUrl,
          maximumLevel: definition.maxLevel,
          minimumLevel: definition.minLevel,
          tilingScheme: new Cesium.WebMercatorTilingScheme(),
          enablePickFeatures: false,
          rectangle: rectangle,
        });
        const hsLayer = targetViewer.imageryLayers.addImageryProvider(hsProvider);
        hsLayer.alpha = Math.max(0.0, Math.min(1.0, Number(definition.hillshadeAlpha) || 0.0));
      }
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
  }

  function resetComparatorViewerLayers(targetViewer) {
    if (!targetViewer) {
      return;
    }
    for (let idx = targetViewer.imageryLayers.length - 1; idx >= 1; idx -= 1) {
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

  function refreshComparatorLayers() {
    if (!comparatorModeEnabled || !comparatorLeftViewer || !comparatorRightViewer) {
      return;
    }
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
    applyLayerDefinitionToViewer(comparatorLeftViewer, leftDef);
    applyLayerDefinitionToViewer(comparatorRightViewer, rightDef);

    const leftTitle = document.getElementById("comparatorTitleLeft");
    const rightTitle = document.getElementById("comparatorTitleRight");
    if (leftTitle) {
      leftTitle.textContent = leftDef.label || "Left layer";
    }
    if (rightTitle) {
      rightTitle.textContent = rightDef.label || "Right layer";
    }

    if (viewer && comparatorLeftViewer) {
      syncViewerCamera(viewer, comparatorLeftViewer);
      syncViewerCamera(viewer, comparatorRightViewer);
    }
    requestSceneRender();
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
    comparatorLeftViewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#1f4f7a");
    comparatorRightViewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#1f4f7a");
    comparatorLeftViewer.scene.backgroundColor = Cesium.Color.BLACK;
    comparatorRightViewer.scene.backgroundColor = Cesium.Color.BLACK;
    comparatorLeftViewer.scene.fxaa = false;
    comparatorRightViewer.scene.fxaa = false;
    bindComparatorSyncHandlers();
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
        layer.splitDirection = Cesium.SplitDirection.NONE;
      }
    }

    if (!swipeComparatorEnabled || candidates.length === 0) {
      viewer.scene.imagerySplitPosition = 0.5;
      requestSceneRender();
      return;
    }

    if (candidates.length === 1) {
      candidates[0].splitDirection = Cesium.SplitDirection.LEFT;
    } else {
      const leftLayer = candidates[candidates.length - 1];
      const rightLayer = candidates[candidates.length - 2];
      leftLayer.splitDirection = Cesium.SplitDirection.LEFT;
      rightLayer.splitDirection = Cesium.SplitDirection.RIGHT;
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
    const candidateCount = getSwipeCandidateLayers().length;
    ensureSwipeDivider();
    if (swipeDividerElement) {
      swipeDividerElement.style.display = "none";
    }
    if (next) {
      ensureComparatorViewers();
      setComparatorWindowsVisible(true);
      if (comparatorLeftViewer && comparatorRightViewer) {
        comparatorLeftViewer.resize();
        comparatorRightViewer.resize();
      }
      refreshComparatorLayers();
      if (candidateCount < 2) {
        setStatus("Comparator enabled. Select two visible layers to render left and right panes.");
      } else {
        setStatus("Comparator enabled. Dual pane globes are synchronized.");
      }
    } else {
      setComparatorWindowsVisible(false);
      setStatus("Swipe comparator disabled.");
    }
    applySwipeComparatorSplit();
  }

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
    const toggle = document.getElementById("sceneModeToggle");
    if (!toggle) return;
    toggle.checked = String(mode || "3d").toLowerCase() !== "2d";
  }

  function setSceneModeControlEnabled(enabled) {
    sceneModeControlEnabled = Boolean(enabled);
    const wrapper = document.getElementById("sceneModeControl");
    const toggle = document.getElementById("sceneModeToggle");
    if (wrapper) {
      wrapper.classList.toggle("disabled", !sceneModeControlEnabled);
    }
    if (toggle) {
      toggle.disabled = !sceneModeControlEnabled;
      if (!sceneModeControlEnabled) {
        toggle.checked = true;
      }
    }
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
    const params = new URLSearchParams(queryText);
    Object.entries(extraQuery || {}).forEach(([key, value]) => {
      if (value === null || value === undefined) {
        return;
      }
      if (Array.isArray(value)) {
        params.delete(key);
        value.forEach((item) => params.append(key, String(item)));
        return;
      }
      params.set(key, String(value));
    });
    const merged = params.toString();
    return merged ? `${base}?${merged}` : base;
  }

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
      return;
    }
    activeImageryLayer = null;
    applySwipeComparatorSplit();
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
        setSceneModeControlEnabled(false);
        setStatus("DEM layer shown.");
        log("info", "DEM layer shown key=" + layerKey);
      } else {
        hideDemColorbar();
        setSceneModeControlEnabled(true);
        setStatus("DEM layer hidden.");
        log("info", "DEM layer hidden key=" + layerKey);
      }
      if (comparatorModeEnabled) {
        refreshComparatorLayers();
      }
      requestSceneRender();
      return true;
    }

    return false;
  }

  function resolveDemColorbarGradient(colormapName) {
    const normalized = String(colormapName || "terrain").toLowerCase();
    const gradients = {
      terrain:
        "to bottom, #f7f7f7 0%, #d9d3c7 14%, #b48f6a 28%, #c7b34a 42%, #7ca860 58%, #4aa8b2 74%, #2d7bd0 88%, #173c8f 100%",
      viridis:
        "to bottom, #fde725 0%, #90d743 24%, #35b779 45%, #21918c 64%, #31688e 82%, #443a83 100%",
      turbo:
        "to bottom, #7a0403 0%, #d84f2a 18%, #f6b44f 36%, #f7f756 50%, #7bd651 66%, #2c8fe3 84%, #23135a 100%",
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
    const colormapName = typeof query.colormap_name === "string" ? query.colormap_name : "terrain";
    gradient.style.background = `linear-gradient(${resolveDemColorbarGradient(colormapName)})`;

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
    if (!globalBasemapLayer) {
      return;
    }
    globalBasemapLayer.alpha = 1.0;
  }

  function applyDefaultSceneSettings() {
    if (!viewer) return;
    viewer.scene.verticalExaggeration = 1.5;
    viewer.scene.globe.enableLighting = true;
    viewer.scene.globe.depthTestAgainstTerrain = true;
    viewer.scene.globe.preloadAncestors = true;
    viewer.scene.globe.preloadSiblings = true;
    viewer.scene.globe.maximumScreenSpaceError = 2.0;
    viewer.scene.globe.showSkirts = true;
    viewer.scene.globe.tileCacheSize = 220;
    viewer.scene.globe.showGroundAtmosphere = false;
    viewer.scene.fog.enabled = false;
    viewer.shadows = false;
    viewer.scene.light = new Cesium.SunLight();
    viewer.scene.light.intensity = 2.0;
  }

  function applyDemSceneSettings() {
    if (!viewer) return;
    viewer.scene.verticalExaggeration = Math.max(0.5, demVisual.exaggeration);
    viewer.scene.globe.enableLighting = true;
    viewer.scene.globe.depthTestAgainstTerrain = true;
    viewer.scene.globe.preloadAncestors = true;
    viewer.scene.globe.preloadSiblings = true;
    viewer.scene.globe.maximumScreenSpaceError = 2.0;
    viewer.scene.globe.showSkirts = true;
    viewer.scene.globe.tileCacheSize = 240;
    viewer.scene.globe.showGroundAtmosphere = false;
    viewer.scene.fog.enabled = false;
    viewer.shadows = false;
    requestSceneRender();
  }

  function tuneCameraController() {
    if (!viewer) return;
    const controller = viewer.scene.screenSpaceCameraController;
    controller.enableCollisionDetection = true;
    controller.maximumMovementRatio = 0.075;
    controller.minimumZoomDistance = 1.0;
    controller.maximumZoomDistance = 40000000.0;
    controller.maximumTiltAngle = Cesium.Math.toRadians(89.0);
    configureCameraControllerForMode(currentSceneMode);
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
    controller.enableRotate = !is2d;
    controller.enableTilt = !is2d;
    controller.enableLook = !is2d;
    controller.inertiaSpin = is2d ? 0.0 : 0.86;
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
    viewer.camera.cancelFlight();
    viewer.camera.lookAt(sphere.center, new Cesium.HeadingPitchRange(cameraOrbitHeading, cameraOrbitPitch, cameraOrbitRange));
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

  function loadImageBitmapCompat(blob) {
    if (typeof createImageBitmap === "function") {
      return createImageBitmap(blob);
    }
    return new Promise((resolve, reject) => {
      const img = new Image();
      const url = URL.createObjectURL(blob);
      img.onload = function () {
        URL.revokeObjectURL(url);
        resolve(img);
      };
      img.onerror = function () {
        URL.revokeObjectURL(url);
        reject(new Error("Could not decode terrain tile image."));
      };
      img.src = url;
    });
  }

  function decodeTerrarium(r, g, b) {
    return r * 256.0 + g + b / 256.0 - 32768.0;
  }

  function sanitizeHeight(height, config) {
    if (!Number.isFinite(height)) {
      return config.minHeight;
    }
    if (Math.abs(height - config.nodataHeight) <= 0.5) {
      return config.minHeight;
    }
    if (height < config.minHeight) {
      return config.minHeight;
    }
    if (height > config.maxHeight) {
      return config.maxHeight;
    }
    return height;
  }

  function createFlatHeightmap(value) {
    const output = new Float32Array(TERRAIN_SAMPLE_SIZE * TERRAIN_SAMPLE_SIZE);
    output.fill(value);
    return output;
  }

  function sampleTerrainRgbHeight(imageData, width, height, x, y, config) {
    const x0 = Math.max(0, Math.min(width - 1, Math.floor(x)));
    const x1 = Math.max(0, Math.min(width - 1, x0 + 1));
    const y0 = Math.max(0, Math.min(height - 1, Math.floor(y)));
    const y1 = Math.max(0, Math.min(height - 1, y0 + 1));
    const tx = Math.max(0, Math.min(1, x - x0));
    const ty = Math.max(0, Math.min(1, y - y0));

    const idx00 = (y0 * width + x0) * 4;
    const idx10 = (y0 * width + x1) * 4;
    const idx01 = (y1 * width + x0) * 4;
    const idx11 = (y1 * width + x1) * 4;

    const h00 = decodeTerrarium(imageData[idx00], imageData[idx00 + 1], imageData[idx00 + 2]);
    const h10 = decodeTerrarium(imageData[idx10], imageData[idx10 + 1], imageData[idx10 + 2]);
    const h01 = decodeTerrarium(imageData[idx01], imageData[idx01 + 1], imageData[idx01 + 2]);
    const h11 = decodeTerrarium(imageData[idx11], imageData[idx11 + 1], imageData[idx11 + 2]);

    const hx0 = h00 * (1 - tx) + h10 * tx;
    const hx1 = h01 * (1 - tx) + h11 * tx;
    return hx0 * (1 - ty) + hx1 * ty;
  }

  function decodeTerrainRgbToHeightmap(imageData, width, height, config) {
    const output = new Float32Array(TERRAIN_SAMPLE_SIZE * TERRAIN_SAMPLE_SIZE);
    for (let row = 0; row < TERRAIN_SAMPLE_SIZE; row += 1) {
      const srcY = (row / (TERRAIN_SAMPLE_SIZE - 1)) * (height - 1);
      for (let col = 0; col < TERRAIN_SAMPLE_SIZE; col += 1) {
        const srcX = (col / (TERRAIN_SAMPLE_SIZE - 1)) * (width - 1);
        const sampled = sampleTerrainRgbHeight(imageData, width, height, srcX, srcY, config);
        output[row * TERRAIN_SAMPLE_SIZE + col] = sanitizeHeight(sampled, config);
      }
    }
    return output;
  }

  function sampleFloatGridBilinear(grid, width, height, x, y) {
    const x0 = Math.max(0, Math.min(width - 1, Math.floor(x)));
    const x1 = Math.max(0, Math.min(width - 1, x0 + 1));
    const y0 = Math.max(0, Math.min(height - 1, Math.floor(y)));
    const y1 = Math.max(0, Math.min(height - 1, y0 + 1));
    const tx = Math.max(0, Math.min(1, x - x0));
    const ty = Math.max(0, Math.min(1, y - y0));
    const h00 = grid[y0 * width + x0];
    const h10 = grid[y0 * width + x1];
    const h01 = grid[y1 * width + x0];
    const h11 = grid[y1 * width + x1];
    const hx0 = h00 * (1 - tx) + h10 * tx;
    const hx1 = h01 * (1 - tx) + h11 * tx;
    return hx0 * (1 - ty) + hx1 * ty;
  }

  function deriveChildTileFromParent(parentGrid, childX, childY) {
    const output = new Float32Array(TERRAIN_SAMPLE_SIZE * TERRAIN_SAMPLE_SIZE);
    const qx = childX % 2;
    const qy = childY % 2;
    for (let row = 0; row < TERRAIN_SAMPLE_SIZE; row += 1) {
      const v = (qy + row / (TERRAIN_SAMPLE_SIZE - 1)) * 0.5 * (TERRAIN_SAMPLE_SIZE - 1);
      for (let col = 0; col < TERRAIN_SAMPLE_SIZE; col += 1) {
        const u = (qx + col / (TERRAIN_SAMPLE_SIZE - 1)) * 0.5 * (TERRAIN_SAMPLE_SIZE - 1);
        output[row * TERRAIN_SAMPLE_SIZE + col] = sampleFloatGridBilinear(parentGrid, TERRAIN_SAMPLE_SIZE, TERRAIN_SAMPLE_SIZE, u, v);
      }
    }
    return output;
  }

  async function requestTerrainHeightmap(url, decodeConfig) {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Terrain request failed: ${response.status}`);
    }
    const blob = await response.blob();
    const image = await loadImageBitmapCompat(blob);
    const width = image.width || 256;
    const height = image.height || 256;
    if (!terrainDecodeCanvas) {
      terrainDecodeCanvas = document.createElement("canvas");
      terrainDecodeContext = terrainDecodeCanvas.getContext("2d", { willReadFrequently: true });
    }
    terrainDecodeCanvas.width = width;
    terrainDecodeCanvas.height = height;
    terrainDecodeContext.clearRect(0, 0, width, height);
    terrainDecodeContext.drawImage(image, 0, 0, width, height);
    const pixels = terrainDecodeContext.getImageData(0, 0, width, height).data;
    if (image.close) {
      image.close();
    }
    return decodeTerrainRgbToHeightmap(pixels, width, height, decodeConfig);
  }

  function cacheTerrainTile(url, promise) {
    terrainTileCache.set(url, promise);
    if (terrainTileCache.size <= MAX_TERRAIN_CACHE_ITEMS) {
      return;
    }
    const firstKey = terrainTileCache.keys().next().value;
    if (firstKey) {
      terrainTileCache.delete(firstKey);
    }
  }

  async function requestTerrainTileWithFallback(urlTemplate, x, y, level, decodeConfig) {
    const url = urlTemplate.replace("{z}", String(level)).replace("{x}", String(x)).replace("{y}", String(y));
    if (terrainTileCache.has(url)) {
      return terrainTileCache.get(url);
    }

    const promise = requestTerrainHeightmap(url, decodeConfig).catch(async (error) => {
      if (level <= 0) {
        log("warn", "DEM terrain fetch failed at root tile: " + String(error));
        return new Float32Array(TERRAIN_SAMPLE_SIZE * TERRAIN_SAMPLE_SIZE);
      }
      const parent = await requestTerrainTileWithFallback(urlTemplate, Math.floor(x / 2), Math.floor(y / 2), level - 1, decodeConfig);
      return deriveChildTileFromParent(parent, x, y);
    });

    cacheTerrainTile(url, promise);
    return promise;
  }

  function buildDemTerrainProvider(terrainUrlTemplate, bounds, decodeConfig) {
    const tilingScheme = new Cesium.WebMercatorTilingScheme();
    const demRectangle = createRectangle(bounds);
    const outsideHeight = Number.isFinite(decodeConfig.outsideHeight)
      ? decodeConfig.outsideHeight
      : decodeConfig.minHeight;
    return new Cesium.CustomHeightmapTerrainProvider({
      width: TERRAIN_SAMPLE_SIZE,
      height: TERRAIN_SAMPLE_SIZE,
      tilingScheme: tilingScheme,
      callback: async function (x, y, level) {
        if (demRectangle) {
          const tileRectangle = tilingScheme.tileXYToRectangle(x, y, level);
          const overlap = Cesium.Rectangle.intersection(tileRectangle, demRectangle, new Cesium.Rectangle());
          if (!overlap) {
            return createFlatHeightmap(outsideHeight);
          }
        }
        try {
          return await requestTerrainTileWithFallback(terrainUrlTemplate, x, y, level, decodeConfig);
        } catch (error) {
          log("warn", "DEM terrain fetch failed: " + String(error));
          return createFlatHeightmap(outsideHeight);
        }
      },
    });
  }

  function applyDemLayer() {
    if (!viewer || !activeDemContext) return;
    const bounds = activeDemContext.options && activeDemContext.options.bounds ? activeDemContext.options.bounds : null;
    const rasterQuery = activeDemContext.options && activeDemContext.options.query ? activeDemContext.options.query : {};
    const minLevel = activeDemContext.options && Number.isInteger(activeDemContext.options.minzoom) ? activeDemContext.options.minzoom : 0;
    const maxLevelRaw = activeDemContext.options && Number.isInteger(activeDemContext.options.maxzoom) ? activeDemContext.options.maxzoom : 19;
    const maxLevel = Math.min(maxLevelRaw, DEM_MAX_TERRAIN_LEVEL);
    const rectangle = createRectangle(bounds);
    const range = parseDemHeightRange(activeDemContext.options);
    const decodeConfig = {
      minHeight: range.min,
      maxHeight: range.max,
      nodataHeight: -9999.0,
    };
    const hillshadeQuery = {
      algorithm: "hillshade",
      azimuth: demVisual.azimuth,
      angle_altitude: demVisual.altitude,
      z_exaggeration: demVisual.exaggeration,
      buffer: 4,
    };
    if (Object.prototype.hasOwnProperty.call(rasterQuery, "nodata")) {
      hillshadeQuery.nodata = rasterQuery.nodata;
    }
    const hillshadeUrl = buildUrlWithQuery(activeDemContext.xyzUrl, hillshadeQuery);
    const terrainRgbUrl = buildUrlWithQuery(activeDemContext.xyzUrl, {
      algorithm: "terrarium",
      nodata_height: decodeConfig.nodataHeight,
      resampling: "nearest",
    });
    const drapeQuery = {
      ...rasterQuery,
      resampling: "nearest",
    };
    const drapeUrl = buildUrlWithQuery(activeDemContext.xyzUrl, drapeQuery);
    const demVisible = activeDemContext.visible !== false;
    layerDefinitions.set(activeDemContext.layerKey, {
      key: activeDemContext.layerKey,
      label: String(activeDemContext.name || activeDemContext.layerKey || "DEM"),
      type: "dem",
      drapeUrl: drapeUrl,
      hillshadeUrl: hillshadeUrl,
      minLevel: minLevel,
      maxLevel: maxLevel,
      bounds: normalizeBounds(bounds),
      hillshadeAlpha: Math.max(0.0, Math.min(0.35, demVisual.hillshadeAlpha * 0.45)),
    });
    layerVisibilityState.set(activeDemContext.layerKey, demVisible);
    const terrainSignature = JSON.stringify({
      xyzUrl: activeDemContext.xyzUrl,
      bounds: bounds || null,
      minLevel: minLevel,
      maxLevel: maxLevel,
      minHeight: range.min,
      maxHeight: range.max,
    });

    if (activeDemTerrainSignature !== terrainSignature) {
      viewer.terrainProvider = buildDemTerrainProvider(terrainRgbUrl, bounds, decodeConfig);
      activeDemTerrainSignature = terrainSignature;
    }

    if (!activeDemDrapeLayer || activeDemDrapeUrl !== drapeUrl) {
      if (activeDemDrapeLayer) {
        viewer.imageryLayers.remove(activeDemDrapeLayer, false);
      }
      const drapeProvider = new Cesium.UrlTemplateImageryProvider({
        url: drapeUrl,
        maximumLevel: maxLevel,
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

    const clampedHillshadeAlpha = Math.max(0.0, Math.min(0.35, demVisual.hillshadeAlpha * 0.45));
    if (clampedHillshadeAlpha > 0.01) {
      if (activeDemHillshadeLayer && activeDemHillshadeUrl !== hillshadeUrl) {
        viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
        activeDemHillshadeLayer = null;
      }
      if (!activeDemHillshadeLayer) {
        const hillshadeProvider = new Cesium.UrlTemplateImageryProvider({
          url: hillshadeUrl,
          maximumLevel: maxLevel,
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
      if (activeDemHillshadeLayer) {
        viewer.imageryLayers.raiseToTop(activeDemHillshadeLayer);
      }
    } else if (activeDemHillshadeLayer) {
      viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
      activeDemHillshadeLayer = null;
      activeDemHillshadeUrl = null;
    }
    applyDemSceneSettings();
    if (activeDemDrapeLayer) {
      viewer.imageryLayers.raiseToTop(activeDemDrapeLayer);
    }
    if (activeDemHillshadeLayer) {
      viewer.imageryLayers.raiseToTop(activeDemHillshadeLayer);
    }
    for (const layer of managedImageryLayers.values()) {
      if (layer && layer.show) {
        viewer.imageryLayers.raiseToTop(layer);
      }
    }
    updateBasemapBlendForCurrentMode();
    if (demVisible) {
      updateDemColorbar(range.min, range.max, activeDemContext.options);
      setStatus("DEM terrain active: " + activeDemContext.name);
    } else {
      hideDemColorbar();
      setStatus("DEM layer hidden.");
    }
    log("info", "DEM terrain activated name=" + activeDemContext.name + " terrain=" + terrainRgbUrl + " drape=" + drapeUrl);
    if (comparatorModeEnabled) {
      refreshComparatorLayers();
    }
    requestSceneRender();
  }

  function setDemColorMode(colormapName) {
    if (!activeDemContext) {
      return;
    }
    if (!activeDemContext.options) {
      activeDemContext.options = {};
    }
    if (!activeDemContext.options.query) {
      activeDemContext.options.query = {};
    }
    activeDemContext.options.query.colormap_name = String(colormapName || "terrain");
    applyDemLayer();
  }

  function initBridge() {
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
      requestRenderMode: true,
      maximumRenderTimeChange: Infinity,
      timeline: false,
      animation: false,
      terrainProvider: new Cesium.EllipsoidTerrainProvider(),
    });
    baseTerrainProvider = viewer.terrainProvider;
    fallbackBasemapLayer = viewer.imageryLayers.get(0);
    const devicePixelRatio = window.devicePixelRatio || 1.0;
    viewer.resolutionScale = Math.min(devicePixelRatio, 1.25);
    viewer.scene.postProcessStages.fxaa.enabled = false;
    viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#1f4f7a");
    viewer.scene.backgroundColor = Cesium.Color.BLACK;
    viewer.canvas.style.backgroundColor = "#000000";
    applyDefaultSceneSettings();
    tuneCameraController();
    window.addEventListener("error", function (event) {
      log("error", "Window error: " + (event && event.message ? event.message : "unknown"));
    });
    window.addEventListener("unhandledrejection", function (event) {
      const reason = event && event.reason ? String(event.reason) : "unknown";
      log("error", "Unhandled promise rejection: " + reason);
    });
    setupSceneModeToggle();
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
    setStatus("Offline Cesium initialized.");
    log("info", "Viewer initialized with local offline basemap pipeline");
  }

  function setupSceneModeToggle() {
    const toggle = document.getElementById("sceneModeToggle");
    if (!toggle) {
      return;
    }
    toggle.checked = true;
    toggle.addEventListener("change", function () {
      sceneDebug(
        "toggle.change checked=" +
          String(toggle.checked) +
          " sceneModeControlEnabled=" +
          String(sceneModeControlEnabled) +
          " detectSceneMode=" +
          detectSceneMode() +
          " currentSceneMode=" +
          currentSceneMode
      );
      if (!sceneModeControlEnabled) {
        toggle.checked = true;
        sceneDebug("toggle.change blocked: sceneModeControlEnabled=false");
        return;
      }
      window.offlineGIS.setSceneMode(toggle.checked ? "3d" : "2d");
    });
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

  async function attachOfflineTerrainPack() {
    if (!viewer) return;
    try {
      const provider = await Cesium.CesiumTerrainProvider.fromUrl("./basemap/terrain");
      baseTerrainProvider = provider;
      if (!activeDemContext) {
        viewer.terrainProvider = provider;
      }
      log("info", "Offline quantized-mesh terrain pack loaded.");
      setStatus("Offline terrain pack loaded.");
      return true;
    } catch (error) {
      if (looksLikeMissingLocalAssetError(error)) {
        log("info", "No offline quantized-mesh terrain pack found. Using ellipsoid terrain.");
      } else {
        log("warn", "Offline quantized-mesh terrain pack could not be loaded: " + String(error));
      }
      if (!AUTO_ATTACH_TERRAIN_RGB_PACK) {
        return false;
      }
      return await attachOfflineTerrainRgbPack();
    }
  }

  async function attachOfflineTerrainRgbPack() {
    try {
      const response = await fetch(LOCAL_TERRAIN_RGB_METADATA_URL, { cache: "no-store" });
      if (!response.ok) {
        log("info", "No offline terrain pack found (quantized-mesh or terrain-rgb). Using ellipsoid terrain.");
        return false;
      }

      const metadata = await response.json();
      const bounds = parseTerrainRgbBounds(metadata);
      if (!bounds) {
        log("warn", "terrain-rgb metadata missing valid bbox; skipping offline terrain-rgb pack.");
        return false;
      }

      const region = typeof metadata.region === "string" ? metadata.region.toLowerCase() : "custom";
      const hasGlobalCoverage =
        bounds.west <= -179.0 &&
        bounds.east >= 179.0 &&
        bounds.south <= -84.0 &&
        bounds.north >= 84.0;
      if (region !== "world" || !hasGlobalCoverage) {
        log("warn", "terrain-rgb pack is partial coverage; skipping automatic global terrain activation.");
        return false;
      }

      const provider = buildDemTerrainProvider(
        `${LOCAL_TERRAIN_RGB_ROOT}/{z}/{x}/{y}.png`,
        bounds,
        {
          minHeight: -11000.0,
          maxHeight: 9000.0,
          nodataHeight: -32768.0,
          outsideHeight: 0.0,
        }
      );
      baseTerrainProvider = provider;
      if (!activeDemContext) {
        viewer.terrainProvider = provider;
      }
      log("info", "Offline terrain-rgb pack loaded for region=" + region);
      setStatus("Offline terrain-rgb pack loaded (" + region + ").");
      return true;
    } catch (error) {
      log("warn", "Offline terrain-rgb pack could not be loaded: " + String(error));
      return false;
    }
  }

  function parseTerrainRgbBounds(metadata) {
    if (!metadata || typeof metadata !== "object") {
      return null;
    }
    const bbox = metadata.bbox;
    if (!bbox || typeof bbox !== "object") {
      return null;
    }
    const west = Number(bbox.west);
    const south = Number(bbox.south);
    const east = Number(bbox.east);
    const north = Number(bbox.north);
    if (!Number.isFinite(west) || !Number.isFinite(south) || !Number.isFinite(east) || !Number.isFinite(north)) {
      return null;
    }
    return { west: west, south: south, east: east, north: north };
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
      const probe = await fetch(COUNTRY_BOUNDARY_GEOJSON_URL, { cache: "no-store" });
      if (!probe.ok) {
        log("info", "No offline country-boundary overlay found.");
        return false;
      }
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
      log("warn", "Offline country-boundary overlay could not be loaded: " + String(error));
      return false;
    }
  }

  function createNaturalEarthProvider() {
    return new Cesium.UrlTemplateImageryProvider({
      url: Cesium.buildModuleUrl("Assets/Textures/NaturalEarthII/{z}/{x}/{y}.jpg"),
      tilingScheme: new Cesium.GeographicTilingScheme(),
      maximumLevel: 2,
      enablePickFeatures: false,
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
    const url = Cesium.buildModuleUrl("Assets/Textures/NaturalEarthII/{z}/{x}/{y}.jpg");
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

  function probeLocalBasemapTile() {
    return new Promise((resolve) => {
      const probe = new Image();
      probe.onload = function () {
        resolve(true);
      };
      probe.onerror = function () {
        resolve(false);
      };
      probe.src = `${LOCAL_SATELLITE_TILE_ROOT}/0/0/0.jpg?ts=${Date.now()}`;
    });
  }

  async function getLocalBasemapMetadata() {
    try {
      const response = await fetch(LOCAL_SATELLITE_METADATA_URL, { cache: "no-store" });
      if (!response.ok) {
        return null;
      }
      return await response.json();
    } catch (_error) {
      return null;
    }
  }

  function getLocalBasemapMaxLevel(metadata) {
    const maxZoom = Number(metadata && metadata.max_zoom);
    if (!Number.isFinite(maxZoom) || maxZoom < 0) {
      return LOCAL_SATELLITE_DEFAULT_MAX_LEVEL;
    }
    return Math.floor(maxZoom);
  }

  function getLocalBasemapCoverageBounds(metadata) {
    const regionKey = String(metadata && metadata.region ? metadata.region : "world").toLowerCase();
    const regionFallback = LOCAL_BASEMAP_REGION_BOUNDS[regionKey] || LOCAL_BASEMAP_REGION_BOUNDS.world;
    const candidate = metadata && metadata.bounds ? metadata.bounds : regionFallback;
    const west = Number(candidate.west);
    const south = Number(candidate.south);
    const east = Number(candidate.east);
    const north = Number(candidate.north);
    if (![west, south, east, north].every(Number.isFinite)) {
      return regionFallback;
    }
    return {
      west: Math.max(-180.0, Math.min(180.0, west)),
      south: Math.max(-WEB_MERCATOR_MAX_LAT_DEGREES, Math.min(WEB_MERCATOR_MAX_LAT_DEGREES, south)),
      east: Math.max(-180.0, Math.min(180.0, east)),
      north: Math.max(-WEB_MERCATOR_MAX_LAT_DEGREES, Math.min(WEB_MERCATOR_MAX_LAT_DEGREES, north)),
    };
  }

  function createLocalBasemapCoverageRectangle(metadata) {
    const bounds = getLocalBasemapCoverageBounds(metadata);
    if (bounds.west >= bounds.east || bounds.south >= bounds.north) {
      return null;
    }
    return Cesium.Rectangle.fromDegrees(bounds.west, bounds.south, bounds.east, bounds.north);
  }

  function ensureFallbackBasemapLayer() {
    if (!viewer || fallbackBasemapLayer) {
      return;
    }
    const provider = createNaturalEarthProvider();
    fallbackBasemapLayer = viewer.imageryLayers.addImageryProvider(provider, 0);
  }

  async function attachLocalSatelliteBasemap() {
    if (!viewer) return;
    const hasTiles = await probeLocalBasemapTile();
    if (!hasTiles) {
      attachOfflineFallbackBasemap("Offline world tiles missing. Run scripts/setup_global_basemap.sh first.");
      return;
    }
    const metadata = await getLocalBasemapMetadata();
    const maxLevel = getLocalBasemapMaxLevel(metadata);
    const coverageRectangle = createLocalBasemapCoverageRectangle(metadata);
    ensureFallbackBasemapLayer();
    if (globalBasemapLayer) {
      viewer.imageryLayers.remove(globalBasemapLayer, false);
      globalBasemapLayer = null;
    }
    const provider = new Cesium.UrlTemplateImageryProvider({
      url: `${LOCAL_SATELLITE_TILE_ROOT}/{z}/{x}/{y}.jpg`,
      tilingScheme: new Cesium.WebMercatorTilingScheme(),
      maximumLevel: maxLevel,
      rectangle: coverageRectangle || undefined,
      enablePickFeatures: false,
      credit: "Offline world imagery",
    });
    attachTileErrorHandler(provider, LOCAL_SATELLITE_LAYER_NAME);
    globalBasemapLayer = viewer.imageryLayers.addImageryProvider(provider, 1);
    globalBasemapLayer.alpha = 1.0;
    ensurePolarCapLayers();
    setStatus(`Offline satellite globe ready (max zoom ${maxLevel}).`);
    log("info", "Loaded local offline world XYZ tiles");
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

  function wireClickHandlers() {
    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction(function (movement) {
      const picked = movement && movement.position ? viewer.scene.pick(movement.position) : null;
      if (picked && picked.id && picked.id._annotationRole === "edit") {
        if (renameAnnotationFromEditIcon(picked.id)) {
          return;
        }
      }
      const clickCartesian = getCartesianFromViewer(viewer, movement.position);
      if (clickCartesian) {
        lastMapClickCartesian = Cesium.Cartesian3.clone(clickCartesian);
      }
      const lonLat = clickCartesian ? cartesianToLonLat(clickCartesian) : getLonLatFromScreen(movement.position);
      if (!lonLat) return;
      const lon = lonLat.lon;
      const lat = lonLat.lat;

      if (searchDrawMode === "polygon") {
        searchPolygonPoints.push({ lon: lon, lat: lat });
        addSearchVertexMarker(lon, lat, Cesium.Color.CYAN);
        searchCursorPoint = null;
        updateSearchPolygonPreview();
        setStatus("Polygon draw: continue points, right-click or Finish to close");
        return;
      }

      if (distanceMeasureModeEnabled) {
        bridge.on_map_click(lon, lat);
        log("debug", "Distance mode click lon=" + lon.toFixed(6) + " lat=" + lat.toFixed(6));
        if (!distanceMeasureAnchor) {
          distanceMeasureAnchor = { lon: lon, lat: lat };
          clickedPoints.length = 0;
          clickedPoints.push([lon, lat]);
          clearMeasurementEntities();
          clearMeasurementPreviewEntities();
          setStatus("Distance tool: move cursor and click second point to finalize.");
          return;
        }

        const start = distanceMeasureAnchor;
        clickedPoints.length = 0;
        clickedPoints.push([start.lon, start.lat]);
        clickedPoints.push([lon, lat]);
        const geodesic = new Cesium.EllipsoidGeodesic(
          Cesium.Cartographic.fromDegrees(start.lon, start.lat),
          Cesium.Cartographic.fromDegrees(lon, lat)
        );
        clearMeasurementPreviewEntities();
        updateMeasurementEntities(
          start.lon,
          start.lat,
          lon,
          lat,
          geodesic.surfaceDistance
        );
        distanceMeasureAnchor = { lon: lon, lat: lat };
        bridge.on_measurement(geodesic.surfaceDistance);
        setStatus("Distance measured. Click next point for chained measure, or right-click to stop.");
        log("info", "Distance measured (m): " + geodesic.surfaceDistance.toFixed(2));
        return;
      }

      clickedPoints.push([lon, lat]);
      if (clickedPoints.length > 2) clickedPoints.shift();
      bridge.on_map_click(lon, lat);
      log("debug", "Map click lon=" + lon.toFixed(6) + " lat=" + lat.toFixed(6));
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

    handler.setInputAction(function (movement) {
      if (movement && movement.endPosition) {
        lastSearchCursorScreenPosition = movement.endPosition;
        updateAnnotationHover(movement.endPosition);
      }
      if (distanceMeasureModeEnabled && distanceMeasureAnchor && searchDrawMode !== "polygon") {
        const lonLat = getLonLatFromScreen(movement.endPosition);
        if (lonLat) {
          const geodesic = new Cesium.EllipsoidGeodesic(
            Cesium.Cartographic.fromDegrees(distanceMeasureAnchor.lon, distanceMeasureAnchor.lat),
            Cesium.Cartographic.fromDegrees(lonLat.lon, lonLat.lat)
          );
          updateMeasurementPreview(
            distanceMeasureAnchor.lon,
            distanceMeasureAnchor.lat,
            lonLat.lon,
            lonLat.lat,
            geodesic.surfaceDistance
          );
        }
      }
      if (searchDrawMode === "polygon") {
        setSearchCursorEnabled(true);
        updateSearchCursorOverlay(lastSearchCursorScreenPosition);
      }
      if (searchDrawMode !== "polygon" || searchPolygonPoints.length === 0) {
        return;
      }
      const lonLat = getLonLatFromScreen(movement.endPosition);
      if (!lonLat) {
        return;
      }
      searchCursorPoint = { lon: lonLat.lon, lat: lonLat.lat };
      updateSearchPolygonPreview();
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

    const polygonVisibilityToggle = document.getElementById("polygonVisibilityToggle");
    if (polygonVisibilityToggle) {
      polygonVisibilityToggle.addEventListener("change", function () {
        polygonVisibilityEnabled = this.checked;
        updatePolygonPreviewVisibility();
        log("debug", "Polygon preview visibility toggled: " + (polygonVisibilityEnabled ? "shown" : "hidden"));
      });
    }

    viewer.canvas.addEventListener("mouseenter", function () {
      if (searchDrawMode === "polygon") {
        setSearchCursorOverlayVisible(true);
      }
    });

    viewer.canvas.addEventListener("mouseleave", function () {
      setSearchCursorOverlayVisible(false);
      if (hoveredAnnotationEditEntity) {
        setAnnotationEditIconHoverState(hoveredAnnotationEditEntity, false);
        hoveredAnnotationEditEntity = null;
      }
    });
  }

  function updatePolygonPreviewVisibility() {
    for (const markerEntity of searchVertexEntities) {
      if (markerEntity) {
        markerEntity.show = polygonVisibilityEnabled;
      }
    }
    if (searchCursorEntity) {
      searchCursorEntity.show = polygonVisibilityEnabled;
    }
    if (searchPreviewLineEntity && searchPreviewLineEntity.polyline) {
      searchPreviewLineEntity.polyline.show = polygonVisibilityEnabled && searchPolygonPoints.length >= 2;
    }
    if (searchPreviewPolygonEntity && searchPreviewPolygonEntity.polygon) {
      searchPreviewPolygonEntity.polygon.show = polygonVisibilityEnabled && searchPolygonPoints.length >= 3;
    }
    if (searchAreaLabelEntity && searchAreaLabelEntity.label) {
      searchAreaLabelEntity.label.show = polygonVisibilityEnabled && searchPolygonPoints.length >= 3;
    }
    if (searchPreviewLineEntity || searchPreviewPolygonEntity || searchAreaLabelEntity) {
      requestSceneRender();
    }
  }

  function setPolygonPreviewVisible(visible) {
    polygonVisibilityEnabled = Boolean(visible);
    const toggle = document.getElementById("polygonVisibilityToggle");
    if (toggle) {
      toggle.checked = polygonVisibilityEnabled;
    }
    updatePolygonPreviewVisibility();
  }

  function getLonLatFromScreen(screenPosition) {
    return getLonLatFromViewer(viewer, screenPosition);
  }

  function addSearchVertexMarker(lon, lat, color) {
    const entity = viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(lon, lat),
      point: {
        pixelSize: 8,
        color: color || Cesium.Color.CYAN,
        outlineColor: Cesium.Color.BLACK.withAlpha(0.7),
        outlineWidth: 1,
        heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
    searchVertexEntities.push(entity);
    requestSceneRender();
  }

  function clearSearchEntities() {
    while (searchVertexEntities.length > 0) {
      const entity = searchVertexEntities.pop();
      if (entity && viewer) viewer.entities.remove(entity);
    }
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
    requestSceneRender();
  }

  function clearMeasurementEntities() {
    if (!viewer) {
      return;
    }
    if (measurementLineEntity) {
      viewer.entities.remove(measurementLineEntity);
      measurementLineEntity = null;
    }
    if (measurementLabelEntity) {
      viewer.entities.remove(measurementLabelEntity);
      measurementLabelEntity = null;
    }
    clearMeasurementPreviewEntities();
    requestSceneRender();
  }

  function clearMeasurementPreviewEntities() {
    if (!viewer) {
      return;
    }
    if (measurementPreviewLineEntity) {
      viewer.entities.remove(measurementPreviewLineEntity);
      measurementPreviewLineEntity = null;
    }
    if (measurementPreviewLabelEntity) {
      viewer.entities.remove(measurementPreviewLabelEntity);
      measurementPreviewLabelEntity = null;
    }
    requestSceneRender();
  }

  function updateMeasurementPreview(startLon, startLat, endLon, endLat, meters) {
    if (!viewer) {
      return;
    }
    clearMeasurementPreviewEntities();
    const start = Cesium.Cartesian3.fromDegrees(startLon, startLat);
    const end = Cesium.Cartesian3.fromDegrees(endLon, endLat);
    const labelLon = (startLon + endLon) / 2.0;
    const labelLat = (startLat + endLat) / 2.0;

    measurementPreviewLineEntity = viewer.entities.add({
      polyline: {
        positions: [start, end],
        width: 2.0,
        material: Cesium.Color.YELLOW.withAlpha(0.6),
        clampToGround: true,
      },
    });

    measurementPreviewLabelEntity = viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(labelLon, labelLat),
      label: {
        text: "Preview: " + meters.toFixed(2) + " m",
        fillColor: Cesium.Color.WHITE,
        showBackground: true,
        backgroundColor: Cesium.Color.BLACK.withAlpha(0.6),
        pixelOffset: new Cesium.Cartesian2(0, -18),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
    requestSceneRender();
  }

  function setDistanceMeasureMode(enabled) {
    distanceMeasureModeEnabled = Boolean(enabled);
    distanceMeasureAnchor = null;
    if (distanceMeasureModeEnabled && searchDrawMode === "polygon") {
      searchDrawMode = "none";
      setSearchCursorEnabled(false);
    }
    clearMeasurementPreviewEntities();
    if (distanceMeasureModeEnabled) {
      clickedPoints.length = 0;
      setStatus("Distance tool enabled. Click first point to begin.");
      return;
    }
    setStatus("Distance tool disabled.");
  }

  function setPanMode(enabled) {
    if (!enabled) {
      return;
    }
    if (distanceMeasureModeEnabled) {
      setDistanceMeasureMode(false);
    }
    if (searchDrawMode === "polygon") {
      searchDrawMode = "none";
      setSearchCursorEnabled(false);
      setStatus("Pan mode enabled.");
      requestSceneRender();
      return;
    }
    setStatus("Pan mode enabled.");
    requestSceneRender();
  }

  function updateMeasurementEntities(startLon, startLat, endLon, endLat, meters) {
    if (!viewer) {
      return;
    }
    clearMeasurementEntities();
    const start = Cesium.Cartesian3.fromDegrees(startLon, startLat);
    const end = Cesium.Cartesian3.fromDegrees(endLon, endLat);
    const labelLon = (startLon + endLon) / 2.0;
    const labelLat = (startLat + endLat) / 2.0;

    measurementLineEntity = viewer.entities.add({
      polyline: {
        positions: [start, end],
        width: 2.2,
        material: Cesium.Color.YELLOW,
        clampToGround: true,
      },
    });

    measurementLabelEntity = viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(labelLon, labelLat),
      label: {
        text: meters.toFixed(2) + " m",
        fillColor: Cesium.Color.WHITE,
        showBackground: true,
        backgroundColor: Cesium.Color.BLACK.withAlpha(0.75),
        pixelOffset: new Cesium.Cartesian2(0, -18),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
    requestSceneRender();
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
    const bounds = activeTileBounds || lastLoadedBounds;
    const camera = viewer.camera;
    camera.cancelFlight();

    if (bounds) {
      const rect = Cesium.Rectangle.fromDegrees(bounds.west, bounds.south, bounds.east, bounds.north);
      camera.flyTo({
        destination: rect,
        orientation: {
          heading: 0.0,
          pitch: -Cesium.Math.PI_OVER_TWO,
          roll: 0.0,
        },
        duration: 0.85,
      });
      return;
    }

    camera.flyHome(0.85);
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
    const rect = Cesium.Rectangle.fromDegrees(bounds.west, bounds.south, bounds.east, bounds.north);
    viewer.camera.cancelFlight();
    viewer.camera.flyTo({ destination: rect, duration: 0.8 });
  }

  function getSearchPreviewPoints() {
    return searchCursorPoint ? searchPolygonPoints.concat([searchCursorPoint]) : searchPolygonPoints.slice();
  }

  function getSearchPreviewCartesianPoints() {
    return getSearchPreviewPoints().map((p) => Cesium.Cartesian3.fromDegrees(p.lon, p.lat));
  }

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
          show: new Cesium.CallbackProperty(
            () => polygonVisibilityEnabled && getSearchPreviewPoints().length >= 2,
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
          material: Cesium.Color.CYAN.withAlpha(0.2),
          perPositionHeight: false,
          show: new Cesium.CallbackProperty(
            () => polygonVisibilityEnabled && getSearchPreviewPoints().length >= 3,
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
          () => polygonVisibilityEnabled && Boolean(searchCursorPoint),
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
            () => polygonVisibilityEnabled && getSearchPreviewPoints().length >= 3,
            false,
          ),
        },
      });
    }
  }

  function updateSearchPolygonPreview() {
    ensureSearchPreviewEntities();
    requestSceneRender();
  }

  function finalizeSearchPolygon() {
    if (searchPolygonPoints.length < 3) {
      log("warn", "Polygon draw requires at least 3 points");
      return;
    }
    searchCursorPoint = null;
    for (const markerEntity of searchVertexEntities) {
      if (markerEntity && markerEntity.point) {
        markerEntity.point.color = Cesium.Color.fromCssColorString("#31d18d");
      }
    }
    if (searchPreviewLineEntity && searchPreviewLineEntity.polyline) {
      searchPreviewLineEntity.polyline.material = Cesium.Color.fromCssColorString("#31d18d");
    }
    if (searchPreviewPolygonEntity && searchPreviewPolygonEntity.polygon) {
      searchPreviewPolygonEntity.polygon.material = Cesium.Color.fromCssColorString("#31d18d").withAlpha(0.28);
    }
    updateSearchPolygonPreview();

    const polygonPayload = { points: searchPolygonPoints.slice() };
    searchDrawMode = "none";
    setSearchCursorEnabled(false);
    const polygonToggleControl = document.getElementById("polygonToggleControl");
    if (polygonToggleControl) {
      polygonToggleControl.style.display = "flex";
    }
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
      return "0 m2";
    }
    if (squareMeters >= 1_000_000) {
      return (squareMeters / 1_000_000).toFixed(2) + " km2";
    }
    return Math.round(squareMeters) + " m2";
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
      viewer.scene.morphTo2D(1.0);
      currentSceneMode = "2d";
      syncSceneModeToggle("2d");
      updateBasemapBlendForCurrentMode();
      setStatus("2D map mode active.");
      log("info", "Scene mode switched to 2D from 3D");
      return;
    }
    sceneDebug("setSceneModeInternal morphTo3D begin pendingFocus=" + String(pendingFocusAfterMorph));
    viewer.scene.morphTo3D(1.0);
    currentSceneMode = "3d";
    syncSceneModeToggle("3d");
    updateBasemapBlendForCurrentMode();
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
      setActiveTileBounds({ west: west, south: south, east: east, north: north });
      const rect = Cesium.Rectangle.fromDegrees(west, south, east, north);
      viewer.camera.cancelFlight();
      viewer.camera.setView({ destination: rect });
      requestSceneRender();
      log("debug", "Focus bounds west=" + west + " south=" + south + " east=" + east + " north=" + north);
    },
    addTileLayer: async function (name, xyzUrl, kind, options) {
      if (!viewer) return;
      await ensureBaseTerrainReady();
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
        const hadActiveDemContext = Boolean(activeDemContext);
        if (hadActiveDemContext) {
          // Preserve current DEM terrain mesh to allow realistic imagery drape in 3D.
          if (activeDemDrapeLayer) {
            viewer.imageryLayers.remove(activeDemDrapeLayer, false);
            activeDemDrapeLayer = null;
          }
          if (activeDemHillshadeLayer) {
            viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
            activeDemHillshadeLayer = null;
          }
          activeDemContext = null;
          hideDemColorbar();
        } else {
          clearDemTerrainMode();
        }
        clearManagedImageryLayers();
      }
      setSceneModeControlEnabled(!(activeDemContext && activeDemContext.visible !== false));
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
      attachTileErrorHandler(provider, name);
      activeImageryLayer = viewer.imageryLayers.addImageryProvider(provider);
      managedImageryLayers.set(layerKey, activeImageryLayer);
      viewer.imageryLayers.raiseToTop(activeImageryLayer);
      activeImageryLayer.alpha = 1.0;
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
    },
    addDemLayer: function (name, xyzUrl, options) {
      if (!viewer) return;
      const replaceExisting = !(options && options.replace_existing === false);
      const layerKey =
        options && typeof options.layer_key === "string" && options.layer_key
          ? options.layer_key
          : "dem:" + String(name || "layer");
      if (replaceExisting) {
        clearManagedImageryLayers();
      }
      setSceneModeInternal("3d");
      setSceneModeControlEnabled(false);
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
      if (!sceneModeControlEnabled && String(mode || "").toLowerCase() === "2d") {
        syncSceneModeToggle("3d");
        sceneDebug("window.setSceneMode blocked 2d due to disabled scene mode control");
        return;
      }
      if (activeDemContext && activeDemContext.visible !== false && String(mode || "").toLowerCase() === "2d") {
        setSceneModeInternal("3d");
        setStatus("DEM terrain requires 3D mode.");
        sceneDebug("window.setSceneMode blocked 2d because DEM context is active");
        log("warn", "Blocked 2D mode while DEM terrain is active");
        return;
      }
      setSceneModeInternal(mode);
    },
    setSceneModeControlEnabled: function (enabled) {
      setSceneModeControlEnabled(Boolean(enabled));
    },
    setSearchBusy: function (active, message) {
      setSearchBusy(active, message);
    },
    setDemColorMode: function (colormapName) {
      setDemColorMode(colormapName);
    },
    setSwipeComparatorLayers: function (leftLayerKey, rightLayerKey, leftLabel, rightLabel) {
      setSwipeComparatorLayerKeys(leftLayerKey, rightLayerKey, leftLabel, rightLabel);
    },
    setLayerVisibility: function (layerKey, visible) {
      const applied = setLayerVisibilityByKey(String(layerKey || ""), Boolean(visible));
      if (!applied) {
        log("warn", "Layer visibility update ignored key=" + String(layerKey));
      }
    },
    flyThroughBounds: function (west, south, east, north) {
      startFlyThroughBounds(west, south, east, north);
    },
    setDemProperties: function (exaggeration, hillshadeAlpha, azimuth, altitude) {
      demVisual.exaggeration = Math.max(0.1, Number(exaggeration) || 1.0);
      demVisual.hillshadeAlpha = Math.max(0.0, Math.min(1.0, Number(hillshadeAlpha) || 0.0));
      demVisual.azimuth = Math.max(0, Math.min(360, Number(azimuth) || 45));
      demVisual.altitude = Math.max(0, Math.min(90, Number(altitude) || 45));
      if (activeDemContext) {
        applyDemLayer();
      } else if (viewer) {
        viewer.scene.verticalExaggeration = demVisual.exaggeration;
      }
      requestSceneRender();
      log(
        "info",
        "DEM properties exaggeration=" +
          demVisual.exaggeration.toFixed(2) +
          " hillshade=" +
          demVisual.hillshadeAlpha.toFixed(2) +
          " azimuth=" +
          demVisual.azimuth +
          " altitude=" +
          demVisual.altitude
      );
    },
    setImageryProperties: function (brightness, contrast) {
      if (!viewer) return;
      const visibleManagedLayers = Array.from(managedImageryLayers.values()).filter((layer) => layer && layer.show);
      const nextBrightness = Math.max(0.2, brightness);
      const nextContrast = Math.max(0.1, contrast);
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
      const targetBounds = cameraOrbitBounds || activeTileBounds || lastLoadedBounds;
      if (targetBounds) {
        syncOrbitFromCurrentCamera(targetBounds);
        cameraOrbitHeading += Cesium.Math.toRadians(degrees);
        applyCameraOrbitTarget();
      } else {
        viewer.camera.rotateRight(Cesium.Math.toRadians(degrees));
      }
      log("debug", "Rotate camera degrees=" + degrees);
    },
    setPitch: function (degrees) {
      if (!viewer) return;
      const targetBounds = cameraOrbitBounds || activeTileBounds || lastLoadedBounds;
      if (targetBounds) {
        syncOrbitFromCurrentCamera(targetBounds);
      }
      cameraOrbitPitch = Cesium.Math.toRadians(degrees);
      if (!applyCameraOrbitTarget()) {
        const camera = viewer.camera;
        camera.setView({
          destination: camera.position,
          orientation: {
            heading: camera.heading,
            pitch: cameraOrbitPitch,
            roll: camera.roll,
          },
        });
      }
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
    clearMeasurements: function () {
      setDistanceMeasureMode(false);
      clickedPoints.length = 0;
      clearMeasurementEntities();
      log("info", "Measurement overlays cleared");
    },
    clearOverlays: function () {
      clickedPoints.length = 0;
      clearMeasurementEntities();
      clearAnnotationEntities();
      clearSearchEntities();
      searchPolygonPoints.length = 0;
      searchCursorPoint = null;
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
      log("info", "Swipe comparator=" + String(Boolean(enabled)));
    },
    setSwipePosition: function (fraction) {
      setSwipePosition(Number(fraction));
      log("debug", "Swipe comparator position=" + String(fraction));
    },
    setDistanceMeasureMode: function (enabled) {
      setDistanceMeasureMode(Boolean(enabled));
      log("info", "Distance measure mode=" + String(Boolean(enabled)));
    },
    setPanMode: function (enabled) {
      setPanMode(Boolean(enabled));
      log("info", "Pan mode=" + String(Boolean(enabled)));
    },
    setSearchDrawMode: function (mode) {
      if (mode !== "polygon") {
        searchDrawMode = "none";
        setSearchCursorEnabled(false);
        setStatus("Search draw disabled");
        requestSceneRender();
        return;
      }
      searchDrawMode = "polygon";
      polygonVisibilityEnabled = true;
      searchCursorPoint = null;
      searchPolygonPoints.length = 0;
      clearSearchEntities();
      emitSearchGeometry("none", {});
      setPolygonPreviewVisible(true);
      setSearchCursorEnabled(true);
      setStatus("Polygon draw: click points, right-click or Finish to close");
      requestSceneRender();
    },
    finishSearchPolygon: function () {
      finalizeSearchPolygon();
    },
    clearSearchGeometry: function () {
      searchDrawMode = "none";
      searchCursorPoint = null;
      searchPolygonPoints.length = 0;
      polygonVisibilityEnabled = true;
      clearSearchEntities();
      emitSearchGeometry("none", {});
      setPolygonPreviewVisible(true);
      setSearchCursorEnabled(false);
      const polygonToggleControl = document.getElementById("polygonToggleControl");
      if (polygonToggleControl) {
        polygonToggleControl.style.display = "none";
      }
      setStatus("Search geometry cleared");
      requestSceneRender();
    },
    setPolygonPreviewVisible: function (visible) {
      setPolygonPreviewVisible(Boolean(visible));
    },
  };

  document.addEventListener("DOMContentLoaded", initBridge);
})();
