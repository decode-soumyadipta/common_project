  // SECTION: Camera & Scene Mode  →  future: modules/camera.js
  // Functions: applyDefaultSceneSettings, applyDemSceneSettings,
  //   tuneCameraController, configureCameraControllerForMode,
  //   _swapTerrainProviderLocked, setSceneModeInternal, detectSceneMode,
  //   syncSceneModeToggle, focusPreferredRegion, focusPreferredRegion3D,
  //   focusLoadedRegion3D, schedule3DFocusAfterMorph, startFlyThroughBounds,
  //   applyDefaultStartupFocus, _updateCompass, Asia camera lock postRender
  // ═══════════════════════════════════════════════════════════════════════════

  function logCameraState(prefix) {
    if (!viewer || !viewer.camera) return;
    const camera = viewer.camera;
    const pos = camera.position;
    const carto = camera.positionCartographic;
    log("info", "[CAMERA_LOG] " + prefix + ": pos=" + (pos ? "(" + pos.x.toFixed(1) + ", " + pos.y.toFixed(1) + ", " + pos.z.toFixed(1) + ")" : "null") + 
        " carto=" + (carto ? "(lon=" + Cesium.Math.toDegrees(carto.longitude).toFixed(5) + ", lat=" + Cesium.Math.toDegrees(carto.latitude).toFixed(5) + ", alt=" + carto.height.toFixed(1) + ")" : "null") +
        " heading=" + (Number.isFinite(camera.heading) ? Cesium.Math.toDegrees(camera.heading).toFixed(1) : "0") +
        " pitch=" + (Number.isFinite(camera.pitch) ? Cesium.Math.toDegrees(camera.pitch).toFixed(1) : "0"));
  }
  window.offlineGIS = window.offlineGIS || {};
  window.offlineGIS.logCameraState = logCameraState;

  function applyDefaultSceneSettings() {
    if (!viewer) return;
    // Smooth implementation settings - balanced performance and quality
    viewer.scene.globe.enableLighting = false;
    viewer.scene.fog.enabled = false;
    viewer.shadows = false;
    requestSceneRender();
  }

  /**
   * Swap the terrain provider while keeping the camera locked on the current view.
   * Cesium 1.78 fires camera resets asynchronously after terrainProvider changes.
   * We lock the camera for 800ms and intercept flights/views to absorb all async resets.
   */
  let _isTerrainSwapping = false;
  let _originalFlyTo = null;
  let _originalFlyToBoundingSphere = null;
  let _originalSetView = null;
  let _originalViewBoundingSphere = null;
  let _pendingCameraAction = null;
  let _terrainSwapTimeout = null;
  let _terrainSwapIntervals = [];

  function _swapTerrainProviderLocked(newProvider) {
    if (!viewer || !newProvider) {
      log("warn", "DEM_RENDER: _swapTerrainProviderLocked called with invalid params viewer=" + !!viewer + " provider=" + !!newProvider);
      return;
    }
    if (viewer.terrainProvider === newProvider) {
      log("info", "DEM_RENDER: _swapTerrainProviderLocked skipped - provider already active");
      return;
    }

    logCameraState("Before terrain swap");
    log("info", "DEM_RENDER: Swapping terrain provider with camera lock & interceptor");
    log("info", "DEM_RENDER: Old provider type: " + (viewer.terrainProvider.constructor ? viewer.terrainProvider.constructor.name : "unknown"));
    
    // Save original camera methods if we haven't already
    if (!_originalFlyTo) {
      _originalFlyTo = viewer.camera.flyTo;
      _originalFlyToBoundingSphere = viewer.camera.flyToBoundingSphere;
      _originalSetView = viewer.camera.setView;
      _originalViewBoundingSphere = viewer.camera.viewBoundingSphere;
    }

    // Cancel any existing timeout/intervals if we are swapping already
    if (_terrainSwapTimeout) {
      clearTimeout(_terrainSwapTimeout);
      _terrainSwapTimeout = null;
    }
    _terrainSwapIntervals.forEach(clearTimeout);
    _terrainSwapIntervals = [];

    // Set swapping flag
    _isTerrainSwapping = true;

    // Disable camera inputs during terrain swap to prevent controller state corruption
    if (viewer.scene && viewer.scene.screenSpaceCameraController) {
      viewer.scene.screenSpaceCameraController.enableInputs = false;
    }

    // Keep rendering active during terrain swap to let tiles stream in
    viewer.scene.requestRenderMode = false;

    const isTransition = !!window._is2DTo3DTransition;
    log("info", "DEM_RENDER: Swapping terrain provider. isTransition=" + isTransition);

    // Clone the camera state before swap (always done to lock position during swap)
    const savedPosition = viewer.camera.position ? Cesium.Cartesian3.clone(viewer.camera.position) : null;
    const savedHeading = viewer.camera.heading;
    const savedPitch = viewer.camera.pitch;
    const savedRoll = viewer.camera.roll;

    // Override the camera methods to intercept flights during swap
    viewer.camera.flyTo = function (options) {
      if (isTransition) {
        if (_originalFlyTo) {
          _originalFlyTo.call(viewer.camera, options);
        } else {
          viewer.camera.flyTo(options);
        }
        return;
      }
      log("info", "DEM_RENDER: flyTo intercepted during terrain swap");
      _pendingCameraAction = { type: "flyTo", args: [options] };
    };
    viewer.camera.flyToBoundingSphere = function (sphere, options) {
      if (isTransition) {
        if (_originalFlyToBoundingSphere) {
          _originalFlyToBoundingSphere.call(viewer.camera, sphere, options);
        } else {
          viewer.camera.flyToBoundingSphere(sphere, options);
        }
        return;
      }
      log("info", "DEM_RENDER: flyToBoundingSphere intercepted during terrain swap");
      _pendingCameraAction = { type: "flyToBoundingSphere", args: [sphere, options] };
    };

    // Swap the terrain provider
    viewer.terrainProvider = newProvider;
    
    log("info", "DEM_RENDER: New provider type: " + (newProvider.constructor ? newProvider.constructor.name : "unknown"));
    log("info", "DEM_RENDER: Provider ready: " + newProvider.ready);

    // Proactively and smoothly realign all search result markers to the new terrain provider
    if (window.offlineGIS && typeof window.offlineGIS.realignMarkersToTerrain === "function") {
      window.offlineGIS.realignMarkersToTerrain();
    }

    // Function to restore saved camera state
    function restoreCameraState() {
      if (isTransition) return; // Do not lock/restore camera position during 2D-3D scene mode transitions!
      if (!viewer || !viewer.camera || !savedPosition || !Number.isFinite(savedHeading)) return;
      // Use the original setView to restore state without triggering interceptor
      _originalSetView.call(viewer.camera, {
        destination: savedPosition,
        orientation: {
          heading: savedHeading,
          pitch: savedPitch,
          roll: savedRoll
        }
      });
    }

    // Restore immediately to lock view
    restoreCameraState();

    // Setup periodic restores to absorb any async resets from Cesium
    const intervals = [10, 30, 50, 80, 120, 180, 250, 350, 450, 550, 650];
    intervals.forEach(t => {
      _terrainSwapIntervals.push(setTimeout(restoreCameraState, t));
    });

    const lockDuration = isTransition ? 1500 : 800;

    // End the swap state after lockDuration to allow Cesium to fully settle
      _terrainSwapTimeout = setTimeout(function () {
        logCameraState("Terrain swap lock ended (before restore)");
        log("info", "DEM_RENDER: Terrain swap lock ended. Settling camera.");
        
        // Clean up timers
        _terrainSwapIntervals.forEach(clearTimeout);
        _terrainSwapIntervals = [];

        // Restore original camera methods
        if (viewer?.camera) {
          viewer.camera.flyTo = _originalFlyTo;
          viewer.camera.flyToBoundingSphere = _originalFlyToBoundingSphere;
          viewer.camera.setView = _originalSetView;
          viewer.camera.viewBoundingSphere = _originalViewBoundingSphere;
        }
        
        _isTerrainSwapping = false;
        window._is2DTo3DTransition = false;
        _terrainSwapTimeout = null;

        // Restore camera inputs after swap settles
        if (viewer?.scene && viewer.scene.screenSpaceCameraController) {
          configureCameraControllerForMode(currentSceneMode);
        }

        // If a camera action was intercepted, execute it now!
        if (_pendingCameraAction) {
          const action = _pendingCameraAction;
          _pendingCameraAction = null;
          try {
            log("info", "DEM_RENDER: Executing pending camera action of type " + action.type);
            if (viewer?.camera) {
              // Keep requestRenderMode=false so Cesium renders every frame during the
              // flight. The focusLoadedRegion3D complete/cancel callbacks own the
              // post-flight tile burst — do NOT start _driveRenderUntilTilesLoaded
              // here, because it would check tilesLoaded at the PRE-POSITION camera
              // angle (not the destination angle) and stop rendering mid-flight.
              viewer.scene.requestRenderMode = false;
              if (action.type === "flyTo") {
                viewer.camera.flyTo(...action.args);
              } else if (action.type === "flyToBoundingSphere") {
                const sphere = action.args[0];
                const opts = action.args[1];
                log("info", "DEM_RENDER: Pending flyToBoundingSphere details center=" + 
                    (sphere?.center ? "(" + sphere.center.x.toFixed(1) + ", " + sphere.center.y.toFixed(1) + ", " + sphere.center.z.toFixed(1) + ")" : "null") +
                    " radius=" + (sphere ? sphere.radius.toFixed(1) : "null") +
                    " heading=" + (opts?.offset ? opts.offset.heading : "null") +
                    " pitch=" + (opts?.offset ? opts.offset.pitch : "null") +
                    " range=" + (opts?.offset ? opts.offset.range : "null")
                );
                viewer.camera.flyToBoundingSphere(...action.args);
              }
              logCameraState("After executing pending action");
            }
          } catch (flightErr) {
            log("error", "DEM_RENDER: Failed to execute pending camera flight: " + flightErr);
            _driveRenderUntilTilesLoaded();
          }
        } else {
          // No pending flight — still need to stream tiles into view.
          // Drive rendering until globe reports tiles loaded.
          log("info", "DEM_RENDER: No pending camera action — driving tile render burst");
          _driveRenderUntilTilesLoaded();
        }
      }, lockDuration);
  }  // end _swapTerrainProviderLocked

  // Helper: drive the render loop until globe tiles finish loading.
  // Hoisted to outer scope (S7721) so it can be reused without nesting.
  // Uses globe.tilesLoaded to detect completion; falls back to 4 seconds.
  // PERF FIX: Guard against interval accumulation — at most one active drive interval.
  let _tileRenderDriveIv = null;
  function _driveRenderUntilTilesLoaded() {
    if (!viewer || !viewer.scene) return;
    // Cancel any existing drive interval before starting a new one.
    // Without this, repeated calls (terrain swap + layer toggle + stretch) stack
    // multiple concurrent 50ms intervals, causing progressive performance loss.
    if (_tileRenderDriveIv !== null) {
      clearInterval(_tileRenderDriveIv);
      _tileRenderDriveIv = null;
    }
    viewer.scene.requestRenderMode = false;
    let _elapsed = 0;
    _tileRenderDriveIv = setInterval(function () {
      if (!viewer || !viewer.scene) { clearInterval(_tileRenderDriveIv); _tileRenderDriveIv = null; return; }
      viewer.scene.requestRender();
      _elapsed += 50;
      const tilesLoaded = viewer.scene.globe ? viewer.scene.globe.tilesLoaded : false;
      if ((tilesLoaded && _elapsed >= 500) || _elapsed >= 4000) {
        clearInterval(_tileRenderDriveIv);
        _tileRenderDriveIv = null;
        log("info", "DEM_RENDER: Tile render burst complete tilesLoaded=" + tilesLoaded + " elapsed=" + _elapsed);
        if (viewer?.scene) {
          viewer.scene.requestRenderMode = true;
          viewer.scene.requestRender();
        }
      }
    }, 50);
  }

  function applyDemSceneSettings() {
    if (!viewer) return;

    // CRITICAL: Terabyte-scale DEM rendering optimizations with anti-flickering
    viewer.scene.globe.terrainExaggeration = Math.max(0.1, demVisual.exaggeration);
    // Also set verticalExaggeration for Cesium 1.90+ compatibility
    if (typeof viewer.scene.verticalExaggeration !== "undefined") {
      viewer.scene.verticalExaggeration = Math.max(0.1, demVisual.exaggeration);
    }
    
    // Disable all expensive visual effects for ultra-high resolution DEM (3-4cm/pixel)
    viewer.scene.globe.enableLighting = false;  // No lighting - major performance gain
    viewer.scene.fog.enabled = false;  // No fog
    viewer.scene.skyAtmosphere.show = false;  // No atmosphere
    viewer.shadows = false;  // No shadows

    // ── OPAQUE DEM: block everything behind the terrain surface ────────────────
    // depthTestAgainstTerrain=true makes Cesium depth-cull any primitive (entity
    // billboard, label, polyline) whose fragment is behind the rendered terrain mesh.
    // We also explicitly disable globe translucency so the terrain tiles are never
    // treated as partially transparent — ensuring zero see-through at any zoom level.
    viewer.scene.globe.depthTestAgainstTerrain = true;
    if (viewer.scene.globe.translucency) {
      viewer.scene.globe.translucency.enabled = false;
    }
    // undergroundColor = null means the underground plane is hidden; combined with
    // depthTest this fully occludes geometry behind the DEM surface.
    if (typeof viewer.scene.globe.undergroundColor !== "undefined") {
      viewer.scene.globe.undergroundColor = Cesium.Color.BLACK;
    }
    
    // ═══════════════════════════════════════════════════════════════════════════
    // DYNAMIC GPU SCALING: Intel vs NVIDIA
    // ═══════════════════════════════════════════════════════════════════════════
    if (window._isHighEndGpu) {
      // HIGH-END CONFIGURATION (NVIDIA/Dedicated GPU)
      viewer.resolutionScale = 1.0;                       // Crisp native resolution
      viewer.scene.globe.depthTestAgainstTerrain = true;  // Proper layer sorting
      viewer.scene.logarithmicDepthBuffer = false;         // Smooth camera dragging
      viewer.scene.globe.maximumScreenSpaceError = 1.0;   // Static high quality fidelity
      viewer.scene.globe.tileCacheSize = 800;             // Large cache without GC stutters
      viewer.scene.globe.preloadAncestors = true;         // Smooth transitions
      viewer.scene.globe.preloadSiblings = true;
      viewer.scene.globe.loadingDescendantLimit = 8;
      viewer.scene.globe.loadingQueueThreshold = 100;
      
      log("info", "DEM settings applied [MAX GPU CONFIG]: res=1.0 depthTest=true logDepth=false sse=1.0");
    } else {
      // SAFE FALLBACK CONFIGURATION (Intel Integrated GPU / Mac)
      viewer.resolutionScale = 1.0;                       // Crisp native resolution
      viewer.scene.globe.depthTestAgainstTerrain = true;  // Proper layer sorting
      viewer.scene.logarithmicDepthBuffer = false;         // Smooth camera dragging
      viewer.scene.globe.maximumScreenSpaceError = 1.5;   // Static balanced geometry for integrated GPU
      viewer.scene.globe.tileCacheSize = 400;             // Moderate cache for smoother pans
      viewer.scene.globe.preloadAncestors = true;         // Reduce tile churn during drag
      viewer.scene.globe.preloadSiblings = true;
      viewer.scene.globe.loadingDescendantLimit = 4;      // Allow fewer in-flight tiles to prevent lag
      viewer.scene.globe.loadingQueueThreshold = 100;
      
      log("info", "DEM settings applied [SAFE INTEL CONFIG modified for High Fidelity]: res=1.0 depthTest=true logDepth=true sse=1.5");
    }
    
    // Improve tile loading priority for better visual stability
    if (viewer.scene.globe._surface) {
      viewer.scene.globe._surface.tileLoadProgressEvent = viewer.scene.globe._surface.tileLoadProgressEvent || new Cesium.Event();
    }
    
    requestSceneRender();
  }

  function tuneCameraController() {
    if (!viewer) return;
    const controller = viewer.scene.screenSpaceCameraController;
    
    // OPTIMIZED CAMERA CONTROLS FOR SMOOTH, INTUITIVE NAVIGATION
    // Uses Cesium's default mouse button mapping for reliability
    
    // Enable collision detection to prevent going inside Earth
    controller.enableCollisionDetection = true;
    controller.maximumMovementRatio = 0.65;  // Faster camera movement
    
    // CRITICAL: Prevent camera from going inside Earth surface
    // Minimum zoom distance = 10 meters above ground (safe minimum)
    controller.minimumZoomDistance = 10.0;  // 10 meters minimum height
    controller.maximumZoomDistance = 100000000.0;  // 100,000 km maximum
// TODO: Refactor this function to reduce its Cognitive Complexity from 41 to the 15 allowed.
    
    viewer.scene.preRender.addEventListener(function () {
      if (!viewer || !viewer.camera || !viewer.scene.globe) return;

      // ── Dynamic 2D frustum width clamp ──────────────────────────────────────
      // Enforce strict minimum and maximum limits for the 2D frustum width to prevent
      // out-of-bounds Web Mercator projection errors/crashes (TypeError: southwest of undefined)
      // from pinch-to-zoom, right-click drag, double click, keyboard, etc.
      if (viewer.scene.mode === Cesium.SceneMode.SCENE2D) {
        const camera = viewer.camera;
        if (camera.frustum) {
          let currentWidth = undefined;
          let isOffCenter = false;
          if (typeof camera.frustum.width !== "undefined") {
            currentWidth = camera.frustum.width;
          } else if (typeof camera.frustum.right !== "undefined" && typeof camera.frustum.left !== "undefined") {
            currentWidth = camera.frustum.right - camera.frustum.left;
            isOffCenter = true;
          }
          
          if (typeof currentWidth !== "undefined" && Number.isFinite(currentWidth)) {
            const MIN_2D_LIMIT = 1.0;
            const MAX_2D_LIMIT = 15000000.0;
            if (currentWidth < MIN_2D_LIMIT || currentWidth > MAX_2D_LIMIT || !Number.isFinite(currentWidth)) {
            // S1854: remove useless initial assignment — value is always overwritten below
            let targetWidth;
            if (currentWidth > MAX_2D_LIMIT) {
                targetWidth = MAX_2D_LIMIT;
              } else {
                targetWidth = MIN_2D_LIMIT; // Catches NaN and < MIN
              }
              
              if (!isOffCenter) {
                camera.frustum.width = targetWidth;
              } else {
                const S = currentWidth > 0 ? (targetWidth / currentWidth) : 1.0;
                camera.frustum.left = camera.frustum.left * S;
                camera.frustum.right = camera.frustum.right * S;
                camera.frustum.top = camera.frustum.top * S;
                camera.frustum.bottom = camera.frustum.bottom * S;
              }
            }
          }
        }
      }

      // ── Camera collision avoidance ─────────────────────────────────────────
      const camera = viewer.camera;
      const positionCartographic = camera.positionCartographic;
      if (!positionCartographic) return;
      
      const terrainHeight = viewer.scene.globe.getHeight(positionCartographic);
      const h = (typeof terrainHeight === "number" && Number.isFinite(terrainHeight)) ? terrainHeight : 0.0;
      const minHeight = h + 10.0; // Keep camera at least 10 metres above terrain/ellipsoid
      
      if (positionCartographic.height < minHeight) {
        const cartographic = Cesium.Cartographic.clone(positionCartographic);
        cartographic.height = minHeight;
        const newCartesian = Cesium.Cartographic.toCartesian(cartographic, viewer.scene.globe.ellipsoid);
        if (newCartesian) {
          camera.position = newCartesian;
        }
      }
    });

    configureCameraControllerForMode(currentSceneMode);

    log("info", "Camera controls initialized: zoomFactor=" + viewer.scene.screenSpaceCameraController.zoomFactor + " pickHeight=" + viewer.scene.screenSpaceCameraController.minimumPickingTerrainHeight + " collision ON, min height 10m");

  }


  function configureCameraControllerForMode(mode) {
    if (!viewer) {
      return;
    }
    const controller = viewer.scene.screenSpaceCameraController;
    const is2d = String(mode || "3d").toLowerCase() === "2d";
    const isPan = panModeActive;
    
    // Use Cesium default input mapping but exclude WHEEL zoom to allow our custom smooth zoom
    controller.enableInputs = true;
    controller.enableTranslate = true;
    controller.enableZoom = true;
    controller.zoomEventTypes = [
      Cesium.CameraEventType.RIGHT_DRAG,
      Cesium.CameraEventType.PINCH
    ];
    // In pan mode keep rotate ON (required for 3D surface dragging) but disable tilt/look
    controller.enableRotate = !is2d;
    controller.enableTilt = !(is2d || isPan);
    controller.enableLook = !(is2d || isPan);

    
    // Inertia — keep spin/translate smooth; zoom MUST be zero-inertia.
    // inertiaZoom > 0 applies momentum over many frames after each scroll tick.
    // At high altitude (6000km), even one tick's momentum carries the camera from
    // space to ground level. Setting to 0 makes each tick a discrete, predictable step.
    controller.inertiaSpin = is2d ? 0.50 : 0.75;
    controller.inertiaTranslate = is2d ? 0.60 : 0.75;
    controller.inertiaZoom = 0.0;  // CRITICAL: must be 0 to prevent momentum runaway

    // zoomFactor=1.5: each tick zooms ~33% of distance — gentle and controllable at all
    // altitudes. 2.5 caused ultra-aggressive single-tick jumps (60%/tick is too much).
    controller.zoomFactor = 1.5;

    // Moderate sensitivity for rotate/translate
    if (controller.rotateSpeed !== undefined) controller.rotateSpeed = 1.5;
    if (controller.translateSpeed !== undefined) controller.translateSpeed = 1.5;

    // minimumPickingTerrainHeight: affects non-zoom interactions (tilt, pan pick).
    // Zoom direction is now handled entirely by our custom wheel handler which does
    // its own globe.pick — this value no longer causes zoom-to-wrong-scene.
    // 150,000m (150km) is Cesium's recommended default.
    controller.minimumPickingTerrainHeight = 150000.0;

    // minimumTrackBallHeight: below this altitude Cesium switches from surface-locked
    // trackball rotation to camera-position rotation. 7.5M was too large — activated
    // in the middle of normal zoom-to-asset range and caused rotation jumps.
    controller.minimumTrackBallHeight = 3000000.0;

    controller.minimumCollisionTerrainHeight = 15000.0;
    controller.minimumZoomDistance = 10.0;  // 10 metres minimum (don't go underground)

    log("info", "configureCameraControllerForMode: mode=" + mode + " zoomFactor=" + controller.zoomFactor + " inertiaZoom=" + controller.inertiaZoom + " pickTerrainH=" + controller.minimumPickingTerrainHeight + " trackballH=" + controller.minimumTrackBallHeight);


  }

  function applySceneModePerformanceHints(mode) {
    if (!viewer || !viewer.scene || !viewer.scene.globe) {
      return;
    }
    if (!scenePerfDefaults) {
      return;
    }
    const is2d = String(mode || "3d").toLowerCase() === "2d" || panModeActive;
    if (is2d) {
      // Favor smooth panning in 2D without lowering imagery/terrain quality.
      viewer.scene.globe.tileCacheSize = Math.max(scenePerfDefaults.tileCacheSize, 1200);
      viewer.scene.globe.loadingDescendantLimit = Math.max(scenePerfDefaults.loadingDescendantLimit, 12);
      viewer.scene.globe.preloadAncestors = true;
      viewer.scene.globe.preloadSiblings = true;
    } else {
      viewer.scene.globe.tileCacheSize = scenePerfDefaults.tileCacheSize;
      viewer.scene.globe.loadingDescendantLimit = scenePerfDefaults.loadingDescendantLimit;
      viewer.scene.globe.preloadAncestors = scenePerfDefaults.preloadAncestors;
      viewer.scene.globe.preloadSiblings = scenePerfDefaults.preloadSiblings;
    }
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
    updateCameraOrbitTarget(normalized);
  }

  function updateCameraOrbitTarget(bounds) {
    const normalized = normalizeBounds(bounds);
    if (!normalized) {
      return;
    }
    const rect = Cesium.Rectangle.fromDegrees(normalized.west, normalized.south, normalized.east, normalized.north);
    const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
    cameraOrbitBounds = normalized;
    cameraOrbitRange = Math.max(compute3DFocusRange(normalized), sphere.radius * 1.2, 250.0);
    if (viewer?.camera) {
      if (Number.isFinite(viewer.camera.heading)) {
        cameraOrbitHeading = viewer.camera.heading;
      }
      if (Number.isFinite(viewer.camera.pitch)) {
        cameraOrbitPitch = viewer.camera.pitch;
      }
    }
  }

  function removeLayerByKey(layerKey) {
    if (!viewer || !layerKey) {
      return false;
    }
    const key = String(layerKey);
    let removed = false;

    if (activeDemContext?.layerKey === key) {
      clearDemTerrainMode();
      removed = true;
    }

    const mainLayer = managedImageryLayers.get(key);
    if (mainLayer) {
      viewer.imageryLayers.remove(mainLayer, false);
      managedImageryLayers.delete(key);
      layerDefinitions.delete(key);
      layerVisibilityState.delete(key);
      removed = true;
    }

    const hillshadeKey = key + ":hillshade";
    const hillshadeLayer = managedImageryLayers.get(hillshadeKey);
    if (hillshadeLayer) {
      viewer.imageryLayers.remove(hillshadeLayer, false);
      managedImageryLayers.delete(hillshadeKey);
      layerDefinitions.delete(hillshadeKey);
      layerVisibilityState.delete(hillshadeKey);
      removed = true;
    }

    if (_lastKnownLayerOrder && Array.isArray(_lastKnownLayerOrder)) {
      _lastKnownLayerOrder = _lastKnownLayerOrder.filter(item => item !== key);
    }

    applySwipeComparatorSplit();
    requestSceneRender();
    return removed;
  }

  function syncOrbitFromCurrentCamera(bounds) {
    if (!viewer || !viewer.camera) {
      return;
    }
    const normalized = normalizeBounds(bounds);
    if (!normalized) {
      return;
    }
    const rect = Cesium.Rectangle.fromDegrees(normalized.west, normalized.south, normalized.east, normalized.north);
    const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
    const camera = viewer.camera;
    if (Number.isFinite(camera.heading)) {
      cameraOrbitHeading = camera.heading;
    }
    if (Number.isFinite(camera.pitch)) {
      cameraOrbitPitch = camera.pitch;
    }
    if (camera.positionWC && sphere.center) {
      const distance = Cesium.Cartesian3.distance(camera.positionWC, sphere.center);
      if (Number.isFinite(distance) && distance > 1.0) {
        cameraOrbitRange = distance;
      }
    }
  }

  function resolvePreferredFocusBounds() {
    const pinnedBounds = normalizeBounds(activeTileBounds);
    if (pinnedBounds && !isNearGlobalBounds(pinnedBounds)) {
      return pinnedBounds;
    }
    if (activeDemContext?.options && activeDemContext.options.bounds) {
      const demBounds = normalizeBounds(activeDemContext.options.bounds);
      if (demBounds) {
        return demBounds;
      }
    }
    if (activeImageryLayer?.imageryProvider && activeImageryLayer.imageryProvider.rectangle) {
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

  function applyDefaultStartupFocus() {
    if (!viewer) {
      return;
    }
    viewer.camera.cancelFlight();
    viewer.camera.setView({
      destination: Cesium.Cartesian3.fromDegrees(
        DEFAULT_STARTUP_CENTER_LON,
        DEFAULT_STARTUP_CENTER_LAT,
        DEFAULT_STARTUP_HEIGHT_M
      ),
      orientation: {
        heading: DEFAULT_STARTUP_HEADING,
        pitch: DEFAULT_STARTUP_PITCH,
        roll: 0.0,
      },
    });
    cameraOrbitHeading = DEFAULT_STARTUP_HEADING;
    cameraOrbitPitch = DEFAULT_STARTUP_PITCH;
    cameraOrbitRange = DEFAULT_STARTUP_HEIGHT_M;
    viewer.scene.requestRender();
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

  function focusLoadedRegion2D(durationSeconds) {
    if (!viewer) {
      return;
    }
    const boundsToUse = pendingFocusBounds || activeTileBounds || lastLoadedBounds;
    if (!boundsToUse) {
      return;
    }
    const paddedBounds = padBounds(boundsToUse, 0.06) || boundsToUse;
    const rect = Cesium.Rectangle.fromDegrees(
      paddedBounds.west,
      paddedBounds.south,
      paddedBounds.east,
      paddedBounds.north
    );
    const duration = Number.isFinite(durationSeconds) ? durationSeconds : 0.6;
    viewer.camera.cancelFlight();
    viewer.camera.flyTo({
      destination: rect,
      duration: duration,
    });
    viewer.scene.requestRender();
// TODO: Refactor this function to reduce its Cognitive Complexity from 18 to the 15 allowed.
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
    const centerLon = (paddedBounds.west + paddedBounds.east) * 0.5;
    const centerLat = (paddedBounds.south + paddedBounds.north) * 0.5;
    const centerCarto = new Cesium.Cartographic(Cesium.Math.toRadians(centerLon), Cesium.Math.toRadians(centerLat));
    let terrainHeight = undefined;
    if (viewer.scene.globe && typeof viewer.scene.globe.getHeight === "function") {
      const h = viewer.scene.globe.getHeight(centerCarto);
      if (typeof h === "number" && Number.isFinite(h)) {
        terrainHeight = h;
      }
    }
    if (terrainHeight === undefined || terrainHeight === null || isNaN(terrainHeight)) {
      terrainHeight = (window.offlineGIS && typeof window.offlineGIS.getDemTerrainHeightFallback === "function")
          ? window.offlineGIS.getDemTerrainHeightFallback()
          : 0.0;
    }
    if (viewer.scene.globe && typeof viewer.scene.globe.terrainExaggeration === "number") {
      terrainHeight *= viewer.scene.globe.terrainExaggeration;
    }
    const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, terrainHeight);
    const range = Math.max(compute3DFocusRange(paddedBounds), sphere.radius * 1.3);
    const duration = Number.isFinite(durationSeconds) ? durationSeconds : 1.0;
    const heading = Number.isFinite(viewer.camera.heading) ? viewer.camera.heading : 0.0;
    const lastClickAt = Number(window._offlineGISLastMapClickAt || 0);
    const anchorCenter = lastMapClickCartesian && Number.isFinite(lastClickAt) && (Date.now() - lastClickAt) <= 1200
      ? Cesium.Cartesian3.clone(lastMapClickCartesian)
      : null;
    const focusSphere = anchorCenter ? new Cesium.BoundingSphere(anchorCenter, range) : sphere;
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
    
    // Keep rendering active during AND after flight so tiles stream in with no blank globe
    viewer.scene.requestRenderMode = false;
    viewer.camera.cancelFlight();
    viewer.camera.flyToBoundingSphere(focusSphere, {
      offset: new Cesium.HeadingPitchRange(
        heading,
        Cesium.Math.toRadians(-35),
        range
      ),
      duration: duration,
      complete: function() {
        if (viewer?.scene) {
          // Ensure continuous rendering for post-flight tile streaming.
          // requestRenderMode may have been re-enabled during the flight;
          // reset it here so the burst keeps Cesium hot while tiles finish.
          viewer.scene.requestRenderMode = false;
          let _t = 0;
          let _iv = setInterval(function() {
            if (!viewer || !viewer.scene) { clearInterval(_iv); return; }
            viewer.scene.requestRender();
            _t += 50;
            let loaded = viewer.scene.globe ? viewer.scene.globe.tilesLoaded : false;
            if ((loaded && _t >= 500) || _t >= 4000) {
              clearInterval(_iv);
              log("info", "focusLoadedRegion3D: tile burst done tilesLoaded=" + loaded + " elapsed=" + _t);
              if (viewer?.scene) {
                viewer.scene.requestRenderMode = true;
                viewer.scene.requestRender();
              }
            }
          }, 50);
        }
      },
      cancel: function() {
        if (viewer?.scene) {
          // Even on cancel keep driving renders until tiles settle
          let _t = 0;
          let _iv = setInterval(function() {
            if (!viewer || !viewer.scene) { clearInterval(_iv); return; }
            viewer.scene.requestRender();
            _t += 50;
            let loaded = viewer.scene.globe ? viewer.scene.globe.tilesLoaded : false;
            if ((loaded && _t >= 300) || _t >= 2000) {
              clearInterval(_iv);
              if (viewer?.scene) {
                viewer.scene.requestRenderMode = true;
                viewer.scene.requestRender();
              }
            }
          }, 50);
        }
      }
    });
  }

  // ─────────────────────────────────────────────────────────────────────────
  //  DEM Rendering — Imagery-Only Pipeline
  //
  //  Design rationale: The previous approach used a custom TerrainProvider that
  //  decoded Terrarium-encoded PNGs frame-by-frame in the main JS thread. Cesium
  //  calls requestTileGeometry() synchronously for every visible tile, which
  //  spawned dozens of parallel Image loads + canvas operations per frame,
  //  exhausting the V8 heap and hanging/white-screening the globe. This is
  //  fundamentally incompatible with the QtWebEngine Chromium 87 environment.
  //
  //  The new approach renders DEM data as two flat EPSG:3857 imagery layers on
  //  the stable EllipsoidTerrainProvider:
  //    1. Colormap drape  — TiTiler colormap (gray/terrain) at full opacity
  //    2. Hillshade overlay — TiTiler hillshade algorithm at ~35% alpha
  //
  //  This is scientifically correct (standard GIS pseudo-color visualization),
  //  fully crash-proof for datasets of any size (2cm–5cm resolution, terabytes),
  //  and works identically on macOS and Windows/NVIDIA.
  // ─────────────────────────────────────────────────────────────────────────

  function shouldUseFetch(url) {
    const value = String(url || "").trim().toLowerCase();
    return value.startsWith("http://") || value.startsWith("https://");
  }

  async function loadJsonResource(url) {
    try {
      return await Cesium.Resource.fetchJson({ url: String(url) });
    } catch (_resourceError) {
      if (!shouldUseFetch(url)) {
        return null;
      }
      try {
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) {
          return null;
        }
        return await response.json();
      } catch (_fetchError) {
        return null;
      }
    }
  }



  // ═══════════════════════════════════════════════════════════════════════════
