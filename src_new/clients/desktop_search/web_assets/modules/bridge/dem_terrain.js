  // SECTION: DEM Terrain Rendering  →  future: modules/dem.js
  // Functions: OfflineCustomTerrainProvider (constructor + prototype),
  //   applyDemLayer, setDemColorMode, clearDemTerrainMode,
  //   updateDemColorbar, hideDemColorbar, resolveDemColorbarGradient,
  //   parseDemHeightRange, applyDemSceneSettings
  // ═══════════════════════════════════════════════════════════════════════════

// TODO: Refactor this function to reduce its Cognitive Complexity from 113 to the 15 allowed.
  function applyDemLayer() {
    if (!viewer || !activeDemContext) return;
    
    log("info", "DEM_RENDER: ========== applyDemLayer START ==========");
    log("info", "DEM_RENDER: Context: " + JSON.stringify({
      name: activeDemContext.name,
      layerKey: activeDemContext.layerKey,
      visible: activeDemContext.visible,
      xyzUrl: activeDemContext.xyzUrl,
      hasBounds: !!(activeDemContext.options && activeDemContext.options.bounds),
      bounds: activeDemContext.options && activeDemContext.options.bounds
    }));
    
    const bounds = activeDemContext.options && activeDemContext.options.bounds ? activeDemContext.options.bounds : null;
    const rasterQuery = activeDemContext.options && activeDemContext.options.query ? activeDemContext.options.query : {};
    const queryAlgorithm = String(rasterQuery.algorithm || "").toLowerCase();
    const queryColorMode = String(rasterQuery.colormap_name || "terrain").toLowerCase();
    // S3358: Extract nested ternary into sequential statements
    let currentMode;
    if (queryAlgorithm === "slope") {
      currentMode = "slope";
    } else if (queryAlgorithm === "aspect") {
      currentMode = "aspect";
    } else {
      currentMode = queryColorMode;
    }
    demVisual.colorMode = currentMode;
    activeDemContext.colorMode = currentMode;

    // Snapshot the original server rescale on FIRST load (before any user color-mode changes).
    // When user returns to gray/terrain we restore this so colors exactly match the colorbar.
    if (!_demOriginalRescale && typeof rasterQuery.rescale === "string" && rasterQuery.rescale.includes(",")) {
      _demOriginalRescale = rasterQuery.rescale;
      log("info", "DEM_RENDER: Captured original rescale range: " + _demOriginalRescale);
    }
    const minLevel = activeDemContext.options && Number.isInteger(activeDemContext.options.minzoom) ? activeDemContext.options.minzoom : 0;
    const maxLevelRaw = activeDemContext.options && Number.isInteger(activeDemContext.options.maxzoom) ? activeDemContext.options.maxzoom : 19;
    const imageryMaxLevel = Math.max(minLevel, maxLevelRaw);
    const terrainMaxLevel = Math.max(minLevel, Math.min(maxLevelRaw, DEM_MAX_TERRAIN_LEVEL));
    const rectangle = createRectangle(bounds);
    
    log("info", "DEM_RENDER: Layer parameters" +
        " minLevel=" + minLevel +
        " maxLevel=" + maxLevelRaw +
        " imageryMaxLevel=" + imageryMaxLevel +
        " terrainMaxLevel=" + terrainMaxLevel +
        " bounds=" + JSON.stringify(bounds) +
        " rectangle=" + (rectangle ? JSON.stringify({
          west: Cesium.Math.toDegrees(rectangle.west),
          south: Cesium.Math.toDegrees(rectangle.south),
          east: Cesium.Math.toDegrees(rectangle.east),
          north: Cesium.Math.toDegrees(rectangle.north)
        }) : "null"));
    
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
    activeDemContext.colorMode = String(demVisual.colorMode || activeDemContext.colorMode || "terrain").toLowerCase();
    layerVisibilityState.set(activeDemContext.layerKey, demVisible);

    // ── 3D DEM Rendering Pipeline ──────────────────────────────────────────
    // Build the terrain provider ONLY when the DEM is first loaded or the URL changes.
    // Never rebuild for exaggeration or color mode — those are handled in-place.
    const terrainQuery = {
      ...rasterQuery,
      resampling: "bilinear",
    };
    delete terrainQuery.colormap_name;
    delete terrainQuery.colormap;
    delete terrainQuery.algorithm;
    const terrainUrl = buildUrlWithQuery(activeDemContext.xyzUrl, terrainQuery);
    const terrainSignatureChanged = activeDemTerrainSignature !== activeDemContext.layerKey;

    log("info", "DEM_RENDER: Terrain provider check" +
        " signatureChanged=" + terrainSignatureChanged +
        " hasProvider=" + !!activeDemTerrainProvider +
        " currentSignature=" + activeDemTerrainSignature +
        " newSignature=" + activeDemContext.layerKey);

    if (terrainSignatureChanged || !activeDemTerrainProvider) {
      log("info", "DEM_RENDER: Building NEW terrain provider for key=" + activeDemContext.layerKey);
      const customTerrainProvider = new OfflineCustomTerrainProvider({
        url: terrainUrl,
        minLevel: minLevel,
        maxLevel: terrainMaxLevel,
        options: activeDemContext.options,
      });
      activeDemTerrainProvider = customTerrainProvider;
      activeDemTerrainSignature = activeDemContext.layerKey;
      log("info", "DEM_RENDER: Terrain provider built successfully" +
          " ready=" + customTerrainProvider.ready +
          " minLevel=" + minLevel +
          " maxLevel=" + terrainMaxLevel);

      // S2392: Declare providerToUse at outer scope to avoid binding outside its block
      let providerToUse;
      if (demVisible) {
        log("info", "DEM_RENDER: Swapping to new terrain provider (DEM visible)");
        providerToUse = (viewer.scene.mode === Cesium.SceneMode.SCENE2D)
          ? new Cesium.EllipsoidTerrainProvider()
          : customTerrainProvider;
        _swapTerrainProviderLocked(providerToUse);
        log("info", "DEM_RENDER: Terrain provider swap complete, current provider type=" + 
            (viewer.terrainProvider === providerToUse ? (viewer.scene.mode === Cesium.SceneMode.SCENE2D ? "ELLIPSOID" : "CUSTOM") : "OTHER"));
      }
    } else if (demVisible) {
      // Re-show after hide — reuse existing provider, no rebuild
      const providerToUse = (viewer.scene.mode === Cesium.SceneMode.SCENE2D)
        ? new Cesium.EllipsoidTerrainProvider()
        : activeDemTerrainProvider;
      if (viewer.terrainProvider !== providerToUse) {
        log("info", "DEM_RENDER: Reusing existing terrain provider (was hidden, now visible)");
        _swapTerrainProviderLocked(providerToUse);
        log("info", "DEM_RENDER: Terrain provider reactivated");
      } else {
        log("info", "DEM_RENDER: Terrain provider already active, no swap needed");
      }
    }

    log("info", "DEM_RENDER: Current terrain provider: " + 
        (viewer.terrainProvider === activeDemTerrainProvider ? "CUSTOM_DEM" : "ELLIPSOID"));
    // ───────────────────────────────────────────────────────────────────────


    // Always clean up hillshade when drape URL changes to ensure proper layer rebuild
    const drapeUrlChanged = activeDemDrapeUrl !== drapeUrl;
    if (drapeUrlChanged && activeDemHillshadeLayer) {
      viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
      
      // CRITICAL FIX: Remove old DEM hillshade layer from managedImageryLayers map
      if (activeDemContext?.layerKey) {
        managedImageryLayers.delete(activeDemContext.layerKey + ":hillshade");
      }
      
      activeDemHillshadeLayer = null;
      activeDemHillshadeUrl = null;
    }

    if (!activeDemDrapeLayer || drapeUrlChanged) {
      if (activeDemDrapeLayer) {
        viewer.imageryLayers.remove(activeDemDrapeLayer, false);
        activeDemDrapeLayer = null;
      }
      // CRITICAL: If there is an existing 2D drape layer in managedImageryLayers for this DEM, remove it first to avoid duplicates
      if (activeDemContext?.layerKey) {
        const existing2DLayer = managedImageryLayers.get(activeDemContext.layerKey);
        if (existing2DLayer && existing2DLayer !== activeDemDrapeLayer) {
          viewer.imageryLayers.remove(existing2DLayer, true);
        }
        managedImageryLayers.delete(activeDemContext.layerKey);
      }
      const drapeProvider = new Cesium.UrlTemplateImageryProvider({
        url: drapeUrl,
        maximumLevel: imageryMaxLevel,
        minimumLevel: minLevel,
        tilingScheme: new Cesium.WebMercatorTilingScheme(),
        enablePickFeatures: false,
        rectangle: rectangle,
      });
      
      log("info", "DEM_RENDER: Creating drape provider" +
          " url=" + drapeUrl +
          " minLevel=" + minLevel +
          " maxLevel=" + imageryMaxLevel +
          " rectangle=" + (rectangle ? JSON.stringify({
            west: Cesium.Math.toDegrees(rectangle.west),
            south: Cesium.Math.toDegrees(rectangle.south),
            east: Cesium.Math.toDegrees(rectangle.east),
            north: Cesium.Math.toDegrees(rectangle.north)
          }) : "null"));
      
      attachTileErrorHandler(drapeProvider, activeDemContext.name + "-drape");
      
      log("info", "DEM_RENDER: Adding drape layer to viewer");
      activeDemDrapeLayer = viewer.imageryLayers.addImageryProvider(drapeProvider);
      activeDemDrapeLayer.preloadAncestorTiles = true;
      if (window.Cesium && window.Cesium.TextureMinificationFilter && window.Cesium.TextureMagnificationFilter) {
        activeDemDrapeLayer.minificationFilter = window.Cesium.TextureMinificationFilter.NEAREST;
        activeDemDrapeLayer.magnificationFilter = window.Cesium.TextureMagnificationFilter.NEAREST;
      }
      activeDemDrapeLayer.alpha = 1.0;
      activeDemDrapeLayer.show = demVisible;
      activeDemDrapeUrl = drapeUrl;
      
      // CRITICAL FIX: Tag DEM drape layer with key for reordering functionality
      activeDemDrapeLayer._layerKey = activeDemContext.layerKey;
      activeDemDrapeLayer._layerName = activeDemContext.name;
      
      // CRITICAL FIX: Add DEM drape layer to managedImageryLayers for reordering
      managedImageryLayers.set(activeDemContext.layerKey, activeDemDrapeLayer);
      
      log("info", "DEM_RENDER: Drape layer added" +
          " layerIndex=" + viewer.imageryLayers.indexOf(activeDemDrapeLayer) +
          " alpha=" + activeDemDrapeLayer.alpha +
          " show=" + activeDemDrapeLayer.show +
          " totalLayers=" + viewer.imageryLayers.length);
      
      // CRITICAL: Force immediate tile loading by requesting render
      viewer.scene.requestRender();
      
      // Log all imagery layers for debugging
      log("info", "DEM_RENDER: All imagery layers:");
      for (let i = 0; i < viewer.imageryLayers.length; i++) {
        const layer = viewer.imageryLayers.get(i);
        log("info", "  Layer " + i + ": alpha=" + layer.alpha + " show=" + layer.show + 
            " ready=" + (layer.imageryProvider && layer.imageryProvider.ready));
      }
    }

    const clampedHillshadeAlpha = Math.max(0.0, Math.min(1.0, demVisual.hillshadeAlpha));
    log("info", "DEM_RENDER: HILLSHADE DEBUG: desiredAlpha=" + demVisual.hillshadeAlpha + " clamped=" + clampedHillshadeAlpha + " demVisible=" + demVisible);
    
    // Always create the hillshade layer, even if alpha is 0.
    // This allows the slider to update alpha in real-time without needing a full DEM rebuild.
    if (activeDemHillshadeLayer && activeDemHillshadeUrl !== hillshadeUrl) {
      log("info", "DEM_RENDER: HILLSHADE DEBUG: URL changed, removing old layer");
      viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
      
      // CRITICAL FIX: Remove old DEM hillshade layer from managedImageryLayers map
      if (activeDemContext?.layerKey) {
        managedImageryLayers.delete(activeDemContext.layerKey + ":hillshade");
      }
      
      activeDemHillshadeLayer = null;
      activeDemHillshadeUrl = null;
    }
    if (!activeDemHillshadeLayer) {
      log("info", "DEM_RENDER: HILLSHADE DEBUG: Creating NEW hillshade layer url=" + hillshadeUrl.substring(0, 80) + "...");
      const hillshadeProvider = new Cesium.UrlTemplateImageryProvider({
        url: hillshadeUrl,
        maximumLevel: imageryMaxLevel,
        minimumLevel: minLevel,
        tilingScheme: new Cesium.WebMercatorTilingScheme(),
        enablePickFeatures: false,
        rectangle: rectangle,
      });
      log("info", "DEM_RENDER: HILLSHADE DEBUG: UrlTemplateImageryProvider created, ready=" + hillshadeProvider.ready);
      attachTileErrorHandler(hillshadeProvider, activeDemContext.name + "-hillshade");
      activeDemHillshadeLayer = viewer.imageryLayers.addImageryProvider(hillshadeProvider);
      log("info", "DEM_RENDER: HILLSHADE DEBUG: Layer added to viewer, index=" + viewer.imageryLayers.indexOf(activeDemHillshadeLayer) + " totalLayers=" + viewer.imageryLayers.length);
      activeDemHillshadeLayer.preloadAncestorTiles = true;
      if (window.Cesium && window.Cesium.TextureMinificationFilter && window.Cesium.TextureMagnificationFilter) {
        activeDemHillshadeLayer.minificationFilter = window.Cesium.TextureMinificationFilter.NEAREST;
        activeDemHillshadeLayer.magnificationFilter = window.Cesium.TextureMagnificationFilter.NEAREST;
      }
      activeDemHillshadeUrl = hillshadeUrl;
      
      // CRITICAL FIX: Tag DEM hillshade layer with key for reordering functionality
      // Use a different key suffix to distinguish from drape layer
      const hillshadeKey = activeDemContext.layerKey + ":hillshade";
      activeDemHillshadeLayer._layerKey = hillshadeKey;
      activeDemHillshadeLayer._layerName = activeDemContext.name + " (Hillshade)";
      
      // CRITICAL FIX: Add DEM hillshade layer to managedImageryLayers for reordering
      managedImageryLayers.set(hillshadeKey, activeDemHillshadeLayer);
      
      log("info", "DEM_RENDER: HILLSHADE DEBUG: Layer fully configured, imageryProvider.ready=" + (activeDemHillshadeLayer.imageryProvider ? activeDemHillshadeLayer.imageryProvider.ready : "N/A"));
      log("info", "DEM_RENDER: Hillshade layer added at index " + viewer.imageryLayers.indexOf(activeDemHillshadeLayer));
    } else {
      log("info", "DEM_RENDER: HILLSHADE DEBUG: Reusing existing layer, NOT creating new one");
    }
    log("info", "DEM_RENDER: HILLSHADE DEBUG: BEFORE set alpha=" + activeDemHillshadeLayer.alpha + " show=" + activeDemHillshadeLayer.show);
    activeDemHillshadeLayer.alpha = clampedHillshadeAlpha;
    activeDemHillshadeLayer.show = demVisible;
    log("info", "DEM_RENDER: HILLSHADE DEBUG: AFTER set alpha=" + activeDemHillshadeLayer.alpha + " show=" + activeDemHillshadeLayer.show);

    applyDemSceneSettings();

    // Keep the globe/basemap visible underneath the DEM
    if (defaultEarthLayer) {
      defaultEarthLayer.show = true;
    }
    if (viewer?.scene && viewer.scene.globe) {
      viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#1a2535");
    }
    if (typeof comparatorViewers !== "undefined" && Array.isArray(comparatorViewers)) {
      comparatorViewers.forEach(v => {
        if (v?.__defaultEarthLayer) v.__defaultEarthLayer.show = true;
        if (v?.scene && v.scene.globe) v.scene.globe.baseColor = Cesium.Color.fromCssColorString("#1a2535");
      });
    }
    
    // CRITICAL FIX: Only ensure basemap is at bottom, don't force other layer positions
    // This allows user reordering to work properly without conflicts
    log("info", "DEM_RENDER: Ensuring basemap at bottom (preserving user layer order)");
    
    // Step 1: Ensure basemap is at the very bottom (index 0) - this is essential
    if (osmBasemapLayer?.show && viewer.imageryLayers.indexOf(osmBasemapLayer) >= 0) {
      viewer.imageryLayers.lowerToBottom(osmBasemapLayer);
      log("info", "DEM_RENDER: OSM basemap at index 0 (bottom)");
    } else if (defaultEarthLayer && viewer.imageryLayers.indexOf(defaultEarthLayer) >= 0) {
      viewer.imageryLayers.lowerToBottom(defaultEarthLayer);
      log("info", "DEM_RENDER: Default Earth layer at index 0 (bottom)");
    }
    
    // REMOVED: Automatic layer stacking that conflicts with user reordering
    // The reorderLayersEventDriven() function now handles all layer positioning
    // This prevents the "dusky" appearance and layer visibility issues
    
    // Log final layer stack for debugging
    log("info", "DEM_RENDER: Current layer stack (bottom to top):");
    for (let i = 0; i < viewer.imageryLayers.length; i++) {
      const layer = viewer.imageryLayers.get(i);
      const layerType = (layer === defaultEarthLayer) ? "Default-Earth" :
                       (layer === osmBasemapLayer) ? "OSM" : 
                       (layer === activeDemDrapeLayer) ? "DEM-drape" :
                       (layer === activeDemHillshadeLayer) ? "DEM-hillshade" :
                       (managedImageryLayers.has(layer)) ? "RGB-imagery" : "unknown";
      log("info", "  [" + i + "] " + layerType + ": alpha=" + layer.alpha.toFixed(2) + 
          " show=" + layer.show + " ready=" + (layer.imageryProvider && layer.imageryProvider.ready));
    }
    
    // Single render request (request-render mode will handle subsequent renders)
    viewer.scene.requestRender();
    
    log("debug", "DEM layer stack: hillshade=" + (activeDemHillshadeLayer ? "yes" : "no") + " drape=" + (activeDemDrapeLayer ? "yes" : "no") + " managed=" + managedImageryLayers.size);
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
    
    log("info", "DEM_RENDER: ========== applyDemLayer END ==========");
    
    // BUG-FIX: Do NOT auto-focus here. Python calls focusBoundsWithPadding after ALL layers
    // load (DEM + imagery), giving one smooth fly-to with tiles visible. An internal
    // setTimeout(focusBounds, 200) inside applyDemLayer raced with the Python fly-to,
    // causing black-screen flicker and erratic camera jumps.
    log("info", "DEM_RENDER: Skipping internal auto-focus — Python controls single fly-to after all layers load.");
    
    logLayerStack();
    if (comparatorModeEnabled) {
      refreshComparatorLayers();
    }
    
    // CRITICAL FIX: Ensure layer display order is reapplied after any DEM rebuild
    // to maintain sync with the user's UI list order.
    reapplyLayerOrderIfKnown();
    
    // CRITICAL FIX: Mark tile loading complete after DEM layer is fully rendered
    if (typeof emitLoadingProgress === "function") {
      emitLoadingProgress(100, "Complete");
    }
    if (typeof _tileLoadingActive !== "undefined") {
      _tileLoadingActive = false;
    }

    // Clean up existing DEM boundary wall and pedestal if they exist
    if (window._demBoundaryWallEntity) {
      viewer.entities.remove(window._demBoundaryWallEntity);
      window._demBoundaryWallEntity = null;
    }
    if (window._demPedestalEntity) {
      viewer.entities.remove(window._demPedestalEntity);
      window._demPedestalEntity = null;
    }

    requestSceneRender();
  }

  // GPU-adaptive decode concurrency: set after GPU detection in initViewer,
  // fallback 1 for safety (Intel gets 1, NVIDIA gets 4).
  let MAX_CONCURRENT_TERRAIN_DECODES = 1;
  let activeTerrainDecodes = 0;
  const terrainDecodeQueue = [];
  const terrainDecodeCanvas = document.createElement("canvas");
  terrainDecodeCanvas.width = TERRAIN_SAMPLE_SIZE;
  terrainDecodeCanvas.height = TERRAIN_SAMPLE_SIZE;
  const terrainDecodeCtx = terrainDecodeCanvas.getContext("2d", { willReadFrequently: true });

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

  class TerrainDecodeWorkerPool {
    constructor() {
      this.workers = [];
      this.activeWorkerIdx = 0;
      this.pendingRequests = new Map();
      this.nextRequestId = 1;
      this.supported = (typeof Worker !== 'undefined' && typeof OffscreenCanvas !== 'undefined');
      
      if (this.supported) {
        const workerCode = `
          self.onmessage = async function(e) {
            const { id, blob, rMin, span, W, H, tileRect, datasetBounds } = e.data;
            try {
              const img = await createImageBitmap(blob);
              const imgW = img.width || 256;
              const imgH = img.height || 256;
              const canvas = new OffscreenCanvas(imgW, imgH);
              const ctx = canvas.getContext('2d');
              ctx.drawImage(img, 0, 0, imgW, imgH);
              const imgData = ctx.getImageData(0, 0, imgW, imgH);
              const data = imgData.data;
              
              const output = new Float32Array(W * H);
              
              // Hard-boundary clipping: pixels outside the dataset bounds get height=0,
              // pixels inside get their full decoded height with NO tapering/blending.
              // A gradual taper (previous approach) creates an artificial elevation ramp
              // that looks like an abrupt wall when zooming — removing it entirely makes
              // edges clean and zoom-level-agnostic.
              const hasBoundsClip = !!(tileRect && datasetBounds);

              for (let r = 0; r < H; r++) {
                const srcY = Math.min(imgH - 1, Math.round(r * (imgH - 1) / (H - 1)));
                let lat = 0;
                if (hasBoundsClip) {
                  lat = tileRect.north - (r / (H - 1)) * (tileRect.north - tileRect.south);
                }

                for (let c = 0; c < W; c++) {
                  const srcX = Math.min(imgW - 1, Math.round(c * (imgW - 1) / (W - 1)));
                  const srcIdx = srcY * imgW + srcX;
                  const alpha = data[srcIdx * 4 + 3];
                  if (alpha > 0) {
                    let height = rMin + (data[srcIdx * 4] / 255.0) * span;
                    if (alpha < 255) {
                      height *= (alpha / 255.0);
                    }
                    if (hasBoundsClip) {
                      const lon = tileRect.west + (c / (W - 1)) * (tileRect.east - tileRect.west);
                      if (lon < datasetBounds.west || lon > datasetBounds.east ||
                          lat < datasetBounds.south || lat > datasetBounds.north) {
                        output[r * W + c] = 0.0;
                        continue;
                      }
                    }
                    output[r * W + c] = height;
                  } else {
                    output[r * W + c] = 0.0;
                  }
                }
              }
              
              self.postMessage({ id, success: true, buffer: output }, [output.buffer]);
            } catch (err) {
              self.postMessage({ id, success: false, error: err.message });
            }
          };
        `;
        
        try {
          const blobUrl = URL.createObjectURL(new Blob([workerCode], { type: "application/javascript" }));
          const numWorkers = Math.max(2, Math.min(4, navigator.hardwareConcurrency || 2));
          for (let i = 0; i < numWorkers; i++) {
            const worker = new Worker(blobUrl);
            worker.onmessage = (e) => {
              const { id, success, buffer, error } = e.data;
              const promiseHandlers = this.pendingRequests.get(id);
              if (promiseHandlers) {
                this.pendingRequests.delete(id);
                if (success) {
                  promiseHandlers.resolve(buffer);
                } else {
                  promiseHandlers.reject(new Error(error));
                }
              }
            };
            worker.onerror = (err) => {
              console.error("Terrain worker error", err);
            };
            this.workers.push(worker);
          }
          log("info", "TerrainDecodeWorkerPool: Initialized with " + numWorkers + " workers");
        } catch (e) {
          log("warn", "TerrainDecodeWorkerPool: Worker creation failed, falling back to main-thread: " + e.message);
          this.supported = false;
        }
      }
    }
    
    decode(blob, rMin, span, W, H, tileRect, datasetBounds) {
      if (!this.supported || this.workers.length === 0) {
        return Promise.reject(new Error("Worker pool not supported or initialized"));
      }
      
      return new Promise((resolve, reject) => {
        const id = this.nextRequestId++;
        this.pendingRequests.set(id, { resolve, reject });
        
        const worker = this.workers[this.activeWorkerIdx];
        this.activeWorkerIdx = (this.activeWorkerIdx + 1) % this.workers.length;
        
        worker.postMessage({
          id,
          blob,
          rMin,
          span,
          W,
          H,
          tileRect: tileRect || null,
          datasetBounds: datasetBounds || null
        });
      });
    }
  }
  
  const terrainDecodeWorkerPool = new TerrainDecodeWorkerPool();

  function OfflineCustomTerrainProvider(options) {
    this.tilingScheme = new Cesium.WebMercatorTilingScheme();
    this.hasWaterMask = false;
    this.hasVertexNormals = false;
    this.ready = true;
    this.readyPromise = Cesium.when.resolve(true);
    this.errorEvent = new Cesium.Event();
    
    this._url = options.url;
    this._min = Number.isInteger(options.minLevel) ? options.minLevel : 0;
    this._max = Number.isInteger(options.maxLevel) ? options.maxLevel : DEM_MAX_TERRAIN_LEVEL;
    this._rangeMin = 0;
    this._rangeMax = 0;

    // Cache decoded terrain heightmaps to avoid redundant decodes/requests
    this._tileCache = new Map();
    this._maxCacheSize = 1000;

    // Mock availability to satisfy Cesium's internal requirements (e.g. sampleTerrainMostDetailed)
    const self = this;
    this.availability = {
      computeMaximumLevelAtPosition: function(position) {
        return self._max;
      }
    };
    
    if (options.options?.query?.rescale) {
      const parts = String(options.options.query.rescale).split(",");
      if (parts.length === 2) {
        this._rangeMin = parseFloat(parts[0]);
        this._rangeMax = parseFloat(parts[1]);
      }
    }
    
    this._bounds = (options.options?.bounds) ? normalizeBounds(options.options.bounds) : null;
    if (this._bounds) {
      try {
        this._boundsRadian = Cesium.Rectangle.fromDegrees(
          this._bounds.west,
          this._bounds.south,
          this._bounds.east,
          this._bounds.north
        );
      } catch (e) {
        log("warn", "Failed to parse bounds to radians: " + e.message);
        this._boundsRadian = null;
      }
    } else {
      this._boundsRadian = null;
    }
  }
