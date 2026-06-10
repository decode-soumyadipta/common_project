  // SECTION: Search Polygon & AOI  →  moved to modules/search/search_polygon_controller.js
  // ═══════════════════════════════════════════════════════════════════════════

  function ensureSearchPreviewEntities() {
    if (searchPolygonController) {
      searchPolygonController.ensureSearchPreviewEntities();
    }
  }

  function syncSearchVertexEntities() {
    if (searchPolygonController) {
      searchPolygonController.syncSearchVertexEntities();
    }
  }

  function updateSearchPolygonPreview() {
    if (searchPolygonController) {
      searchPolygonController.updateSearchPolygonPreview();
    }
  }

  function finalizeSearchPolygon() {
    if (searchPolygonController) {
      searchPolygonController.finalizeSearchPolygon();
    }
  }

  function loadSearchPolygon(points) {
    if (!Array.isArray(points)) {
      return;
    }
    searchPolygonPoints.length = 0;
    for (let i = 0; i < points.length; i++) {
      const item = points[i] || {};
      const lon = Number(item.lon);
      const lat = Number(item.lat);
      if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
        continue;
      }
      searchPolygonPoints.push({
        lon: lon,
        lat: lat,
        cartesian: Cesium.Cartesian3.fromDegrees(lon, lat),
      });
    }
    searchPolygonLocked = true;
    updateSearchPolygonPreview();
    updateAoiPanel(searchPolygonPoints);
    emitSearchGeometry("polygon", { points: searchPolygonPoints.map(p => ({ lon: p.lon, lat: p.lat })) });
    requestSceneRender();
  }

  function updateAoiPanel(points) {
    if (searchPolygonController) {
      searchPolygonController.updateAoiPanel(points);
    }
  }

  function toggleAoiPanelMinimize() {
    if (searchPolygonController) {
      searchPolygonController.toggleAoiPanelMinimize();
    }
  }

  function updatePolygonDropdownUI() {
    if (searchPolygonController) {
      searchPolygonController.updatePolygonDropdownUI();
    }
  }

  function toggleDrawnPolygonVisibility(polyId, visible) {
    if (searchPolygonController) {
      searchPolygonController.toggleDrawnPolygonVisibility(polyId, visible);
    }
  }

  function toggleAllDrawnPolygonsVisibility(visible) {
    if (searchPolygonController) {
      searchPolygonController.toggleAllDrawnPolygonsVisibility(visible);
    }
  }

  const comparatorPolygonEntities = { left: [], right: [] };

  let _cameraStateBeforeMorph = null;

  function hasSavedCameraState() {
    return _cameraStateBeforeMorph !== null;
  }

  function restoreCameraAfterMorph() {
    if (!_cameraStateBeforeMorph) return;
    const saved = _cameraStateBeforeMorph;
    _cameraStateBeforeMorph = null;
    
    try {
      viewer.camera.cancelFlight();
      
      const safeRange = Math.max(saved.range, 100.0);
      
      if (viewer.scene.mode === Cesium.SceneMode.SCENE2D) {
        // In 2D mode, set view directly to the point on the flat map using setView to prevent flight cancels/zoom bugs
        sceneDebug("restoreCameraAfterMorph (2D): setting view to center: lon=" + saved.lon.toFixed(4) + 
                   " lat=" + saved.lat.toFixed(4) + " range/height=" + safeRange.toFixed(0));
        viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(saved.lon, saved.lat, safeRange),
          orientation: {
            heading: saved.heading,
            pitch: Cesium.Math.toRadians(-90.0), // Always look straight down in 2D
            roll: 0.0
          }
        });
      } else {
        // In 3D mode, set view using lookAt + lookAtTransform(IDENTITY) to preserve pitch and range exactly
        let targetPitch = saved.pitch;
        if (targetPitch > Cesium.Math.toRadians(-15.0)) {
          targetPitch = Cesium.Math.toRadians(-35.0);
        }
        
        let targetHeight = saved.height || 0.0;
        if (targetHeight === 0.0 && activeDemTerrainProvider && activeDemContext && activeDemContext.visible !== false) {
          const fallback = (window.offlineGIS && typeof window.offlineGIS.getDemTerrainHeightFallback === "function")
              ? window.offlineGIS.getDemTerrainHeightFallback()
              : 0.0;
          let exag = 1.0;
          if (viewer.scene.globe && typeof viewer.scene.globe.terrainExaggeration === "number") {
            exag = viewer.scene.globe.terrainExaggeration;
          }
          targetHeight = fallback * exag;
        }

        sceneDebug("restoreCameraAfterMorph (3D): setting view: lon=" + saved.lon.toFixed(4) + 
                   " lat=" + saved.lat.toFixed(4) + " targetHeight=" + targetHeight.toFixed(1) +
                   " range=" + safeRange.toFixed(0) + 
                   " pitch=" + Cesium.Math.toDegrees(targetPitch).toFixed(1) + "°");
                   
        const targetCartesian = Cesium.Cartesian3.fromDegrees(saved.lon, saved.lat, targetHeight);
        viewer.camera.lookAt(
          targetCartesian,
          new Cesium.HeadingPitchRange(saved.heading, targetPitch, safeRange)
        );
        // Unbind the camera transform lock to allow regular panning controls
        viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
      }
      
      // Explicitly ensure user map panning/zooming controls are active
      if (viewer?.scene?.screenSpaceCameraController) {
        viewer.scene.screenSpaceCameraController.enableInputs = true;
      }
      requestSceneRender();
    } catch (err) {
      if (viewer?.scene?.screenSpaceCameraController) {
        viewer.scene.screenSpaceCameraController.enableInputs = true;
      }
      sceneDebug("restoreCameraAfterMorph failed: " + err);
    }
  }

  function updateComparatorPolygons(visible) {
    if (searchPolygonController) {
      searchPolygonController.updateComparatorPolygons(visible);
    }
  }

  function handleMorphTo2D() {
    sceneDebug("setSceneModeInternal morphTo2D begin pendingFocus=" + String(pendingFocusAfterMorph));
    viewer.scene.morphTo2D(1.0);
    currentSceneMode = "2d";
    applySceneModePerformanceHints("2d");
    syncSceneModeToggle("2d");
    if (comparatorModeEnabled && typeof comparatorViewers !== "undefined" && Array.isArray(comparatorViewers)) {
      comparatorViewers.forEach(v => setComparatorViewerModeByType(v));
    }
    updateBasemapBlendForCurrentMode();
    
    window.requestAnimationFrame(function () {
      if (window._activeCompositorBounds && window.offlineGIS && typeof window.offlineGIS.lockCameraToCompositorAsset === "function") {
        window.offlineGIS.lockCameraToCompositorAsset(window._activeCompositorBounds);
      } else if (_cameraStateBeforeMorph) {
        sceneDebug("handleMorphTo2D: deferring camera restoration to morphComplete");
      } else {
        const bounds = activeTileBounds || lastLoadedBounds;
        if (bounds) {
          if (typeof focusLoadedRegion2D === "function") {
            focusLoadedRegion2D(1.0);
          }
        }
      }
      requestSceneRender();
    });

    requestSceneRender();
    window.requestAnimationFrame(requestSceneRender);
    setStatus("2D map mode active.");
    log("info", "Scene mode switched to 2D from 3D");
  }

  function handleMorphTo3D() {
    sceneDebug("setSceneModeInternal morphTo3D begin pendingFocus=" + String(pendingFocusAfterMorph));
    viewer.scene.morphTo3D(1.0);
    currentSceneMode = "3d";

    applySceneModePerformanceHints("3d");
    syncSceneModeToggle("3d");
    if (comparatorModeEnabled && typeof comparatorViewers !== "undefined" && Array.isArray(comparatorViewers)) {
      comparatorViewers.forEach(v => setComparatorViewerModeByType(v));
    }
    updateBasemapBlendForCurrentMode();

    if (cameraOrbitPitch < MIN_3D_PITCH_RAD || Math.abs(cameraOrbitPitch - Cesium.Math.toRadians(-90.0)) < Cesium.Math.toRadians(5.0)) {
      cameraOrbitPitch = DEFAULT_3D_PITCH_RAD;
      sceneDebug("setSceneModeInternal: clamped pitch to default 3D pitch " + Cesium.Math.toDegrees(cameraOrbitPitch).toFixed(1) + "°");
    }

    window.requestAnimationFrame(function () {
      if (window.offlineGIS && typeof window.offlineGIS.logCameraState === "function") {
        window.offlineGIS.logCameraState("At requestAnimationFrame of morphTo3D");
      }

      if (_cameraStateBeforeMorph) {
        sceneDebug("handleMorphTo3D: deferring camera restoration to morphComplete");
      }

      if (window._activeCompositorBounds && window.offlineGIS && typeof window.offlineGIS.lockCameraToCompositorAsset === "function") {
        window.offlineGIS.lockCameraToCompositorAsset(window._activeCompositorBounds);
      } else if (!_cameraStateBeforeMorph) {
        const bounds = activeTileBounds || lastLoadedBounds;
        if (bounds) {
          schedule3DFocusAfterMorph(1.0);
        }
      }
      requestSceneRender();
    });

    requestSceneRender();
    setStatus("3D globe mode active.");
    log("info", "Scene mode switched to 3D from 2D");
  }

  function setSceneModeInternal(mode) {
    if (!viewer) return;
    try {
      viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
    } catch (_) {}
    const normalized = String(mode || "3d").toLowerCase() === "2d" ? "2d" : "3d";
    if (normalized === "3d" && currentSceneMode !== "3d") {
      window._is2DTo3DTransition = true;
      setTimeout(function () {
        window._is2DTo3DTransition = false;
      }, 1500);
    }
    let actualMode = detectSceneMode();
    sceneDebug(
      "setSceneModeInternal enter requested=" +
        mode +
        " normalized=" +
        normalized +
        " actualMode=" +
        actualMode +
        " currentSceneMode=" +
        currentSceneMode +
        " pendingSceneModeAfterMorph=" +
        String(pendingSceneModeAfterMorph)
    );
    if (actualMode === "morphing") {
      sceneDebug("setSceneModeInternal scene is morphing; forcing completeMorph before queueing");
      try {
        viewer.scene.completeMorph();
      } catch (_err) {
      }
      actualMode = detectSceneMode();
      sceneDebug("setSceneModeInternal after completeMorph actualMode=" + actualMode);
    }
    if (actualMode === "morphing") {
      pendingSceneModeAfterMorph = normalized;
      syncSceneModeToggle(normalized);
      sceneDebug("setSceneModeInternal queued mode while morphing queued=" + normalized);
      return;
    }
    if (actualMode !== currentSceneMode) {
      currentSceneMode = actualMode;
      syncSceneModeToggle(actualMode);
      sceneDebug("setSceneModeInternal synced currentSceneMode to actualMode=" + actualMode);
    }
    pendingSceneModeAfterMorph = null;
    const preferredBounds = resolvePreferredFocusBounds();
    if (preferredBounds) {
      setActiveTileBounds(preferredBounds);
    }
    if (normalized === currentSceneMode) {
      sceneDebug("setSceneModeInternal no-op branch normalized matches current=" + normalized);
      configureCameraControllerForMode(normalized);
      syncSceneModeToggle(normalized);
      if (window._activeCompositorBounds && window.offlineGIS && typeof window.offlineGIS.lockCameraToCompositorAsset === "function") {
        window.offlineGIS.lockCameraToCompositorAsset(window._activeCompositorBounds);
      }
      requestSceneRender();
      return;
    }
    pendingFocusBounds = preferredBounds;
    pendingFocusAfterMorph = Boolean(preferredBounds);
    pendingTerrainSceneAfterMorph = normalized === "3d" && Boolean(preferredBounds);
    configureCameraControllerForMode(normalized);

    if (viewer && viewer.camera) {
      try {
        if (viewer.scene.mode === Cesium.SceneMode.SCENE2D) {
          // In 2D mode, the camera is looking straight down, so unproject the camera position cartesian to get accurate coordinates
          const projection = viewer.scene.mapProjection || new Cesium.GeographicProjection();
          const carto = projection.unproject(viewer.camera.position);
          if (carto && Number.isFinite(carto.longitude)) {
            _cameraStateBeforeMorph = {
              lon: Cesium.Math.toDegrees(carto.longitude),
              lat: Cesium.Math.toDegrees(carto.latitude),
              height: 0.0,
              range: Number.isFinite(carto.height) ? carto.height : 100000.0,
              heading: Number.isFinite(viewer.camera.heading) ? viewer.camera.heading : 0.0,
              pitch: Cesium.Math.toRadians(-90.0)
            };
            sceneDebug("setSceneModeInternal (2D pre-save): saved camera look-at target lon=" +
              _cameraStateBeforeMorph.lon.toFixed(4) + " lat=" + _cameraStateBeforeMorph.lat.toFixed(4) +
              " range=" + _cameraStateBeforeMorph.range.toFixed(0));
          }
        } else {
          // In 3D / CV modes, perform ray picking to find look-at target on globe/terrain
          let targetCartesian = null;
          const centerPos = new Cesium.Cartesian2(viewer.canvas.clientWidth / 2, viewer.canvas.clientHeight / 2);
          const ray = viewer.camera.getPickRay(centerPos);
          if (ray && viewer.scene.globe) {
            targetCartesian = viewer.scene.globe.pick(ray, viewer.scene);
          }
          if (!targetCartesian) {
            targetCartesian = viewer.camera.pickEllipsoid(centerPos);
          }
          if (!targetCartesian) {
            targetCartesian = viewer.camera.position;
          }

          if (targetCartesian) {
            const targetCarto = Cesium.Cartographic.fromCartesian(targetCartesian);
            let range = Cesium.Cartesian3.distance(viewer.camera.position, targetCartesian);
            if (!Number.isFinite(range) || range < 10.0) {
              const camCarto = viewer.camera.positionCartographic;
              range = camCarto ? camCarto.height : 100000.0;
            }
            _cameraStateBeforeMorph = {
              lon: Cesium.Math.toDegrees(targetCarto.longitude),
              lat: Cesium.Math.toDegrees(targetCarto.latitude),
              height: targetCarto.height,
              range: range,
              heading: Number.isFinite(viewer.camera.heading) ? viewer.camera.heading : 0.0,
              pitch: Number.isFinite(viewer.camera.pitch) ? viewer.camera.pitch : Cesium.Math.toRadians(-90.0)
            };
            sceneDebug("setSceneModeInternal (3D pre-save): saved camera look-at target lon=" +
              _cameraStateBeforeMorph.lon.toFixed(4) + " lat=" + _cameraStateBeforeMorph.lat.toFixed(4) +
              " range=" + _cameraStateBeforeMorph.range.toFixed(0) + " pitch=" + Cesium.Math.toDegrees(_cameraStateBeforeMorph.pitch).toFixed(1));
          }
        }
      } catch (_saveErr) {
        _cameraStateBeforeMorph = null;
        sceneDebug("setSceneModeInternal: failed to save pre-morph camera state: " + _saveErr);
      }
    }

    if (normalized === "2d") {
      handleMorphTo2D();
    } else {
      handleMorphTo3D();
    }
  }

  function startFlyThroughBounds(west, south, east, north) {
    if (!viewer) return;
    const targetBounds = { west: west, south: south, east: east, north: north };
    setActiveTileBounds(targetBounds);
    const modeNow = detectSceneMode();
    sceneDebug("startFlyThroughBounds modeNow=" + modeNow + " currentSceneMode=" + currentSceneMode);

    if (modeNow !== "3d") {
      pendingFlyThroughBounds = targetBounds;
      setSceneModeInternal("3d");
      setStatus("Switching to 3D globe...");
      sceneDebug("startFlyThroughBounds queued until 3d morph completes");
      return;
    }

    const rect = Cesium.Rectangle.fromDegrees(west, south, east, north);
    const centerLon = (west + east) * 0.5;
    const centerLat = (south + north) * 0.5;
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
    const nearRange = Math.max(compute3DFocusRange(lastLoadedBounds), sphere.radius * 1.4);
    const farRange = Math.min(Math.max(nearRange * 3.25, 280.0), 4500000.0);

    // Clamp near range so the camera never goes below ~80 m above the bounding
    // sphere surface — prevents the "enters the globe / black surroundings" bug
    // caused by the camera clipping through terrain during the fly-through arc.
    const safeNearRange = Math.max(nearRange, sphere.radius * 0.5, 80.0);

    // Enhanced camera positioning debug (reduced verbosity)
    log("debug", "CAMERA_DEBUG: Range calculation nearRange=" + nearRange.toFixed(0) + 
        " farRange=" + farRange.toFixed(0) + " safeNearRange=" + safeNearRange.toFixed(0));

    viewer.camera.cancelFlight();
    
    // First position: Far view
    const farHeading = Cesium.Math.toRadians(-45);
    const farPitch = Cesium.Math.toRadians(-55);
    
    viewer.camera.flyToBoundingSphere(sphere, {
      offset: new Cesium.HeadingPitchRange(farHeading, farPitch, farRange),
      duration: 2.6,
      complete: function () {
        // Second position: Near view
        const nearHeading = Cesium.Math.toRadians(30);
        const nearPitch = Cesium.Math.toRadians(-35);
        
        viewer.camera.flyToBoundingSphere(sphere, {
          offset: new Cesium.HeadingPitchRange(nearHeading, nearPitch, safeNearRange),
          duration: 3.2,
          complete: function() {
            // Final position logging (reduced verbosity)
            const finalPos = viewer.camera.positionCartographic;
            if (finalPos) {
              const finalLon = Cesium.Math.toDegrees(finalPos.longitude);
              const finalLat = Cesium.Math.toDegrees(finalPos.latitude);
              log("debug", "CAMERA_DEBUG: Final position lon=" + finalLon.toFixed(4) + 
                  " lat=" + finalLat.toFixed(4) + " height=" + finalPos.height.toFixed(0));
              
              // Force render after camera positioning
              if (viewer.scene) {
                viewer.scene.requestRender();
              }
            }
          }
        });
      },
    });
    setStatus("Fly-through started.");
    sceneDebug("startFlyThroughBounds flight started in 3d");
    log("info", "Fly-through started for selected bounds");
  }

  window.offlineGIS = window.offlineGIS || {};
  Object.assign(window.offlineGIS, {
    setSceneModeInternal: setSceneModeInternal,
    hasSavedCameraState: hasSavedCameraState,
    restoreCameraAfterMorph: restoreCameraAfterMorph,
  });
