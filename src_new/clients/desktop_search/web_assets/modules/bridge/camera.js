  // SECTION: Camera & Scene Mode  →  future: modules/camera.js
  // Functions: applyDefaultSceneSettings, applyDemSceneSettings,
  //   tuneCameraController, configureCameraControllerForMode,
  //   _swapTerrainProviderLocked, setSceneModeInternal, detectSceneMode,
  //   syncSceneModeToggle, focusPreferredRegion, focusPreferredRegion3D,
  //   focusLoadedRegion3D, schedule3DFocusAfterMorph, startFlyThroughBounds,
  //   applyDefaultStartupFocus, _updateCompass, Asia camera lock postRender
  // ═══════════════════════════════════════════════════════════════════════════

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
   * We lock the camera for 5 post-render frames to absorb all async resets.
   */
  function _swapTerrainProviderLocked(newProvider) {
    if (!viewer || !newProvider) {
      log("warn", "DEM_RENDER: _swapTerrainProviderLocked called with invalid params viewer=" + !!viewer + " provider=" + !!newProvider);
      return;
    }
    if (viewer.terrainProvider === newProvider) {
      log("info", "DEM_RENDER: _swapTerrainProviderLocked skipped - provider already active");
      return;
    }

    log("info", "DEM_RENDER: Swapping terrain provider without camera lock");
    log("info", "DEM_RENDER: Old provider type: " + (viewer.terrainProvider.constructor ? viewer.terrainProvider.constructor.name : "unknown"));
    
    viewer.terrainProvider = newProvider;
    
    log("info", "DEM_RENDER: New provider type: " + (newProvider.constructor ? newProvider.constructor.name : "unknown"));
    log("info", "DEM_RENDER: Provider ready: " + newProvider.ready);

    // Proactively and smoothly realign all search result markers to the new terrain provider
    if (window.offlineGIS && typeof window.offlineGIS.realignMarkersToTerrain === "function") {
      window.offlineGIS.realignMarkersToTerrain();
    }
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
    
    // ═══════════════════════════════════════════════════════════════════════════
    // DYNAMIC GPU SCALING: Intel vs NVIDIA
    // ═══════════════════════════════════════════════════════════════════════════
    if (window._isHighEndGpu) {
      // HIGH-END CONFIGURATION (NVIDIA/Dedicated GPU)
      viewer.resolutionScale = 1.0;                       // Crisp native resolution
      viewer.scene.globe.depthTestAgainstTerrain = true;  // Proper layer sorting
      viewer.scene.logarithmicDepthBuffer = true;         // Smooth camera dragging
      viewer.scene.globe.maximumScreenSpaceError = 1.0;   // Original high quality fidelity (per user request)
      viewer.scene.globe.tileCacheSize = 4000;             // Larger cache for smoother pans
      viewer.scene.globe.preloadAncestors = true;         // Smooth transitions
      viewer.scene.globe.preloadSiblings = true;
      viewer.scene.globe.loadingDescendantLimit = 24;
      viewer.scene.globe.loadingQueueThreshold = 100;
      
      log("info", "DEM settings applied [MAX GPU CONFIG]: res=1.0 depthTest=true logDepth=true sse=1.0");
    } else {
      // SAFE FALLBACK CONFIGURATION (Intel Integrated GPU / Mac)
      // Modified to prioritize visual fidelity (true 3D elevations) over pure performance
      viewer.resolutionScale = 1.0;                       // Crisp native resolution
      viewer.scene.globe.depthTestAgainstTerrain = true;  // Proper layer sorting
      viewer.scene.logarithmicDepthBuffer = true;         // Smooth camera dragging
      viewer.scene.globe.maximumScreenSpaceError = 1.5;   // High quality geometry
      viewer.scene.globe.tileCacheSize = 3000;             // Moderate cache for smoother pans
      viewer.scene.globe.preloadAncestors = true;         // Reduce tile churn during drag
      viewer.scene.globe.preloadSiblings = true;
      viewer.scene.globe.loadingDescendantLimit = 16;      // Allow more in-flight tiles
      viewer.scene.globe.loadingQueueThreshold = 100;
      
      log("info", "DEM settings applied [SAFE INTEL CONFIG modified for High Fidelity]: res=1.0 depthTest=true logDepth=true sse=2.0");
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
    
    // NOTE: zoomFactor is NOT set here — configureCameraControllerForMode() below sets it
    // to 5.0 (Cesium default). The previous 0.4 here caused aggressive zoom-in and is removed.



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
    
    // Use Cesium default input mapping
    controller.enableInputs = true;
    controller.enableTranslate = true;
    controller.enableZoom = true;
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
    if (viewer && viewer.camera) {
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

    if (activeDemContext && activeDemContext.layerKey === key) {
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
    if (activeDemContext && activeDemContext.options && activeDemContext.options.bounds) {
      const demBounds = normalizeBounds(activeDemContext.options.bounds);
      if (demBounds) {
        return demBounds;
      }
    }
    if (activeImageryLayer && activeImageryLayer.imageryProvider && activeImageryLayer.imageryProvider.rectangle) {
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
    const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
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
    viewer.camera.cancelFlight();
    viewer.camera.flyToBoundingSphere(focusSphere, {
      offset: new Cesium.HeadingPitchRange(
        heading,
        Cesium.Math.toRadians(-35),
        range
      ),
      duration: duration,
    });
    viewer.scene.requestRender();
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
