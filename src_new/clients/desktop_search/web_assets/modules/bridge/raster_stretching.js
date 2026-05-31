  window.offlineGIS = window.offlineGIS || {};
  Object.assign(window.offlineGIS, {
    _findStretchTargetLayer: function (layerKey) {
      const normalizedKey = String(layerKey || "");
      const searchViewers = [];
      if (typeof comparatorModeEnabled !== "undefined" && comparatorModeEnabled && typeof comparatorViewers !== "undefined" && Array.isArray(comparatorViewers)) {
        if (typeof comparatorSelectedPane !== "undefined" && typeof getComparatorPaneViewer === "function") {
          const selectedViewer = getComparatorPaneViewer(comparatorSelectedPane);
          if (selectedViewer) {
            searchViewers.push(selectedViewer);
          }
        }
        for (const candidateViewer of comparatorViewers) {
          if (candidateViewer && searchViewers.indexOf(candidateViewer) === -1) {
            searchViewers.push(candidateViewer);
          }
        }
      }
      if (typeof viewer !== "undefined" && viewer && searchViewers.indexOf(viewer) === -1) {
        searchViewers.push(viewer);
      }

      for (const candidateViewer of searchViewers) {
        if (!candidateViewer || !candidateViewer.imageryLayers) {
          continue;
        }
        for (let i = 0; i < candidateViewer.imageryLayers.length; i++) {
          const layer = candidateViewer.imageryLayers.get(i);
          if (layer && layer._layerKey === normalizedKey) {
            return { viewer: candidateViewer, layer: layer };
          }
        }
      }
      return { viewer: null, layer: null };
    },
    _getStretchColorMode: function () {
      if (typeof getActiveDemColorMode === "function") {
        return getActiveDemColorMode();
      }
      if (typeof demVisual !== "undefined" && demVisual && demVisual.colorMode) {
        return String(demVisual.colorMode).toLowerCase();
      }
      if (activeDemContext && activeDemContext.colorMode) {
        return String(activeDemContext.colorMode).toLowerCase();
      }
      return "terrain";
    },
    _getStretchRangeForMode: function (mode) {
      if (typeof getDemRescaleRangeForColorMode === "function") {
        return getDemRescaleRangeForColorMode(mode);
      }
      const normalized = String(mode || "terrain").toLowerCase();
      if (normalized === "slope") return { min: 0.0, max: 90.0 };
      if (normalized === "aspect") return { min: 0.0, max: 360.0 };
      return { min: -500.0, max: 9000.0 };
    },
    // SECTION: Raster Stretching (Imagery and DEM)
    // ═══════════════════════════════════════════════════════════════════════════
    applyRasterStretch: function (layerKey, stretchType, method, params) {
      if (!viewer) {
        log("warn", "applyRasterStretch: viewer not initialized");
        return;
      }
      
      log("info", "Applying raster stretch: layer=" + layerKey + " type=" + stretchType + " method=" + method);
      
      // Find the layer
      const targetSearch = this._findStretchTargetLayer(layerKey);
      const targetViewer = targetSearch.viewer;
      const targetLayer = targetSearch.layer;
      
      if (!targetLayer) {
        log("warn", "applyRasterStretch: layer not found: " + layerKey);
        return;
      }
      
      // CRITICAL FIX: Verify stretch type matches layer type
      // Don't apply imagery stretch to DEM layers or vice versa
      const isDemLayer = activeDemContext && activeDemContext.layerKey === layerKey;
      if (stretchType === "imagery" && isDemLayer) {
        log("warn", "applyRasterStretch: cannot apply imagery stretch to DEM layer");
        return;
      }
      if (stretchType === "dem" && !isDemLayer) {
        log("warn", "applyRasterStretch: cannot apply DEM stretch to imagery layer");
        return;
      }
      
      // Store stretch settings on the layer for persistence
      targetLayer._stretchSettings = {
        type: stretchType,
        method: method,
        params: params || {}
      };
      
      // Apply stretch based on type and method
      if (stretchType === "imagery") {
        this._applyImageryStretch(targetLayer, method, params);
      } else if (stretchType === "dem") {
        this._applyDemStretch(targetLayer, method, params);
      }

      if (targetViewer && targetViewer.scene) {
        targetViewer.scene.requestRender();
      }
      
      requestSceneRender();
      log("info", "Raster stretch applied successfully");
    },
    
    _applyImageryStretch: function (layer, method, params) {
      // For imagery, we adjust brightness and contrast to simulate stretching
      // Real stretching would require tile reprocessing on the server
      
      if (method === "min_max" || method === "linear") {
        // Min-max stretch: increase contrast
        layer.brightness = params.brightness || 1.0;
        layer.contrast = params.contrast || 1.5;
      } else if (method === "std_dev") {
        // Standard deviation stretch: moderate contrast boost
        const k = params.k || 2.0;
        layer.brightness = params.brightness || 1.0;
        layer.contrast = 1.0 + (k * 0.2); // Scale contrast based on k
      } else if (method === "histogram_eq") {
        // Histogram equalization: strong contrast
        layer.brightness = params.brightness || 1.0;
        layer.contrast = params.contrast || 2.0;
      }
      
      // CRITICAL FIX: Ensure DEM layers remain visible when adjusting imagery stretch
      // Imagery stretch only modifies brightness/contrast, it should not affect DEM visibility
      if (activeDemDrapeLayer && activeDemContext && activeDemContext.visible !== false) {
        if (!activeDemDrapeLayer.show) {
          log("debug", "Imagery stretch: Restoring DEM drape visibility");
          activeDemDrapeLayer.show = true;
        }
      }
      if (activeDemHillshadeLayer && activeDemContext && activeDemContext.visible !== false) {
        if (!activeDemHillshadeLayer.show && activeDemHillshadeLayer.alpha > 0.01) {
          log("debug", "Imagery stretch: Restoring DEM hillshade visibility");
          activeDemHillshadeLayer.show = true;
        }
      }
      
      log("debug", "Imagery stretch applied: brightness=" + layer.brightness + " contrast=" + layer.contrast);
    },
    
    _applyDemStretch: function (layer, method, params) {
      // For DEM, we can adjust the colormap rescale parameters
      // This requires rebuilding the DEM drape with new rescale values
      
      if (!activeDemContext || activeDemContext.layerKey !== layer._layerKey) {
        log("warn", "DEM stretch: layer is not the active DEM");
        return;
      }
      
      // Calculate new rescale range based on method
      let newMin, newMax;
      const currentRange = this._getStretchRangeForMode(this._getStretchColorMode());
      
      if (method === "min_max") {
        // Use full data range
        newMin = params.min !== undefined ? params.min : currentRange.min;
        newMax = params.max !== undefined ? params.max : currentRange.max;
      } else if (method === "std_dev") {
        // Standard deviation stretch
        const k = params.k || 2.0;
        const mean = (currentRange.min + currentRange.max) / 2;
        const range = currentRange.max - currentRange.min;
        const std = range / 6; // Approximate std dev
        newMin = mean - (k * std);
        newMax = mean + (k * std);
      } else if (method === "linear") {
        // Linear stretch with custom range
        newMin = params.min !== undefined ? params.min : currentRange.min;
        newMax = params.max !== undefined ? params.max : currentRange.max;
      } else if (method === "histogram_eq") {
        // Histogram equalization (approximate with enhanced contrast)
        const range = currentRange.max - currentRange.min;
        newMin = currentRange.min + (range * 0.1);
        newMax = currentRange.max - (range * 0.1);
      } else {
        newMin = currentRange.min;
        newMax = currentRange.max;
      }
      
      // Rebuild DEM drape with new rescale
      if (activeDemDrapeUrl) {
        const baseUrl = activeDemDrapeUrl.split("?")[0];
        const newRescale = newMin.toFixed(1) + "," + newMax.toFixed(1);
        
        // Update the drape layer URL with new rescale
        const newUrl = buildUrlWithQuery(baseUrl, {
          rescale: newRescale,
          colormap_name: this._getStretchColorMode()
        });
        
        // Snapshot camera and properties for smooth swap
        const oldDrapeLayer = activeDemDrapeLayer;
        const wasVisible = oldDrapeLayer ? oldDrapeLayer.show : true;
        const currentAlpha = oldDrapeLayer ? oldDrapeLayer.alpha : 1.0;
        
        // CRITICAL FIX: Get rectangle bounds from activeDemContext
        const rectangle = activeDemContext.bounds ? createRectangle(activeDemContext.bounds) : null;
        
        // Add new drape layer with stretched values
        const newDrapeLayer = viewer.imageryLayers.addImageryProvider(
          new Cesium.UrlTemplateImageryProvider({
            url: newUrl,
            maximumLevel: 18,
            minimumLevel: 0,
            tilingScheme: new Cesium.WebMercatorTilingScheme(),
            enablePickFeatures: false,
            rectangle: rectangle
          })
        );
        
        // Restore visibility and properties
        newDrapeLayer.show = wasVisible;
        newDrapeLayer.alpha = currentAlpha;
        newDrapeLayer._layerKey = activeDemContext.layerKey;
        newDrapeLayer._layerName = activeDemContext.name;
        
        // SYNC FIX: Store stretch settings with calculated min/max for real-time coordination
        // This ensures setDemColorMode can retrieve the exact stretch range
        newDrapeLayer._stretchSettings = { 
          type: "dem", 
          method: method, 
          params: Object.assign({}, params, { min: newMin, max: newMax })
        };
        
        activeDemDrapeLayer = newDrapeLayer;
        activeDemDrapeUrl = newUrl;

        // Fast cleanup of old layer to avoid flicker while maintaining speed
        if (oldDrapeLayer) {
          setTimeout(() => {
            if (viewer && viewer.imageryLayers && viewer.imageryLayers.contains(oldDrapeLayer)) {
              viewer.imageryLayers.remove(oldDrapeLayer, false);
            }
          }, 120);
        }
        
        // Update managed layers
        managedImageryLayers.set(activeDemContext.layerKey, newDrapeLayer);
        
        // CRITICAL FIX: Ensure all other imagery layers remain visible
        // When we rebuild the DEM drape, we must not affect other layers' visibility
        for (const [key, imgLayer] of managedImageryLayers.entries()) {
          if (key !== activeDemContext.layerKey && imgLayer && layerVisibilityState.has(key)) {
            const shouldBeVisible = layerVisibilityState.get(key);
            if (imgLayer.show !== shouldBeVisible) {
              log("debug", "DEM stretch: Restoring visibility for layer " + key + " to " + shouldBeVisible);
              imgLayer.show = shouldBeVisible;
            }
          }
        }
        
        // Reapply layer order
        reapplyLayerOrderIfKnown();
        
        // SYNC FIX: Update colorbar to match new stretch range
        if (typeof updateDemColorbar === "function") {
          updateDemColorbar(newMin, newMax, activeDemContext.options);
        }
        
        log("info", "DEM stretch applied: rescale=" + newRescale + " visible=" + wasVisible);
      }
    },
    
    updateRasterStretchParams: function (layerKey, params) {
      if (!viewer) return;
      
      const targetSearch = this._findStretchTargetLayer(layerKey);
      const targetLayer = targetSearch.layer;
      
      if (!targetLayer || !targetLayer._stretchSettings) {
        log("warn", "updateRasterStretchParams: layer not found or no stretch applied: " + layerKey);
        return;
      }
      
      // Update params
      Object.assign(targetLayer._stretchSettings.params, params);
      
      // Reapply stretch with updated params
      const settings = targetLayer._stretchSettings;
      this.applyRasterStretch(layerKey, settings.type, settings.method, settings.params);
      
      log("debug", "Raster stretch params updated for layer: " + layerKey);
    },
    
    removeRasterStretch: function (layerKey) {
      if (!viewer) return;
      
      const targetSearch = this._findStretchTargetLayer(layerKey);
      const targetViewer = targetSearch.viewer;
      const targetLayer = targetSearch.layer;
      
      if (!targetLayer) {
        log("warn", "removeRasterStretch: layer not found: " + layerKey);
        return;
      }
      
      // Reset to defaults
      if (targetLayer._stretchSettings) {
        if (targetLayer._stretchSettings.type === "imagery") {
          targetLayer.brightness = 1.0;
          targetLayer.contrast = 1.0;
        } else if (targetLayer._stretchSettings.type === "dem") {
          // Rebuild DEM with original rescale
          if (_demOriginalRescale && activeDemContext && activeDemContext.layerKey === layerKey) {
            const baseUrl = activeDemDrapeUrl.split("?")[0];
            const originalRescale = _demOriginalRescale.min + "," + _demOriginalRescale.max;
            
            const newUrl = buildUrlWithQuery(baseUrl, {
              rescale: originalRescale,
              colormap_name: this._getStretchColorMode()
            });
            
            // CRITICAL FIX: Preserve current visibility and properties
            const wasVisible = activeDemDrapeLayer ? activeDemDrapeLayer.show : true;
            const currentAlpha = activeDemDrapeLayer ? activeDemDrapeLayer.alpha : 1.0;
            
            if (activeDemDrapeLayer) {
              targetViewer.imageryLayers.remove(activeDemDrapeLayer, false);
            }
            
            // CRITICAL FIX: Get rectangle bounds from activeDemContext
            const rectangle = activeDemContext.bounds ? createRectangle(activeDemContext.bounds) : null;
            
            const newDrapeLayer = targetViewer.imageryLayers.addImageryProvider(
              new Cesium.UrlTemplateImageryProvider({
                url: newUrl,
                maximumLevel: 18,
                minimumLevel: 0,
                tilingScheme: new Cesium.WebMercatorTilingScheme(),
                enablePickFeatures: false,
                rectangle: rectangle
              })
            );
            
            // CRITICAL FIX: Restore visibility and properties
            newDrapeLayer.show = wasVisible;
            newDrapeLayer.alpha = currentAlpha;
            newDrapeLayer._layerKey = activeDemContext.layerKey;
            newDrapeLayer._layerName = activeDemContext.name;
            
            activeDemDrapeLayer = newDrapeLayer;
            activeDemDrapeUrl = newUrl;
            
            managedImageryLayers.set(activeDemContext.layerKey, newDrapeLayer);
            reapplyLayerOrderIfKnown();
            
            log("info", "DEM stretch removed: restored original rescale, visible=" + wasVisible);
          }
        }
        
        delete targetLayer._stretchSettings;
      }
      
      requestSceneRender();
      log("info", "Raster stretch removed from layer: " + layerKey);
    }
  });
