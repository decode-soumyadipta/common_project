  window.offlineGIS = window.offlineGIS || {};
  Object.assign(window.offlineGIS, {
      addTileLayerEventDriven: async function (name, xyzUrl, kind, options) {
        if (!viewer) return;
        
        log("info", "EVENT_DRIVEN: addTileLayer name=" + String(name || "") + 
            " kind=" + String(kind || "") + " server_optimized=" + Boolean(options && options.server_optimized));
        
        // Event-driven optimization: Pre-configure for terabyte-scale performance
        if (options && options.server_optimized) {
          // Apply ultra-high performance settings for large datasets
          viewer.scene.globe.maximumScreenSpaceError = 1.0; // Original high detail fidelity
          viewer.scene.globe.tileCacheSize = 2000; // Aggressive tile caching
          // FIX: requestRenderMode disabled to prevent auto-blurring and shaking
          viewer.scene.requestRenderMode = false;
          
          log("info", "EVENT_DRIVEN: Applied terabyte-scale performance optimizations");
        }
        
        // Use existing addTileLayer with performance enhancements
        await window.offlineGIS.addTileLayer(name, xyzUrl, kind, options);
        
        // Additional event-driven optimizations
        if (options && options.server_optimized) {
          // Force aggressive tile loading for smooth interaction
          if (viewer.scene) {
            viewer.scene.requestRender();
            
            // Staggered render requests for smooth loading
            const renderDelays = [50, 150, 300, 600];
            renderDelays.forEach(delay => {
              setTimeout(() => {
                if (viewer && viewer.scene) {
                  viewer.scene.requestRender();
                }
              }, delay);
            });
          }
          
          log("info", "EVENT_DRIVEN: Tile layer loaded with server optimization");
        }
      },
      
      addDemLayerEventDriven: function (name, xyzUrl, options) {
        if (!viewer) return;
        
        log("info", "EVENT_DRIVEN: addDemLayer name=" + String(name || "") + 
            " server_optimized=" + Boolean(options && options.server_optimized));
        
        // Event-driven DEM optimization for terabyte-scale terrain data
        if (options && options.server_optimized) {
          // Ultra-high performance DEM settings
          viewer.scene.globe.terrainExaggeration = Math.min(2.0, options.exaggeration || 1.5);
          viewer.scene.globe.enableLighting = false; // Disable lighting for performance
          viewer.scene.fog.enabled = false; // Disable fog for clarity
          viewer.scene.skyAtmosphere.show = false; // Reduce atmospheric rendering
          
          // Optimize terrain provider for large datasets
          if (viewer.terrainProvider && viewer.terrainProvider.requestTileGeometry) {
            viewer.scene.globe.maximumScreenSpaceError = 1.0; // Max fidelity terrain
          }
          
          log("info", "EVENT_DRIVEN: Applied DEM terabyte-scale optimizations");
        }
        
        // Use existing addDemLayer with performance enhancements
        window.offlineGIS.addDemLayer(name, xyzUrl, options);
        
        // Additional event-driven DEM optimizations
        if (options && options.server_optimized) {
          // Optimize camera for DEM viewing
          setTimeout(() => {
            if (viewer && viewer.camera) {
              // Set optimal camera settings for large terrain datasets
              viewer.camera.percentageChanged = 0.1; // More responsive camera updates
              viewer.scene.requestRender();
            }
          }, 100);
          
          log("info", "EVENT_DRIVEN: DEM layer loaded with server optimization");
        }
      },
      
      optimizeForTerabyteScale: function (options) {
        if (!viewer) return;
        
        const opts = options || {};
        
        log("info", "EVENT_DRIVEN: Applying terabyte-scale optimizations");
        
        // Ultra-high performance rendering settings
        // FIX: requestRenderMode disabled to prevent auto-blurring
        viewer.scene.requestRenderMode = false;
        viewer.scene.maximumRenderTimeChange = 0.0;
        viewer.scene.globe.maximumScreenSpaceError = opts.screenSpaceError || 1.5;
        viewer.scene.globe.tileCacheSize = opts.tileCacheSize || 2000;
        
        // Disable expensive visual effects for performance
        viewer.scene.fog.enabled = false;
        viewer.scene.skyAtmosphere.show = false;
        viewer.scene.globe.enableLighting = false;
        viewer.scene.sun.show = false;
        viewer.scene.moon.show = false;
        
        // Optimize imagery layers for large datasets
        if (viewer.imageryLayers) {
          for (let i = 0; i < viewer.imageryLayers.length; i++) {
            const layer = viewer.imageryLayers.get(i);
            if (layer && layer.imageryProvider) {
              // Apply performance optimizations to existing layers
              layer.imageryProvider.maximumLevel = Math.min(layer.imageryProvider.maximumLevel || 18, 16);
            }
          }
        }
        
        // Memory management for large datasets
        if (Cesium.Resource && Cesium.Resource.fetchImage) {
          // Configure aggressive image caching
          Cesium.Resource.fetchImage.cache = new Map();
        }
        
        log("info", "EVENT_DRIVEN: Terabyte-scale optimizations applied successfully");
        
        // Force render to apply changes
        viewer.scene.requestRender();
      },
      
      enableEventDrivenMode: function (enabled) {
        if (!viewer) return;
        
        const isEnabled = Boolean(enabled);
        
        log("info", "EVENT_DRIVEN: Mode " + (isEnabled ? "enabled" : "disabled"));
        
        if (isEnabled) {
          // Enable event-driven optimizations
          // FIX: requestRenderMode disabled to prevent auto-blurring
          viewer.scene.requestRenderMode = false;
          viewer.scene.maximumRenderTimeChange = 0.0;
          
          // Performance monitoring disabled for smooth performance (from smooth implementation)
          
          log("info", "EVENT_DRIVEN: Performance monitoring disabled for smooth performance");
        } else {
          // Restore default rendering mode
          viewer.scene.requestRenderMode = false;
          viewer.scene.globe.maximumScreenSpaceError = 1.5;
          
          log("info", "EVENT_DRIVEN: Restored default rendering mode");
        }
        
        viewer.scene.requestRender();
      },
  });
