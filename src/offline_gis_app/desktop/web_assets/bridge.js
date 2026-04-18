(function () {
  let bridge = null;
  let viewer = null;
  let activeImageryLayer = null;
  let activeDemHillshadeLayer = null;
  let activeDemContext = null;
  let globalBasemapLayer = null;
  let fallbackBasemapLayer = null;
  let northPolarCapLayer = null;
  let southPolarCapLayer = null;
  let baseTerrainProvider = null;
  let baseTerrainReadyPromise = Promise.resolve(false);
  let countryBoundaryDataSource = null;
  const clickedPoints = [];
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
  let searchBoxStart = null;
  const searchPolygonPoints = [];
  const searchEntities = [];
  let searchCursorPoint = null;
  let sceneModeControlEnabled = true;
  let currentSceneMode = "3d";
  let activeTileBounds = null;
  let lastLoadedBounds = null;
  let pendingFocusAfterMorph = false;
  let pendingTerrainSceneAfterMorph = false;
  let pendingFocusBounds = null;
  let pendingFlyThroughBounds = null;
  let pendingSceneModeAfterMorph = null;
  let lastEdgeScaleUpdateMs = 0;
  let has2DWheelZoomFallback = false;
  const EDGE_SCALE_UPDATE_INTERVAL_MS = 120;

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
    if (activeDemHillshadeLayer) {
      viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
      activeDemHillshadeLayer = null;
    }
    activeDemContext = null;
    terrainTileCache.clear();
    viewer.terrainProvider = baseTerrainProvider || new Cesium.EllipsoidTerrainProvider();
    applyDefaultSceneSettings();
    if (globalBasemapLayer) {
      globalBasemapLayer.alpha = 1.0;
    }
    hideDemColorbar();
    setSceneModeControlEnabled(true);
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
    const hillshadeUrl = buildUrlWithQuery(activeDemContext.xyzUrl, {
      algorithm: "hillshade",
      azimuth: demVisual.azimuth,
      angle_altitude: demVisual.altitude,
      z_exaggeration: demVisual.exaggeration,
      buffer: 4,
    });
    const terrainRgbUrl = buildUrlWithQuery(activeDemContext.xyzUrl, {
      algorithm: "terrarium",
      nodata_height: decodeConfig.nodataHeight,
      resampling: "bilinear",
    });
    const drapeUrl = buildUrlWithQuery(activeDemContext.xyzUrl, rasterQuery);

    if (activeImageryLayer) {
      viewer.imageryLayers.remove(activeImageryLayer, false);
      activeImageryLayer = null;
    }
    if (activeDemHillshadeLayer) {
      viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
      activeDemHillshadeLayer = null;
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
    activeImageryLayer = viewer.imageryLayers.addImageryProvider(drapeProvider);
    activeImageryLayer.alpha = 1.0;

    const clampedHillshadeAlpha = Math.max(0.0, Math.min(0.35, demVisual.hillshadeAlpha * 0.45));
    if (clampedHillshadeAlpha > 0.01) {
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
      activeDemHillshadeLayer.alpha = clampedHillshadeAlpha;
      viewer.imageryLayers.raiseToTop(activeDemHillshadeLayer);
    }

    viewer.terrainProvider = buildDemTerrainProvider(terrainRgbUrl, bounds, decodeConfig);
    applyDemSceneSettings();
    viewer.imageryLayers.raiseToTop(activeImageryLayer);
    updateBasemapBlendForCurrentMode();
    updateDemColorbar(range.min, range.max, activeDemContext.options);
    setStatus("DEM terrain active: " + activeDemContext.name);
    log("info", "DEM terrain activated name=" + activeDemContext.name + " terrain=" + terrainRgbUrl + " drape=" + drapeUrl);
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

  function wireClickHandlers() {
    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction(function (movement) {
      const lonLat = getLonLatFromScreen(movement.position);
      if (!lonLat) return;
      const lon = lonLat.lon;
      const lat = lonLat.lat;

      clickedPoints.push([lon, lat]);
      if (clickedPoints.length > 2) clickedPoints.shift();
      bridge.on_map_click(lon, lat);
      log("debug", "Map click lon=" + lon.toFixed(6) + " lat=" + lat.toFixed(6));

      if (searchDrawMode === "box") {
        if (!searchBoxStart) {
          searchBoxStart = { lon: lon, lat: lat };
          clearSearchEntities();
          addSearchMarker(lon, lat, Cesium.Color.CYAN);
          setStatus("Box draw: click second corner");
        } else {
          const bbox = {
            west: Math.min(searchBoxStart.lon, lon),
            south: Math.min(searchBoxStart.lat, lat),
            east: Math.max(searchBoxStart.lon, lon),
            north: Math.max(searchBoxStart.lat, lat),
          };
          drawSearchBox(bbox);
          emitSearchGeometry("bbox", bbox);
          searchBoxStart = null;
          searchDrawMode = "none";
          setStatus("Search box ready");
        }
        return;
      }

      if (searchDrawMode === "polygon") {
        searchPolygonPoints.push({ lon: lon, lat: lat });
        searchCursorPoint = null;
        drawSearchPolygonPreview();
        setStatus("Polygon draw: continue points, right-click or Finish to close");
      }

      if (clickedPoints.length === 2) {
        const geodesic = new Cesium.EllipsoidGeodesic(
          Cesium.Cartographic.fromDegrees(clickedPoints[0][0], clickedPoints[0][1]),
          Cesium.Cartographic.fromDegrees(clickedPoints[1][0], clickedPoints[1][1])
        );
        bridge.on_measurement(geodesic.surfaceDistance);
        log("info", "Distance measured (m): " + geodesic.surfaceDistance.toFixed(2));
      }
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

    handler.setInputAction(function (movement) {
      if (searchDrawMode !== "polygon" || searchPolygonPoints.length === 0) {
        return;
      }
      const lonLat = getLonLatFromScreen(movement.endPosition);
      if (!lonLat) {
        return;
      }
      searchCursorPoint = { lon: lonLat.lon, lat: lonLat.lat };
      drawSearchPolygonPreview();
    }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

    handler.setInputAction(function () {
      if (searchDrawMode === "polygon") {
        window.offlineGIS.finishSearchPolygon();
      }
    }, Cesium.ScreenSpaceEventType.RIGHT_CLICK);
  }

  function getLonLatFromScreen(screenPosition) {
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

  function addSearchMarker(lon, lat, color) {
    const entity = viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(lon, lat),
      point: {
        pixelSize: 8,
        color: color || Cesium.Color.CYAN,
      },
    });
    searchEntities.push(entity);
  }

  function clearSearchEntities() {
    while (searchEntities.length > 0) {
      const entity = searchEntities.pop();
      if (entity) viewer.entities.remove(entity);
    }
  }

  function drawSearchBox(bbox) {
    clearSearchEntities();
    const rectangle = Cesium.Rectangle.fromDegrees(bbox.west, bbox.south, bbox.east, bbox.north);
    const entity = viewer.entities.add({
      rectangle: {
        coordinates: rectangle,
        material: Cesium.Color.CYAN.withAlpha(0.18),
        outline: true,
        outlineColor: Cesium.Color.WHITE,
        outlineWidth: 2,
      },
    });
    searchEntities.push(entity);
  }

  function drawSearchPolygonPreview() {
    clearSearchEntities();
    const previewPoints = searchCursorPoint
      ? searchPolygonPoints.concat([searchCursorPoint])
      : searchPolygonPoints.slice();

    searchPolygonPoints.forEach((point) => addSearchMarker(point.lon, point.lat, Cesium.Color.CYAN));
    if (searchCursorPoint) {
      addSearchMarker(searchCursorPoint.lon, searchCursorPoint.lat, Cesium.Color.YELLOW);
    }

    if (previewPoints.length >= 2) {
      const lineEntity = viewer.entities.add({
        polyline: {
          positions: previewPoints.map((p) => Cesium.Cartesian3.fromDegrees(p.lon, p.lat)),
          width: 2.5,
          material: Cesium.Color.CYAN,
        },
      });
      searchEntities.push(lineEntity);
    }

    if (previewPoints.length >= 3) {
      const polygonEntity = viewer.entities.add({
        polygon: {
          hierarchy: previewPoints.map((p) => Cesium.Cartesian3.fromDegrees(p.lon, p.lat)),
          material: Cesium.Color.CYAN.withAlpha(0.2),
          outline: true,
          outlineColor: Cesium.Color.CYAN.withAlpha(0.9),
          perPositionHeight: false,
        },
      });
      searchEntities.push(polygonEntity);
    }
  }

  function finalizeSearchPolygon() {
    if (searchPolygonPoints.length < 3) {
      log("warn", "Polygon draw requires at least 3 points");
      return;
    }
    clearSearchEntities();
    searchCursorPoint = null;
    const hierarchy = searchPolygonPoints.map((p) => Cesium.Cartesian3.fromDegrees(p.lon, p.lat));
    const polygonEntity = viewer.entities.add({
      polygon: {
        hierarchy: hierarchy,
        material: Cesium.Color.fromCssColorString("#3aaed8").withAlpha(0.26),
        outline: true,
        outlineColor: Cesium.Color.fromCssColorString("#f7b267"),
        perPositionHeight: false,
      },
    });
    searchEntities.push(polygonEntity);

    const borderEntity = viewer.entities.add({
      polyline: {
        positions: hierarchy.concat([hierarchy[0]]),
        width: 3,
        material: Cesium.Color.fromCssColorString("#f7b267"),
      },
    });
    searchEntities.push(borderEntity);

    const areaSquareMeters = computePolygonAreaSquareMeters(searchPolygonPoints);
    const center = polygonLabelPosition(searchPolygonPoints);
    if (center && Number.isFinite(areaSquareMeters) && areaSquareMeters > 0) {
      const areaLabel = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(center.lon, center.lat),
        label: {
          text: "Area " + formatArea(areaSquareMeters),
          fillColor: Cesium.Color.WHITE,
          showBackground: true,
          backgroundColor: Cesium.Color.BLACK.withAlpha(0.72),
          pixelOffset: new Cesium.Cartesian2(0, -12),
          scale: 0.95,
        },
      });
      searchEntities.push(areaLabel);
    }

    emitSearchGeometry("polygon", { points: searchPolygonPoints.slice() });
    searchDrawMode = "none";
    setStatus("Search polygon ready");
  }

  function computePolygonAreaSquareMeters(points) {
    if (!Array.isArray(points) || points.length < 3) {
      return 0.0;
    }
    const radius = 6378137.0;
    let sum = 0.0;
    for (let i = 0; i < points.length; i += 1) {
      const current = points[i];
      const next = points[(i + 1) % points.length];
      const lon1 = Cesium.Math.toRadians(current.lon);
      const lon2 = Cesium.Math.toRadians(next.lon);
      const lat1 = Cesium.Math.toRadians(current.lat);
      const lat2 = Cesium.Math.toRadians(next.lat);
      sum += (lon2 - lon1) * (2 + Math.sin(lat1) + Math.sin(lat2));
    }
    return Math.abs(sum) * radius * radius * 0.5;
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
      if (normalized === "3d") {
        focusPreferredRegion3D(0.65);
      } else {
        focusPreferredRegion(0.45);
      }
      syncSceneModeToggle(normalized);
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
    addTileLayer: async function (name, xyzUrl, kind, options) {
      if (!viewer) return;
      await ensureBaseTerrainReady();
      const isDem =
        (options && options.is_dem === true) ||
        String(kind || "").toLowerCase() === "dem" ||
        String(name || "").toLowerCase().includes("dem");
      if (isDem) {
        window.offlineGIS.addDemLayer(name, xyzUrl, options || {});
        return;
      }
      const hadActiveDemContext = Boolean(activeDemContext);
      if (hadActiveDemContext) {
        // Preserve current DEM terrain mesh to allow realistic imagery drape in 3D.
        if (activeDemHillshadeLayer) {
          viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
          activeDemHillshadeLayer = null;
        }
        activeDemContext = null;
        hideDemColorbar();
      } else {
        clearDemTerrainMode();
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
      if (activeImageryLayer) {
        viewer.imageryLayers.remove(activeImageryLayer, false);
        activeImageryLayer = null;
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
      viewer.imageryLayers.raiseToTop(activeImageryLayer);
      activeImageryLayer.alpha = 1.0;
      updateBasemapBlendForCurrentMode();
      setStatus("Layer added: " + name);
      log("info", "Layer added name=" + name + " kind=" + kind + " url=" + providerUrl + " min=" + minLevel + " max=" + maxLevel);
    },
    addDemLayer: function (name, xyzUrl, options) {
      if (!viewer) return;
      setSceneModeInternal("3d");
      setSceneModeControlEnabled(false);
      const normalizedBounds = normalizeBounds(options && options.bounds ? options.bounds : null);
      if (normalizedBounds) {
        setActiveTileBounds(normalizedBounds);
      }
      activeDemContext = {
        name: name,
        xyzUrl: xyzUrl,
        options: options || {},
      };
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
      if (activeDemContext && String(mode || "").toLowerCase() === "2d") {
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
      const layer = activeImageryLayer || viewer.imageryLayers.get(0);
      if (!layer) return;
      layer.brightness = Math.max(0.2, brightness);
      layer.contrast = Math.max(0.1, contrast);
      log("debug", "Set imagery brightness=" + brightness + " contrast=" + contrast);
    },
    rotateCamera: function (degrees) {
      if (!viewer) return;
      viewer.camera.rotateRight(Cesium.Math.toRadians(degrees));
      log("debug", "Rotate camera degrees=" + degrees);
    },
    setPitch: function (degrees) {
      if (!viewer) return;
      const camera = viewer.camera;
      camera.setView({
        destination: camera.position,
        orientation: {
          heading: camera.heading,
          pitch: Cesium.Math.toRadians(degrees),
          roll: camera.roll,
        },
      });
      log("debug", "Set pitch degrees=" + degrees);
    },
    addAnnotation: function (text, lon, lat) {
      if (!viewer) return;
      viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(lon, lat),
        label: {
          text: text,
          fillColor: Cesium.Color.WHITE,
          showBackground: true,
          backgroundColor: Cesium.Color.BLACK.withAlpha(0.7),
          pixelOffset: new Cesium.Cartesian2(0, -18),
        },
      });
      log("info", "Annotation added lon=" + lon + " lat=" + lat);
    },
    setSearchDrawMode: function (mode) {
      searchDrawMode = mode === "box" || mode === "polygon" ? mode : "none";
      searchBoxStart = null;
      searchCursorPoint = null;
      if (searchDrawMode !== "polygon") {
        searchPolygonPoints.length = 0;
      }
      if (searchDrawMode === "none") {
        setStatus("Search draw disabled");
      } else {
        setStatus("Search draw mode: " + searchDrawMode);
      }
    },
    finishSearchPolygon: function () {
      finalizeSearchPolygon();
    },
    clearSearchGeometry: function () {
      searchDrawMode = "none";
      searchBoxStart = null;
      searchCursorPoint = null;
      searchPolygonPoints.length = 0;
      clearSearchEntities();
      emitSearchGeometry("none", {});
      setStatus("Search geometry cleared");
    },
  };

  document.addEventListener("DOMContentLoaded", initBridge);
})();