// TODO: Refactor this function to reduce its Cognitive Complexity from 26 to the 15 allowed.

  OfflineCustomTerrainProvider.prototype.requestTileGeometry = function (x, y, level) {
    if (level > this._max) {
      return Cesium.when.reject(new Error("Exceeded max level"));
    }
    // CRITICAL FIX: Tiles below minLevel must return flat terrain, NOT be fetched
    // from TiTiler.  TiTiler overview tiles at low zoom (e.g. level 0-9 for a
    // minLevel=10 DEM) contain 99%+ nodata pixels encoded as -32767m in Terrarium
    // format.  The decoded heights of -32768m produce catastrophic terrain geometry
    // that crashes/blanks the Cesium renderer whenever the camera is far enough out
    // to trigger low-level tile requests (e.g. during a 2D→3D transition).
    if (level < this._min) {
      const _W = TERRAIN_SAMPLE_SIZE, _H = TERRAIN_SAMPLE_SIZE;
      const flatBuf = new Float32Array(_W * _H); // all zeros = sea level
      return Cesium.when(new Cesium.HeightmapTerrainData({
        buffer: flatBuf,
        width: _W,
        height: _H,
        structure: { heightScale: 1.0, heightOffset: 0.0, elementsPerHeight: 1, stride: 1 }
      }));
    }
    
    // Add debugging
    if (typeof window._terrainRequestCount === "undefined") {
      window._terrainRequestCount = 0;
      window._terrainResolveCount = 0;
    }
    window._terrainRequestCount++;
    if (window._terrainRequestCount <= 30) {
      log("info", "[TERRAIN_DEBUG] Request #" + window._terrainRequestCount + ": x=" + x + " y=" + y + " level=" + level);
    }
    
    // S7740: avoid `const self = this` — use a named reference captured via closure at construction
    const terrainProvider = this;
    const cacheKey = `${x}_${y}_${level}`;
    if (terrainProvider._tileCache && terrainProvider._tileCache.has(cacheKey)) {
      const cached = terrainProvider._tileCache.get(cacheKey);
      // Move to end for LRU
      terrainProvider._tileCache.delete(cacheKey);
      terrainProvider._tileCache.set(cacheKey, cached);
      
      window._terrainResolveCount++;
      if (window._terrainResolveCount <= 30) {
        log("info", "[TERRAIN_DEBUG] Resolve #" + window._terrainResolveCount + " (cached): x=" + x + " y=" + y + " level=" + level);
      }
      return Cesium.when(cached);
    }
    
    const W = TERRAIN_SAMPLE_SIZE;
    const H = TERRAIN_SAMPLE_SIZE;
    
    // Check if tile is completely outside the dataset bounds
    if (this._boundsRadian) {
      const tileRect = this.tilingScheme.tileXYToRectangle(x, y, level);
      const intersection = Cesium.Rectangle.intersection(tileRect, this._boundsRadian);
      if (!intersection) {
        // Tile is completely outside the bounds. Return flat terrain.
        const output = new Float32Array(W * H);
        const flatData = new Cesium.HeightmapTerrainData({
          buffer: output,
          width: W,
          height: H,
          structure: { heightScale: 1.0, heightOffset: 0.0, elementsPerHeight: 1, stride: 1 }
        });
        if (terrainProvider._tileCache) {
          if (terrainProvider._tileCache.size >= terrainProvider._maxCacheSize) {
            const firstKey = terrainProvider._tileCache.keys().next().value;
            if (firstKey !== undefined) terrainProvider._tileCache.delete(firstKey);
          }
          terrainProvider._tileCache.set(cacheKey, flatData);
        }
        
        window._terrainResolveCount++;
        if (window._terrainResolveCount <= 30) {
          log("info", "[TERRAIN_DEBUG] Resolve #" + window._terrainResolveCount + " (outside bounds): x=" + x + " y=" + y + " level=" + level);
        }
        return Cesium.when(flatData);
      }
    }
    
    const tileUrl = this._url.replace("%7Bz%7D", level).replace("%7Bx%7D", x).replace("%7By%7D", y).replace("{z}", level).replace("{x}", x).replace("{y}", y);
    const rMin = this._rangeMin;
    const span = this._rangeMax - rMin;
    
    return Cesium.when(new Promise((resolve, reject) => {
      const originalResolve = resolve;
      resolve = (data) => {
        window._terrainResolveCount++;
        if (window._terrainResolveCount <= 30) {
          log("info", "[TERRAIN_DEBUG] Resolve #" + window._terrainResolveCount + " (fetched): x=" + x + " y=" + y + " level=" + level);
        }
        if (terrainProvider._tileCache) {
          if (terrainProvider._tileCache.size >= terrainProvider._maxCacheSize) {
            const firstKey = terrainProvider._tileCache.keys().next().value;
            if (firstKey !== undefined) terrainProvider._tileCache.delete(firstKey);
          }
          terrainProvider._tileCache.set(cacheKey, data);
        }
        originalResolve(data);
      };
      
      fetch(tileUrl)
        .then(response => {
          if (!response.ok) {
            throw new Error("HTTP error " + response.status);
          }
          return response.blob();
        })
        .then(blob => {
          // Decode using worker pool
          const tileRect = terrainProvider.tilingScheme.tileXYToRectangle(x, y, level);
          const tileRectDeg = {
            west: Cesium.Math.toDegrees(tileRect.west),
            south: Cesium.Math.toDegrees(tileRect.south),
            east: Cesium.Math.toDegrees(tileRect.east),
            north: Cesium.Math.toDegrees(tileRect.north)
          };
          terrainDecodeWorkerPool.decode(blob, rMin, span, W, H, tileRectDeg, terrainProvider._bounds)
            .then(output => {
              resolve(new Cesium.HeightmapTerrainData({
                buffer: output,
                width: W,
                height: H,
                structure: { heightScale: 1.0, heightOffset: 0.0, elementsPerHeight: 1, stride: 1 }
              }));
            })
            .catch(workerErr => {
              // Fallback to main thread image decoding using the already fetched blob!
              log("debug", "Worker decode failed, falling back to main-thread: " + workerErr.message);
              const img = new Image();
              img.crossOrigin = "anonymous";
              const blobUrl = URL.createObjectURL(blob);
              
              const timeoutId = setTimeout(() => {
                img.onload = null;
                img.onerror = null;
                URL.revokeObjectURL(blobUrl);
                // Resolve to flat 0.0 terrain on timeout to prevent black holes
                const output = new Float32Array(W * H);
                resolve(new Cesium.HeightmapTerrainData({
                  buffer: output,
                  width: W,
                  height: H,
                  structure: { heightScale: 1.0, heightOffset: 0.0, elementsPerHeight: 1, stride: 1 }
                }));
// TODO: Refactor this function to reduce its Cognitive Complexity from 24 to the 15 allowed.
              }, 5000);
              
              img.onload = () => {
                clearTimeout(timeoutId);
                URL.revokeObjectURL(blobUrl);
                try {
                  const imgW = img.width || 256;
                  const imgH = img.height || 256;
                  const canvas = terrainDecodeCanvas;
                  canvas.width = imgW;
                  canvas.height = imgH;
                  const ctx = terrainDecodeCtx;
                  ctx.drawImage(img, 0, 0, imgW, imgH);
                  const imgData = ctx.getImageData(0, 0, imgW, imgH);
                  const data = imgData.data;
                  const output = new Float32Array(W * H);
                  
                  // Hard-boundary clipping (main-thread fallback mirrors the worker logic).
                  // No tapering/blending — pixels outside dataset bounds get 0, inside get full height.
                  const datasetBounds = terrainProvider._bounds;
                  const hasBoundsClip = !!(tileRectDeg && datasetBounds);

                  for (let r = 0; r < H; r++) {
                    const srcY = Math.min(imgH - 1, Math.round(r * (imgH - 1) / (H - 1)));
                    let lat = 0;
                    if (hasBoundsClip) {
                      lat = tileRectDeg.north - (r / (H - 1)) * (tileRectDeg.north - tileRectDeg.south);
                    }
                    for (let c = 0; c < W; c++) {
                      const srcX = Math.min(imgW - 1, Math.round(c * (imgW - 1) / (W - 1)));
                      const srcIdx = srcY * imgW + srcX;
                      const alpha = data[srcIdx * 4 + 3];
                      if (alpha > 0) {
                        let height = rMin + (data[srcIdx * 4] / 255.0) * span;
                        if (alpha < 255) {
                          height *= (alpha / 255.0);
                        }
                        if (hasBoundsClip) {
                          const lon = tileRectDeg.west + (c / (W - 1)) * (tileRectDeg.east - tileRectDeg.west);
                          if (lon < datasetBounds.west || lon > datasetBounds.east ||
                              lat < datasetBounds.south || lat > datasetBounds.north) {
                            output[r * W + c] = 0.0;
                            continue;
                          }
                        }
                        output[r * W + c] = height;
                      } else {
                        output[r * W + c] = 0.0;
                      }
                    }
                  }
                  
                  img.onload = null;
                  img.onerror = null;
                  resolve(new Cesium.HeightmapTerrainData({
                    buffer: output,
                    width: W,
                    height: H,
                    structure: { heightScale: 1.0, heightOffset: 0.0, elementsPerHeight: 1, stride: 1 }
                  }));
                } catch (decodeErr) {
                  // Resolve to flat 0.0 terrain on error to prevent black holes
                  const output = new Float32Array(W * H);
                  resolve(new Cesium.HeightmapTerrainData({
                    buffer: output,
                    width: W,
                    height: H,
                    structure: { heightScale: 1.0, heightOffset: 0.0, elementsPerHeight: 1, stride: 1 }
                  }));
                }
              };
              
              img.onerror = (err) => {
                clearTimeout(timeoutId);
                URL.revokeObjectURL(blobUrl);
                img.onload = null;
                img.onerror = null;
                // Resolve to flat 0.0 terrain on error to prevent black holes
                const output = new Float32Array(W * H);
                resolve(new Cesium.HeightmapTerrainData({
                  buffer: output,
                  width: W,
                  height: H,
                  structure: { heightScale: 1.0, heightOffset: 0.0, elementsPerHeight: 1, stride: 1 }
                }));
              };
              
              img.src = blobUrl;
            });
        })
        .catch(err => {
          // Fetch failed or other error. Resolve with flat 0.0 terrain instead of rejecting.
          // This avoids rendering black holes/missing tiles on the ground outside the bounds.
          log("warn", "Failed to fetch or process terrain tile: " + err.message);
          const output = new Float32Array(W * H);
          resolve(new Cesium.HeightmapTerrainData({
            buffer: output,
            width: W,
            height: H,
            structure: { heightScale: 1.0, heightOffset: 0.0, elementsPerHeight: 1, stride: 1 }
          }));
        });
    }));
  };

  OfflineCustomTerrainProvider.prototype.getLevelMaximumGeometricError = function (level) {
    if (level >= 28) {
      return 0.0;
    }
    // Standard Cesium heightmap geometric error formula:
    //   GE(0) = 2 * ellipsoidMaxRadius * PI * heightmapQuality / (tilePixels * numTiles)
    // heightmapQuality = 0.25 (Cesium standard), tilePixels = TERRAIN_SAMPLE_SIZE = 129
    // This forces Cesium to refine tiles more aggressively at each zoom level,
    // giving sharper edges and eliminates slanting/zig-zag boundary artifacts.
    return (2.0 * 6378137.0 * Math.PI * 0.25) / (129.0 * Math.pow(2, level));
  };
  OfflineCustomTerrainProvider.prototype.getTileDataAvailable = function (x, y, level) {
// TODO: Refactor this function to reduce its Cognitive Complexity from 93 to the 15 allowed.
    return level <= this._max;
  };

  function setDemColorMode(colormapName) {
    if (!activeDemContext) return;
    if (!activeDemContext.options) activeDemContext.options = {};
    if (!activeDemContext.options.query) activeDemContext.options.query = {};

    const normalized = String(colormapName || "gray").toLowerCase();
    const query = activeDemContext.options.query;
    const currentStretch = activeDemDrapeLayer?._stretchSettings;
    const activeRange = getDemRescaleRangeForColorMode(normalized);

    if (normalized === "slope") {
      query.algorithm = "slope";
      query.colormap_name = "viridis";
      query.rescale = `${activeRange.min.toFixed(1)},${activeRange.max.toFixed(1)}`;
    } else {
      // Returning to gray/terrain: preserve current rescale if it exists, otherwise use original
      delete query.algorithm;
      query.colormap_name = normalized;
      if (query.rescale) {
        // Keep the active stretch rescale already calculated and applied!
      } else if (currentStretch?.params && currentStretch.params.min !== undefined) {
        query.rescale = currentStretch.params.min.toFixed(1) + "," + currentStretch.params.max.toFixed(1);
      } else {
        query.rescale = `${activeRange.min.toFixed(1)},${activeRange.max.toFixed(1)}`;
      }
    }

    demVisual.colorMode = normalized;
    activeDemContext.colorMode = normalized;
    log("info", "setDemColorMode: Starting color mode change from " + (demVisual.colorMode || "unknown") + " to " + normalized);

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

        // FIX: Smooth layer swapping without black flash.
        // We add the new layer first, then wait 1500ms before removing the old one.
        const oldDrapeLayer = activeDemDrapeLayer;

        const drapeProvider = new Cesium.UrlTemplateImageryProvider({
          url: newDrapeUrl,
          maximumLevel: maxLevel,
          minimumLevel: minLevel,
          tilingScheme: new Cesium.WebMercatorTilingScheme(),
          enablePickFeatures: false,
          rectangle: rectangle,
        });
        // Attach tile error handler and readiness logging for debugging slope/symbol tiles
        try {
          attachTileErrorHandler(drapeProvider, activeDemContext.name + "-drape");
          if (drapeProvider.readyPromise && typeof drapeProvider.readyPromise.then === 'function') {
            drapeProvider.readyPromise.then(function() {
              log("info", "DRAPE_DEBUG: provider.ready for " + activeDemContext.name + " newDrapeUrl=" + (String(newDrapeUrl).substring(0,200) + "..."));
              // Force a render once provider is ready so newly-styled tiles appear immediately
              if (viewer?.scene) viewer.scene.requestRender();
            }, function(err) {
              log("error", "DRAPE_DEBUG: provider.ready FAILED for " + activeDemContext.name + " err=" + String(err));
            });
          }
        } catch (e) {
          log("warn", "DRAPE_DEBUG: attachTileErrorHandler failed: " + e.message);
        }
        activeDemDrapeLayer = viewer.imageryLayers.addImageryProvider(drapeProvider);
        activeDemDrapeLayer.preloadAncestorTiles = true;
        if (window.Cesium && window.Cesium.TextureMinificationFilter && window.Cesium.TextureMagnificationFilter) {
          activeDemDrapeLayer.minificationFilter = window.Cesium.TextureMinificationFilter.NEAREST;
          activeDemDrapeLayer.magnificationFilter = window.Cesium.TextureMagnificationFilter.NEAREST;
        }
        activeDemDrapeLayer.alpha = 1.0;
        activeDemDrapeLayer.show = activeDemContext.visible !== false;
        activeDemDrapeUrl = newDrapeUrl;
        
        // CRITICAL FIX: Tag the new drape layer with its key so the reordering system 
        // can find and position it correctly.
        activeDemDrapeLayer._layerKey = activeDemContext.layerKey;
        activeDemDrapeLayer._layerName = activeDemContext.name;
        
        // SYNC FIX: Preserve stretch settings from old layer to new layer for real-time coordination
        if (oldDrapeLayer?._stretchSettings) {
          activeDemDrapeLayer._stretchSettings = oldDrapeLayer._stretchSettings;
          log("debug", "setDemColorMode: preserved stretch settings on new drape layer");
        }
        
        managedImageryLayers.set(activeDemContext.layerKey, activeDemDrapeLayer);

        // Clean up the old layer quickly — 200ms is enough for 2-3 new tiles to arrive
        // avoiding the black flash while still feeling near-instant to the user
        if (oldDrapeLayer) {
          // Wait longer to ensure a few tiles arrive for the new provider before removing the old one.
          // Short timeouts caused brief gaps or the new tiles not appearing on slower machines.
          setTimeout(() => {
            try {
              if (viewer?.imageryLayers && viewer.imageryLayers.contains(oldDrapeLayer)) {
                viewer.imageryLayers.remove(oldDrapeLayer, false);
                log("debug", "DRAPE_DEBUG: removed old drape layer for " + activeDemContext.name);
              }
            } catch (e) {
              log("warn", "DRAPE_DEBUG: error removing old drape layer: " + e.message);
            }
          }, 800); // Slightly longer to allow tile arrival
        }

        // Re-apply the last known layer display order so imagery stays on top (or below)
        // without requiring a Python round-trip. This prevents color-mode changes from
        // breaking the layer stack the user explicitly arranged.
        if (_lastKnownLayerOrder?.length > 0) {
          // Small defer so the new provider settles before reordering
          setTimeout(function() {
            if (window.offlineGIS && window.offlineGIS.enforceLayerDisplayOrder) {
              window.offlineGIS.enforceLayerDisplayOrder(_lastKnownLayerOrder);
            }
          }, 0);
        } else {
          // Fallback: raise hillshade and managed imagery layers above new drape
          if (activeDemDrapeLayer) viewer.imageryLayers.raiseToTop(activeDemDrapeLayer);
          if (activeDemHillshadeLayer) viewer.imageryLayers.raiseToTop(activeDemHillshadeLayer);
          for (const layer of managedImageryLayers.values()) {
            if (layer?.show && viewer.imageryLayers.indexOf(layer) >= 0) {
              viewer.imageryLayers.raiseToTop(layer);
            }
          }
        }

        if (activeDemDrapeLayer) {
          activeDemDrapeLayer.show = true;
          activeDemDrapeLayer.alpha = 1.0;
        }
        if (activeDemHillshadeLayer) {
          activeDemHillshadeLayer.show = activeDemHillshadeLayer.alpha > 0.01;
        }

        // Removed camera locking to prevent jumping when changing color modes

        // OPTIMIZATION: Only render the affected viewer, not all comparator panes
        if (viewer?.scene) {
          viewer.scene.requestRender();
        }
        log("info", "setDemColorMode: Color mode swap complete, rendering main viewer only, colormap=" + normalized);

        // SYNC FIX: Update colorbar gradient to match new color mode AND current stretch
        // Use the actual rescale from the query (which includes stretch if applied)
        const range = parseDemHeightRange({ query: query }); // Use updated query for accurate range
        updateDemColorbar(range.min, range.max, activeDemContext.options);
        
        // SYNC FIX: Also update activeDemContext.options.query to keep it in sync
        activeDemContext.options.query = query;

        if (typeof emitLoadingProgress === "function") {
          emitLoadingProgress(100, "Complete");
        }
        if (typeof _tileLoadingActive !== "undefined") {
          _tileLoadingActive = false;
        }
        
        log("info", "DEM color mode changed to " + normalized + " with rescale=" + query.rescale + " newDrapeUrl=" + (String(newDrapeUrl).substring(0,200) + "..."));
      }
    } else {
      // No active drape layer yet — do a full apply with camera lock
      // CRITICAL FIX (Bug 4): Prevent applyDemLayer from resetting camera
      // when changing style dropdown
      if (viewer?.camera) {
        let is2D = (viewer.scene.mode === Cesium.SceneMode.SCENE2D);
        let savedPos = viewer.camera.position.clone();
        let savedHdg = viewer.camera.heading;
        let savedPitch = viewer.camera.pitch;
        let savedRoll = viewer.camera.roll;
        
        let savedFrustumWidth, savedFrustumLeft, savedFrustumRight, savedFrustumTop, savedFrustumBottom;
        if (is2D && viewer.camera.frustum) {
          savedFrustumWidth = viewer.camera.frustum.width;
          savedFrustumLeft = viewer.camera.frustum.left;
          savedFrustumRight = viewer.camera.frustum.right;
          savedFrustumTop = viewer.camera.frustum.top;
          savedFrustumBottom = viewer.camera.frustum.bottom;
        }

// TODO: Refactor this function to reduce its Cognitive Complexity from 20 to the 15 allowed.
        applyDemLayer();
        
        // Lock camera for 5 frames to absorb async resets from layer changes
        let framesLeft = 5;
        let lockHandle = viewer.scene.postRender.addEventListener(function () {
          if (is2D) {
            viewer.camera.position.x = savedPos.x;
            viewer.camera.position.y = savedPos.y;
            viewer.camera.position.z = savedPos.z;
            if (viewer.camera.frustum) {
              if (typeof savedFrustumWidth !== "undefined") viewer.camera.frustum.width = savedFrustumWidth;
              if (typeof savedFrustumLeft !== "undefined") viewer.camera.frustum.left = savedFrustumLeft;
              if (typeof savedFrustumRight !== "undefined") viewer.camera.frustum.right = savedFrustumRight;
              if (typeof savedFrustumTop !== "undefined") viewer.camera.frustum.top = savedFrustumTop;
              if (typeof savedFrustumBottom !== "undefined") viewer.camera.frustum.bottom = savedFrustumBottom;
            }
          } else {
            viewer.camera.setView({
              destination: savedPos,
              orientation: { heading: savedHdg, pitch: savedPitch, roll: savedRoll },
            });
          }
          framesLeft -= 1;
          if (framesLeft <= 0) lockHandle();
        });
      } else {
        applyDemLayer();
      }
    }
  }
          if (typeof emitLoadingProgress === "function") {
            emitLoadingProgress(100, "Complete");
          }
          if (typeof _tileLoadingActive !== "undefined") {
            _tileLoadingActive = false;
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
      runtime.bridge = bridge;
      setStatus("Bridge connected.");
      log("info", "QWebChannel bridge connected");
      initViewer();
    });
  }
  function installSmoothInteractionManager(targetViewer) {
    if (!targetViewer || !targetViewer.scene || !targetViewer.canvas) {
      return;
    }
    if (targetViewer.__smoothInteractionManagerInstalled) {
      return;
    }
    targetViewer.__smoothInteractionManagerInstalled = true;

    const scene = targetViewer.scene;
    const canvas = targetViewer.canvas;
    let interacting = false;
    let idleTimer = null;
    const IDLE_DELAY_MS = 150;
    let baseSse = Number(scene.globe.maximumScreenSpaceError) || 2.0;
    
    function setIdleRenderMode(isIdle) {
      if (!scene) {
        return;
      }
      const desiredMode = Boolean(isIdle);
      if (scene.requestRenderMode !== desiredMode) {
        scene.requestRenderMode = desiredMode;
      }
      const desiredMaxChange = desiredMode ? Number.POSITIVE_INFINITY : 0;
      if (scene.maximumRenderTimeChange !== desiredMaxChange) {
        scene.maximumRenderTimeChange = desiredMaxChange;
      }
      if (typeof comparatorViewers !== "undefined" && Array.isArray(comparatorViewers)) {
        comparatorViewers.forEach(v => {
          if (v?.scene) {
            if (v.scene.requestRenderMode !== desiredMode) {
              v.scene.requestRenderMode = desiredMode;
            }
            if (v.scene.maximumRenderTimeChange !== desiredMaxChange) {
              v.scene.maximumRenderTimeChange = desiredMaxChange;
            }
          }
        });
      }
    }

    function applyInteractionTilePolicy(active) {
      if (!scene.globe) {
        return;
      }
      // Keep preloading active at all times for smooth shape transitions and consistency
      scene.globe.preloadAncestors = true;
      scene.globe.preloadSiblings = true;
    }

    function startInteraction() {
      if (idleTimer) {
        clearTimeout(idleTimer);
        idleTimer = null;
      }
      if (!interacting) {
        interacting = true;
        isInteracting = true;
        setIdleRenderMode(false);
        applyInteractionTilePolicy(true);
        if (typeof adjustScreenSpaceErrorDynamically === "function") {
          adjustScreenSpaceErrorDynamically();
        }
      }
      scene.requestRender();
    }

    function scheduleIdle() {
      if (idleTimer) {
        clearTimeout(idleTimer);
      }
      idleTimer = setTimeout(function () {
        interacting = false;
        isInteracting = false;
        setIdleRenderMode(true);
        applyInteractionTilePolicy(false);
        if (typeof adjustScreenSpaceErrorDynamically === "function") {
          adjustScreenSpaceErrorDynamically();
        }
        scene.requestRender();
        idleTimer = null;
      }, IDLE_DELAY_MS);
    }

    targetViewer.camera.moveStart.addEventListener(startInteraction);
    targetViewer.camera.moveEnd.addEventListener(scheduleIdle);

    ["pointerdown", "touchstart"].forEach(function (eventName) {
      canvas.addEventListener(eventName, startInteraction, { passive: true });
    });
    ["pointermove", "touchmove"].forEach(function (eventName) {
      canvas.addEventListener(
        eventName,
        function () {
          if (!interacting) {
            startInteraction();
          }
        },
        { passive: true }
      );
    });


    // ── Custom symmetric wheel zoom — replaces Cesium's asymmetric pick-distance zoom ──
    // Problem: Cesium's zoom-in computes zoomAmount = pickDistance × zoomFactor, where
    // pickDistance is the ray intersection with the terrain/ellipsoid. With EllipsoidTerrainProvider
    // this intersection can be meters away from the camera, resulting in violent ultra-fast
    // zoom-in even though zoom-out (which uses altitude) feels slow and correct.
    //
    // Fix: Disable Cesium's built-in wheel zoom entirely and replace it with a custom handler
    // that computes a SYMMETRIC zoom amount = currentAltitude × STEP_FRACTION for BOTH in and out.
    // We move along the camera direction to avoid pick-distance jitter while tiles refine.
    const WHEEL_ZOOM_STEP = 0.15;  // 15% of current altitude per tick — snappier
    let wheelZoomImpulse = 0;
    let wheelZoomRaf = null;
    let lastClientX = 0;
    let lastClientY = 0;

    canvas.addEventListener("wheel", function (event) {
      event.preventDefault();
      if (!targetViewer || !targetViewer.scene || !targetViewer.camera) {
        return;
      }
      startInteraction();

      const delta = event.deltaY !== 0 ? event.deltaY : -event.wheelDelta;
      wheelZoomImpulse += delta < 0 ? 1 : -1;
      
      // Capture coordinates synchronously before RAF executes
      lastClientX = event.clientX;
      lastClientY = event.clientY;
// TODO: Refactor this function to reduce its Cognitive Complexity from 134 to the 15 allowed.

      if (wheelZoomRaf !== null) {
        return;
      }

      wheelZoomRaf = window.requestAnimationFrame(function () {
        wheelZoomRaf = null;
        const camera = targetViewer.camera;
        const scene = targetViewer.scene;

        const stepCount = Math.max(-10, Math.min(10, wheelZoomImpulse));
        const zoomingIn = stepCount > 0;
        wheelZoomImpulse = 0;

        if (scene.mode === Cesium.SceneMode.SCENE2D) {
          log("debug", "[ZOOM2D] Wheel zoom triggered in 2D mode, stepCount=" + stepCount + ", zoomingIn=" + zoomingIn);
          const rect = canvas.getBoundingClientRect();
          const mouseX = lastClientX - rect.left;
          const mouseY = lastClientY - rect.top;
          
          const cw = canvas.clientWidth;
          const ch = canvas.clientHeight;
          log("debug", "[ZOOM2D] rect=" + JSON.stringify(rect) + ", mouseX=" + mouseX + ", mouseY=" + mouseY + ", cw=" + cw + ", ch=" + ch);

          if (cw > 0 && ch > 0 && Number.isFinite(mouseX) && Number.isFinite(mouseY)) {
            const nx = (mouseX / cw) - 0.5;
            const ny = 0.5 - (mouseY / ch);
            
            let oldWidth = undefined;
            let isOffCenter = false;
            if (camera.frustum) {
              if (typeof camera.frustum.width !== "undefined") {
                oldWidth = camera.frustum.width;
              } else if (typeof camera.frustum.right !== "undefined" && typeof camera.frustum.left !== "undefined") {
                oldWidth = camera.frustum.right - camera.frustum.left;
                isOffCenter = true;
              }
            }
            log("debug", "[ZOOM2D] oldWidth=" + oldWidth + ", isOffCenter=" + isOffCenter + ", pos.x=" + camera.position.x + ", pos.y=" + camera.position.y + ", pos.z=" + camera.position.z);

            if (Number.isFinite(oldWidth) && Number.isFinite(camera.position.x) && Number.isFinite(camera.position.y) && Number.isFinite(camera.position.z)) {
              // Calculate mouse position in projected space
              const mouseProjX = camera.position.x + nx * oldWidth;
              const mouseProjY = camera.position.y + ny * (oldWidth * (ch / cw));
              log("debug", "[ZOOM2D] mouseProjX=" + mouseProjX + ", mouseProjY=" + mouseProjY + ", nx=" + nx + ", ny=" + ny);
              
              // Calculate target width using symmetric exponential zoom
              const factor = Math.pow(1.0 + WHEEL_ZOOM_STEP, Math.abs(stepCount || 1));
              let targetWidth = zoomingIn ? (oldWidth / factor) : (oldWidth * factor);
              
              const MIN_2D_WIDTH = 1.0;
              const MAX_2D_LIMIT = 15000000.0; 
              const aspect = cw / ch;
              let maxWidth = MAX_2D_LIMIT;
              if (aspect < 1.0) {
                // Portrait mode: height is larger, so scale down maxWidth to respect MAX_2D_LIMIT vertically
                maxWidth = MAX_2D_LIMIT * aspect;
              }
              targetWidth = Math.max(MIN_2D_WIDTH, Math.min(maxWidth, targetWidth));
              log("debug", "[ZOOM2D] targetWidth=" + targetWidth + ", MIN_2D_WIDTH=" + MIN_2D_WIDTH + ", maxWidth=" + maxWidth);
              
              const S = oldWidth > 0 ? (targetWidth / oldWidth) : 1.0;
              
              // Adjust camera position in projected space to anchor to mouse position
              const newX = mouseProjX + S * (camera.position.x - mouseProjX);
              const newY = mouseProjY + S * (camera.position.y - mouseProjY);
              log("debug", "[ZOOM2D] S=" + S + ", newX=" + newX + ", newY=" + newY);

              if (Number.isFinite(newX) && Number.isFinite(newY)) {
                if (!isOffCenter) {
                  camera.frustum.width = targetWidth;
                } else {
                  camera.frustum.left = camera.frustum.left * S;
                  camera.frustum.right = camera.frustum.right * S;
                  camera.frustum.top = camera.frustum.top * S;
                  camera.frustum.bottom = camera.frustum.bottom * S;
                }
                camera.position.x = newX;
                camera.position.y = newY;
                const actualWidth = isOffCenter ? (camera.frustum.right - camera.frustum.left) : camera.frustum.width;
                log("debug", "[ZOOM2D] Zoom applied: width=" + actualWidth + ", pos.x=" + camera.position.x + ", pos.y=" + camera.position.y);
              } else {
                log("warn", "[ZOOM2D] Calculated coordinates newX or newY are not finite!");
              }
            } else {
              log("warn", "[ZOOM2D] Camera properties (width/x/y/z) are not finite numbers!");
            }
          } else {
            let oldWidth = undefined;
            let isOffCenter = false;
            if (camera.frustum) {
              if (typeof camera.frustum.width !== "undefined") {
                oldWidth = camera.frustum.width;
              } else if (typeof camera.frustum.right !== "undefined" && typeof camera.frustum.left !== "undefined") {
                oldWidth = camera.frustum.right - camera.frustum.left;
                isOffCenter = true;
              }
            }
            log("debug", "[ZOOM2D] Fallback zoom, oldWidth=" + oldWidth);
            if (Number.isFinite(oldWidth)) {
              const factor = Math.pow(1.0 + WHEEL_ZOOM_STEP, Math.abs(stepCount || 1));
              let targetWidth = zoomingIn ? (oldWidth / factor) : (oldWidth * factor);
              const MIN_2D_WIDTH = 1.0;
              const MAX_2D_LIMIT = 15000000.0;
              targetWidth = Math.max(MIN_2D_WIDTH, Math.min(MAX_2D_LIMIT, targetWidth));
              
              if (!isOffCenter) {
                camera.frustum.width = targetWidth;
              } else {
                const S = oldWidth > 0 ? (targetWidth / oldWidth) : 1.0;
                camera.frustum.left = camera.frustum.left * S;
                camera.frustum.right = camera.frustum.right * S;
                camera.frustum.top = camera.frustum.top * S;
                camera.frustum.bottom = camera.frustum.bottom * S;
              }
              const actualWidth = isOffCenter ? (camera.frustum.right - camera.frustum.left) : camera.frustum.width;
              log("debug", "[ZOOM2D] Fallback applied: width=" + actualWidth);
            }
          }
        } else {
          const posCart = camera.positionCartographic;
          if (!posCart || !Number.isFinite(posCart.height)) {
            wheelZoomImpulse = 0;
            scheduleIdle();
            return;
          }
          const altitude = Math.max(posCart.height, 50.0);

          // Ray-cast to find the terrain/ellipsoid intersection under the mouse pointer
          const rect = canvas.getBoundingClientRect();
          const mouseX = lastClientX - rect.left;
          const mouseY = lastClientY - rect.top;
          const mousePosition = new Cesium.Cartesian2(mouseX, mouseY);
          
          let targetCartesian = null;
          if (Number.isFinite(mouseX) && Number.isFinite(mouseY)) {
            const ray = camera.getPickRay(mousePosition);
            if (ray) {
              targetCartesian = scene.globe.pick(ray, scene);
              if (!targetCartesian) {
                const intersection = Cesium.IntersectionTests.rayEllipsoid(ray, scene.globe.ellipsoid);
                if (intersection) {
                  targetCartesian = Cesium.Ray.getPoint(ray, intersection.start);
                }
              }
            }
          }

          let nextPos;
          if (targetCartesian && Number.isFinite(targetCartesian.x) && Number.isFinite(targetCartesian.y) && Number.isFinite(targetCartesian.z)) {
            const distance = Cesium.Cartesian3.distance(camera.position, targetCartesian);
            // Limit maximum step distance relative to current altitude to prevent violent jumps
            const maxStepDist = Math.min(distance, altitude * 2.0);
            const zoomAmount = maxStepDist * WHEEL_ZOOM_STEP * Math.abs(stepCount || 1);
            
            const direction = Cesium.Cartesian3.subtract(targetCartesian, camera.position, new Cesium.Cartesian3());
            Cesium.Cartesian3.normalize(direction, direction);
            
            const move = Cesium.Cartesian3.multiplyByScalar(direction, zoomingIn ? zoomAmount : -zoomAmount, new Cesium.Cartesian3());
            nextPos = Cesium.Cartesian3.add(camera.position, move, new Cesium.Cartesian3());
          } else {
            // Fallback: zoom along camera direction vector
            const direction = camera.direction ? camera.direction.clone() : null;
            if (!direction) {
              scheduleIdle();
              return;
            }
            if (!zoomingIn) {
              Cesium.Cartesian3.negate(direction, direction);
            }
            const zoomAmount = altitude * WHEEL_ZOOM_STEP * Math.abs(stepCount || 1);
            const move = Cesium.Cartesian3.multiplyByScalar(direction, zoomAmount, new Cesium.Cartesian3());
            nextPos = Cesium.Cartesian3.add(camera.position, move, new Cesium.Cartesian3());
          }

          if (nextPos && Number.isFinite(nextPos.x) && Number.isFinite(nextPos.y) && Number.isFinite(nextPos.z)) {
            const nextCarto = Cesium.Cartographic.fromCartesian(nextPos);
            if (nextCarto && Number.isFinite(nextCarto.height)) {
              // Retrieve actual terrain height under the next position to enforce collision bounds
              const terrainHeight = scene.globe.getHeight(nextCarto);
              const h = (typeof terrainHeight === "number" && Number.isFinite(terrainHeight)) ? terrainHeight : 0.0;
              const minHeight = h + 10.0; // Enforce safe minimum of 10m above ground
              
              if (nextCarto.height < minHeight) {
                nextCarto.height = minHeight;
                const adjustedPos = Cesium.Cartographic.toCartesian(nextCarto, scene.globe.ellipsoid);
                if (adjustedPos && Number.isFinite(adjustedPos.x) && Number.isFinite(adjustedPos.y) && Number.isFinite(adjustedPos.z)) {
                  nextPos = adjustedPos;
                }
              }
 
              camera.setView({
                destination: nextPos,
                orientation: {
                  heading: camera.heading,
                  pitch: camera.pitch,
                  roll: camera.roll
                }
              });
            }
          }
        }

        scene.requestRender();
        scheduleIdle();
      });
    }, { passive: false });

    ["pointerup", "pointercancel", "touchend"].forEach(function (eventName) {
      canvas.addEventListener(eventName, scheduleIdle, { passive: true });
    });

    scene.globe.tileLoadProgressEvent.addEventListener(function (tilesRemaining) {
      if (tilesRemaining > 0) {
        startInteraction();
        return;
      }
      scheduleIdle();
    });

    window._requestRender = function () {
      if (!targetViewer || !targetViewer.scene) {
        return;
      }
      const currentScene = targetViewer.scene;
      const wasOnDemand = currentScene.requestRenderMode;
      currentScene.requestRenderMode = false;
      currentScene.requestRender();
      setTimeout(function () {
        currentScene.requestRenderMode = wasOnDemand;
        currentScene.requestRender();
      }, 200);
// TODO: Refactor this function to reduce its Cognitive Complexity from 33 to the 15 allowed.
    };

    scheduleIdle();
    log("info", "Smooth interaction manager installed (Windows-optimized)");
  }

  function initViewer() {
    if (!window.Cesium) {
      setStatus("Cesium.js not found. Add local Cesium assets under web_assets/cesium.");
      log("error", "Cesium runtime not found");
      return;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // CRITICAL PATCH: Prevent 2D zoom crash due to infinite tile subdivision
    // ─────────────────────────────────────────────────────────────────────────
    if (Cesium.EllipsoidTerrainProvider && Cesium.EllipsoidTerrainProvider.prototype && Cesium.EllipsoidTerrainProvider.prototype.getLevelMaximumGeometricError) {
      const origEllipsoidError = Cesium.EllipsoidTerrainProvider.prototype.getLevelMaximumGeometricError;
      Cesium.EllipsoidTerrainProvider.prototype.getLevelMaximumGeometricError = function(level) {
        if (level >= 28) return 0.0;
        return origEllipsoidError.apply(this, arguments);
      };
      log("info", "Cesium.EllipsoidTerrainProvider.prototype.getLevelMaximumGeometricError patched to cap at level 28.");
    }

    // ─────────────────────────────────────────────────────────────────────────
    // CRITICAL PATCH: Fix WebGL NPOT minificationFilter warnings
    // ─────────────────────────────────────────────────────────────────────────
    if (Cesium.ImageryLayers && Cesium.ImageryLayers.prototype && Cesium.ImageryLayers.prototype.add) {
      const originalAdd = Cesium.ImageryLayers.prototype.add;
      Cesium.ImageryLayers.prototype.add = function(layer, index) {
        if (layer) {
          if (layer.minificationFilter === undefined || 
              layer.minificationFilter === Cesium.TextureMinificationFilter.LINEAR_MIPMAP_LINEAR) {
            layer.minificationFilter = Cesium.TextureMinificationFilter.LINEAR;
          }
          if (layer.magnificationFilter === undefined) {
            layer.magnificationFilter = Cesium.TextureMagnificationFilter.LINEAR;
          }
        }
        return originalAdd.call(this, layer, index);
      };
      log("info", "Cesium.ImageryLayers.prototype.add patched for WebGL NPOT filter safety.");
    }

    // ─────────────────────────────────────────────────────────────────────────
    // CRITICAL PATCH: Handle statusCode 0 for local Assets (Windows/file://)
    // ─────────────────────────────────────────────────────────────────────────
    if (Cesium.Resource && Cesium.Resource.prototype && Cesium.Resource.prototype.fetchJson) {
      const originalFetchJson = Cesium.Resource.prototype.fetchJson;
      Cesium.Resource.prototype.fetchJson = function() {
        const reqUrl = String(this.url || "");
        
        const handleRejection = function(error) {
          if (error?.statusCode === 0 && typeof error.response === "string") {
            try {
              return JSON.parse(error.response);
            } catch (e) {
              log("warn", "JSON.parse failed for local file (" + reqUrl + "): " + e.message);
            }
          }
          if (Cesium.when && Cesium.when.reject) {
            return Cesium.when.reject(error);
          }
          return Promise.reject(error);
        };

        const promise = originalFetchJson.apply(this, arguments);
        if (promise && typeof promise.then === "function") {
          return promise.then(undefined, handleRejection);
        }
        return promise;
      };
      log("info", "Cesium.Resource.fetchJson patched for local file compatibility.");
    }

    // ─────────────────────────────────────────────────────────────────────────
    // CRITICAL BYPASS: Prevent approximateTerrainHeights.json fetch crash
    // ─────────────────────────────────────────────────────────────────────────
    // On Windows local file://, this 2.5MB asset often truncates or fails, causing a synchronous 
    // renderer crash when clampToGround is first used (e.g., drawing AOI). By pre-initializing it 
    // with an empty object and a resolved promise, Cesium skips the fetch entirely and safely falls 
    // back to generic terrain bounds without crashing.
    if (Cesium.ApproximateTerrainHeights) {
      Cesium.ApproximateTerrainHeights._terrainHeights = {};
      Cesium.ApproximateTerrainHeights._initPromise = (Cesium.when && Cesium.when.resolve) 
        ? Cesium.when.resolve() 
        : Promise.resolve();
      log("info", "Bypassed approximateTerrainHeights.json fetch to prevent clampToGround crashes.");
    }

    // Probe NaturalEarthII availability — on Windows the cesium/ symlink may not
    viewer = new Cesium.Viewer("cesiumContainer", {
      imageryProvider: false,  // No basemap - bare globe only
      baseLayerPicker: false,
      geocoder: false,
      navigationHelpButton: false,
      sceneModePicker: false,
      homeButton: false,
      fullscreenButton: false,
      infoBox: false,
      selectionIndicator: false,
      scene3DOnly: false,
      requestRenderMode: false,  // Globally disabled to maintain continuous render loop
      maximumRenderTimeChange: Infinity,  // Let smooth interaction manager control render timing
      timeline: false,
      animation: false,
      terrainProvider: new Cesium.EllipsoidTerrainProvider(),
      orderIndependentTranslucency: false,
      contextOptions: {
        webgl: {
          alpha: false,
          depth: true,
          stencil: false,
          antialias: true,  // Enable antialiasing for high-quality visuals
          powerPreference: "high-performance",  // Use discrete GPU (NVIDIA) if available
          preserveDrawingBuffer: true,
          failIfMajorPerformanceCaveat: false,
          desynchronized: false,
        },
      },
      msaaSamples: 4,  // Enable MSAA for smooth edges
      useBrowserRecommendedResolution: false,
    });
    runtime.viewer = viewer;
    
    // GPU-accelerated rendering optimizations
    viewer.resolutionScale = 1.0;  // Full resolution for sharp rendering (don't divide by devicePixelRatio)
    viewer.scene.postProcessStages.fxaa.enabled = true;  // Enable FXAA for high quality
    viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#1a2535");
    viewer.scene.backgroundColor = Cesium.Color.fromCssColorString("#0a0a0a");
    viewer.canvas.style.backgroundColor = "#0a0a0a";
    
    // Performance optimizations for ultra-smooth interaction
    viewer.useDefaultRenderLoop = true;
    viewer.scene.requestRenderMode = false; // Always live for maximum smoothness
    viewer.scene.maximumRenderTimeChange = 0;
    viewer.scene.globe.maximumScreenSpaceError = 1.0; // High-fidelity terrain — locked at max quality
    viewer.scene.globe.tileCacheSize = 800;  // Optimized cache to reduce memory footprint and GC stutters
    viewer.scene.fog.enabled = false;  // Disable fog for performance
    viewer.scene.skyAtmosphere.show = false;  // Disable atmosphere for performance
    viewer.scene.sun.show = false;  // Disable sun for performance
    viewer.scene.moon.show = false;  // Disable moon for performance
    viewer.scene.skyBox.show = false;  // Disable skybox for performance
    viewer.scene.globe.showGroundAtmosphere = false;  // Disable ground atmosphere
    viewer.scene.globe.enableLighting = false;  // Disable lighting for performance
    viewer.scene.globe.depthTestAgainstTerrain = true;  // Required for proper DEM layer sorting and occlusion
    
    // Optimize tile loading for smoother experience
    viewer.scene.globe.preloadAncestors = true;  // Preload for smoother zooming
    viewer.scene.globe.preloadSiblings = true;  // Preload for smoother panning
    viewer.scene.globe.loadingQueueThreshold = 100;
    viewer.scene.globe.loadingDescendantLimit = 8;
    
    // Additional performance optimizations
    viewer.scene.fxaa = false;  // Disable FXAA post-processing
    viewer.scene.highDynamicRange = false;  // Disable HDR for performance
    viewer.scene.logarithmicDepthBuffer = false;  // Disabled to prevent GroundPolyline culling at high zoom levels
    viewer.scene.globe.showWaterEffect = false;  // Disable water effect
    viewer.scene.globe.showSkirts = true;  // Keep skirts to avoid gaps between tiles
    
    // Optimize rendering pipeline
    viewer.scene.pickTranslucentDepth = false;  // Disable translucent depth picking
    viewer.scene.useDepthPicking = false;  // Disable depth picking for performance
    
    log("info", "Viewer initialized with GPU acceleration and ultra-smooth interaction settings");
    
    // ═══════════════════════════════════════════════════════════════════════════
    // CRITICAL: GPU Detection for Intel vs NVIDIA performance tuning
    // ═══════════════════════════════════════════════════════════════════════════
    window._isHighEndGpu = false;
    window._gpuRenderer = "Unknown";
    try {
      const canvas = document.createElement('canvas');
      const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
      if (gl) {
        const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
        if (debugInfo) {
          const renderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);
          if (renderer) {
            window._gpuRenderer = renderer;
            const r = renderer.toLowerCase();
            // Detect dedicated or high-performance GPUs (NVIDIA, AMD Radeon, Apple Silicon, Metal)
            if (r.indexOf("nvidia") !== -1 || r.indexOf("rtx") !== -1 || r.indexOf("gtx") !== -1 || 
                r.indexOf("quadro") !== -1 || (r.indexOf("amd") !== -1 && r.indexOf("radeon rx") !== -1) ||
                r.indexOf("apple") !== -1 || r.indexOf("metal") !== -1) {
              window._isHighEndGpu = true;
            }
          }
        }
      }
    } catch (e) {
      log("warn", "Failed to detect GPU renderer: " + e);
    }
    
    log("info", "GPU Detected: " + window._gpuRenderer + " (High-End: " + window._isHighEndGpu + ")");
 
    // ═══════════════════════════════════════════════════════════════════════════
    // CRITICAL: GPU-adaptive viewer initialization
    // Two profiles: MAX (NVIDIA/dedicated) vs SAFE (Intel/integrated)
    // NOTE: requestRenderMode stays FALSE (set above) for continuous render loop.
    // ═══════════════════════════════════════════════════════════════════════════
    
    // Shared: always disable expensive cosmetics
    viewer.scene.fog.enabled = false;
    viewer.scene.skyAtmosphere.show = false;
    viewer.scene.sun.show = false;
    viewer.scene.moon.show = false;
    viewer.scene.globe.enableLighting = false;
    viewer.scene.globe.showGroundAtmosphere = false;
    
    if (window._isHighEndGpu) {
      // ── MAX CONFIG (NVIDIA / Quadro / Apple Silicon) ─────────────────────
      MAX_CONCURRENT_TERRAIN_DECODES = 8;   // Parallel terrain decodes for workstation
      viewer.resolutionScale = 1.0;          // Full native resolution
      viewer.scene.logarithmicDepthBuffer = false;
      viewer.scene.globe.depthTestAgainstTerrain = true;
      viewer.scene.globe.tileCacheSize = 2500; // Raised to 2500 for workstation performance
      viewer.scene.globe.maximumScreenSpaceError = 1.0; // Static high-fidelity error threshold
      viewer.scene.globe.preloadAncestors = true;
      viewer.scene.globe.preloadSiblings = true;
      viewer.scene.globe.loadingDescendantLimit = 8;
      viewer.scene.globe.loadingQueueThreshold = 100;
      
      // RequestScheduler limits for dedicated GPU pipeline
      if (Cesium.RequestScheduler) {
        Cesium.RequestScheduler.maximumRequestsPerServer = 24;
        Cesium.RequestScheduler.maximumRequests = 100;
      }
      
      // NVIDIA GL hint
      if (viewer.scene.context && viewer.scene.context._gl) {
        const gl = viewer.scene.context._gl;
        gl.hint(gl.GENERATE_MIPMAP_HINT, gl.FASTEST);
      }
      
      log("info", "[INIT MAX GPU CONFIG] Dedicated GPU detected — Extreme fidelity enabled (cache=2500, maxRequests=100)");
    } else {
      // ── SAFE CONFIG (Intel integrated / unknown) ──────────────────────────
      MAX_CONCURRENT_TERRAIN_DECODES = 2;   // Slightly more parallel decodes for modern Intel
      viewer.resolutionScale = 1.0;          // Full native resolution to maintain imagery quality
      viewer.scene.logarithmicDepthBuffer = false;
      viewer.scene.globe.depthTestAgainstTerrain = true; // Essential for true 3D fidelity
      viewer.scene.globe.tileCacheSize = 1000;  // Raised to 1000 for smoother panning
      viewer.scene.globe.maximumScreenSpaceError = 1.5;  // Static balanced error threshold
      viewer.scene.globe.preloadAncestors = true; // Enabled for smoother zoom transitions
      viewer.scene.globe.preloadSiblings = true;
      viewer.scene.globe.loadingDescendantLimit = 4;  // Faster tile loading
      viewer.scene.globe.loadingQueueThreshold = 100;
      
      // RequestScheduler limits for integrated/slower GPU pipeline
      if (Cesium.RequestScheduler) {
        Cesium.RequestScheduler.maximumRequestsPerServer = 12;
        Cesium.RequestScheduler.maximumRequests = 50;
      }
      
      log("info", "[INIT SAFE INTEL CONFIG] Integrated GPU optimized for smooth performance (res=1.0 sse=1.5 cache=1000, maxRequests=50)");
    }

    scenePerfDefaults = {
      tileCacheSize: Number(viewer.scene.globe.tileCacheSize) || 0,
      loadingDescendantLimit: Number(viewer.scene.globe.loadingDescendantLimit) || 0,
      preloadAncestors: Boolean(viewer.scene.globe.preloadAncestors),
      preloadSiblings: Boolean(viewer.scene.globe.preloadSiblings),
    };
    
    applyDefaultSceneSettings();
    tuneCameraController();
    
    // Set camera sensitivity for smooth performance (from smooth implementation)
    viewer.camera.percentageChanged = 0.001;
    
    log("info", "Cesium default camera controls enabled");
    
    // ═══════════════════════════════════════════════════════════════════════════
    // CRITICAL: WebGL Context Loss Recovery for Desktop Application
    // Handles GPU context loss from laptop sleep, driver crashes, or GPU resets
    // Essential for long-running desktop applications (days/weeks uptime)
    // ═══════════════════════════════════════════════════════════════════════════
    
    let contextLostCount = 0;
    let contextRestoreRenderMode = false;
    const MAX_CONTEXT_RECOVERY_ATTEMPTS = 3;
    
    // Listen for WebGL context loss events
    if (viewer.canvas) {
      viewer.canvas.addEventListener('webglcontextlost', function(event) {
        event.preventDefault();  // Prevent default behavior
        contextLostCount++;
        
        log("error", "WebGL context lost (attempt " + contextLostCount + "/" + MAX_CONTEXT_RECOVERY_ATTEMPTS + ") - GPU may have been powered down or driver crashed");
        
        // Show user-friendly message
        setStatus("GPU context lost - attempting recovery...");
        
        // Disable rendering during recovery
        if (viewer?.scene) {
          contextRestoreRenderMode = viewer.scene.requestRenderMode;
          viewer.scene.requestRenderMode = false;
          viewer.scene.requestRender();
        }
      }, false);
      
      // Listen for WebGL context restored events
      viewer.canvas.addEventListener('webglcontextrestored', function(event) {
        log("info", "WebGL context restored - reinitializing scene");
        
        if (contextLostCount >= MAX_CONTEXT_RECOVERY_ATTEMPTS) {
          log("error", "Max context recovery attempts reached - manual restart required");
          setStatus("GPU recovery failed - please restart the application");
          return;
        }
        
        try {
          // Reinitialize scene after context restoration
          if (viewer?.scene) {
            // Force scene re-render
            viewer.scene.requestRenderMode = false;
            viewer.scene.requestRender();
            setTimeout(function() {
              if (viewer?.scene) {
                viewer.scene.requestRenderMode = false;
                viewer.scene.requestRender();
              }
            }, 250);
            
            // Reload all active layers
            log("info", "Reloading active layers after context restoration");
            
            // Reload DEM if active
            if (activeDemContext?.visible) {
              log("info", "Reloading DEM layer: " + activeDemContext.name);
              applyDemLayer();
            }
            
            // Reload imagery layers
            for (const [layerKey, layer] of managedImageryLayers.entries()) {
              if (layer?.show) {
                log("info", "Reloading imagery layer: " + layerKey);
                // Layer will be reloaded automatically by Cesium
              }
            }
            
            // Reload OSM basemap if visible
            if (osmBasemapLayer?.show) {
              log("info", "Reloading OSM basemap");
              // OSM will be reloaded automatically by Cesium
            }
            
            if (viewer?.scene) {
              viewer.scene.requestRenderMode = contextRestoreRenderMode;
              viewer.scene.requestRender();
            }
            setStatus("GPU context recovered successfully");
            log("info", "WebGL context recovery complete");
          }
        } catch (e) {
          log("error", "Failed to recover from context loss: " + e.message);
          setStatus("GPU recovery failed - please restart the application");
        }
      }, false);
      
      log("info", "WebGL context loss recovery handlers installed");
    }
    
    // ── Add default Earth imagery layer (always visible as base) ────────────
    // This provides a fast, single-image world map when OSM tiles are hidden
    try {
      // Use Cesium's built-in TileMapServiceImageryProvider with NaturalEarthII
      // This is a single low-resolution world map that loads instantly
      // FIXED: Use constructor syntax instead of fromUrl() which doesn't exist
      const defaultEarthProvider = new Cesium.TileMapServiceImageryProvider({
        url: Cesium.buildModuleUrl('Assets/Textures/NaturalEarthII')
      });
      
      defaultEarthLayer = viewer.imageryLayers.addImageryProvider(defaultEarthProvider);
      defaultEarthLayer.alpha = 1.0;
      defaultEarthLayer.show = true;  // Always visible as base layer
      log("info", "Default Earth imagery layer added (NaturalEarthII)");
    } catch (e) {
      log("warn", "Failed to add NaturalEarthII default Earth layer: " + e.message);
      // Fallback: Create a minimal 1x1 solid dark-blue base canvas layer as globe background
      try {
        const solidBg = document.createElement('canvas');
        solidBg.width = 1; solidBg.height = 1;
        const ctx = solidBg.getContext('2d');
        ctx.fillStyle = '#0d1b2e';
        ctx.fillRect(0, 0, 1, 1);
        const bgProvider = new Cesium.SingleTileImageryProvider({
          url: solidBg.toDataURL(),
          rectangle: Cesium.Rectangle.fromDegrees(-180, -90, 180, 90)
        });
        defaultEarthLayer = viewer.imageryLayers.addImageryProvider(bgProvider);
        defaultEarthLayer.alpha = 1.0;
        defaultEarthLayer.show = true;
        log("info", "Default Earth fallback (solid dark-blue canvas) added successfully");
      } catch (err) {
        log("error", "Failed to add default Earth fallback layer: " + err.message);
        viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#1a2535");
      }
    }
    
    // ── OSM basemap tiles (lazy-loaded, initially hidden) ────────────────
    // OSM tiles are NOT loaded on startup - only when user selects "Show Map"
    // This provides instant startup and smooth transition
    osmBasemapLayer = null;  // Will be created on first "Show Map" request
    
    log("info", "Basemap system initialized: Default Earth (always visible) + OSM tiles (lazy-loaded)");
    
    applyDefaultStartupFocus();
    let lastErrorMessage = "";
    let lastErrorTime = 0;
    window.addEventListener("error", function (event) {
      // Ignore errors from Cesium.js itself
      if (event?.filename && event.filename.includes("Cesium.js")) {
        return;
      }
      const msg = event?.message ? event.message : "unknown";
      const now = Date.now();
      // Suppress duplicate errors within 1 second
      if (msg === lastErrorMessage && now - lastErrorTime < 1000) {
        return;
      }
      lastErrorMessage = msg;
      lastErrorTime = now;
      const err = event?.error ? event.error : null;
      const stack = err?.stack ? err.stack : "";
      log("error", "Window error: " + msg + (stack ? " | " + stack : ""));
    });
    window.addEventListener("unhandledrejection", function (event) {
      const reason = event?.reason ? String(event.reason) : "unknown";
      log("error", "Unhandled promise rejection: " + reason);
    });

    if (SHOW_COUNTRY_BOUNDARY_OVERLAY) {
      void attachCountryBoundaryOverlay();
    }
    let _renderErrorCount = 0;
    let _renderErrorResetTimer = null;
    let _lastRenderErrorTime = 0;
    
    viewer.scene.renderError.addEventListener(function (scene, error) {
      const now = Date.now();
      _renderErrorCount += 1;
      
      if (_renderErrorResetTimer) clearTimeout(_renderErrorResetTimer);
      // Reset count after 10 seconds of stability
      _renderErrorResetTimer = setTimeout(function () { _renderErrorCount = 0; }, 10000);
      
      let msg = "unknown render error";
      if (error) {
        if (typeof error === "string") {
          msg = error;
        } else if (error.stack) {
          msg = error.stack;
        } else if (error.message) {
          msg = error.message;
        } else {
          // Robust inspection for RequestErrorEvent or other complex objects
          msg = "Error: " + (error.name || "Object");
          if (error.statusCode) msg += " (Status: " + error.statusCode + ")";
          if (error.url) msg += " [URL: " + error.url + "]";
          try { 
            // Extract common non-enumerable properties before stringifying
            const detailObj = {
              message: error.message,
              name: error.name,
              stack: error.stack,
              statusCode: error.statusCode,
              response: (typeof error.response === "string" && error.response.length > 500) 
                        ? error.response.substring(0, 500) + "... [truncated]" 
                        : error.response
            };
            const stringified = JSON.stringify(detailObj); 
            msg += " Details: " + stringified;
          } catch (e) { 
            msg += " (Non-stringifiable details)"; 
          }
        }
      }

      log("error", "Cesium render error (" + _renderErrorCount + "): " + msg);

      // CRITICAL: Throttle recovery attempts. Stop at 8 errors.
      if (_renderErrorCount > 8) {
        if (_renderErrorCount === 9) {
          log("error", "Render errors exceeded threshold — stopping recovery to prevent infinite loop.");
          setStatus("3D engine encountered a critical error. Please refresh.");
        }
        viewer.useDefaultRenderLoop = false;
        return;
      }

      // If we errored too quickly after the last error (within 50ms), skip this recovery step
      if (now - _lastRenderErrorTime < 50) {
        return;
      }
      _lastRenderErrorTime = now;

      try {
        viewer.useDefaultRenderLoop = true;
        // Force a synchronous render to verify recovery
        viewer.render();
        log("info", "Render loop recovered successfully.");
      } catch (recoveryErr) {
        log("error", "Render recovery attempt failed: " + recoveryErr);
      }
    });

    viewer.imageryLayers.layerAdded.addEventListener(function (_layer, index) {
      log("info", "Imagery layer added at index " + index);
    });
    viewer.scene.morphStart.addEventListener(function (_transitioner, oldMode, newMode) {
      sceneDebug(
        "morphStart oldMode=" +
          oldMode +
          " newMode=" +
// TODO: Refactor this function to reduce its Cognitive Complexity from 25 to the 15 allowed.
          newMode +
          " currentSceneMode=" +
          currentSceneMode +
          " pendingSceneModeAfterMorph=" +
          String(pendingSceneModeAfterMorph)
      );
    });
    viewer.scene.morphComplete.addEventListener(function () {
      // Clear transition flag immediately to allow camera locking
      window._is2DTo3DTransition = false;

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

      const hasSavedState = window.offlineGIS && typeof window.offlineGIS.hasSavedCameraState === "function" && window.offlineGIS.hasSavedCameraState();

      if (hasSavedState) {
        sceneDebug("morphComplete: saved camera state found. Restoring camera position first.");
        window.offlineGIS.restoreCameraAfterMorph();

        // Perform terrain swaps after camera restoration so locking captures the correct coordinates
        if (currentSceneMode === "2d") {
          if (viewer.terrainProvider && !(viewer.terrainProvider instanceof Cesium.EllipsoidTerrainProvider)) {
            viewer.terrainProvider = new Cesium.EllipsoidTerrainProvider();
          }
        } else if (currentSceneMode === "3d") {
          if (activeDemTerrainProvider && activeDemContext && activeDemContext.visible !== false) {
            if (viewer.terrainProvider !== activeDemTerrainProvider) {
              _swapTerrainProviderLocked(activeDemTerrainProvider);
            }
            if (activeDemDrapeLayer) activeDemDrapeLayer.show = true;
            if (activeDemHillshadeLayer) activeDemHillshadeLayer.show = true;
            viewer.scene.globe.terrainExaggeration = Math.max(0.1, demVisual.exaggeration);
            if (typeof viewer.scene.verticalExaggeration !== "undefined") {
              viewer.scene.verticalExaggeration = Math.max(0.1, demVisual.exaggeration);
            }
          }
        }

        pendingFocusAfterMorph = false;
        pendingFocusBounds = null;
        pendingTerrainSceneAfterMorph = false;
        return;
      }

      // If no saved state, perform terrain swaps before flying to focus bounds (which gets locked & deferred)
      if (currentSceneMode === "2d") {
        if (viewer.terrainProvider && !(viewer.terrainProvider instanceof Cesium.EllipsoidTerrainProvider)) {
          viewer.terrainProvider = new Cesium.EllipsoidTerrainProvider();
        }
      } else if (currentSceneMode === "3d") {
        if (activeDemTerrainProvider && activeDemContext && activeDemContext.visible !== false) {
          if (viewer.terrainProvider !== activeDemTerrainProvider) {
            _swapTerrainProviderLocked(activeDemTerrainProvider);
          }
          if (activeDemDrapeLayer) activeDemDrapeLayer.show = true;
          if (activeDemHillshadeLayer) activeDemHillshadeLayer.show = true;
          viewer.scene.globe.terrainExaggeration = Math.max(0.1, demVisual.exaggeration);
          if (typeof viewer.scene.verticalExaggeration !== "undefined") {
            viewer.scene.verticalExaggeration = Math.max(0.1, demVisual.exaggeration);
          }
        }
      }

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
        const bounds = pendingFocusBounds;
        pendingFocusBounds = null;
        if (bounds) {
          if (currentSceneMode === "2d") {
            focusLoadedRegion2D(0.6);
          } else if (currentSceneMode === "3d") {
            if (window.offlineGIS && typeof window.offlineGIS.focusBoundsWithPadding === "function") {
              window.offlineGIS.focusBoundsWithPadding(bounds.west, bounds.south, bounds.east, bounds.north, 1.2);
            }
          }
        } else if (pendingTerrainSceneAfterMorph) {
          focusPreferredRegion3D(1.0);
        }
      }
      pendingTerrainSceneAfterMorph = false;
    });
    viewer.scene.postRender.addEventListener(updateEdgeScaleWidgets);
    wireClickHandlers();
    wireStatusBarListeners();
    installSmoothInteractionManager(viewer);
    
    // Real-time mouse coordinate updates in NORMAL mode (non-comparator)
    // In comparator mode, the comparator pane listeners handle this.
    // In normal mode, we need canvas-level mousemove to update coordinates in real-time.
    let lastMouseUpdateTime = 0;
    const MOUSE_UPDATE_THROTTLE_MS = 16; // ~60 FPS for smooth updates
    viewer.canvas.addEventListener('mousemove', function(event) {
      // Skip if comparator mode (it handles its own coordinates via comparator pane listeners)
      if (typeof comparatorModeEnabled !== 'undefined' && comparatorModeEnabled) return;
      
      const now = Date.now();
      if (now - lastMouseUpdateTime < MOUSE_UPDATE_THROTTLE_MS) return;
      lastMouseUpdateTime = now;
      
      try {
        const rect = viewer.canvas.getBoundingClientRect();
        const localX = event.clientX - rect.left;
        const localY = event.clientY - rect.top;
        const screenPos = new Cesium.Cartesian2(localX, localY);
        
        // Try to get terrain-corrected position first, fallback to ray-picking
        let lonLat = null;
        if (typeof getCartesianFromViewer === 'function') {
          const cartesian = getCartesianFromViewer(viewer, screenPos);
          if (cartesian && typeof cartesianToLonLat === 'function') {
            lonLat = cartesianToLonLat(cartesian);
          }
        }
        
        if (!lonLat && typeof getLonLatFromViewer === 'function') {
          lonLat = getLonLatFromViewer(viewer, screenPos);
        }
        
        if (lonLat && typeof emitMouseCoordinates === 'function') {
          emitMouseCoordinates(Number(lonLat.lon), Number(lonLat.lat));
        }
      } catch (e) {
        log('warn', 'mousemove handler error: ' + e.message);
      }
    }, { passive: true });
    log('info', 'Real-time mouse coordinate updates enabled for main viewer (normal mode)');

    // Force a few initial renders to ensure the globe paints
    viewer.scene.requestRender();
    window.requestAnimationFrame(function () {
      viewer.scene.requestRender();
      window.requestAnimationFrame(function () {
        viewer.scene.requestRender();
      });
    });
    setStatus("Offline Cesium initialized.");
    log("info", "Viewer initialized with local offline basemap pipeline");
  }

  // ═══════════════════════════════════════════════════════════════════════════
