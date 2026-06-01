  window.offlineGIS = window.offlineGIS || {};
  Object.assign(window.offlineGIS, {
      setCameraState: function (lon, lat, height, heading, pitch, roll) {
        if (!viewer) return;
        try {
          viewer.camera.cancelFlight();
          viewer.camera.setView({
            destination: Cesium.Cartesian3.fromDegrees(lon, lat, height),
            orientation: {
              heading: Cesium.Math.toRadians(heading),
              pitch: Cesium.Math.toRadians(pitch),
              roll: Cesium.Math.toRadians(roll)
            }
          });
          requestSceneRender();
          log("info", "Restored camera state lon=" + lon + " lat=" + lat + " height=" + height);
        } catch (e) {
          log("error", "setCameraState failed: " + e);
        }
      },

      // NOTE: focusBoundsWithPadding is defined further below (authoritative definition).
      // An earlier duplicate was removed — Object.assign last-write-wins, so the first
      // copy was dead code and has been eliminated to prevent reader confusion.
      instantFocusBounds: function (west, south, east, north) {
        if (!viewer) return;
        try {
          const padLon = (east - west) * 0.15;
          const padLat = (north - south) * 0.15;
          const paddedWest  = Math.max(-180, west  - padLon);
          const paddedEast  = Math.min( 180, east  + padLon);
          const paddedSouth = Math.max( -90, south - padLat);
          const paddedNorth = Math.min(  90, north + padLat);
          const rect = Cesium.Rectangle.fromDegrees(paddedWest, paddedSouth, paddedEast, paddedNorth);
          const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
          const range = Math.max(compute3DFocusRange({ west: paddedWest, south: paddedSouth, east: paddedEast, north: paddedNorth }), sphere.radius * 1.5, 300.0);
          
          viewer.camera.cancelFlight();
          
          // Disable requestRenderMode temporarily to let tiles stream in
          viewer.scene.requestRenderMode = false;
          
          // setView is instant — no animation, just teleport
          viewer.camera.viewBoundingSphere(sphere, new Cesium.HeadingPitchRange(
            Cesium.Math.toRadians(0.0),
            Cesium.Math.toRadians(-40.0),
            range
          ));
          
          // Reset the transform so camera control/navigation is not locked to the sphere's center
          viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
          
          // Continuous render for 2.0s post-snap so tiles finish loading
          var t = 0;
          var iv = setInterval(function() {
            if (!viewer || !viewer.scene) { clearInterval(iv); return; }
            viewer.scene.requestRender();
            t += 100;
            if (t >= 2000) { 
              clearInterval(iv); 
              viewer.scene.requestRenderMode = true; 
              viewer.scene.requestRender();
            }
          }, 100);
          
          log("info", "Instant focus bounds west=" + west + " south=" + south + " east=" + east + " north=" + north);
        } catch(e) {
          log("error", "instantFocusBounds failed: " + e);
          if (viewer && viewer.scene) {
            viewer.scene.requestRenderMode = true;
          }
        }
      },

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
        const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
        const range = Math.max(compute3DFocusRange({ west, south, east, north }), sphere.radius * 1.5, 300.0);
        // Persist range so pitch slider can orbit without recomputing live distance
        _cameraOrbitRange = range;
        // Keep rendering active during AND after flight so tiles stream in with no blank globe
        viewer.scene.requestRenderMode = false;
        viewer.camera.cancelFlight();
        viewer.camera.flyToBoundingSphere(sphere, {
          offset: new Cesium.HeadingPitchRange(
            Cesium.Math.toRadians(0.0),
            Cesium.Math.toRadians(-40.0),
            range
          ),
          duration: 2.0,
          complete: function() {
            if (!viewer || !viewer.scene) return;
            // Hold continuous render for 1.5s post-flight so tiles finish loading
            var t = 0;
            var iv = setInterval(function() {
              if (!viewer || !viewer.scene) { clearInterval(iv); return; }
              viewer.scene.requestRender();
              t += 100;
              if (t >= 1500) { clearInterval(iv); viewer.scene.requestRenderMode = true; }
            }, 100);
          },
          cancel: function() {
            if (viewer && viewer.scene) {
              viewer.scene.requestRenderMode = true;
              viewer.scene.requestRender();
            }
          }
        });
        requestSceneRender();
        log("info", "Fly-to bounds (3D oblique) west=" + west + " south=" + south + " east=" + east + " north=" + north);
      },
      focusBounds: function (west, south, east, north) {
        if (!viewer) return;
        setActiveTileBounds({ west: west, south: south, east: east, north: north });
        const padLon = (east - west) * 0.10;
        const padLat = (north - south) * 0.10;
        const paddedWest  = Math.max(-180, west  - padLon);
        const paddedEast  = Math.min( 180, east  + padLon);
        const paddedSouth = Math.max( -90, south - padLat);
        const paddedNorth = Math.min(  90, north + padLat);
        const rect = Cesium.Rectangle.fromDegrees(paddedWest, paddedSouth, paddedEast, paddedNorth);
        const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
        const range = Math.max(compute3DFocusRange({ west: paddedWest, south: paddedSouth, east: paddedEast, north: paddedNorth }), sphere.radius * 1.5, 300.0);
        // Persist range so pitch slider can orbit without recomputing live distance
        _cameraOrbitRange = range;
        viewer.scene.requestRenderMode = false;
        viewer.camera.cancelFlight();
        viewer.camera.flyToBoundingSphere(sphere, {
          offset: new Cesium.HeadingPitchRange(
            Cesium.Math.toRadians(0.0),
            Cesium.Math.toRadians(-40.0),
            range
          ),
          duration: 1.2,
          complete: function() {
            if (!viewer || !viewer.scene) return;
            var t = 0;
            var iv = setInterval(function() {
              if (!viewer || !viewer.scene) { clearInterval(iv); return; }
              viewer.scene.requestRender();
              t += 100;
              if (t >= 1500) { clearInterval(iv); viewer.scene.requestRenderMode = true; }
            }, 100);
          },
          cancel: function() {
            if (viewer && viewer.scene) {
              viewer.scene.requestRenderMode = true;
              viewer.scene.requestRender();
            }
          }
        });
        requestSceneRender();
        log("debug", "Focus bounds (3D oblique) west=" + west + " south=" + south + " east=" + east + " north=" + north);
      },
      focusBoundsWithPadding: function (west, south, east, north, paddingFactor) {
        if (!viewer) return;
        // Use custom padding factor (e.g., 1.5 = 50% padding)
        const padFactor = Number(paddingFactor) || 1.1; // Default to 10% if not specified
        const padLon = (east - west) * (padFactor - 1.0) * 0.5;
        const padLat = (north - south) * (padFactor - 1.0) * 0.5;
        const paddedWest  = Math.max(-180, west  - padLon);
        const paddedEast  = Math.min( 180, east  + padLon);
        const paddedSouth = Math.max( -90, south - padLat);
        const paddedNorth = Math.min(  90, north + padLat);
        setActiveTileBounds({ west: west, south: south, east: east, north: north });
        // SEARCH FIX: Use 3D oblique view (-40° pitch) so search results appear on the globe
        const rect = Cesium.Rectangle.fromDegrees(paddedWest, paddedSouth, paddedEast, paddedNorth);
        const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
        const range = Math.max(compute3DFocusRange({ west: paddedWest, south: paddedSouth, east: paddedEast, north: paddedNorth }), sphere.radius * 1.5, 300.0);
        const wasRequestRenderMode = viewer.scene.requestRenderMode;
        viewer.scene.requestRenderMode = false;
        viewer.camera.cancelFlight();
        viewer.camera.flyToBoundingSphere(sphere, {
          offset: new Cesium.HeadingPitchRange(
            Cesium.Math.toRadians(0.0),
            Cesium.Math.toRadians(-40.0),  // 40° oblique — clear 3D globe perspective
            range
          ),
          duration: 1.8, // Slightly longer duration for multi-asset focus
          complete: function() {
            if (viewer && viewer.scene) {
              viewer.scene.requestRenderMode = wasRequestRenderMode;
              viewer.scene.requestRender();
            }
          },
          cancel: function() {
            if (viewer && viewer.scene) {
              viewer.scene.requestRenderMode = wasRequestRenderMode;
              viewer.scene.requestRender();
            }
          }
        });
        requestSceneRender();
        log("info", "Focus bounds with padding=" + padFactor + " (3D oblique) west=" + west + " south=" + south + " east=" + east + " north=" + north);
      },
      flyThroughBounds: function (west, south, east, north) {
        startFlyThroughBounds(west, south, east, north);
      },
      addTileLayer: async function (name, xyzUrl, kind, options) {
        if (!viewer) return;
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
        let layerKey =
          options && typeof options.layer_key === "string" && options.layer_key
            ? options.layer_key
            : "imagery:" + String(name || "layer");
        layerKey = String(layerKey).replace(/\\/g, "/");
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
          // Keep DEM terrain unless explicitly requested to clear it.
          if (options && options.clear_dem === true) {
            clearDemTerrainMode();
          }
          clearManagedImageryLayers();
        }
        setSceneModeControlEnabled(true);
        // Use buildUrlWithQuery (same as DEM pipeline) to fully pre-encode the url=
        // query parameter value via encodeURIComponent.  This prevents Cesium's
        // UrlTemplateImageryProvider from double-encoding already-encoded sequences
        // like %20 (space) → %2520, which would make GDAL fail to find the file.
        const extraQuery = options && options.query ? options.query : {};
        const providerUrl = buildUrlWithQuery(xyzUrl, extraQuery);
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
        const maxLevel = options && Number.isInteger(options.maxzoom) ? options.maxzoom : 26;
        const existingLayer = managedImageryLayers.get(layerKey);
        if (existingLayer) {
          if (existingLayer.imageryProvider && existingLayer.imageryProvider.url === providerUrl && !(options && options.force_rebuild === true)) {
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
          } else {
            log("info", "Imagery URL changed or force rebuild requested. Recreating layer: " + layerKey);
            const index = viewer.imageryLayers.indexOf(existingLayer);
            const wasVisible = existingLayer.show;
            const currentAlpha = existingLayer.alpha;
            
            viewer.imageryLayers.remove(existingLayer, true);
            
            const provider = new Cesium.UrlTemplateImageryProvider({
              url: providerUrl,
              maximumLevel: maxLevel,
              minimumLevel: minLevel,
              tilingScheme: new Cesium.WebMercatorTilingScheme(),
              enablePickFeatures: false,
              rectangle: rectangle,
            });
            
            const newLayer = new Cesium.ImageryLayer(provider);
            if (index >= 0) {
              viewer.imageryLayers.add(newLayer, index);
            } else {
              viewer.imageryLayers.add(newLayer);
            }
            
            newLayer.show = wasVisible;
            newLayer.alpha = currentAlpha;
            newLayer._layerKey = layerKey;
            newLayer._layerName = name;
            
            managedImageryLayers.set(layerKey, newLayer);
            activeImageryLayer = newLayer;
            
            applySwipeComparatorSplit();
            if (comparatorModeEnabled) {
              refreshComparatorLayers();
            }
            updateBasemapBlendForCurrentMode();
            setStatus("Layer rebuilt: " + name);
            log("info", "Layer rebuilt key=" + layerKey + " name=" + name);
            requestSceneRender();
            return;
          }
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
        
        // Add layer at proper index to ensure basemap stays at bottom
        // Calculate insertion index: basemap layers should always be at index 0
        let insertionIndex = viewer.imageryLayers.length;
        
        // If we have basemap layers, ensure user layers start from index 1+
        if (osmBasemapLayer || defaultEarthLayer) {
          // Find the highest basemap index
          let basemapIndex = -1;
          if (osmBasemapLayer) {
            basemapIndex = Math.max(basemapIndex, viewer.imageryLayers.indexOf(osmBasemapLayer));
          }
          if (defaultEarthLayer) {
            basemapIndex = Math.max(basemapIndex, viewer.imageryLayers.indexOf(defaultEarthLayer));
          }
          
          // Insert user layers after basemap layers
          if (basemapIndex >= 0) {
            insertionIndex = basemapIndex + 1;
          }
        }
        
        activeImageryLayer = viewer.imageryLayers.addImageryProvider(provider, insertionIndex);
        activeImageryLayer.preloadAncestorTiles = false;
        if (window.Cesium && window.Cesium.TextureMinificationFilter && window.Cesium.TextureMagnificationFilter) {
          activeImageryLayer.minificationFilter = window.Cesium.TextureMinificationFilter.NEAREST;
          activeImageryLayer.magnificationFilter = window.Cesium.TextureMagnificationFilter.NEAREST;
        }
        managedImageryLayers.set(layerKey, activeImageryLayer);
        
        log("debug", "Layer added at index " + viewer.imageryLayers.indexOf(activeImageryLayer) + 
            " (requested index: " + insertionIndex + ")");
        
        // Tag the layer with its key for reordering functionality
        activeImageryLayer._layerKey = layerKey;
        activeImageryLayer._layerName = name;
        
        // CRITICAL FIX: Only ensure basemap is at bottom, don't force layer positions
        // This allows user reordering to work properly without conflicts
        
        // Step 1: Ensure basemap is at bottom (essential for proper rendering)
        if (osmBasemapLayer && osmBasemapLayer.show && viewer.imageryLayers.indexOf(osmBasemapLayer) >= 0) {
          viewer.imageryLayers.lowerToBottom(osmBasemapLayer);
        } else if (defaultEarthLayer && viewer.imageryLayers.indexOf(defaultEarthLayer) >= 0) {
          viewer.imageryLayers.lowerToBottom(defaultEarthLayer);
        }
        
        // REMOVED: Automatic layer stacking that conflicts with user reordering
        // The reorderLayersEventDriven() function now handles all layer positioning
        // This prevents visual conflicts and allows seamless reordering
        
        activeImageryLayer.alpha = 1.0;
        activeImageryLayer.show = true;
        
        // CRITICAL: Hide DEM colorbar when showing regular imagery
        hideDemColorbar();
        
        // REMOVED: Auto-switch to 2D mode - let search results control the scene mode
        // This allows search results to properly force 3D mode when needed
        log("debug", "Imagery layer loaded without forcing scene mode: " + name);
        
        // Debug layer state after addition
        log("debug", "Layer added: " + name + " at index " + viewer.imageryLayers.indexOf(activeImageryLayer) + " (top)");
        log("debug", "DEM colorbar hidden (regular imagery layer)");
        
        // BUG-FIX: Do NOT auto-focus here. Python calls flyToBounds/focusBoundsWithPadding
        // after ALL layers are loaded, giving a single smooth fly-to with tiles visible.
        // An internal setTimeout(focusBounds, 100) here raced with the Python fly and caused
        // black-screen flicker as the two flights fought each other.
        
        // Final step: ensure the map reflects the user's intended display order
        reapplyLayerOrderIfKnown();
        
        // Force multiple render requests with improved timing for tile loading
        if (viewer.scene) {
          viewer.scene.requestRender();
          
          // Staggered render requests with better timing for tile loading
          const renderDelays = [50, 150, 300, 600, 1000];
          renderDelays.forEach((delay, index) => {
            setTimeout(function() {
              if (viewer && viewer.scene) {
                viewer.scene.requestRender();
              }
            }, delay);
          });
          
          // Additional check for tile loading after initial burst
          setTimeout(function() {
            if (viewer && viewer.imageryLayers && activeImageryLayer) {
              const layerIndex = viewer.imageryLayers.indexOf(activeImageryLayer);
              
              // Force one more render if layer is still active
              if (layerIndex >= 0) {
                viewer.scene.requestRender();
              }
            }
          }, 1500);
        }
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
        // CRITICAL FIX: Don't clear imagery layers when replacing DEM
        // DEM layers are managed separately via activeDemContext
        // Clearing imagery layers here would remove user's imagery layers
        // if (replaceExisting) {
        //   clearManagedImageryLayers();
        // }
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
        const normalized = String(colormapName || "gray").toLowerCase();
        const allowed = new Set(["gray", "terrain", "slope", "aspect"]);
        const mode = allowed.has(normalized) ? normalized : "gray";
        if (comparatorModeEnabled) {
          const paneState = getComparatorPaneVisual(comparatorSelectedPane);
          if (!paneState) {
            return;
          }
          paneState.dem.colorMode = mode;
          if (typeof setSearchBusy === "function") {
            setSearchBusy(true, "Applying DEM style...");
          }
          if (getComparatorPaneLayerType(comparatorSelectedPane) === "dem") {
            scheduleComparatorDemRefresh(comparatorSelectedPane);
          } else if (typeof setSearchBusy === "function") {
            setSearchBusy(false, "");
          }
          notifyComparatorPaneState(comparatorSelectedPane);
          requestSceneRender();
          return;
        }
        setDemColorMode(mode);
      },
      setSwipeComparatorLayers: function (leftLayerKey, rightLayerKey, leftLabel, rightLabel) {
        // Store explicit keys so resolveComparatorLayerKeys returns exactly the selected layers
        swipeComparatorLeftLayerKey  = String(leftLayerKey  || "") || null;
        swipeComparatorRightLayerKey = String(rightLayerKey || "") || null;
        swipeComparatorExplicitKeys  = [swipeComparatorLeftLayerKey, swipeComparatorRightLayerKey].filter(Boolean);
        if (typeof refreshComparatorLayers === "function") {
          refreshComparatorLayers();
        }
      },
      setComparatorLayers: function (leftLayerKey, rightLayerKey, leftLabel, rightLabel) {
        // Store explicit keys so resolveComparatorLayerKeys returns exactly the selected layers
        swipeComparatorLeftLayerKey  = String(leftLayerKey  || "") || null;
        swipeComparatorRightLayerKey = String(rightLayerKey || "") || null;
        swipeComparatorExplicitKeys  = [swipeComparatorLeftLayerKey, swipeComparatorRightLayerKey].filter(Boolean);
        if (typeof refreshComparatorLayers === "function") {
          refreshComparatorLayers();
        }
      },
      // N-pane comparator: called from Python with the full list of selected paths.
      // The pane count is exactly len(allKeys), preventing ghost panes.
      setComparatorAllLayers: function (allKeysJson) {
        try {
          var parsed = JSON.parse(allKeysJson);
          if (Array.isArray(parsed) && parsed.length >= 2) {
            swipeComparatorExplicitKeys  = parsed.map(function(k) { return String(k || ""); }).filter(Boolean);
            swipeComparatorLeftLayerKey  = swipeComparatorExplicitKeys[0] || null;
            swipeComparatorRightLayerKey = swipeComparatorExplicitKeys[1] || null;
          }
        } catch (e) {
          log("warn", "setComparatorAllLayers parse error: " + e.message);
        }
        if (typeof refreshComparatorLayers === "function") {
          refreshComparatorLayers();
        }
      },
      // Clear explicit comparator key list (called when comparator is disabled).
      clearComparatorExplicitKeys: function () {
        swipeComparatorExplicitKeys  = [];
        swipeComparatorLeftLayerKey  = null;
        swipeComparatorRightLayerKey = null;
      },
      setLayerVisibility: function (layerKey, visible) {
        const applied = setLayerVisibilityByKey(String(layerKey || ""), Boolean(visible));
        if (!applied) {
          log("warn", "Layer visibility update ignored key=" + String(layerKey));
        }
      },
      removeLayerByKey: function (layerKey) {
        removeLayerByKey(String(layerKey || ""));
      },
      setPolygonVisibility: function (polyId, visible) {
        toggleDrawnPolygonVisibility(polyId, visible);
      },
      setAnnotationDrawingMode: function (active) {
        isAnnotationDrawing = Boolean(active);
        log("info", "Annotation drawing mode set: " + isAnnotationDrawing);
      },
      setSearchPolygonVisibility: function (visible) {
        polygonVisibilityEnabled = Boolean(visible);
        updatePolygonPreviewVisibility();
        log("debug", "All polygons visibility set to " + String(visible));
      },
      loadSearchPolygon: function (points) {
        loadSearchPolygon(points);
      },
      restoreAnnotationPolygon: function(points) {
        if (searchPolygonController && typeof searchPolygonController.restoreAnnotationPolygon === "function") {
          searchPolygonController.restoreAnnotationPolygon(points);
        }
      },
      clearAllLayers: function () {
        clearManagedImageryLayers();
        clearDemTerrainMode();
        clearVectorLayers();
        if (typeof clearMeasurementEntities === "function") clearMeasurementEntities();
        if (typeof clearMeasurementPreviewEntities === "function") clearMeasurementPreviewEntities();
        if (typeof clearAnnotationEntities === "function") clearAnnotationEntities();
        if (typeof clearLineDrawPreview === "function") clearLineDrawPreview();
        if (searchPolygonController && typeof searchPolygonController.clearAllData === "function") {
          searchPolygonController.clearAllData();
        }
        // ── Clear search result markers (red/yellow pins) ──────────────────────
        // These survive clearManagedImageryLayers because they are Cesium entity
        // billboards, not imagery layers.  Must be removed explicitly on New Project
        // so they don't bleed into the next session.
        if (typeof clearSearchResultMarkerEntities === "function") {
          clearSearchResultMarkerEntities();
        } else if (window.offlineGIS && typeof window.offlineGIS.clearSearchResultMarkers === "function") {
          window.offlineGIS.clearSearchResultMarkers();
        }
        // Reset search overlay visibility to visible (default for a new project)
        searchOverlayVisible = true;
        window._offlineGISSearchOverlayVisible = true;
        drawnPolygonCounter = 0;
        flyThroughPoints.length = 0;
        if (flyThroughPathEntity) { viewer.entities.remove(flyThroughPathEntity); flyThroughPathEntity = null; }
        if (flyThroughPreviewLineEntity) { viewer.entities.remove(flyThroughPreviewLineEntity); flyThroughPreviewLineEntity = null; }
        _lastKnownLayerOrder = null;
        setStatus("Project cleared.");
        requestSceneRender();
      },
      resetDefaultView: function () {
        setSceneModeInternal("3d");
        applyDefaultStartupFocus();
        requestSceneRender();
      },
      addVectorLayer: function (layerKey, label, geojson, options) {
        addVectorLayer(layerKey, label, geojson, options || {});
      },
      removeVectorLayer: function (layerKey) {
        removeVectorLayer(layerKey);
      },
      setVectorLayerVisibility: function (layerKey, visible) {
        setVectorLayerVisibility(layerKey, visible);
      },
      clearVectorLayers: function () {
        clearVectorLayers();
      },
      setBasemapVisibility: function (visible) {
        // Toggle OSM basemap visibility with lazy loading and smooth transition
        if (!viewer || !viewer.imageryLayers) {
          log("warn", "Cannot toggle basemap visibility - viewer not ready");
          return;
        }
        
        const shouldShow = Boolean(visible);
        
        if (window._basemapToggleTimer) {
          clearTimeout(window._basemapToggleTimer);
          window._basemapToggleTimer = null;
        }
        
        if (window._basemapToggleInProgress) {
          window._basemapToggleTimer = setTimeout(() => {
            window.offlineGIS.setBasemapVisibility(visible);
          }, 150);
          return;
        }
        
        window._basemapToggleInProgress = true;
        window._currentBasemapVisibility = shouldShow;
        
        const applyBasemapToViewer = function(targetViewer, isMain) {
            if (!targetViewer || !targetViewer.imageryLayers) return;
            
            if (shouldShow) {
                // Smooth transition: Ensure the basemap exists but don't force a re-render yet
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
                        osmProvider.errorEvent.addEventListener(function (error) { error.retry = false; });
                        targetViewer.__osmBasemapLayer = targetViewer.imageryLayers.addImageryProvider(osmProvider, 0);
                        targetViewer.__osmBasemapLayer.alpha = 1.0;
                    } catch (e) {
                        log("error", "Failed to create OSM basemap: " + e.message);
                        return;
                    }
                }
                
                // Apply visibility and order in a single batch
                targetViewer.__osmBasemapLayer.show = true;
                if (targetViewer.imageryLayers.indexOf(targetViewer.__osmBasemapLayer) !== 0) {
                    targetViewer.imageryLayers.lowerToBottom(targetViewer.__osmBasemapLayer);
                }
                
                if (isMain && defaultEarthLayer) defaultEarthLayer.show = false;
                if (targetViewer.__defaultEarthLayer) targetViewer.__defaultEarthLayer.show = false;
                
                if (isMain) osmBasemapLayer = targetViewer.__osmBasemapLayer;
            } else {
              // Hide OSM basemap and restore the default Earth imagery as the base layer
              if (targetViewer.__osmBasemapLayer) targetViewer.__osmBasemapLayer.show = false;
              if (isMain && defaultEarthLayer) defaultEarthLayer.show = true;
              if (targetViewer.__defaultEarthLayer) targetViewer.__defaultEarthLayer.show = false;
            }
        };

        if (osmBasemapLayer) viewer.__osmBasemapLayer = osmBasemapLayer;
        applyBasemapToViewer(viewer, true);
        
        if (typeof comparatorViewers !== 'undefined' && Array.isArray(comparatorViewers)) {
            comparatorViewers.forEach(v => applyBasemapToViewer(v, false));
        }

        // PERFORMANCE & STABILITY: Use requestAnimationFrame to let the browser settle
        // before requesting a Cesium scene render. This prevents WebGL 'deleted object'
        // errors on some Intel GPUs when imagery layers are swapped.
        window.requestAnimationFrame(() => {
            window._basemapToggleInProgress = false;
            if (viewer && viewer.scene) {
              viewer.scene.requestRender();
            }
        });
        
        // Reset the in-progress flag immediately (no need to wait for render)
        window._basemapToggleInProgress = false;
        
        log("debug", "Basemap visibility set to " + (shouldShow ? "SHOW (OSM at index 0)" : "HIDE (default Earth at index 0)"));
      },
      setDemProperties: function (hillshadeAlpha) {
        const nextHillshadeAlpha = Math.max(0.0, Math.min(1.0, Number(hillshadeAlpha) || 0.0));

        if (_demPropertiesDebounceTimer) clearTimeout(_demPropertiesDebounceTimer);
        _demPropertiesDebounceTimer = setTimeout(function () {
          log("info", "setDemProperties (debounced): hillshadeAlpha=" + nextHillshadeAlpha.toFixed(2));

          if (comparatorModeEnabled) {
            const paneState = getComparatorPaneVisual(comparatorSelectedPane);
            if (!paneState) return;

            paneState.dem.hillshadeAlpha = nextHillshadeAlpha;
            applyComparatorPaneVisualState(comparatorSelectedPane);
            notifyComparatorPaneState(comparatorSelectedPane);
            requestSceneRender();
            return;
          }

          demVisual.hillshadeAlpha = nextHillshadeAlpha;

          if (activeDemHillshadeLayer) {
            activeDemHillshadeLayer.alpha = demVisual.hillshadeAlpha;
            const demVisible = activeDemContext && activeDemContext.visible !== false;
            activeDemHillshadeLayer.show = demVisible && demVisual.hillshadeAlpha > 0.01;
          }

          if (viewer && viewer.scene) {
            viewer.scene.requestRender();
          }
        }, VISUAL_UPDATE_DEBOUNCE_MS);
      },
      setImageryProperties: function (brightness, contrast) {
        if (!viewer) return;
        const nextBrightness = Math.max(0.2, brightness);
        const nextContrast = Math.max(0.1, contrast);

        if (_imageryPropertiesDebounceTimer) clearTimeout(_imageryPropertiesDebounceTimer);
        _imageryPropertiesDebounceTimer = setTimeout(function () {
          log("info", "setImageryProperties (debounced): brightness=" + nextBrightness.toFixed(2) + " contrast=" + nextContrast.toFixed(2));

          if (comparatorModeEnabled) {
            const paneState = getComparatorPaneVisual(comparatorSelectedPane);
            if (!paneState) return;

            paneState.imagery.brightness = nextBrightness;
            paneState.imagery.contrast = nextContrast;
            applyComparatorPaneVisualState(comparatorSelectedPane);
            notifyComparatorPaneState(comparatorSelectedPane);
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
          }
          
          // Only update managed imagery asset layers (those added via the
          // Python event-driven flow). Avoid modifying the global basemap
          // layers (osmBasemapLayer/defaultEarthLayer) or using a generic
          // viewer layer fallback, which would change the whole globe.
          // This ensures brightness/contrast affect only asset tiles in-place.
          // Note: comparator mode handles its own pane visual state above.
          // No further per-globe changes here.

          requestSceneRender();
        }, VISUAL_UPDATE_DEBOUNCE_MS);
      },
      rotateCamera: function (degrees) {
        if (!viewer) return;
        // Rotation (heading change) works in both 2D and 3D modes
        log("info", "rotateCamera called: degrees=" + degrees + " comparatorMode=" + comparatorModeEnabled);
        // Rotate around the center of the screen, staying locked to the target asset
        const canvas = viewer.scene.canvas;
        const center = new Cesium.Cartesian2(canvas.clientWidth / 2.0, canvas.clientHeight / 2.0);
        const pickRay = viewer.camera.getPickRay(center);
        const target = viewer.scene.globe.pick(pickRay, viewer.scene);
        
        if (target) {
          log("info", "rotateCamera: orbiting around surface target");
          const transform = Cesium.Transforms.eastNorthUpToFixedFrame(target);
          viewer.camera.lookAtTransform(transform);
          viewer.camera.rotateRight(Cesium.Math.toRadians(degrees));
          viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
        } else {
          log("info", "rotateCamera: no surface found, rotating camera directly");
          viewer.camera.rotateRight(Cesium.Math.toRadians(degrees));
        }
        // Apply to the selected comparator DEM pane using its focused bounds.
        if (comparatorModeEnabled && Array.isArray(comparatorViewers)) {
          const selectedComparatorViewer = getComparatorPaneViewer(comparatorSelectedPane);
          const selectedComparatorLayerType = getComparatorPaneLayerType(comparatorSelectedPane);
          if (
            selectedComparatorViewer &&
            selectedComparatorLayerType === "dem" &&
            selectedComparatorViewer.scene &&
            selectedComparatorViewer.scene.mode === Cesium.SceneMode.SCENE3D &&
            activeTileBounds
          ) {
            const focusRect = Cesium.Rectangle.fromDegrees(
              activeTileBounds.west,
              activeTileBounds.south,
              activeTileBounds.east,
              activeTileBounds.north
            );
            const currentRange =
              selectedComparatorViewer.camera &&
              selectedComparatorViewer.camera.positionCartographic
                ? selectedComparatorViewer.camera.positionCartographic.height
                : undefined;
            const newHeading = selectedComparatorViewer.camera.heading + Cesium.Math.toRadians(degrees);
            try {
              setComparatorDemCameraFromRectangle(
                selectedComparatorViewer,
                focusRect,
                newHeading,
                currentRange
              );
            } catch (e) {
              log("warn", "rotateCamera: selected comparator DEM setView failed: " + e);
            }
            selectedComparatorViewer.scene.requestRender();
          }
        }
        requestSceneRender();
        log("info", "rotateCamera completed: degrees=" + degrees);
      },
      setPitch: function (degrees) {
        if (!viewer) return;
        if (currentSceneMode === "2d") {
          log("info", "setPitch: ignored in 2D mode");
          return;
        }
        log("info", "setPitch called: degrees=" + degrees);

        cameraOrbitPitch = Cesium.Math.toRadians(degrees);
        if (cameraOrbitPitch < MIN_3D_PITCH_RAD) {
          cameraOrbitPitch = MIN_3D_PITCH_RAD;
        }
        log("info", "setPitch: cameraOrbitPitch set to degrees=" + Cesium.Math.toDegrees(cameraOrbitPitch).toFixed(1));

        // Pitch around the center of the screen, staying locked to the target asset
        const canvas = viewer.scene.canvas;
        const center = new Cesium.Cartesian2(canvas.clientWidth / 2.0, canvas.clientHeight / 2.0);
        const pickRay = viewer.camera.getPickRay(center);
        const target = viewer.scene.globe.pick(pickRay, viewer.scene);
        
        if (target) {
          log("info", "setPitch: tilting around surface target");
          // Calculate current range to the target
          const distance = Cesium.Cartesian3.distance(viewer.camera.position, target);
          // Apply lookAt with the new pitch
          viewer.camera.lookAt(target, new Cesium.HeadingPitchRange(viewer.camera.heading, cameraOrbitPitch, distance));
          viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
        } else {
          log("info", "setPitch: no surface found, tilting camera directly");
          viewer.camera.setView({
            destination: viewer.camera.position.clone(),
            orientation: { heading: viewer.camera.heading, pitch: cameraOrbitPitch, roll: viewer.camera.roll },
          });
        }

        // Apply to the selected comparator DEM pane using its focused bounds.
        if (comparatorModeEnabled && Array.isArray(comparatorViewers)) {
          const selectedComparatorViewer = getComparatorPaneViewer(comparatorSelectedPane);
          const selectedComparatorLayerType = getComparatorPaneLayerType(comparatorSelectedPane);
          if (
            selectedComparatorViewer &&
            selectedComparatorLayerType === "dem" &&
            selectedComparatorViewer.scene &&
            selectedComparatorViewer.scene.mode === Cesium.SceneMode.SCENE3D &&
            activeTileBounds
          ) {
            const focusRect = Cesium.Rectangle.fromDegrees(
              activeTileBounds.west,
              activeTileBounds.south,
              activeTileBounds.east,
              activeTileBounds.north
            );
            const currentRange =
              selectedComparatorViewer.camera &&
              selectedComparatorViewer.camera.positionCartographic
                ? selectedComparatorViewer.camera.positionCartographic.height
                : undefined;
            try {
              setComparatorDemCameraFromRectangle(
                selectedComparatorViewer,
                focusRect,
                selectedComparatorViewer.camera.heading,
                currentRange
              );
            } catch (e) {
              log("warn", "setPitch: selected comparator DEM setView failed: " + e);
            }
            selectedComparatorViewer.scene.requestRender();
          }
        }

        requestSceneRender();
        log("info", "setPitch completed: degrees=" + degrees);
      },
      setLineDrawMode: function (enabled) {
        lineDrawModeEnabled = Boolean(enabled);
        log("debug", "setLineDrawMode called enabled=" + lineDrawModeEnabled + " start=" + (lineDrawStart ? (lineDrawStart.lon + "," + lineDrawStart.lat) : "none"));
        clearLineDrawPreview();
        log("info", "Line draw mode set: " + lineDrawModeEnabled);
      },
      setLineDrawStart: function (lon, lat) {
        if (lon === null || lat === null || lon === undefined || lat === undefined) {
          lineDrawStart = null;
          clearLineDrawPreview();
          return;
        }
        lineDrawStart = { lon: Number(lon), lat: Number(lat) };
        log("debug", "setLineDrawStart lon=" + lineDrawStart.lon.toFixed(6) + " lat=" + lineDrawStart.lat.toFixed(6));
        if (typeof lastMousePosition !== "undefined" && lastMousePosition && typeof getLonLatFromScreen === "function") {
          try {
            const hoverLonLat = getLonLatFromScreen(lastMousePosition);
            if (hoverLonLat) {
              log("debug", "setLineDrawStart preview seed hover=" + hoverLonLat.lon.toFixed(6) + "," + hoverLonLat.lat.toFixed(6));
              updateLineDrawPreview(lineDrawStart.lon, lineDrawStart.lat, hoverLonLat.lon, hoverLonLat.lat);
            }
          } catch (e) {
            log("debug", "setLineDrawStart preview seed failed: " + e.message);
          }
        }
      },
      clearLineDrawPreview: function () {
        lineDrawStart = null;
        clearLineDrawPreview();
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
            font: "600 15px 'Segoe UI', 'Helvetica Neue', sans-serif",
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

        const deleteEntity = viewer.entities.add({
          position: anchorPosition,
          billboard: {
            image: ANNOTATION_DELETE_ICON_IMAGE,
            width: 17,
            height: 17,
            color: Cesium.Color.WHITE.withAlpha(0.62),
            pixelOffset: new Cesium.Cartesian2(32, -26),
            horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1700000.0, 0.62),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });
        deleteEntity.show = annotationVisibilityEnabled;
        deleteEntity._annotationId = annotationId;
        deleteEntity._annotationRole = "delete";
        deleteEntity._annotationAnchorEntity = anchorEntity;
        deleteEntity._annotationLabelEntity = labelEntity;
        deleteEntity._annotationEditEntity = editEntity;

        annotationEntities.push(anchorEntity);
        annotationEntities.push(labelEntity);
        annotationEntities.push(editEntity);
        annotationEntities.push(deleteEntity);
        requestSceneRender();
        window.requestAnimationFrame(requestSceneRender);
        log("info", "Annotation added lon=" + lon + " lat=" + lat);
      },

      addLineAnnotation: function (coords, text) {
        if (!viewer || !Array.isArray(coords) || coords.length < 2) return;
        annotationCounter += 1;
        const annotationId = "line-annotation-" + String(annotationCounter);
        const labelText = String(text || "Line").trim() || "Line";

        const positions = [];
        const cleanCoords = [];
        for (let i = 0; i < coords.length; i++) {
          const pt = coords[i] || [];
          const lon = Number(pt[0]);
          const lat = Number(pt[1]);
          if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
          const carto = Cesium.Cartographic.fromDegrees(lon, lat);
          const sampledHeight = viewer.scene && viewer.scene.globe ? viewer.scene.globe.getHeight(carto) : null;
          const height = Number.isFinite(sampledHeight) ? Number(sampledHeight) : 0.0;
          positions.push(Cesium.Cartesian3.fromDegrees(lon, lat, height));
          cleanCoords.push([lon, lat]);
        }
        if (positions.length < 2) return;

        const lineEntity = viewer.entities.add({
          polyline: {
            positions: positions,
            width: 3,
            arcType: Cesium.ArcType.GEODESIC,
            clampToGround: true,
            material: Cesium.Color.fromCssColorString("#f2c94c"),
            depthFailMaterial: Cesium.Color.fromCssColorString("#f2c94c").withAlpha(0.65),
          },
        });
        lineEntity.show = annotationVisibilityEnabled;
        lineEntity._annotationId = annotationId;
        lineEntity._annotationRole = "line";

        const midIdx = Math.floor(cleanCoords.length / 2);
        const mid = cleanCoords[midIdx] || cleanCoords[0];
        const labelEntity = viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(mid[0], mid[1]),
          label: {
            text: labelText,
            fillColor: Cesium.Color.WHITE,
            showBackground: true,
            backgroundColor: Cesium.Color.BLACK.withAlpha(0.62),
            outlineColor: Cesium.Color.BLACK.withAlpha(0.9),
            outlineWidth: 2,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            font: "600 14px 'Segoe UI', 'Helvetica Neue', sans-serif",
            pixelOffset: new Cesium.Cartesian2(0, -10),
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });
        labelEntity.show = annotationVisibilityEnabled;
        labelEntity._annotationId = annotationId;
        labelEntity._annotationRole = "label";

        const editEntity = viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(mid[0], mid[1]),
          billboard: {
            image: ANNOTATION_EDIT_ICON_IMAGE,
            width: 17,
            height: 17,
            color: Cesium.Color.WHITE.withAlpha(0.42),
            pixelOffset: new Cesium.Cartesian2(-20, -26),
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1700000.0, 0.62),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });
        editEntity.show = annotationVisibilityEnabled;
        editEntity._annotationId = annotationId;
        editEntity._annotationRole = "edit";
        editEntity._annotationAnchorEntity = lineEntity;
        editEntity._annotationLabelEntity = labelEntity;

        const deleteEntity = viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(mid[0], mid[1]),
          billboard: {
            image: ANNOTATION_DELETE_ICON_IMAGE,
            width: 17,
            height: 17,
            color: Cesium.Color.WHITE.withAlpha(0.62),
            pixelOffset: new Cesium.Cartesian2(20, -26),
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1700000.0, 0.62),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });
        deleteEntity.show = annotationVisibilityEnabled;
        deleteEntity._annotationId = annotationId;
        deleteEntity._annotationRole = "delete";
        deleteEntity._annotationAnchorEntity = lineEntity;
        deleteEntity._annotationLabelEntity = labelEntity;
        deleteEntity._annotationEditEntity = editEntity;

        annotationEntities.push(lineEntity);
        annotationEntities.push(labelEntity);
        annotationEntities.push(editEntity);
        annotationEntities.push(deleteEntity);
        requestSceneRender();
        log("info", "Line annotation added with " + cleanCoords.length + " point(s)");
      },
  });
