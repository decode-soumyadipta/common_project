  // SECTION: Status Bar Bridge Emitters  →  future: modules/ui.js
  // Functions: emitMouseCoordinates, emitCameraChanged,
  //   wireStatusBarListeners, _updateCompass
  // ═══════════════════════════════════════════════════════════════════════════

  // ── Status-bar bridge emitters (QGIS-style) ──────────────────────────────
  function emitMouseCoordinates(lon, lat) {
    if (!bridge || !bridge.on_mouse_coordinates) return;
    const now = Date.now();
    const throttleMs = isInteracting ? 33 : (currentSceneMode === "2d" ? 60 : _SB_COORD_THROTTLE_MS);
    if (now - _sbLastCoordEmitMs < throttleMs) return;
    _sbLastCoordEmitMs = now;

    // Elevation field has been removed from the UI; emit lon/lat only.
    bridge.on_mouse_coordinates(lon, lat);
  }

  function emitCameraChanged() {
    if (!bridge || !bridge.on_camera_changed || !viewer || !viewer.camera) return;
    
    // Throttle camera change events to reduce overhead
    const now = Date.now();
    const cameraThrottleMs = currentSceneMode === "2d" ? 200 : _SB_CAMERA_THROTTLE_MS;
    if (now - _sbLastCameraEmitMs < cameraThrottleMs) return;
    _sbLastCameraEmitMs = now;
    
    try {
      // Compute approximate scale denominator from camera altitude + canvas size
      const height = viewer.camera.positionCartographic.height;
      const canvas = viewer.canvas;
      const fovY = viewer.camera.frustum.fovy || 1.0472;
      const visibleMeters = 2.0 * height * Math.tan(fovY * 0.5);
      const pixelHeight = canvas.clientHeight || 1;
      const metersPerPixel = visibleMeters / pixelHeight;
      // 96 dpi screen: 1 pixel ≈ 0.000265 m physical → scale = mPx / 0.000265
      const scaleDenom = metersPerPixel / 0.000265;

      let headingDeg = Cesium.Math.toDegrees(viewer.camera.heading);
      if (headingDeg < 0) headingDeg += 360.0;
      
      let pitchDeg = Cesium.Math.toDegrees(viewer.camera.pitch);
      
      bridge.on_camera_changed(scaleDenom, headingDeg, pitchDeg);
    } catch (_) {}
  }

  function wireStatusBarListeners() {
    if (!viewer || !viewer.scene) return;
    
    // Camera moved → update scale + heading + start tile loading monitor
    viewer.camera.changed.addEventListener(function() {
      if (isInteracting) {
        return;
      }
      emitCameraChanged();
      _updateCompass();
      if (!_tileLoadingActive) {
        startTileLoadingMonitor();
      }
    });
    
    // CRITICAL: Force render after camera stops moving (prevents black screens in request-render mode)
    viewer.camera.moveEnd.addEventListener(function() {
      emitCameraChanged();
      _updateCompass();
      if (!_tileLoadingActive) {
        startTileLoadingMonitor();
      }
      
      // Force multiple renders to ensure tiles load after camera movement
      // This prevents black screens when using requestRenderMode=true
      viewer.scene.requestRender();
      setTimeout(function() { 
        if (viewer && viewer.scene) viewer.scene.requestRender(); 
      }, 50);
      setTimeout(function() { 
        if (viewer && viewer.scene) viewer.scene.requestRender(); 
      }, 150);
      setTimeout(function() { 
        if (viewer && viewer.scene) viewer.scene.requestRender(); 
      }, 300);
    });

    // Re-apply terrainExaggeration after every tile load batch.
    // Cesium 1.78 resets globe.terrainExaggeration when new terrain tiles are decoded.
    // Also drive the progress bar from this native event — accurate, zero polling lag.
    viewer.scene.globe.tileLoadProgressEvent.addEventListener(function (queueLength) {
      // Real-time progress bar — driven by native tile queue length
      // We process this regardless of isInteracting to ensure the bar always reflects reality.
      if (queueLength > 0) {
        _tileQueuePeak = Math.max(_tileQueuePeak, queueLength);
        const loaded = _tileQueuePeak - queueLength;
        const percent = _tileQueuePeak > 0 ? Math.min(95, Math.round((loaded / _tileQueuePeak) * 100)) : 10;
        emitLoadingProgress(percent, "Loading tiles");
        _tileLoadingActive = true;
        // Cancel any pending drain timer — queue is still active
        if (_tileQueuePeak > 0 && typeof _tileDrainTimer !== 'undefined' && _tileDrainTimer) {
          clearTimeout(_tileDrainTimer);
          _tileDrainTimer = null;
        }
      } else if (_tileLoadingActive) {
        // Queue drained — debounce the completion signal by 200 ms so a
        // rapid new-layer load doesn't cause a 100 → 0 flash on the bar.
        if (typeof _tileDrainTimer === 'undefined' || !_tileDrainTimer) {
          _tileDrainTimer = setTimeout(function () {
            _tileDrainTimer = null;
            if (!_tileLoadingActive) return;
            emitLoadingProgress(100, "Complete");
            _tileLoadingActive = false;
            _tileQueuePeak = 0;
          }, 200);
        }
      }

      if (isInteracting) {
        return;
      }

      // Terrain exaggeration persistence (only when idle to avoid jitter)
      if (queueLength === 0 && activeDemContext && activeDemContext.visible !== false) {
        const target = Math.max(0.1, demVisual.exaggeration);
        if (Math.abs(viewer.scene.globe.terrainExaggeration - target) > 0.001) {
          viewer.scene.globe.terrainExaggeration = target;
        }
        // Also persist verticalExaggeration for Cesium 1.90+
        if (typeof viewer.scene.verticalExaggeration !== "undefined" && Math.abs(viewer.scene.verticalExaggeration - target) > 0.001) {
          viewer.scene.verticalExaggeration = target;
        }
      }
    });
    const compassEl = document.getElementById("compassWidget");
    if (compassEl) {
      compassEl.addEventListener("click", function () {
        if (!viewer) return;
        
        // Check if any assets are active
        const bounds = activeTileBounds || lastLoadedBounds;
        
        if (bounds) {
          // Assets active: Focus on active asset bounds smoothly and fast
          const rect = Cesium.Rectangle.fromDegrees(bounds.west, bounds.south, bounds.east, bounds.north);
          viewer.camera.flyTo({
            destination: rect,
            orientation: { heading: 0.0, pitch: Cesium.Math.toRadians(-90), roll: 0.0 },
            duration: 0.8  // Fast 0.8 second animation
          });
          log("info", "Compass clicked: focusing on active asset bounds");
        } else {
          // No assets active: Return to default India view
          viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(78.0, 22.0, 6000000),  // India center, 6000km height
            orientation: { heading: 0.0, pitch: Cesium.Math.toRadians(-90), roll: 0.0 },
            duration: 1.2  // Smooth 1.2 second animation
          });
          log("info", "Compass clicked: returning to default India view");
        }
        requestSceneRender();
      });
    }

    // Throttled compass rotation update — only update when camera moves
    let lastCompassHeading = NaN;
    const COMPASS_UPDATE_THRESHOLD = 0.5;  // degrees
    viewer.scene.postRender.addEventListener(function() {
      if (isInteracting || currentSceneMode === "2d") return;
      if (!viewer || !viewer.camera) return;
      const headingDeg = Cesium.Math.toDegrees(viewer.camera.heading);
      
      // Only update if heading changed significantly
      if (Math.abs(headingDeg - lastCompassHeading) < COMPASS_UPDATE_THRESHOLD) return;
      lastCompassHeading = headingDeg;
      
      const needle = document.getElementById("compassNeedle");
      const nLabel = document.getElementById("compassNLabel");
      if (!needle) return;
      
      // Use CSS transform for GPU-accelerated rotation
      needle.style.transform = `rotate(${headingDeg.toFixed(2)}deg)`;
      needle.style.transformOrigin = "32px 32px";
      if (nLabel) {
        nLabel.style.transform = `rotate(${(-headingDeg).toFixed(2)}deg)`;
        nLabel.style.transformOrigin = "32px 20px";
      }
    });
  }

  function _updateCompass() {
    // Deprecated - compass now updates via postRender listener
  }

  function wireClickHandlers() {
    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    
    // Track mouse down position to distinguish clicks from drags
    let mouseDownPosition = null;
    const CLICK_THRESHOLD = 5; // pixels - if mouse moves more than this, it's a drag, not a click
    let lastHoverUpdateMs = 0;
    const HOVER_THROTTLE_MS = 80;
    
    // Track LEFT_DOWN to detect clicks vs drags
    handler.setInputAction(function (movement) {
      if (movement && movement.position) {
        mouseDownPosition = {
          x: movement.position.x,
          y: movement.position.y
        };
      }
    }, Cesium.ScreenSpaceEventType.LEFT_DOWN);
    
    // Handle LEFT_UP - only process as click if mouse didn't move much
    handler.setInputAction(function (movement) {
      // Check if this was a click (minimal movement) or a drag (significant movement)
      if (mouseDownPosition && movement && movement.position) {
        const dx = Math.abs(movement.position.x - mouseDownPosition.x);
        const dy = Math.abs(movement.position.y - mouseDownPosition.y);
        const distance = Math.sqrt(dx * dx + dy * dy);
        
        // If mouse moved more than threshold, this was a drag, not a click - ignore it
        if (distance > CLICK_THRESHOLD) {
          mouseDownPosition = null;
          return;
        }
      }
      
      mouseDownPosition = null;
      
      // Process as click
      if (handleFlyThroughClick(movement)) return;
      
      const picked = movement && movement.position ? viewer.scene.pick(movement.position) : null;
      if (picked && picked.id && picked.id._annotationRole === "edit") {
        if (renameAnnotationFromEditIcon(picked.id)) {
          return;
        }
      }
      if (picked && picked.id && picked.id._annotationRole === "delete") {
        var delE = picked.id;
        var delTargets = [delE._annotationAnchorEntity, delE._annotationLabelEntity, delE._annotationEditEntity, delE];
        for (var di = 0; di < delTargets.length; di++) {
          var dIdx = annotationEntities.indexOf(delTargets[di]);
          if (dIdx > -1) annotationEntities.splice(dIdx, 1);
          if (delTargets[di]) viewer.entities.remove(delTargets[di]);
        }
        requestSceneRender();
        log("info", "Deleted annotation id=" + (delE._annotationId || "?"));
        return;
      }
      // Polygon edit (rename)
      if (picked && picked.id && picked.id._polyRole === "edit") {
        var polyId = picked.id._polyRecordId;
        var polys = drawnPolygons;
        for (var pi = 0; pi < polys.length; pi++) {
          if (polys[pi].id === polyId && polys[pi].nameLabelEntity) {
            var curName = polys[pi].label || "Polygon " + polyId;
            var newName = prompt("Rename polygon:", curName);
            if (newName && newName.trim()) {
              polys[pi].label = newName.trim();
              polys[pi].nameLabelEntity.label.text = newName.trim();
              requestSceneRender();
            }
            break;
          }
        }
        return;
      }
      // Polygon delete
      if (picked && picked.id && picked.id._polyRole === "delete") {
        var delPolyId = picked.id._polyRecordId;
        for (var pj = drawnPolygons.length - 1; pj >= 0; pj--) {
          if (drawnPolygons[pj].id === delPolyId) {
            var rec = drawnPolygons[pj];
            if (rec.lineEntity) viewer.entities.remove(rec.lineEntity);
            if (rec.polygonEntity) viewer.entities.remove(rec.polygonEntity);
            if (rec.areaLabelEntity) viewer.entities.remove(rec.areaLabelEntity);
            if (rec.nameLabelEntity) viewer.entities.remove(rec.nameLabelEntity);
            if (rec.editEntity) viewer.entities.remove(rec.editEntity);
            if (rec.deleteEntity) viewer.entities.remove(rec.deleteEntity);
            for (var vi = 0; vi < (rec.vertexEntities || []).length; vi++) {
              if (rec.vertexEntities[vi]) viewer.entities.remove(rec.vertexEntities[vi]);
            }
            drawnPolygons.splice(pj, 1);
            requestSceneRender();
            log("info", "Deleted polygon id=" + delPolyId);
            break;
          }
        }
        return;
      }

      // Try multiple picking strategies to guarantee a coordinate.
      // Strategy 1: scene.pickPosition (uses depth buffer, most accurate)
      // Strategy 2: globe.pick (works on terrain surface)
      // Strategy 3: pickEllipsoid (always works, ignores terrain height)
      let lonLat = null;
      let clickCartesian = null;

      if (movement && movement.position) {
        // Strategy 1: scene.pickPosition — uses depth buffer, most accurate at any zoom
        // This correctly handles high-resolution imagery where terrain mesh may lag
        if (viewer.scene.pickPositionSupported) {
          try {
            const depthCart = viewer.scene.pickPosition(movement.position);
            if (depthCart && Cesium.Cartesian3.magnitude(depthCart) > 1.0) {
              clickCartesian = depthCart;
            }
          } catch (_) {}
        }

        // Strategy 2: globe.pick via ray (works on terrain surface when depth unavailable)
        if (!clickCartesian) {
          const ray = viewer.camera.getPickRay(movement.position);
          if (ray) {
            clickCartesian = viewer.scene.globe.pick(ray, viewer.scene);
          }
        }

        // Strategy 3: ellipsoid fallback (always succeeds, ignores terrain height)
        if (!clickCartesian) {
          clickCartesian = viewer.camera.pickEllipsoid(
            movement.position,
            viewer.scene.globe.ellipsoid
          );
        }

        if (clickCartesian) {
          lonLat = cartesianToLonLat(clickCartesian);
          lastMapClickCartesian = Cesium.Cartesian3.clone(clickCartesian);
        }
      }

      if (!lonLat) {
        // Click was outside globe or on UI element - silently ignore
        // This is normal behavior when clicking on controls, edges, etc.
        log("debug", "Click outside globe or on UI element - no coordinate resolved");
        return;
      }
      
      const lon = lonLat.lon;
      const lat = lonLat.lat;

      // Fly Through draw
      if (flyThroughModeEnabled) {
        flyThroughPoints.push(clickCartesian);
        updateFlyThroughPreview();
        setStatus("Fly Through: added point " + flyThroughPoints.length + ". Right-click to finish.");
        return;
      }

      // Polygon draw — always fires if in polygon mode (doesn't block annotation placement below)
      if (searchDrawMode === "polygon") {
        if (searchPolygonLocked) {
          setStatus("Polygon restored. Clear geometry to start a new polygon.");
          // Don't return — annotation point can still be placed
        } else {
          searchPolygonPoints.push({ lon: lon, lat: lat, cartesian: clickCartesian ? Cesium.Cartesian3.clone(clickCartesian) : null });
          searchCursorPoint = null;
          updateSearchPolygonPreview();
          setStatus("Polygon draw: continue points, right-click or Finish to close");
          // Fall through — annotation point can also be placed simultaneously if annotationModeEnabled
        }
      }

      if (distanceMeasureModeEnabled) {
        try {
          emitMapClick(lon, lat);
          log("info", "Distance mode click lon=" + lon.toFixed(6) + " lat=" + lat.toFixed(6));
          if (!distanceMeasureAnchor) {
            // First click: set anchor and draw a visible dot
            distanceMeasureAnchor = { lon: lon, lat: lat, height: lonLat.height || 0 };
            clickedPoints.length = 0;
            clickedPoints.push([lon, lat]);
            clearMeasurementPreviewEntities();
            // Add a visible anchor dot at the first click point
            const anchorHeight = distanceMeasureAnchor.height;
            const anchorPos = Cesium.Cartesian3.fromDegrees(lon, lat, anchorHeight);
            if (measurementAnchorDotEntity) {
              try { viewer.entities.remove(measurementAnchorDotEntity); } catch(_) {}
            }
            measurementAnchorDotEntity = viewer.entities.add({
              position: anchorPos,
              point: {
                pixelSize: 11,
                color: Cesium.Color.fromCssColorString("#00e5ff"),
                outlineColor: Cesium.Color.WHITE,
                outlineWidth: 2,
                disableDepthTestDistance: Number.POSITIVE_INFINITY,
              },
            });
            requestSceneRender();
            setStatus("Distance tool: move cursor and click second point to finalize.");
            return;
          }

          // Second click: finalize measurement, clear anchor (stop chaining)
          const geodesic = new Cesium.EllipsoidGeodesic(
            Cesium.Cartographic.fromDegrees(distanceMeasureAnchor.lon, distanceMeasureAnchor.lat),
            Cesium.Cartographic.fromDegrees(lon, lat)
          );
          let azDegrees = Cesium.Math.toDegrees(geodesic.startHeading);
          if (azDegrees < 0) azDegrees += 360.0;
          clearMeasurementPreviewEntities();
          updateMeasurementEntities(
            distanceMeasureAnchor.lon,
            distanceMeasureAnchor.lat,
            lon,
            lat,
            geodesic.surfaceDistance,
            azDegrees,
            distanceMeasureAnchor.height,
            lonLat.height || 0
          );
          distanceMeasureAnchor = null;  // reset so next click starts fresh
          const _dist = geodesic.surfaceDistance;
          setTimeout(function() { emitMeasurementUpdated(_dist); }, 0);
          setStatus("Distance measured. Click to start a new measurement, or right-click to stop.");
          log("info", "Distance measured (m): " + geodesic.surfaceDistance.toFixed(2));
        } catch (e) {
          log("error", "Distance measurement error: " + (e.message || String(e)));
        }
        return;
      }

      clickedPoints.push([lon, lat]);
      if (clickedPoints.length > 2) clickedPoints.shift();

      // Fill-volume label expand/collapse — handled here in the persistent handler
      // to avoid creating/destroying ScreenSpaceEventHandler per analysis (macOS crash).
      if (window._fillVolumeEntities && window._fillVolumeEntities.length > 0) {
        var picked2 = viewer.scene.pick(movement.position);
        if (Cesium.defined(picked2) && Cesium.defined(picked2.id)) {
          var ent2 = picked2.id;
          if (ent2.isRegionLabel === true && ent2.detailsEntity) {
            var det = ent2.detailsEntity;
            var wasExpanded = ent2.expanded;
            det.label.show = !wasExpanded;
            ent2.expanded = !wasExpanded;
            ent2.label.text = (wasExpanded ? '\u25bc' : '\u25b2') + ' Region ' + ent2.regionId;
            requestSceneRender();
            return;
          }
        }
      }

      emitMapClick(lon, lat);
      log("debug", "Map click lon=" + lon.toFixed(6) + " lat=" + lat.toFixed(6));
    }, Cesium.ScreenSpaceEventType.LEFT_UP);

    handler.setInputAction(function (movement) {
      let statusCoordEmitted = false;
      if (movement && movement.endPosition) {
        if (window.OfflineGISCursorControls) {
          window.OfflineGISCursorControls.lastSearchCursorScreenPosition = movement.endPosition;
        }
        if (!isInteracting) {
          const now = Date.now();
          if (now - lastHoverUpdateMs >= HOVER_THROTTLE_MS) {
            lastHoverUpdateMs = now;
            updateAnnotationHover(movement.endPosition);
          }
        }

        // Keep status-bar lon/lat responsive during drag using a cheap ellipsoid pick.
        let fastLonLat = null;
        if (isInteracting) {
          const ellipsoidCart = viewer.camera.pickEllipsoid(movement.endPosition, viewer.scene.globe.ellipsoid);
          if (ellipsoidCart) {
            fastLonLat = cartesianToLonLat(ellipsoidCart);
          }
        } else {
          fastLonLat = getLonLatFromScreen(movement.endPosition);
        }
        if (fastLonLat) {
          emitMouseCoordinates(fastLonLat.lon, fastLonLat.lat);
          statusCoordEmitted = true;
        }
      }
      
      // During interaction (pan/rotate), we've already emitted coordinates above,
      // so we can skip the rest of the handler unless in special modes
      if (
        isInteracting &&
        searchDrawMode !== "polygon" &&
        !distanceMeasureModeEnabled &&
        !window._profileModeActive &&
        !window._profileLineActive
      ) {
        return;
      }
      if (distanceMeasureModeEnabled && distanceMeasureAnchor && searchDrawMode !== "polygon") {
        try {
          // Use pickEllipsoid as guaranteed fallback for preview over terrain
          let lonLat = getLonLatFromScreen(movement.endPosition);
          if (!lonLat && movement.endPosition) {
            const ellipsoidCart = viewer.camera.pickEllipsoid(movement.endPosition, viewer.scene.globe.ellipsoid);
            if (ellipsoidCart) lonLat = cartesianToLonLat(ellipsoidCart);
          }
          if (lonLat) {
            const geodesic = new Cesium.EllipsoidGeodesic(
              Cesium.Cartographic.fromDegrees(distanceMeasureAnchor.lon, distanceMeasureAnchor.lat),
              Cesium.Cartographic.fromDegrees(lonLat.lon, lonLat.lat)
            );
            let azDegrees = Cesium.Math.toDegrees(geodesic.startHeading);
            if (azDegrees < 0) azDegrees += 360.0;
            updateMeasurementPreview(
              distanceMeasureAnchor.lon,
              distanceMeasureAnchor.lat,
              lonLat.lon,
              lonLat.lat,
              geodesic.surfaceDistance,
              azDegrees
            );
          }
        } catch (e) {
          // Silently ignore preview errors to avoid spam
        }
      }

      if (lineDrawModeEnabled && lineDrawStart) {
        try {
          let lonLat = getLonLatFromScreen(movement.endPosition);
          if (!lonLat && movement.endPosition) {
            const ellipsoidCart = viewer.camera.pickEllipsoid(movement.endPosition, viewer.scene.globe.ellipsoid);
            if (ellipsoidCart) lonLat = cartesianToLonLat(ellipsoidCart);
          }
          if (lonLat) {
            updateLineDrawPreview(
              lineDrawStart.lon,
              lineDrawStart.lat,
              lonLat.lon,
              lonLat.lat
            );
          }
        } catch (e) {
          // Silently ignore preview errors
        }
      }
      
      // Always emit mouse coordinates for status bar (not just during polygon drawing)
      let lonLat = null;
      if (!statusCoordEmitted || searchDrawMode === "polygon") {
        lonLat = getLonLatFromScreen(movement.endPosition);
        if (lonLat && !statusCoordEmitted) {
          emitMouseCoordinates(lonLat.lon, lonLat.lat);
        }
      }

      // Live rubber-band line for elevation profile mode — mirrors distance tool approach
      if (window._profileModeActive && window._profileStartLon !== undefined) {
        try {
          // Throttle profile preview updates for smooth performance (60fps max)
          const now = Date.now();
          if (!window._lastProfilePreviewUpdate) {
            window._lastProfilePreviewUpdate = 0;
          }
          const timeSinceLastUpdate = now - window._lastProfilePreviewUpdate;
          if (timeSinceLastUpdate < 16) {
            // Skip this update - too soon after last one
            return;
          }
          window._lastProfilePreviewUpdate = now;
          
          let profileLonLat = getLonLatFromScreen(movement.endPosition);
          if (!profileLonLat && movement.endPosition) {
            const ellipsoidCart = viewer.camera.pickEllipsoid(movement.endPosition, viewer.scene.globe.ellipsoid);
            if (ellipsoidCart) profileLonLat = cartesianToLonLat(ellipsoidCart);
          }
          if (profileLonLat) {
            _updateProfilePreviewLine(
              window._profileStartLon, window._profileStartLat,
              profileLonLat.lon, profileLonLat.lat
            );
          }
        } catch (e) {
          // Silently ignore preview errors
        }
      }

      // Georeferenced cursor: project mouse onto completed profile line → emit fraction
      if (window._profileLineActive &&
          window._profileLineLon1 !== undefined && window._profileLineLon2 !== undefined) {
        try {
          let cursorLonLat = getLonLatFromScreen(movement.endPosition);
          if (!cursorLonLat && movement.endPosition) {
            const ec = viewer.camera.pickEllipsoid(movement.endPosition, viewer.scene.globe.ellipsoid);
            if (ec) cursorLonLat = cartesianToLonLat(ec);
          }
          if (cursorLonLat) {
            // Project cursor onto the geodesic line using Cartesian dot product
            // (accurate for any line length, including ultra-high-res cm-scale data)
            const p1 = Cesium.Cartesian3.fromDegrees(window._profileLineLon1, window._profileLineLat1);
            const p2 = Cesium.Cartesian3.fromDegrees(window._profileLineLon2, window._profileLineLat2);
            const pc = Cesium.Cartesian3.fromDegrees(cursorLonLat.lon, cursorLonLat.lat);
            const v  = Cesium.Cartesian3.subtract(p2, p1, new Cesium.Cartesian3());
            const w  = Cesium.Cartesian3.subtract(pc, p1, new Cesium.Cartesian3());
            const lenSq = Cesium.Cartesian3.dot(v, v);
            let frac = 0.5;
            if (lenSq > 1e-6) {
              frac = Cesium.Cartesian3.dot(w, v) / lenSq;
              frac = Math.max(0.0, Math.min(1.0, frac));
            }
            window._profileCursorFrac = frac;
            // Emit to Python so the Qt panel can draw the cursor crosshair
            if (bridge && bridge.on_profile_cursor) {
              bridge.on_profile_cursor(frac);
            }
            requestSceneRender();
          }
        } catch (e) {
          // Silently ignore
        }
      }
      
      if (searchDrawMode === "polygon") {
        updateSearchCursorOverlay(
          window.OfflineGISCursorControls && window.OfflineGISCursorControls.lastSearchCursorScreenPosition
        );
      }
      if (movement && movement.endPosition) {
        updateMeasureCursorOverlay(movement.endPosition);
      }
      if (movement && movement.endPosition) {
        lastMousePosition = movement.endPosition;
      }
      if (flyThroughModeEnabled && flyThroughPoints.length > 0 && movement && movement.endPosition) {
        updateFlyThroughPreview(movement.endPosition);
      }
      if (searchDrawMode !== "polygon" || searchPolygonPoints.length === 0) {
        return;
      }
      // CRITICAL FIX: Throttle polygon preview updates for smooth pixel-perfect drawing
      // Update at most 60fps (every ~16ms) to prevent lag on rapid mouse movements
      const now = Date.now();
      if (!window._lastPolygonPreviewUpdate) {
        window._lastPolygonPreviewUpdate = 0;
      }
      const timeSinceLastUpdate = now - window._lastPolygonPreviewUpdate;
      if (timeSinceLastUpdate < 16) {
        // Skip this update - too soon after last one
        // But still update the cursor point so next update uses latest position
        if (lonLat) {
          searchCursorPoint = { lon: lonLat.lon, lat: lonLat.lat };
        }
        return;
      }
      window._lastPolygonPreviewUpdate = now;
      
      // Update search polygon preview during drawing
      if (lonLat) {
        searchCursorPoint = { lon: lonLat.lon, lat: lonLat.lat };
        updateSearchPolygonPreview();
      }
    }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

    handler.setInputAction(function () {
      if (searchDrawMode === "polygon") {
        window.offlineGIS.finishSearchPolygon();
        return;
      }
      if (flyThroughModeEnabled) {
        finishFlyThroughPath();
        return;
      }
      if (distanceMeasureModeEnabled) {
        if (distanceMeasureAnchor) {
            distanceMeasureAnchor = null;
            clearMeasurementPreviewEntities();
            setStatus("Measurement cancelled. Click to start a new measurement.");
        }
        return;
      }
    }, Cesium.ScreenSpaceEventType.RIGHT_CLICK);

    viewer.canvas.addEventListener("mouseenter", function () {
      if (searchDrawMode === "polygon") {
        setSearchCursorOverlayVisible(true);
      }
      setMeasureCursorOverlayVisible(true);
    });

    viewer.canvas.addEventListener("mouseleave", function () {
      setSearchCursorOverlayVisible(false);
      setMeasureCursorOverlayVisible(false);
      if (hoveredAnnotationEditEntity) {
        setAnnotationEditIconHoverState(hoveredAnnotationEditEntity, false);
        hoveredAnnotationEditEntity = null;
      }
      if (hoveredAnnotationDeleteEntity) {
        setAnnotationDeleteIconHoverState(hoveredAnnotationDeleteEntity, false);
        hoveredAnnotationDeleteEntity = null;
      }
      // Clear status bar coordinates when cursor leaves the map
      if (bridge && bridge.on_mouse_coordinates) {
        bridge.on_mouse_coordinates(0, 0);
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════════════
