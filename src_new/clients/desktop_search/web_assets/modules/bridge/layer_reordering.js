(function () {
  window.offlineGIS = window.offlineGIS || {};
  Object.assign(window.offlineGIS, {
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
          const imageryLayers = viewer.imageryLayers;
          const layerMap = new Map();
          const expandedOrder = [];
          const layersToMove = new Set();
          
          // Build a map of current layers by key and log all available layers
          log("debug", "EVENT_DRIVEN: Available layers in viewer:");
          for (let i = 0; i < imageryLayers.length; i++) {
            const layer = imageryLayers.get(i);
            if (layer && layer._layerKey) {
              layerMap.set(layer._layerKey, layer);
              log("debug", "  Layer " + i + ": key=" + layer._layerKey + " name=" + (layer._layerName || "unknown"));
            } else {
              log("debug", "  Layer " + i + ": no _layerKey (probably basemap)");
            }
          }
          
          log("debug", "EVENT_DRIVEN: Requested layers:");
          for (const command of layerCommands) {
            log("debug", "  Request: key=" + command.layer_key + " name=" + command.file_name + " order=" + command.new_order);
          }
          
          const requestedKeys = new Set(
            layerCommands.map(function (cmd) {
              return String(cmd && cmd.layer_key ? cmd.layer_key : "");
            })
          );
          const sortedCommands = layerCommands.slice().sort((a, b) => a.new_order - b.new_order);
          const orderedGroups = [];
          for (const command of sortedCommands) {
            const layer = layerMap.get(command.layer_key);
            const kind = String(command.kind || "");
            const isDem = Boolean(command.is_dem) || kind.toLowerCase() === "dem";
            const hillshadeKey = command.layer_key + ":hillshade";
            const hillshadeLayer = layerMap.get(hillshadeKey);
            log(
              "info",
              "EVENT_DRIVEN: reorder candidate key=" +
                command.layer_key +
                " name=" +
                command.file_name +
                " kind=" +
                kind +
                " is_dem=" +
                String(isDem) +
                " hillshadeKey=" +
                hillshadeKey +
                " hillshadeFound=" +
                String(Boolean(hillshadeLayer))
            );
            const groupLayers = [];
            if (layer) {
              const currentIndex = imageryLayers.indexOf(layer);
              log("debug", "EVENT_DRIVEN: Found layer for reordering: " + command.file_name +
                  " currentIndex=" + currentIndex + " targetOrder=" + command.new_order);
              expandedOrder.push({ layer: layer, label: command.file_name });
              layersToMove.add(layer);
              groupLayers.push({ layer: layer, label: command.file_name });
            } else {
              log("warn", "EVENT_DRIVEN: Layer not found for reordering: " + command.layer_key +
                  " (" + command.file_name + ")");
            }
            if (hillshadeLayer && !requestedKeys.has(hillshadeKey) && !layersToMove.has(hillshadeLayer)) {
              expandedOrder.push({ layer: hillshadeLayer, label: command.file_name + " (Hillshade)" });
              layersToMove.add(hillshadeLayer);
              groupLayers.push({ layer: hillshadeLayer, label: command.file_name + " (Hillshade)" });
              log("info", "EVENT_DRIVEN: Included hillshade for " + command.file_name);
            } else if (hillshadeLayer && (requestedKeys.has(hillshadeKey) || layersToMove.has(hillshadeLayer))) {
              log("debug", "EVENT_DRIVEN: Skipping duplicate hillshade for " + command.file_name);
            }
            if (groupLayers.length > 0) {
              orderedGroups.push(groupLayers);
            }
          }
          
          if (expandedOrder.length === 0) {
            log("warn", "EVENT_DRIVEN: No valid layers found for reordering");
            log("debug", "EVENT_DRIVEN: Available layer keys: " + Array.from(layerMap.keys()).join(", "));
            log("debug", "EVENT_DRIVEN: Requested layer keys: " + layerCommands.map(c => c.layer_key).join(", "));
            return;
          }
          
          log("debug", "EVENT_DRIVEN: Reordering plan:");
          for (let i = 0; i < expandedOrder.length; i++) {
            log("debug", "  " + i + ": " + expandedOrder[i].label);
          }
          
          for (let i = imageryLayers.length - 1; i >= 0; i--) {
            const layer = imageryLayers.get(i);
            if (layersToMove.has(layer)) {
              imageryLayers.remove(layer, false);
              log("debug", "EVENT_DRIVEN: Removed layer from index " + i);
            }
          }
          
          const applyReorderVisibility = function (layer) {
            if (!layer) {
              return;
            }
            if (layer === activeDemDrapeLayer) {
              layer.show = activeDemContext ? activeDemContext.visible !== false : layer.show;
              return;
            }
            if (layer === activeDemHillshadeLayer) {
              layer.show = activeDemContext
                ? activeDemContext.visible !== false && layer.alpha > 0.01
                : layer.show;
              return;
            }
            const key = layer._layerKey;
            if (key && layerVisibilityState.has(key)) {
              layer.show = Boolean(layerVisibilityState.get(key));
            }
          };

          for (let g = orderedGroups.length - 1; g >= 0; g--) {
            const group = orderedGroups[g];
            for (let i = 0; i < group.length; i++) {
              const item = group[i];
              imageryLayers.add(item.layer);
              applyReorderVisibility(item.layer);
              const newIndex = imageryLayers.indexOf(item.layer);
              log("debug", "EVENT_DRIVEN: Added layer " + item.label + " at index " + newIndex);
            }
          }
          
          // Ensure basemap layers are always at the bottom (index 0)
          // This prevents user layers from mixing with basemap layers
          if (osmBasemapLayer && imageryLayers.indexOf(osmBasemapLayer) >= 0) {
            imageryLayers.lowerToBottom(osmBasemapLayer);
            log("debug", "EVENT_DRIVEN: Moved OSM basemap to bottom (index 0)");
          }
          if (defaultEarthLayer && imageryLayers.indexOf(defaultEarthLayer) >= 0) {
            imageryLayers.lowerToBottom(defaultEarthLayer);
            log("debug", "EVENT_DRIVEN: Moved Default Earth basemap to bottom (index 0)");
          }
          
          // Verify basemap is at index 0 and user layers start from index 1+
          const basemapAtBottom = imageryLayers.get(0);
          if (basemapAtBottom && (basemapAtBottom === osmBasemapLayer || basemapAtBottom === defaultEarthLayer)) {
            log("info", "EVENT_DRIVEN: Basemap correctly positioned at index 0, user layers start from index 1");
          } else {
            log("warn", "EVENT_DRIVEN: Basemap positioning may be incorrect");
          }

          log("info", "EVENT_DRIVEN: Final layer stack (bottom to top):");
          for (let i = 0; i < imageryLayers.length; i++) {
            const layer = imageryLayers.get(i);
            const key = layer && layer._layerKey ? layer._layerKey : "basemap";
            const name = layer && layer._layerName ? layer._layerName : "basemap";
            const show = layer && layer.show === false ? "hidden" : "visible";
            log("info", "  [" + i + "] " + name + " key=" + key + " " + show);
          }
          
          // Force render to show changes
          viewer.scene.requestRender();
          
          // ── CRITICAL: Update persistent order state to prevent resets by other modules ──
          const finalOrderKeys = sortedCommands.map(c => c.layer_key);
          _lastKnownLayerOrder = finalOrderKeys.slice();
          
          // Unify with enforceLayerDisplayOrder to ensure hillshade/drape logic is consistent
          this.enforceLayerDisplayOrder(finalOrderKeys);
          
          // Additional render after a short delay to ensure visibility
          setTimeout(function() {
            if (viewer && viewer.scene) {
              viewer.scene.requestRender();
            }
          }, 100);
          
          log("info", "EVENT_DRIVEN: Layer reordering completed successfully (" + expandedOrder.length + " layers)");

          // FIX: Update _lastKnownLayerOrder so color-mode drape swaps restore THIS order
          // (not the stale initial Python order from when layers first loaded).
          // Build the order as [topmost-layer-key, ..., bottommost-layer-key]:
          // sortedCommands[0] = new_order 0 = user's row 0 = should end on top.
          var newOrderKeys = sortedCommands.map(function(cmd) { return String(cmd.layer_key); });
          if (newOrderKeys.length > 0) {
            _lastKnownLayerOrder = newOrderKeys;
            log("info", "EVENT_DRIVEN: _lastKnownLayerOrder updated to [" + newOrderKeys.join(", ") + "]");
            
            // CRITICAL: If the top-most layer is a DEM, or if a DEM is visible, 
            // ensure the terrain provider is correctly synced.
            if (activeDemContext && activeDemContext.visible !== false) {
               log("info", "EVENT_DRIVEN: Refreshing DEM layer state during reorder");
               applyDemLayer();
            }
          }
          
        } catch (error) {
          log("error", "EVENT_DRIVEN: Layer reordering failed - " + String(error));
          console.error("Layer reordering error:", error);
          
          // Force a render even if reordering failed
          if (viewer && viewer.scene) {
            viewer.scene.requestRender();
          }
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

          // ── Step 3: Always pin basemap to the bottom ──
          if (osmBasemapLayer && imageryLayers.indexOf(osmBasemapLayer) >= 0) {
            imageryLayers.lowerToBottom(osmBasemapLayer);
          }
          if (defaultEarthLayer && imageryLayers.indexOf(defaultEarthLayer) >= 0) {
            imageryLayers.lowerToBottom(defaultEarthLayer);
          }

          // ── Step 4: DEM drape visibility rule ──
          // Rely exclusively on the user's explicit visibility toggles (activeDemContext.visible)
          // rather than blindly hiding the DEM just because it isn't index 0. This allows users
          // to see DEM color modes even if they have translucent or spatially-offset imagery on top.
          if (activeDemDrapeLayer) {
            activeDemDrapeLayer.show = (activeDemContext && activeDemContext.visible !== false);
          }
          if (activeDemHillshadeLayer) {
            activeDemHillshadeLayer.show = (
              activeDemContext && activeDemContext.visible !== false &&
              activeDemHillshadeLayer.alpha > 0.01
            );
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
        viewer.render();
        return viewer.canvas.toDataURL("image/png");
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
        
        return {
          mode: currentSceneMode,
          camera: getCameraInfo(),
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
        }},
  });
})();
