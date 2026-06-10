  window.offlineGIS = window.offlineGIS || {};
  Object.assign(window.offlineGIS, {
    // SECTION: Layer Reordering Functions
    // ═══════════════════════════════════════════════════════════════════════════
    
    reorderLayersEventDriven: function (layerCommands) {
      if (!viewer || !Array.isArray(layerCommands)) {
        log("warn", "EVENT_DRIVEN: Invalid layer reorder request");
        return;
      }
      
      if (layerCommands.length === 0) {
        log("debug", "EVENT_DRIVEN: No layers to reorder");
        return;
      }
      
      log("info", "EVENT_DRIVEN: Reordering " + layerCommands.length + " layers");
      
      try {
        const sortedCommands = layerCommands.slice().sort((a, b) => a.new_order - b.new_order);
        const finalOrderKeys = sortedCommands.map(c => c.layer_key);
        
        // Persist order so color-mode drape swaps can re-apply it without Python round-trip
        _lastKnownLayerOrder = finalOrderKeys.slice();
        
        // Unify with enforceLayerDisplayOrder to ensure hillshade/drape logic is consistent
        this.enforceLayerDisplayOrder(finalOrderKeys);
        
        log("info", "EVENT_DRIVEN: Layer reordering completed successfully (" + layerCommands.length + " layers)");
      } catch (e) {
        log("error", "reorderLayersEventDriven failed: " + e);
      }
    },
    
    raiseLayerToTop: function (layerKey) {
      if (!viewer || !layerKey) return;
      
      try {
        const imageryLayers = viewer.imageryLayers;
        var subLayers = [];
        // Find all sublayers for this layerKey
        for (let i = 0; i < imageryLayers.length; i++) {
          const layer = imageryLayers.get(i);
          if (layer && (layer._layerKey === layerKey || layer._layerKey === layerKey + ":hillshade")) {
            subLayers.push(layer);
          }
        }
        
        if (subLayers.length > 0) {
          // Raise drape first, hillshade last (so hillshade is on top of drape)
          for (var s = 0; s < subLayers.length; s++) {
            imageryLayers.raiseToTop(subLayers[s]);
          }
          viewer.scene.requestRender();
          log("debug", "Raised " + subLayers.length + " sublayers to top for: " + layerKey);
          return;
        }
        
        log("warn", "Layer not found for raising to top: " + layerKey);
        
      } catch (error) {
        log("error", "Failed to raise layer to top: " + String(error));
      }
    },

    // ── Enforce correct visual layer order after all search layers load ──
    // orderedKeys[0] = top of UI list = must end at HIGHEST Cesium index (drawn last = on top)
    // orderedKeys[last] = bottom of UI list = lowest Cesium index above basemap
    //
    // DEM draping rule:
    //   If any imagery key is above a DEM key in the list → hide DEM drape (grayscale),
    //   keep terrain provider active so imagery drapes over 3D elevation automatically.
    //   If DEM is on top (or no imagery above it) → show DEM drape normally.
    enforceLayerDisplayOrder: function (orderedKeys) {
      if (!viewer || !viewer.imageryLayers || !Array.isArray(orderedKeys) || orderedKeys.length === 0) return;
      // Persist order so color-mode drape swaps can re-apply it without Python round-trip
      _lastKnownLayerOrder = orderedKeys.slice();
      try {
        const imageryLayers = viewer.imageryLayers;
        const activeColorMode = String((activeDemContext && activeDemContext.colorMode) || (demVisual && demVisual.colorMode) || "terrain").toLowerCase();
        const forceDemToTop = activeColorMode === "slope" || activeColorMode === "aspect";

        // ── Step 1: Determine Top Key for Logging ──
        const demKey = activeDemContext ? activeDemContext.layerKey : null;
        const topKey = orderedKeys[0];
        const imageryIsOnTop = !!(demKey && topKey !== demKey);

        // ── Step 2: Raise layers in reverse UI order so orderedKeys[0] wins the top spot ──
        for (let k = orderedKeys.length - 1; k >= 0; k--) {
          const key = orderedKeys[k];
          var subLayers = [];
          for (let i = 0; i < imageryLayers.length; i++) {
            const layer = imageryLayers.get(i);
            if (layer && (layer._layerKey === key || layer._layerKey === key + ":hillshade")) {
              subLayers.push(layer);
            }
          }
          // Raise drape first, hillshade last (hillshade stays on top of its DEM block)
          for (var s = 0; s < subLayers.length; s++) {
            imageryLayers.raiseToTop(subLayers[s]);
          }
        }

        // ── Step 3: Layer stack adjustment for DEM / Basemaps ──
        if (forceDemToTop) {
          if (osmBasemapLayer && imageryLayers.indexOf(osmBasemapLayer) >= 0) {
            imageryLayers.lowerToBottom(osmBasemapLayer);
          }
          if (defaultEarthLayer && imageryLayers.indexOf(defaultEarthLayer) >= 0) {
            imageryLayers.lowerToBottom(defaultEarthLayer);
          }
          if (activeDemDrapeLayer && imageryLayers.indexOf(activeDemDrapeLayer) >= 0) {
            imageryLayers.raiseToTop(activeDemDrapeLayer);
          }
          if (activeDemHillshadeLayer && imageryLayers.indexOf(activeDemHillshadeLayer) >= 0) {
            imageryLayers.raiseToTop(activeDemHillshadeLayer);
          }
        } else {
          // If forceDemToTop is false, ensure DEM drape/hillshade are below all other layers
          if (activeDemHillshadeLayer && imageryLayers.indexOf(activeDemHillshadeLayer) >= 0) {
            imageryLayers.lowerToBottom(activeDemHillshadeLayer);
          }
          if (activeDemDrapeLayer && imageryLayers.indexOf(activeDemDrapeLayer) >= 0) {
            imageryLayers.lowerToBottom(activeDemDrapeLayer);
          }
          if (defaultEarthLayer && imageryLayers.indexOf(defaultEarthLayer) >= 0) {
            imageryLayers.lowerToBottom(defaultEarthLayer);
          }
          if (osmBasemapLayer && imageryLayers.indexOf(osmBasemapLayer) >= 0) {
            imageryLayers.lowerToBottom(osmBasemapLayer);
          }
        }

        // ── Step 4: DEM drape visibility rule ──
        // Rely exclusively on the user's explicit visibility toggles (activeDemContext.visible)
        // rather than blindly hiding the DEM just because it isn't index 0. This allows users
        // to see DEM color modes even if they have translucent or spatially-offset imagery on top.
        if (activeDemDrapeLayer) {
          activeDemDrapeLayer.show = (activeDemContext && activeDemContext.visible !== false);
          if (forceDemToTop) {
            activeDemDrapeLayer.show = true;
          }
        }
        if (activeDemHillshadeLayer) {
          activeDemHillshadeLayer.show = (
            activeDemContext && activeDemContext.visible !== false &&
            activeDemHillshadeLayer.alpha > 0.01
          );
          if (forceDemToTop && activeDemHillshadeLayer.alpha > 0.0) {
            activeDemHillshadeLayer.show = true;
          }
        }

        // CRITICAL: Ensure terrain provider matches active DEM visibility
        if (activeDemContext && activeDemContext.visible !== false && activeDemTerrainProvider) {
          if (viewer.terrainProvider !== activeDemTerrainProvider) {
            log("info", "enforceLayerDisplayOrder: Reactivating DEM terrain provider");
            _swapTerrainProviderLocked(activeDemTerrainProvider);
          }
        } else if ((!activeDemContext || activeDemContext.visible === false) && activeDemTerrainProvider) {
            if (viewer.terrainProvider === activeDemTerrainProvider) {
              log("info", "enforceLayerDisplayOrder: Restoring ellipsoid terrain (DEM hidden)");
              _swapTerrainProviderLocked(new Cesium.EllipsoidTerrainProvider());
            }
        }

        viewer.scene.requestRender();
        log("info", "enforceLayerDisplayOrder: order=[" + orderedKeys.join(", ") + "] imageryOnTop=" + imageryIsOnTop);
      } catch (e) {
        log("error", "enforceLayerDisplayOrder failed: " + e);
      }
    },
    
    setLayerOrder: function (layerKey, newIndex) {
      if (!viewer || !layerKey || typeof newIndex !== 'number') return;
      
      try {
        const imageryLayers = viewer.imageryLayers;
        
        // Find the layer with the matching key
        for (let i = 0; i < imageryLayers.length; i++) {
          const layer = imageryLayers.get(i);
          if (layer && layer._layerKey === layerKey) {
            // Remove and re-add at new position
            imageryLayers.remove(layer, false);
            imageryLayers.add(layer, Math.max(0, Math.min(newIndex, imageryLayers.length)));
            viewer.scene.requestRender();
            log("debug", "Set layer order: " + layerKey + " to index " + newIndex);
            return;
          }
        }
        
        log("warn", "Layer not found for reordering: " + layerKey);
        
      } catch (error) {
        log("error", "Failed to set layer order: " + String(error));
      }
    },
    
    // CRITICAL: Add the missing requestSceneRender function
    requestSceneRender: function() {
      if (viewer && viewer.scene && typeof viewer.scene.requestRender === "function") {
        viewer.scene.requestRender();
      }
    },
    captureSnapshot: function() {
      if (!viewer || !viewer.canvas) return null;
      
      const hiddenEntities = [];
      const entities = viewer.entities.values;
      for (let i = 0; i < entities.length; i++) {
        const ent = entities[i];
        if (ent && (ent._annotationRole === "edit" || ent._annotationRole === "delete" || ent._polyRole === "edit" || ent._polyRole === "delete")) {
          hiddenEntities.push({ entity: ent, originalShow: ent.show });
          ent.show = false;
        }
      }
      
      viewer.render();
      const dataUrl = viewer.canvas.toDataURL("image/png");
      
      // Restore
      for (let i = 0; i < hiddenEntities.length; i++) {
        const item = hiddenEntities[i];
        item.entity.show = item.originalShow;
      }
      
      return dataUrl;
    },
    getSceneState: function() {
      const getCameraInfo = function() {
        if (!viewer) return null;
        const cam = viewer.camera;
        const carto = cam.positionCartographic;
        if (!carto) return null;
        return {
          position: {
            lon: Cesium.Math.toDegrees(carto.longitude),
            lat: Cesium.Math.toDegrees(carto.latitude),
            height: carto.height
          },
          heading: Cesium.Math.toDegrees(cam.heading),
          pitch: Cesium.Math.toDegrees(cam.pitch),
          roll: Cesium.Math.toDegrees(cam.roll)
        };
      };
      
      const getCameraExtent = function() {
        if (!viewer) return null;
        try {
          const rect = viewer.camera.computeViewRectangle();
          if (rect) {
            return {
              west: Cesium.Math.toDegrees(rect.west),
              south: Cesium.Math.toDegrees(rect.south),
              east: Cesium.Math.toDegrees(rect.east),
              north: Cesium.Math.toDegrees(rect.north)
            };
          }
        } catch (_) {}
        return null;
      };
      
      return {
        mode: currentSceneMode,
        camera: getCameraInfo(),
        extent: getCameraExtent(),
        visibleLayers: Array.from(layerVisibilityState.entries())
          .filter(([_, vis]) => vis)
          .map(([key, _]) => key),
        annotations: {
          points: typeof annotationRecords !== 'undefined' ? annotationRecords : [],
          lines: typeof annotationLineRecords !== 'undefined' ? annotationLineRecords : [],
          polygons: typeof drawnPolygons !== 'undefined' ? drawnPolygons.map(p => ({
            id: p.id,
            label: p.label,
            points: p.points
          })) : []
        }
      };
    },
    
    // ═══════════════════════════════════════════════════════════════════════════
  });
