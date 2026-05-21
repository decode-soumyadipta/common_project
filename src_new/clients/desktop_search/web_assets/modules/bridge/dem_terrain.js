  // SECTION: DEM Terrain Rendering  →  future: modules/dem.js
  // Functions: OfflineCustomTerrainProvider (constructor + prototype),
  //   applyDemLayer, setDemColorMode, clearDemTerrainMode,
  //   updateDemColorbar, hideDemColorbar, resolveDemColorbarGradient,
  //   parseDemHeightRange, applyDemSceneSettings
  // ═══════════════════════════════════════════════════════════════════════════

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
    layerVisibilityState.set(activeDemContext.layerKey, demVisible);

    // ── 3D DEM Rendering Pipeline ──────────────────────────────────────────
    // Build the terrain provider ONLY when the DEM is first loaded or the URL changes.
    // Never rebuild for exaggeration or color mode — those are handled in-place.
    const terrainUrl = drapeUrl;
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

      if (demVisible) {
        log("info", "DEM_RENDER: Swapping to new terrain provider (DEM visible)");
        _swapTerrainProviderLocked(customTerrainProvider);
        log("info", "DEM_RENDER: Terrain provider swap complete, current provider type=" + 
            (viewer.terrainProvider === customTerrainProvider ? "CUSTOM" : "OTHER"));
      }
    } else if (demVisible && viewer.terrainProvider !== activeDemTerrainProvider) {
      // Re-show after hide — reuse existing provider, no rebuild
      log("info", "DEM_RENDER: Reusing existing terrain provider (was hidden, now visible)");
      _swapTerrainProviderLocked(activeDemTerrainProvider);
      log("info", "DEM_RENDER: Terrain provider reactivated");
    } else if (demVisible) {
      log("info", "DEM_RENDER: Terrain provider already active, no swap needed");
    }

    log("info", "DEM_RENDER: Current terrain provider: " + 
        (viewer.terrainProvider === activeDemTerrainProvider ? "CUSTOM_DEM" : "ELLIPSOID"));
    // ───────────────────────────────────────────────────────────────────────


    // Always clean up hillshade when drape URL changes to ensure proper layer rebuild
    const drapeUrlChanged = activeDemDrapeUrl !== drapeUrl;
    if (drapeUrlChanged && activeDemHillshadeLayer) {
      viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
      
      // CRITICAL FIX: Remove old DEM hillshade layer from managedImageryLayers map
      if (activeDemContext && activeDemContext.layerKey) {
        managedImageryLayers.delete(activeDemContext.layerKey + ":hillshade");
      }
      
      activeDemHillshadeLayer = null;
      activeDemHillshadeUrl = null;
    }

    if (!activeDemDrapeLayer || drapeUrlChanged) {
      if (activeDemDrapeLayer) {
        viewer.imageryLayers.remove(activeDemDrapeLayer, false);
        
        // CRITICAL FIX: Remove old DEM drape layer from managedImageryLayers map
        if (activeDemContext && activeDemContext.layerKey) {
          managedImageryLayers.delete(activeDemContext.layerKey);
        }
        
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
    
    // Always create the hillshade layer, even if alpha is 0.
    // This allows the slider to update alpha in real-time without needing a full DEM rebuild.
    if (activeDemHillshadeLayer && activeDemHillshadeUrl !== hillshadeUrl) {
      viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
      
      // CRITICAL FIX: Remove old DEM hillshade layer from managedImageryLayers map
      if (activeDemContext && activeDemContext.layerKey) {
        managedImageryLayers.delete(activeDemContext.layerKey + ":hillshade");
      }
      
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
      
      // CRITICAL FIX: Tag DEM hillshade layer with key for reordering functionality
      // Use a different key suffix to distinguish from drape layer
      const hillshadeKey = activeDemContext.layerKey + ":hillshade";
      activeDemHillshadeLayer._layerKey = hillshadeKey;
      activeDemHillshadeLayer._layerName = activeDemContext.name + " (Hillshade)";
      
      // CRITICAL FIX: Add DEM hillshade layer to managedImageryLayers for reordering
      managedImageryLayers.set(hillshadeKey, activeDemHillshadeLayer);
      
      log("info", "DEM_RENDER: Hillshade layer added at index " + viewer.imageryLayers.indexOf(activeDemHillshadeLayer));
    }
    activeDemHillshadeLayer.alpha = clampedHillshadeAlpha;
    activeDemHillshadeLayer.show = demVisible;

    applyDemSceneSettings();
    
    // CRITICAL FIX: Only ensure basemap is at bottom, don't force other layer positions
    // This allows user reordering to work properly without conflicts
    log("info", "DEM_RENDER: Ensuring basemap at bottom (preserving user layer order)");
    
    // Step 1: Ensure basemap is at the very bottom (index 0) - this is essential
    if (osmBasemapLayer && osmBasemapLayer.show && viewer.imageryLayers.indexOf(osmBasemapLayer) >= 0) {
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
        
        // CRITICAL: Timeout for terabyte-scale data (prevent infinite hangs)
        const timeoutId = setTimeout(() => {
          img.onload = null;
          img.onerror = null;
          // Return flat tile on timeout (prevents black screens)
          const output = new Float32Array(TERRAIN_SAMPLE_SIZE * TERRAIN_SAMPLE_SIZE);
          resolve(new Cesium.HeightmapTerrainData({
            buffer: output,
            width: TERRAIN_SAMPLE_SIZE,
            height: TERRAIN_SAMPLE_SIZE,
            // Use unit scale; exaggeration is applied via globe.terrainExaggeration for live updates.
            structure: { heightScale: 1.0, heightOffset: 0.0, elementsPerHeight: 1, stride: 1 }
          }));
        }, 5000);  // 5 second timeout for ultra-high resolution tiles
        
        img.onload = () => {
          clearTimeout(timeoutId);
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
            // Use unit scale; exaggeration is applied via globe.terrainExaggeration for live updates.
            structure: { heightScale: 1.0, heightOffset: 0.0, elementsPerHeight: 1, stride: 1 }
          }));
        };
        
        img.onerror = () => {
          clearTimeout(timeoutId);
          img.onload = null;
          img.onerror = null;
          // Return flat tile on error (prevents black screens)
          const output = new Float32Array(TERRAIN_SAMPLE_SIZE * TERRAIN_SAMPLE_SIZE);
          resolve(new Cesium.HeightmapTerrainData({
            buffer: output,
            width: TERRAIN_SAMPLE_SIZE,
            height: TERRAIN_SAMPLE_SIZE,
            // Use unit scale; exaggeration is applied via globe.terrainExaggeration for live updates.
            structure: { heightScale: 1.0, heightOffset: 0.0, elementsPerHeight: 1, stride: 1 }
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
    } else {
      // Returning to gray/terrain: preserve current rescale if it exists, otherwise use original
      delete query.algorithm;
      query.colormap_name = normalized;
      
      // SYNC FIX: If a stretch is already applied, keep it!
      const currentStretch = activeDemDrapeLayer && activeDemDrapeLayer._stretchSettings;
      if (currentStretch && currentStretch.params && currentStretch.params.min !== undefined) {
        query.rescale = currentStretch.params.min.toFixed(1) + "," + currentStretch.params.max.toFixed(1);
      } else if (_demOriginalRescale) {
        query.rescale = _demOriginalRescale;
      }
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
        activeDemDrapeLayer = viewer.imageryLayers.addImageryProvider(drapeProvider);
        activeDemDrapeLayer.alpha = 1.0;
        activeDemDrapeLayer.show = activeDemContext.visible !== false;
        activeDemDrapeUrl = newDrapeUrl;
        
        // CRITICAL FIX: Tag the new drape layer with its key so the reordering system 
        // can find and position it correctly.
        activeDemDrapeLayer._layerKey = activeDemContext.layerKey;
        activeDemDrapeLayer._layerName = activeDemContext.name;
        
        // SYNC FIX: Preserve stretch settings from old layer to new layer for real-time coordination
        if (oldDrapeLayer && oldDrapeLayer._stretchSettings) {
          activeDemDrapeLayer._stretchSettings = oldDrapeLayer._stretchSettings;
          log("debug", "setDemColorMode: preserved stretch settings on new drape layer");
        }
        
        managedImageryLayers.set(activeDemContext.layerKey, activeDemDrapeLayer);

        // Clean up the old layer quickly — 200ms is enough for 2-3 new tiles to arrive
        // avoiding the black flash while still feeling near-instant to the user
        if (oldDrapeLayer) {
          setTimeout(() => {
            if (viewer && viewer.imageryLayers && viewer.imageryLayers.contains(oldDrapeLayer)) {
              viewer.imageryLayers.remove(oldDrapeLayer, false);
            }
          }, 120); // Faster cleanup for "fast" requirement
        }

        // Re-apply the last known layer display order so imagery stays on top (or below)
        // without requiring a Python round-trip. This prevents color-mode changes from
        // breaking the layer stack the user explicitly arranged.
        if (_lastKnownLayerOrder && _lastKnownLayerOrder.length > 0) {
          // Small defer so the new provider settles before reordering
          setTimeout(function() {
            if (window.offlineGIS && window.offlineGIS.enforceLayerDisplayOrder) {
              window.offlineGIS.enforceLayerDisplayOrder(_lastKnownLayerOrder);
            }
          }, 0);
        } else {
          // Fallback: raise hillshade and managed imagery layers above new drape
          if (activeDemHillshadeLayer) viewer.imageryLayers.raiseToTop(activeDemHillshadeLayer);
          for (const layer of managedImageryLayers.values()) {
            if (layer && layer.show && viewer.imageryLayers.indexOf(layer) >= 0) {
              viewer.imageryLayers.raiseToTop(layer);
            }
          }
        }

        // Removed camera locking to prevent jumping when changing color modes

        requestSceneRender();
        log("debug", "setDemColorMode: in-place drape swap colormap=" + normalized);

        // SYNC FIX: Update colorbar gradient to match new color mode AND current stretch
        // Use the actual rescale from the query (which includes stretch if applied)
        const range = parseDemHeightRange({ query: query }); // Use updated query for accurate range
        updateDemColorbar(range.min, range.max, activeDemContext.options);
        
        // SYNC FIX: Also update activeDemContext.options.query to keep it in sync
        activeDemContext.options.query = query;
        
        log("info", "DEM color mode changed to " + normalized + " with rescale=" + query.rescale);
      }
    } else {
      // No active drape layer yet — do a full apply with camera lock
      // CRITICAL FIX (Bug 4): Prevent applyDemLayer from resetting camera
      // when changing style dropdown
      if (viewer && viewer.camera) {
        var savedPos = viewer.camera.position.clone();
        var savedHdg = viewer.camera.heading;
        var savedPitch = viewer.camera.pitch;
        var savedRoll = viewer.camera.roll;
        applyDemLayer();
        // Lock camera for 5 frames to absorb async resets from layer changes
        var framesLeft = 5;
        var lockHandle = viewer.scene.postRender.addEventListener(function () {
          viewer.camera.setView({
            destination: savedPos,
            orientation: { heading: savedHdg, pitch: savedPitch, roll: savedRoll },
          });
          framesLeft -= 1;
          if (framesLeft <= 0) lockHandle();
        });
      } else {
        applyDemLayer();
      }
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
    const baseSse = Number(scene.globe.maximumScreenSpaceError) || 2.0;
    const movingSse = Math.max(4.0, baseSse + 2.0);
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
    }

    function applyInteractionTilePolicy(active) {
      if (!scene.globe) {
        return;
      }
      // Keep tile preloading enabled during interaction to reduce choppy pans/zooms
      // without lowering imagery or terrain quality.
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
    if (viewer && viewer.scene && viewer.scene.screenSpaceCameraController) {
      viewer.scene.screenSpaceCameraController.enableZoom = false;
    }

    const WHEEL_ZOOM_STEP = 0.15;  // 15% of current altitude per tick — snappier
    let wheelZoomImpulse = 0;
    let wheelZoomRaf = null;

    canvas.addEventListener("wheel", function (event) {
      event.preventDefault();
      if (!targetViewer || !targetViewer.scene || !targetViewer.camera) {
        return;
      }
      startInteraction();

      const delta = event.deltaY !== 0 ? event.deltaY : -event.wheelDelta;
      wheelZoomImpulse += delta < 0 ? 1 : -1;

      if (wheelZoomRaf !== null) {
        return;
      }

      wheelZoomRaf = window.requestAnimationFrame(function () {
        wheelZoomRaf = null;
        const camera = targetViewer.camera;
        const scene = targetViewer.scene;

        const posCart = camera.positionCartographic;
        if (!posCart || !Number.isFinite(posCart.height)) {
          wheelZoomImpulse = 0;
          scheduleIdle();
          return;
        }

        const altitude = Math.max(posCart.height, 50.0);
        const stepCount = Math.max(-10, Math.min(10, wheelZoomImpulse));
        const zoomAmount = altitude * WHEEL_ZOOM_STEP * Math.abs(stepCount || 1);
        const zoomingIn = stepCount > 0;
        wheelZoomImpulse = 0;

        if (scene.mode === Cesium.SceneMode.SCENE2D) {
          if (zoomingIn) {
            camera.zoomIn(zoomAmount);
          } else {
            camera.zoomOut(zoomAmount);
          }
        } else {
          const direction = camera.direction ? camera.direction.clone() : null;
          if (!direction) {
            scheduleIdle();
            return;
          }
          if (!zoomingIn) {
            Cesium.Cartesian3.negate(direction, direction);
          }

          const move = Cesium.Cartesian3.multiplyByScalar(direction, zoomAmount, new Cesium.Cartesian3());
          const nextPos = Cesium.Cartesian3.add(camera.position, move, new Cesium.Cartesian3());
          const nextCarto = Cesium.Cartographic.fromCartesian(nextPos);
          if (nextCarto && Number.isFinite(nextCarto.height) && nextCarto.height >= 10.0) {
            camera.setView({
              destination: nextPos,
              orientation: {
                heading: camera.heading,
                pitch: camera.pitch,
                roll: camera.roll,
              },
            });
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
    // CRITICAL PATCH: Handle statusCode 0 for local Assets (Windows/file://)
    // ─────────────────────────────────────────────────────────────────────────
    if (Cesium.Resource && Cesium.Resource.prototype && Cesium.Resource.prototype.fetchJson) {
      const originalFetchJson = Cesium.Resource.prototype.fetchJson;
      Cesium.Resource.prototype.fetchJson = function() {
        const reqUrl = String(this.url || "");
        
        const handleRejection = function(error) {
          if (error && error.statusCode === 0 && typeof error.response === "string") {
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
    viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#2a3a4a");
    viewer.scene.backgroundColor = Cesium.Color.fromCssColorString("#0a0a0a");
    viewer.canvas.style.backgroundColor = "#0a0a0a";
    
    // Performance optimizations for ultra-smooth interaction
    viewer.useDefaultRenderLoop = true;
    viewer.scene.requestRenderMode = false; // Always live for maximum smoothness
    viewer.scene.maximumRenderTimeChange = 0;
    viewer.scene.globe.maximumScreenSpaceError = 1.0; // High quality terrain
    viewer.scene.globe.tileCacheSize = 800;  // Larger cache for ultra-smooth panning (optimized for Windows/NVIDIA)
    viewer.scene.fog.enabled = false;  // Disable fog for performance
    viewer.scene.skyAtmosphere.show = false;  // Disable atmosphere for performance
    viewer.scene.sun.show = false;  // Disable sun for performance
    viewer.scene.moon.show = false;  // Disable moon for performance
    viewer.scene.skyBox.show = false;  // Disable skybox for performance
    viewer.scene.globe.showGroundAtmosphere = false;  // Disable ground atmosphere
    viewer.scene.globe.enableLighting = false;  // Disable lighting for performance
    viewer.scene.globe.depthTestAgainstTerrain = true;  // Required for proper DEM layer sorting and occlusion
    
    // Optimize tile loading for smoother experience
    viewer.scene.globe.maximumScreenSpaceError = 3;  // Optimized for faster loading while maintaining quality
    viewer.scene.globe.preloadAncestors = true;  // Preload for smoother zooming
    viewer.scene.globe.preloadSiblings = true;  // Preload for smoother panning
    
    // Additional performance optimizations
    viewer.scene.fxaa = false;  // Disable FXAA post-processing
    viewer.scene.highDynamicRange = false;  // Disable HDR for performance
    viewer.scene.logarithmicDepthBuffer = true;  // Required for smooth 3D camera dragging and Z-fighting prevention
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
            // Detect dedicated GPUs (NVIDIA, AMD Radeon RX/Pro)
            if (r.indexOf("nvidia") !== -1 || r.indexOf("rtx") !== -1 || r.indexOf("gtx") !== -1 || 
                r.indexOf("quadro") !== -1 || (r.indexOf("amd") !== -1 && r.indexOf("radeon rx") !== -1)) {
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
      // ── MAX CONFIG (NVIDIA / Quadro) ──────────────────────────────────────
      MAX_CONCURRENT_TERRAIN_DECODES = 8;   // Parallel terrain decodes for workstation
      viewer.resolutionScale = 1.0;          // Full native resolution
      viewer.scene.logarithmicDepthBuffer = true;
      viewer.scene.globe.depthTestAgainstTerrain = true;
      viewer.scene.globe.tileCacheSize = 1000; // Large cache for high-fidelity assets
      viewer.scene.globe.maximumScreenSpaceError = 0.8; // Ultra fidelity for workstation
      viewer.scene.globe.preloadAncestors = true;
      viewer.scene.globe.preloadSiblings = true;
      viewer.scene.globe.loadingDescendantLimit = 16;
      
      // NVIDIA GL hint
      if (viewer.scene.context && viewer.scene.context._gl) {
        const gl = viewer.scene.context._gl;
        gl.hint(gl.GENERATE_MIPMAP_HINT, gl.FASTEST);
      }
      
      log("info", "[INIT MAX GPU CONFIG] NVIDIA/Quadro workstation GPU detected — Extreme fidelity enabled");
    } else {
      // ── SAFE CONFIG (Intel integrated / unknown) ──────────────────────────
      MAX_CONCURRENT_TERRAIN_DECODES = 2;   // Slightly more parallel decodes for modern Intel
      viewer.resolutionScale = 1.0;          // Full native resolution to maintain imagery quality
      viewer.scene.logarithmicDepthBuffer = true;
      viewer.scene.globe.depthTestAgainstTerrain = true; // Essential for true 3D fidelity
      viewer.scene.globe.tileCacheSize = 400;  // Optimized cache for smoother panning on Windows
      viewer.scene.globe.maximumScreenSpaceError = 3.5;  // Balanced performance/quality for Intel UHD
      viewer.scene.globe.preloadAncestors = true; // Enabled for smoother zoom transitions
      viewer.scene.globe.preloadSiblings = true;
      viewer.scene.globe.loadingDescendantLimit = 2;  // Faster tile loading
      
      log("info", "[INIT SAFE INTEL CONFIG] Integrated GPU optimized for smooth performance (res=1.0 sse=3.5 cache=400)");
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
        if (viewer && viewer.scene) {
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
          if (viewer && viewer.scene) {
            // Force scene re-render
            viewer.scene.requestRenderMode = false;
            viewer.scene.requestRender();
            setTimeout(function() {
              if (viewer && viewer.scene) {
                viewer.scene.requestRenderMode = false;
                viewer.scene.requestRender();
              }
            }, 250);
            
            // Reload all active layers
            log("info", "Reloading active layers after context restoration");
            
            // Reload DEM if active
            if (activeDemContext && activeDemContext.visible) {
              log("info", "Reloading DEM layer: " + activeDemContext.name);
              applyDemLayer();
            }
            
            // Reload imagery layers
            for (const [layerKey, layer] of managedImageryLayers.entries()) {
              if (layer && layer.show) {
                log("info", "Reloading imagery layer: " + layerKey);
                // Layer will be reloaded automatically by Cesium
              }
            }
            
            // Reload OSM basemap if visible
            if (osmBasemapLayer && osmBasemapLayer.show) {
              log("info", "Reloading OSM basemap");
              // OSM will be reloaded automatically by Cesium
            }
            
            if (viewer && viewer.scene) {
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
      // Fallback: Use a solid color if NaturalEarthII is not available
      log("warn", "Failed to add default Earth layer: " + e.message);
      viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#2a3a4a");
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
        const bounds = pendingFocusBounds;
        pendingFocusBounds = null;
        if (bounds) {
          if (currentSceneMode === "2d") {
            focusLoadedRegion2D(0.6);
          } else if (window.offlineGIS && typeof window.offlineGIS.focusBoundsWithPadding === "function") {
            window.offlineGIS.focusBoundsWithPadding(bounds.west, bounds.south, bounds.east, bounds.north, 1.2);
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
