(function () {
  let bridge = null;
  let viewer = null;
  let activeImageryLayer = null;
  let activeDemHillshadeLayer = null;
  let activeDemContext = null;
  let globalBasemapLayer = null;
  const clickedPoints = [];
  const tileErrorSeen = new Set();
  const layerErrorCounts = new Map();
  const TERRAIN_SAMPLE_SIZE = 33;
  const DEM_MAX_TERRAIN_LEVEL = 14;
  const MAX_TERRAIN_CACHE_ITEMS = 512;
  const terrainTileCache = new Map();
  const demVisual = {
    exaggeration: 1.5,
    hillshadeAlpha: 0.75,
    azimuth: 45,
    altitude: 45,
  };
  let terrainDecodeCanvas = null;
  let terrainDecodeContext = null;

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

  function setScaleLabel(text, widthPx, detailText) {
    const label = document.getElementById("scaleLabel");
    const bar = document.getElementById("scaleBar");
    const detail = document.getElementById("scaleDetail");
    if (label) label.textContent = text;
    if (bar && Number.isFinite(widthPx)) {
      bar.style.width = Math.max(24, Math.min(140, Math.round(widthPx))) + "px";
    }
    if (detail) detail.textContent = detailText || "1 px = n/a";
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
    viewer.terrainProvider = new Cesium.EllipsoidTerrainProvider();
    viewer.scene.verticalExaggeration = 1.0;
  }

  function applyDemSceneSettings() {
    if (!viewer) return;
    viewer.scene.verticalExaggeration = Math.max(0.1, demVisual.exaggeration);
    viewer.scene.globe.enableLighting = true;
    viewer.scene.globe.depthTestAgainstTerrain = true;
    viewer.scene.globe.preloadAncestors = true;
    viewer.scene.globe.preloadSiblings = false;
    viewer.scene.globe.maximumScreenSpaceError = 2.5;
    viewer.scene.globe.showSkirts = true;
    viewer.scene.globe.tileCacheSize = 300;
    viewer.shadows = true;
  }

  function tuneCameraController() {
    if (!viewer) return;
    const controller = viewer.scene.screenSpaceCameraController;
    controller.enableCollisionDetection = true;
    controller.inertiaSpin = 0.88;
    controller.inertiaTranslate = 0.88;
    controller.inertiaZoom = 0.72;
    controller.maximumMovementRatio = 0.09;
    controller.minimumZoomDistance = 10.0;
    controller.maximumZoomDistance = 40000000.0;
    controller.maximumTiltAngle = Cesium.Math.toRadians(89.0);
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
    return new Cesium.CustomHeightmapTerrainProvider({
      width: TERRAIN_SAMPLE_SIZE,
      height: TERRAIN_SAMPLE_SIZE,
      tilingScheme: tilingScheme,
      callback: async function (x, y, level) {
        if (demRectangle) {
          const tileRectangle = tilingScheme.tileXYToRectangle(x, y, level);
          const overlap = Cesium.Rectangle.intersection(tileRectangle, demRectangle, new Cesium.Rectangle());
          if (!overlap) {
            return createFlatHeightmap(decodeConfig.minHeight);
          }
        }
        try {
          return await requestTerrainTileWithFallback(terrainUrlTemplate, x, y, level, decodeConfig);
        } catch (error) {
          log("warn", "DEM terrain fetch failed: " + String(error));
          return createFlatHeightmap(decodeConfig.minHeight);
        }
      },
    });
  }

  function updateScaleWidget() {
    if (!viewer) return;
    const canvas = viewer.scene.canvas;
    const y = 56;
    const pixelSpan = 120;
    const centerX = canvas.clientWidth * 0.5;
    const leftX = centerX - pixelSpan * 0.5;
    const rightX = centerX + pixelSpan * 0.5;
    const leftCartesian = viewer.camera.pickEllipsoid(new Cesium.Cartesian2(leftX, y), viewer.scene.globe.ellipsoid);
    const rightCartesian = viewer.camera.pickEllipsoid(new Cesium.Cartesian2(rightX, y), viewer.scene.globe.ellipsoid);
    if (!leftCartesian || !rightCartesian) {
      setScaleLabel("Scale", 24, "1 px = n/a");
      return;
    }
    const left = Cesium.Cartographic.fromCartesian(leftCartesian);
    const right = Cesium.Cartographic.fromCartesian(rightCartesian);
    const geodesic = new Cesium.EllipsoidGeodesic(left, right);
    const distance = geodesic.surfaceDistance;
    if (!Number.isFinite(distance) || distance <= 0) {
      setScaleLabel("Scale", 24, "1 px = n/a");
      return;
    }
    const magnitude = Math.pow(10, Math.floor(Math.log10(distance)));
    const normalized = distance / magnitude;
    const step = normalized >= 5 ? 5 : normalized >= 2 ? 2 : 1;
    const niceDistance = step * magnitude;
    const barWidth = (niceDistance / distance) * pixelSpan;
    const text = niceDistance >= 1000 ? `${(niceDistance / 1000).toFixed(2)} km` : `${Math.round(niceDistance)} m`;
    const metersPerPixel = distance / pixelSpan;
    const cmPerPixel = metersPerPixel * 100.0;
    const detail = cmPerPixel >= 100
      ? `1 px = ${(cmPerPixel / 100).toFixed(2)} m (${Math.round(cmPerPixel)} cm)`
      : `1 px = ${cmPerPixel.toFixed(2)} cm`;
    setScaleLabel(text, barWidth, detail);
  }

  function applyDemLayer() {
    if (!viewer || !activeDemContext) return;
    const bounds = activeDemContext.options && activeDemContext.options.bounds ? activeDemContext.options.bounds : null;
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

    if (activeImageryLayer) {
      viewer.imageryLayers.remove(activeImageryLayer, false);
      activeImageryLayer = null;
    }
    if (activeDemHillshadeLayer) {
      viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
      activeDemHillshadeLayer = null;
    }

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
    activeDemHillshadeLayer.alpha = Math.max(0.0, Math.min(1.0, demVisual.hillshadeAlpha));
    activeImageryLayer = activeDemHillshadeLayer;

    viewer.terrainProvider = buildDemTerrainProvider(terrainRgbUrl, bounds, decodeConfig);
    applyDemSceneSettings();
    viewer.imageryLayers.raiseToTop(activeDemHillshadeLayer);
    if (globalBasemapLayer) {
      globalBasemapLayer.alpha = 0.35;
    }
    setStatus("DEM terrain active: " + activeDemContext.name);
    log("info", "DEM terrain activated name=" + activeDemContext.name + " url=" + terrainRgbUrl);
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
    const naturalEarth = new Cesium.UrlTemplateImageryProvider({
      url: Cesium.buildModuleUrl("Assets/Textures/NaturalEarthII/{z}/{x}/{y}.jpg"),
      tilingScheme: new Cesium.GeographicTilingScheme(),
      maximumLevel: 2,
      enablePickFeatures: false,
      credit: "NaturalEarthII (offline)",
    });
    viewer = new Cesium.Viewer("cesiumContainer", {
      imageryProvider: naturalEarth,
      baseLayerPicker: false,
      geocoder: false,
      navigationHelpButton: false,
      timeline: false,
      animation: false,
      terrainProvider: new Cesium.EllipsoidTerrainProvider(),
    });
    viewer.scene.globe.baseColor = Cesium.Color.BLACK;
    tuneCameraController();
    window.addEventListener("error", function (event) {
      log("error", "Window error: " + (event && event.message ? event.message : "unknown"));
    });
    window.addEventListener("unhandledrejection", function (event) {
      const reason = event && event.reason ? String(event.reason) : "unknown";
      log("error", "Unhandled promise rejection: " + reason);
    });
    tryAttachPackagedBasemap();
    viewer.imageryLayers.layerAdded.addEventListener(function (_layer, index) {
      log("info", "Imagery layer added at index " + index);
    });
    viewer.scene.postRender.addEventListener(updateScaleWidget);
    wireClickHandlers();
    setStatus("Offline Cesium initialized.");
    log("info", "Viewer initialized with offline NaturalEarth basemap");
  }

  function tryAttachPackagedBasemap() {
    const img = new Image();
    img.onload = function () {
      if (!viewer) return;
      const provider = new Cesium.SingleTileImageryProvider({
        url: "./basemap/world.jpg",
        rectangle: Cesium.Rectangle.fromDegrees(-180.0, -90.0, 180.0, 90.0),
      });
      globalBasemapLayer = viewer.imageryLayers.addImageryProvider(provider, 0);
      log("info", "Loaded packaged global basemap ./basemap/world.jpg");
    };
    img.onerror = function () {
      log("debug", "Packaged basemap missing; using NaturalEarthII fallback");
    };
    img.src = "./basemap/world.jpg";
  }

  function wireClickHandlers() {
    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction(function (movement) {
      const cartesian = viewer.camera.pickEllipsoid(
        movement.position,
        viewer.scene.globe.ellipsoid
      );
      if (!cartesian) return;
      const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
      const lon = Cesium.Math.toDegrees(cartographic.longitude);
      const lat = Cesium.Math.toDegrees(cartographic.latitude);
      clickedPoints.push([lon, lat]);
      if (clickedPoints.length > 2) clickedPoints.shift();

      viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(lon, lat),
        point: { pixelSize: 7, color: Cesium.Color.ORANGE },
      });
      bridge.on_map_click(lon, lat);
      log("debug", "Map click lon=" + lon.toFixed(6) + " lat=" + lat.toFixed(6));

      if (clickedPoints.length === 2) {
        const geodesic = new Cesium.EllipsoidGeodesic(
          Cesium.Cartographic.fromDegrees(clickedPoints[0][0], clickedPoints[0][1]),
          Cesium.Cartographic.fromDegrees(clickedPoints[1][0], clickedPoints[1][1])
        );
        bridge.on_measurement(geodesic.surfaceDistance);
        log("info", "Distance measured (m): " + geodesic.surfaceDistance.toFixed(2));
      }
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
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
      const rect = Cesium.Rectangle.fromDegrees(west, south, east, north);
      viewer.camera.flyTo({
        destination: rect,
        duration: 2.2,
      });
      log("info", "Fly-to bounds west=" + west + " south=" + south + " east=" + east + " north=" + north);
    },
    addTileLayer: function (name, xyzUrl, kind, options) {
      if (!viewer) return;
      const isDem =
        (options && options.is_dem === true) ||
        String(kind || "").toLowerCase() === "dem" ||
        String(name || "").toLowerCase().includes("dem");
      if (isDem) {
        window.offlineGIS.addDemLayer(name, xyzUrl, options || {});
        return;
      }
      clearDemTerrainMode();
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
      let rectangle;
      if (bounds && Number.isFinite(bounds.west) && Number.isFinite(bounds.south) && Number.isFinite(bounds.east) && Number.isFinite(bounds.north)) {
        rectangle = Cesium.Rectangle.fromDegrees(bounds.west, bounds.south, bounds.east, bounds.north);
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
      if (globalBasemapLayer) {
        globalBasemapLayer.alpha = 0.75;
      }
      setStatus("Layer added: " + name);
      log("info", "Layer added name=" + name + " kind=" + kind + " url=" + providerUrl + " min=" + minLevel + " max=" + maxLevel);
    },
    addDemLayer: function (name, xyzUrl, options) {
      if (!viewer) return;
      activeDemContext = {
        name: name,
        xyzUrl: xyzUrl,
        options: options || {},
      };
      applyDemLayer();
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
  };

  document.addEventListener("DOMContentLoaded", initBridge);
})();
