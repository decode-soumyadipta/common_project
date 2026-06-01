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

  function updateComparatorPolygons(visible) {
    if (searchPolygonController) {
      searchPolygonController.updateComparatorPolygons(visible);
    }
  }

  function setSceneModeInternal(mode) {
    if (!viewer) return;
    const normalized = String(mode || "3d").toLowerCase() === "2d" ? "2d" : "3d";
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
        // Ignore completeMorph failures and continue with queueing below.
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
      requestSceneRender();
      return;
    }
    pendingFocusBounds = preferredBounds;
    pendingFocusAfterMorph = Boolean(preferredBounds);
    pendingTerrainSceneAfterMorph = normalized === "3d" && Boolean(preferredBounds);
    configureCameraControllerForMode(normalized);
    if (normalized === "2d") {
      sceneDebug("setSceneModeInternal morphTo2D begin pendingFocus=" + String(pendingFocusAfterMorph));
      // Instant morph (0-duration) to avoid lag and frame drops
      viewer.scene.morphTo2D(0.0);
      currentSceneMode = "2d";
      applySceneModePerformanceHints("2d");
      syncSceneModeToggle("2d");
      if (comparatorModeEnabled && typeof comparatorViewers !== "undefined" && Array.isArray(comparatorViewers)) {
        comparatorViewers.forEach(v => setComparatorViewerModeByType(v));
      }
      updateBasemapBlendForCurrentMode();
      // Force immediate re-render after instant morph
      requestSceneRender();
      window.requestAnimationFrame(requestSceneRender);
      setStatus("2D map mode active.");
      log("info", "Scene mode switched to 2D from 3D");
      return;
    }
    sceneDebug("setSceneModeInternal morphTo3D begin pendingFocus=" + String(pendingFocusAfterMorph));
    // Instant morph (0-duration) to avoid lag and frame drops
    viewer.scene.morphTo3D(0.0);
    currentSceneMode = "3d";
    applySceneModePerformanceHints("3d");
    syncSceneModeToggle("3d");
    if (comparatorModeEnabled && typeof comparatorViewers !== "undefined" && Array.isArray(comparatorViewers)) {
      comparatorViewers.forEach(v => setComparatorViewerModeByType(v));
    }
    updateBasemapBlendForCurrentMode();

    // CRITICAL FIX (Bug 1+2): Ensure 3D always has perspective pitch.
    // Clamp pitch so 3D never looks like 2D (top-down).  Default to -35°.
    if (cameraOrbitPitch < MIN_3D_PITCH_RAD || Math.abs(cameraOrbitPitch - Cesium.Math.toRadians(-90.0)) < Cesium.Math.toRadians(5.0)) {
      cameraOrbitPitch = DEFAULT_3D_PITCH_RAD;
      sceneDebug("setSceneModeInternal: clamped pitch to default 3D pitch " + Cesium.Math.toDegrees(cameraOrbitPitch).toFixed(1) + "°");
    }

    // After morphTo3D, re-attach terrain provider and focus on active asset.
    // morphTo3D(0) resets the terrain provider — we must restore it.
    window.requestAnimationFrame(function () {
      if (activeDemTerrainProvider && activeDemContext && activeDemContext.visible !== false) {
        if (viewer.terrainProvider !== activeDemTerrainProvider) {
          _swapTerrainProviderLocked(activeDemTerrainProvider);
        }
        viewer.scene.globe.terrainExaggeration = Math.max(0.1, demVisual.exaggeration);
        // Also set verticalExaggeration for Cesium 1.90+ compatibility
        if (typeof viewer.scene.verticalExaggeration !== "undefined") {
          viewer.scene.verticalExaggeration = Math.max(0.1, demVisual.exaggeration);
        }
      }
      // Focus on active asset after morph with 3D pitch
      const bounds = activeTileBounds || lastLoadedBounds;
      if (bounds) {
        schedule3DFocusAfterMorph(1.0);
      }
      requestSceneRender();
    });

    requestSceneRender();
    setStatus("3D globe mode active.");
    log("info", "Scene mode switched to 3D from 2D");
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
    const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
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


