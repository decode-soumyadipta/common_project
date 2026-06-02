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
      
      
      function resolveTileTemplateUrl(template, providerRef, errorRef) {
        if (!template || !errorRef) {
          return "";
        }
        let url = String(template);
        let yValue = errorRef.y;
        if (url.indexOf("{reverseY}") >= 0) {
          try {
            if (providerRef && providerRef.tilingScheme && typeof providerRef.tilingScheme.getNumberOfYTilesAtLevel === "function") {
              const total = providerRef.tilingScheme.getNumberOfYTilesAtLevel(errorRef.level);
              yValue = total - errorRef.y - 1;
            }
          } catch (_err) {
            yValue = errorRef.y;
          }
        }
        url = url.replace("{z}", String(errorRef.level));
        url = url.replace("{x}", String(errorRef.x));
        url = url.replace("{y}", String(errorRef.y));
        url = url.replace("{reverseY}", String(yValue));
        return url;
      }

      let templateUrlForError = "";
      try {
        templateUrlForError = String(provider && provider.url ? provider.url : "");
      } catch (_err) {
        templateUrlForError = "";
      }
      const resolvedTileUrl = resolveTileTemplateUrl(templateUrlForError, provider, error);

      // Log tile errors at debug level to keep standard logs clean, since edge tile 404s
      // are normal boundary occurrences in web GIS applications. Do NOT hide/disable layers.
      log("debug", "TILE_ERROR: provider=" + name + 
          " count=" + currentCount + 
          " z=" + error.level + 
          " x=" + error.x + 
          " y=" + error.y + 
          " msg=" + msg +
          " url=" + (error.url || resolvedTileUrl || templateUrlForError || "unknown"));
      
      // Log tile coordinate analysis for debugging only on first error at debug level
      if (provider.rectangle && currentCount === 1) {
        const rect = provider.rectangle;
        const westDeg = Cesium.Math.toDegrees(rect.west);
        const southDeg = Cesium.Math.toDegrees(rect.south);
        const eastDeg = Cesium.Math.toDegrees(rect.east);
        const northDeg = Cesium.Math.toDegrees(rect.north);
        
        log("debug", "Tile error in bounds: west=" + westDeg.toFixed(3) + 
            " south=" + southDeg.toFixed(3) + 
            " east=" + eastDeg.toFixed(3) + 
            " north=" + northDeg.toFixed(3) +
            " requested z=" + error.level + " x=" + error.x + " y=" + error.y);
      }
      
      if (currentCount === 1) {
        if (templateUrlForError) {
          log("debug", "TILE_DEBUG: Template URL for " + name + " => " + templateUrlForError);
        }
        if (resolvedTileUrl) {
          log("debug", "TILE_DEBUG: Sample tile URL for " + name + " => " + resolvedTileUrl);
        }
        
        // Log provider details
        log("debug", "TILE_DEBUG: Provider details for " + name + 
            " ready=" + (provider.ready || false) +
            " tilingScheme=" + (provider.tilingScheme ? provider.tilingScheme.constructor.name : "none") +
            " minLevel=" + (provider.minimumLevel || "unknown") +
            " maxLevel=" + (provider.maximumLevel || "unknown") +
            " rectangle=" + (provider.rectangle ? "defined" : "undefined"));
      }
      
      if (currentCount <= 10 || currentCount % 25 === 0) {
        log(
          "debug",
          "TILE_DEBUG: Repeated tile error for " +
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
    
    // Add success logging for first few tiles
    if (provider.readyPromise && typeof provider.readyPromise.then === "function") {
      provider.readyPromise.then(
        function () {
          log("debug", "Provider ready: " + name);
        },
        function (err) {
          log("error", "Provider ready failed: " + name + " - " + String(err));
        }
      );
    }
  }

  function clearDemTerrainMode() {
    if (!viewer) return;
    const previousDemLayerKey = activeDemContext && activeDemContext.layerKey ? activeDemContext.layerKey : null;
    if (activeDemDrapeLayer) {
      viewer.imageryLayers.remove(activeDemDrapeLayer, false);
      
      // CRITICAL FIX: Remove DEM drape layer from managedImageryLayers map
      if (previousDemLayerKey) {
        managedImageryLayers.delete(previousDemLayerKey);
      }
      
      activeDemDrapeLayer = null;
    }
    if (activeDemHillshadeLayer) {
      viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
      
      // CRITICAL FIX: Remove DEM hillshade layer from managedImageryLayers map
      if (previousDemLayerKey) {
        managedImageryLayers.delete(previousDemLayerKey + ":hillshade");
      }
      
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
    viewer.terrainProvider = new Cesium.EllipsoidTerrainProvider();
    applyDefaultSceneSettings();
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
      
      // CRITICAL FIX: Don't remove DEM layers when clearing imagery layers
      // DEM drape and hillshade layers should only be removed via clearDemTerrainMode
      if (activeDemContext && activeDemContext.layerKey === layerKey) {
        log("debug", "clearManagedImageryLayers: Preserving DEM layer " + layerKey);
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

  function addVectorLayer(layerKey, label, geojson, options) {
    if (!viewer || !viewer.dataSources) {
      return;
    }
    const key = String(layerKey || label || "vector");
    const name = String(label || layerKey || "Vector");
    const opts = options || {};
    let payload = geojson;
    try {
      if (typeof payload === "string") {
        payload = JSON.parse(payload);
      }
    } catch (e) {
      log("error", "Vector parse failed key=" + key + " err=" + e.message);
      return;
    }

    if (vectorLayerSources.has(key)) {
      const existing = vectorLayerSources.get(key);
      try {
        viewer.dataSources.remove(existing, true);
      } catch (_) {}
      vectorLayerSources.delete(key);
    }

    Cesium.GeoJsonDataSource.load(payload, {
      clampToGround: opts.clampToGround !== false,
      stroke: Cesium.Color.fromCssColorString(opts.stroke || "#ffcc00"),
      fill: Cesium.Color.fromCssColorString(opts.fill || "#ffcc00").withAlpha(0.25),
      strokeWidth: Number(opts.strokeWidth || 2),
    }).then(function (dataSource) {
      dataSource.name = name;
      dataSource.show = opts.visible !== false;
      dataSource._layerKey = key;
      viewer.dataSources.add(dataSource);
      vectorLayerSources.set(key, dataSource);
      requestSceneRender();
      log("info", "Vector layer added key=" + key + " name=" + name);
    }, function (err) {
      log("error", "Vector layer load failed key=" + key + " err=" + String(err));
    });
  }

  function removeVectorLayer(layerKey) {
    if (!viewer || !viewer.dataSources) {
      return;
    }
    const key = String(layerKey || "");
    if (!vectorLayerSources.has(key)) {
      return;
    }
    const dataSource = vectorLayerSources.get(key);
    try {
      viewer.dataSources.remove(dataSource, true);
    } catch (_) {}
    vectorLayerSources.delete(key);
    requestSceneRender();
    log("info", "Vector layer removed key=" + key);
  }

  function setVectorLayerVisibility(layerKey, visible) {
    const key = String(layerKey || "");
    if (!vectorLayerSources.has(key)) {
      return;
    }
    const dataSource = vectorLayerSources.get(key);
    dataSource.show = Boolean(visible);
    requestSceneRender();
  }

  function syncSceneModeForDemVisibility() {
    if (!viewer || typeof setSceneModeInternal !== "function") {
      return;
    }
    const demVisible = !!(activeDemContext && activeDemContext.visible !== false);
    if (demVisible) {
      if (currentSceneMode !== "3d") {
        setSceneModeInternal("3d");
      }
      return;
    }
    if (currentSceneMode !== "2d") {
      setSceneModeInternal("2d");
    }
  }

  function clearVectorLayers() {
    if (!viewer || !viewer.dataSources) {
      vectorLayerSources.clear();
      return;
    }
    for (const [key, dataSource] of Array.from(vectorLayerSources.entries())) {
      try {
        viewer.dataSources.remove(dataSource, true);
      } catch (_) {}
      vectorLayerSources.delete(key);
    }
    requestSceneRender();
  }

  function setLayerVisibilityByKey(layerKey, visible) {
    console.log(`DEBUG: setLayerVisibilityByKey called: layerKey=${layerKey}, visible=${visible}`);
    
    if (!viewer || !layerKey) {
      console.warn("DEBUG: setLayerVisibilityByKey - invalid viewer or layerKey");
      return false;
    }
    layerVisibilityState.set(layerKey, Boolean(visible));
    console.log(`DEBUG: Updated layerVisibilityState for ${layerKey} = ${Boolean(visible)}`);

    // CRITICAL FIX: Check if this is a DEM layer FIRST before treating it as regular imagery
    // DEM layers need special handling for terrain provider swapping
    if (activeDemContext && activeDemContext.layerKey === layerKey) {
      const shouldShow = Boolean(visible);
      console.log(`DEBUG: Found DEM layer for ${layerKey}, setting visible=${shouldShow}`);
      activeDemContext.visible = shouldShow;
      if (activeDemDrapeLayer) {
        activeDemDrapeLayer.show = shouldShow;
        console.log(`DEBUG: DEM drape layer show=${shouldShow}`);
      }
      if (activeDemHillshadeLayer) {
        activeDemHillshadeLayer.show = shouldShow && activeDemHillshadeLayer.alpha > 0.01;
        console.log(`DEBUG: DEM hillshade layer show=${shouldShow && activeDemHillshadeLayer.alpha > 0.01}`);
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
          if (typeof viewer.scene.verticalExaggeration !== "undefined") {
            viewer.scene.verticalExaggeration = Math.max(0.1, demVisual.exaggeration);
          }
          log("debug", "DEM show: re-applied terrainExaggeration=" + demVisual.exaggeration.toFixed(2));
        }
        if (currentSceneMode !== "3d") {
          setSceneModeInternal("3d");
        }
      } else {
        hideDemColorbar();
        setSceneModeControlEnabled(true);
        setStatus("DEM layer hidden.");
        log("info", "DEM layer hidden key=" + layerKey);
        viewer.terrainProvider = new Cesium.EllipsoidTerrainProvider();
        if (viewer && viewer.scene && viewer.scene.globe) {
          viewer.scene.globe.terrainExaggeration = 1.0;
          if (typeof viewer.scene.verticalExaggeration !== "undefined") {
            viewer.scene.verticalExaggeration = 1.0;
          }
        }
      }
      const anyVisible = Array.from(layerVisibilityState.values()).some(Boolean);
      if (!anyVisible) {
        if (activeDemDrapeLayer) {
          activeDemDrapeLayer.show = false;
        }
        if (activeDemHillshadeLayer) {
          activeDemHillshadeLayer.show = false;
        }
      }
      if (comparatorModeEnabled) {
        refreshComparatorLayers();
      }
      requestSceneRender();
      return true;
    }

    const imageryLayer = managedImageryLayers.get(layerKey);
    if (imageryLayer) {
      const shouldShow = Boolean(visible);
      console.log(`DEBUG: Found imagery layer for ${layerKey}, setting show=${shouldShow}`);
      imageryLayer.show = shouldShow;
      if (shouldShow) {
        activeImageryLayer = imageryLayer;
      } else if (activeImageryLayer === imageryLayer) {
        activeImageryLayer = null;
      }
      const anyVisible = Array.from(layerVisibilityState.values()).some(Boolean);
      if (!anyVisible) {
        if (activeDemDrapeLayer) {
          activeDemDrapeLayer.show = false;
        }
        if (activeDemHillshadeLayer) {
          activeDemHillshadeLayer.show = false;
        }
      }
      applySwipeComparatorSplit();
      if (comparatorModeEnabled) {
        refreshComparatorLayers();
      }
      requestSceneRender();
      console.log(`DEBUG: Imagery layer visibility updated successfully for ${layerKey}`);
      return true;
    }

    return false;
  }

  // ═══════════════════════════════════════════════════════════════════════════
