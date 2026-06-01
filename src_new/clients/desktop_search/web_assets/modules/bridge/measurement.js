  // SECTION: Measurement Tools  →  future: modules/measurement.js
  // Functions: setDistanceMeasureMode, _enforceMeasureCursor,
  //   updateMeasurementPreview, updateMeasurementEntities,
  //   clearMeasurementEntities, clearMeasurementPreviewEntities,
  //   updateDistanceScaleOverlay, clearDistanceScaleOverlay
  // ═══════════════════════════════════════════════════════════════════════════

  function updatePolygonPreviewVisibility() {
    const visible = polygonVisibilityEnabled;
    // Note: show properties for preview entities are managed via CallbackProperty in the controller
    // to ensure high-frequency updates during drawing. Static overrides here are avoided.
    if (searchCursorEntity) {
      searchCursorEntity.show = false;
    }
    if (searchPreviewLineEntity || searchPreviewPolygonEntity || searchAreaLabelEntity) {
      requestSceneRender();
    }
  }

  function setPolygonPreviewVisible(visible) {
    polygonVisibilityEnabled = Boolean(visible);
    updatePolygonPreviewVisibility();
  }

  function getLonLatFromScreen(screenPosition) {
    return getLonLatFromViewer(viewer, screenPosition);
  }

  function getGroundHeightAtLonLat(lon, lat) {
    if (!viewer || !viewer.scene || !viewer.scene.globe) {
      return 0;
    }
    try {
      const height = viewer.scene.globe.getHeight(Cesium.Cartographic.fromDegrees(lon, lat));
      return Number.isFinite(height) ? height : 0;
    } catch (_) {
      return 0;
    }
  }

  function clearSearchEntities() {
    if (searchCursorEntity) {
      viewer.entities.remove(searchCursorEntity);
      searchCursorEntity = null;
    }
    if (searchPreviewLineEntity) {
      viewer.entities.remove(searchPreviewLineEntity);
      searchPreviewLineEntity = null;
    }
    if (searchPreviewPolygonEntity) {
      viewer.entities.remove(searchPreviewPolygonEntity);
      searchPreviewPolygonEntity = null;
    }
    if (searchAreaLabelEntity) {
      viewer.entities.remove(searchAreaLabelEntity);
      searchAreaLabelEntity = null;
    }
    if (typeof searchRectangleEntity !== "undefined" && searchRectangleEntity) {
      viewer.entities.remove(searchRectangleEntity);
      searchRectangleEntity = null;
    }
    if (typeof searchAoiEntity !== "undefined" && searchAoiEntity) {
      viewer.entities.remove(searchAoiEntity);
      searchAoiEntity = null;
      searchAoiBounds = null;
    }
    // Clear vertex marker entities
    while (searchVertexEntities.length > 0) {
      const ve = searchVertexEntities.pop();
      if (ve && viewer) {
        viewer.entities.remove(ve);
      }
    }
    requestSceneRender();
    if (window.bridge && window.bridge.on_aoi_stats_updated) {
      window.bridge.on_aoi_stats_updated(0, "0 m\u00b2");
    }
  }

  function setAnnotationVisibility(visible) {
    annotationVisibilityEnabled = Boolean(visible);
    for (const entity of annotationEntities) {
      if (entity) {
        entity.show = annotationVisibilityEnabled;
      }
    }
    requestSceneRender();
  }

  function clearMeasurementEntities() {
    if (!viewer) {
      return;
    }
    try {
      while (measurementPointEntities.length > 0) {
        const ent = measurementPointEntities.pop();
        if (ent) viewer.entities.remove(ent);
      }
    } catch (e) {}
    clearMeasurementPreviewEntities();
    clearDistanceScaleOverlay();
    requestSceneRender();
  }

  function clearMeasurementPreviewEntities() {
    if (!viewer) {
      return;
    }
    try {
      if (measurementPreviewLineEntity) {
        viewer.entities.remove(measurementPreviewLineEntity);
        measurementPreviewLineEntity = null;
      }
      if (measurementAnchorDotEntity) {
        viewer.entities.remove(measurementAnchorDotEntity);
        measurementAnchorDotEntity = null;
      }
      measurementPreviewStart = null;
      measurementPreviewEnd = null;
    } catch (e) {}
    try {
      if (measurementPreviewLabelEntity) {
        viewer.entities.remove(measurementPreviewLabelEntity);
        measurementPreviewLabelEntity = null;
      }
    } catch (e) {}
    requestSceneRender();
  }

  // ── Distance Scale Overlay (screen-space ruler) ──
  function ensureDistanceScaleOverlay() {
    if (distanceScaleOverlay || !document.body) {
      return;
    }
    const el = document.createElement("div");
    el.id = "distanceScaleOverlay";
    el.setAttribute("aria-hidden", "true");
    // Container is just a positioning anchor — no overflow clipping
    el.style.cssText = [
      "position:fixed",
      "pointer-events:none",
      "z-index:99999",
      "display:none",
      "overflow:visible",
    ].join(";");

    // The bar — positioned absolutely, rotated via transform on the container
    const barWrap = document.createElement("div");
    barWrap.className = "distScaleBarWrap";
    barWrap.style.cssText = [
      "position:absolute",
      "top:0",
      "left:0",
      "transform-origin:0% 50%",
      "overflow:visible",
    ].join(";");

    const bar = document.createElement("div");
    bar.className = "distScaleBar";
    bar.style.cssText = [
      "height:4px",
      "background:rgba(0,229,255,0.85)",
      "border:1px solid rgba(0,0,0,0.4)",
      "border-radius:2px",
      "box-shadow:0 1px 4px rgba(0,0,0,0.5)",
      "position:relative",
      "min-width:8px",
    ].join(";");
    barWrap.appendChild(bar);

    // Start/end ticks on the bar
    const tickStart = document.createElement("div");
    tickStart.style.cssText = "position:absolute;left:-1px;top:-4px;width:2px;height:12px;background:rgba(0,229,255,0.9);border-radius:1px;";
    bar.appendChild(tickStart);
    const tickEnd = document.createElement("div");
    tickEnd.className = "distScaleTickEnd";
    tickEnd.style.cssText = "position:absolute;right:-1px;top:-4px;width:2px;height:12px;background:rgba(0,229,255,0.9);border-radius:1px;";
    bar.appendChild(tickEnd);

    el.appendChild(barWrap);

    // Distance label — separate from bar, always horizontal, positioned at midpoint
    const distLabel = document.createElement("div");
    distLabel.className = "distScaleText";
    distLabel.style.cssText = [
      "position:fixed",
      "pointer-events:none",
      "z-index:100000",
      "display:none",
      "color:#fff",
      "font-size:12px",
      "font-weight:700",
      "font-family:'SF Mono','Menlo','Consolas',monospace",
      "text-shadow:0 1px 3px rgba(0,0,0,0.9),0 0 6px rgba(0,0,0,0.6)",
      "white-space:nowrap",
      "background:rgba(10,25,41,0.78)",
      "padding:2px 7px",
      "border-radius:4px",
      "transform:translate(-50%,-100%)",
    ].join(";");
    document.body.appendChild(distLabel);

    // Azimuth label — below midpoint, always horizontal
    const azLabel = document.createElement("div");
    azLabel.className = "distScaleAz";
    azLabel.style.cssText = [
      "position:fixed",
      "pointer-events:none",
      "z-index:100000",
      "display:none",
      "color:rgba(0,229,255,0.95)",
      "font-size:11px",
      "font-weight:600",
      "font-family:'SF Mono','Menlo','Consolas',monospace",
      "text-shadow:0 1px 2px rgba(0,0,0,0.9)",
      "white-space:nowrap",
      "transform:translate(-50%,6px)",
    ].join(";");
    document.body.appendChild(azLabel);

    document.body.appendChild(el);
    distanceScaleOverlay = el;
  }

  let _scaleOverlayLastMs = 0;
  function updateDistanceScaleOverlay(startLon, startLat, endLon, endLat, meters, azimuth) {
    // Disabled HTML overlay because 3D Entity lines now exist.
    return;
  }

  function clearDistanceScaleOverlay() {
    return;
  }

  function _clearFillVolumeEntities() {
    if (!viewer) return;
    var ents = window._fillVolumeEntities || [];
    for (var i = 0; i < ents.length; i++) {
      var ent = ents[i];
      try {
        if (!ent) continue;
        if (viewer.entities.contains(ent)) {
          viewer.entities.remove(ent);
        }
      } catch (_) {}
    }
    window._fillVolumeEntities = [];
    window._fillVolumePrimitives = [];
  }

  // Profile rubber-band preview — recreates entity on every mouse move (same as distance tool)
  function _updateProfilePreviewLine(startLon, startLat, endLon, endLat) {
    if (!viewer) return;
    // Update the shared positions every mouse move
    window._profilePreviewStart = Cesium.Cartesian3.fromDegrees(startLon, startLat);
    window._profilePreviewEnd = Cesium.Cartesian3.fromDegrees(endLon, endLat);

    if (!window._profilePreviewEntity) {
      // Create once with CallbackProperty(isConstant=false) — re-evaluated every frame
      window._profilePreviewEntity = viewer.entities.add({
        polyline: {
          positions: new Cesium.CallbackProperty(function() {
            if (window._profilePreviewStart && window._profilePreviewEnd) {
              return [window._profilePreviewStart, window._profilePreviewEnd];
            }
            return [];
          }, false),
          width: 2,
          arcType: Cesium.ArcType.GEODESIC,
          material: Cesium.Color.fromCssColorString("#00e5ff").withAlpha(0.85),
          clampToGround: true,
        },
      });
      log("debug", "Profile preview line entity created");
    }
    requestSceneRender();
  }

  function updateMeasurementPreview(startLon, startLat, endLon, endLat, meters, azimuth, startHeightOpt, endHeightOpt) {
    if (!viewer) {
      return;
    }
    try {
      let startHeight = startHeightOpt !== undefined ? startHeightOpt : getGroundHeightAtLonLat(startLon, startLat);
      let endHeight = endHeightOpt !== undefined ? endHeightOpt : getGroundHeightAtLonLat(endLon, endLat);

      // Update shared mutable positions — the CallbackProperty reads these every frame
      measurementPreviewStart = Cesium.Cartesian3.fromDegrees(startLon, startLat, startHeight);
      measurementPreviewEnd = Cesium.Cartesian3.fromDegrees(endLon, endLat, endHeight);

      if (!measurementPreviewLineEntity) {
        // Create ONCE with CallbackProperty(isConstant=false) — re-evaluated every frame
        measurementPreviewLineEntity = viewer.entities.add({
          polyline: {
            positions: new Cesium.CallbackProperty(function() {
              if (measurementPreviewStart && measurementPreviewEnd) {
                return [measurementPreviewStart, measurementPreviewEnd];
              }
              return [];
            }, false),
            width: 3,
            arcType: Cesium.ArcType.GEODESIC,
            material: Cesium.Color.fromCssColorString("#00e5ff").withAlpha(0.85),
            depthFailMaterial: Cesium.Color.fromCssColorString("#00e5ff").withAlpha(0.45),
            clampToGround: true,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });
      }
      requestSceneRender();
    } catch (e) {
      // Silently ignore preview errors
    }
  }

  function updateLineDrawPreview(startLon, startLat, endLon, endLat) {
    if (!viewer) {
      return;
    }
    try {
      log(
        "debug",
        "updateLineDrawPreview start=" + Number(startLon).toFixed(6) + "," + Number(startLat).toFixed(6) + " end=" + Number(endLon).toFixed(6) + "," + Number(endLat).toFixed(6) + " lineMode=" + String(lineDrawModeEnabled) + " hasStart=" + Boolean(lineDrawStart)
      );
      // CRITICAL FIX: Match distance measurement tool exactly for proper terrain draping
      // Use same height calculation approach as measurement preview
      let startHeight = viewer.scene.globe.getHeight(Cesium.Cartographic.fromDegrees(startLon, startLat)) || 0;
      let endHeight = viewer.scene.globe.getHeight(Cesium.Cartographic.fromDegrees(endLon, endLat)) || 0;

      // Update shared mutable positions — the CallbackProperty reads these every frame
      lineDrawPreviewStart = Cesium.Cartesian3.fromDegrees(startLon, startLat, startHeight);
      lineDrawPreviewEnd = Cesium.Cartesian3.fromDegrees(endLon, endLat, endHeight);

      if (!lineDrawPreviewLineEntity) {
        // Create ONCE with CallbackProperty(isConstant=false) — re-evaluated every frame
        // EXACTLY matching measurement preview configuration for consistent terrain draping
        lineDrawPreviewLineEntity = viewer.entities.add({
          polyline: {
            positions: new Cesium.CallbackProperty(function() {
              if (lineDrawPreviewStart && lineDrawPreviewEnd) {
                return [lineDrawPreviewStart, lineDrawPreviewEnd];
              }
              return [];
            }, false),
            width: 3,
            arcType: Cesium.ArcType.GEODESIC,
            material: Cesium.Color.fromCssColorString("#00e5ff").withAlpha(0.85),
            depthFailMaterial: Cesium.Color.fromCssColorString("#00e5ff").withAlpha(0.45),
            clampToGround: true,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            show: new Cesium.CallbackProperty(function () {
              return Boolean(lineDrawModeEnabled && lineDrawPreviewStart && lineDrawPreviewEnd);
            }, false),
          },
        });
        log("debug", "Line draw preview entity created");
      }
      requestSceneRender();
    } catch (e) {
      log("warn", "Line draw preview error: " + e.message);
    }
  }

  function clearLineDrawPreview() {
    if (!viewer) {
      return;
    }
    try {
      log("debug", "clearLineDrawPreview invoked");
      if (lineDrawPreviewLineEntity) {
        viewer.entities.remove(lineDrawPreviewLineEntity);
        lineDrawPreviewLineEntity = null;
      }
      lineDrawPreviewStart = null;
      lineDrawPreviewEnd = null;
    } catch (e) {}
    requestSceneRender();
  }

  function setDistanceMeasureMode(enabled) {
    distanceMeasureModeEnabled = Boolean(enabled);
    distanceMeasureAnchor = null;
    
    const container = document.getElementById("cesiumContainer");
    if (distanceMeasureModeEnabled) {
      if (container) container.classList.add("measure-distance-cursor-active");
      _enforceMeasureCursor(true);
    } else {
      if (container) container.classList.remove("measure-distance-cursor-active");
      _enforceMeasureCursor(false);
    }
    
    if (distanceMeasureModeEnabled && searchDrawMode === "polygon") {
      searchDrawMode = "none";
      setSearchCursorEnabled(false);
      updatePolygonPreviewVisibility();
    }
    clearMeasurementPreviewEntities();
    clearDistanceScaleOverlay();
    if (distanceMeasureModeEnabled) {
      setMeasurementCursorEnabled(true);
      clickedPoints.length = 0;
      setStatus("Distance tool: click first point, move to preview, click second point to measure. Right-click to stop.");
      reapplyLayerOrderIfKnown();
      return;
    }
    // Turning off — clear ALL measurement marks (line, label, preview, overlay)
    clearMeasurementEntities();
    setMeasurementCursorEnabled(false);
    setStatus("Distance tool disabled.");
    reapplyLayerOrderIfKnown();
  }

  function setPanMode(enabled) {
    panModeActive = Boolean(enabled);
    const container = document.getElementById("cesiumContainer");
    if (panModeActive) {
      if (distanceMeasureModeEnabled) {
        setDistanceMeasureMode(false);
      }
      if (searchDrawMode === "polygon") {
        searchDrawMode = "none";
        setSearchCursorEnabled(false);
        updatePolygonPreviewVisibility();
      }
      clearDistanceScaleOverlay();
      if (container) container.classList.add("pan-mode-active");
      // Force 2D-like flat drag: disable rotate/tilt/look
      configureCameraControllerForMode(currentSceneMode);
      setStatus("Pan mode enabled — drag to translate view.");
      log("info", "Pan mode activated (2D-like drag)");
    } else {
      if (container) container.classList.remove("pan-mode-active");
      // Force remove from all elements just in case of bubbling issues
      document.body.classList.remove("pan-mode-active");
      document.documentElement.classList.remove("pan-mode-active");
      // Restore normal 3D interaction controls
      configureCameraControllerForMode(currentSceneMode);
      setStatus("Pan mode disabled — 3D navigation restored.");
      log("info", "Pan mode deactivated (3D navigation restored)");
    }
    reapplyLayerOrderIfKnown();
    requestSceneRender();
  }

  function updateMeasurementEntities(startLon, startLat, endLon, endLat, meters, azimuth, startHeightOpt, endHeightOpt) {
    if (!viewer) {
      return;
    }
    
    try {
      let startHeight = startHeightOpt !== undefined ? startHeightOpt : (viewer.scene.globe.getHeight(Cesium.Cartographic.fromDegrees(startLon, startLat)) || 0);
      let endHeight = endHeightOpt !== undefined ? endHeightOpt : (viewer.scene.globe.getHeight(Cesium.Cartographic.fromDegrees(endLon, endLat)) || 0);

      const start = Cesium.Cartesian3.fromDegrees(startLon, startLat, startHeight);
      const end = Cesium.Cartesian3.fromDegrees(endLon, endLat, endHeight);
      
      const labelLon = (startLon + endLon) / 2.0;
      const labelLat = (startLat + endLat) / 2.0;
      const labelHeight = (startHeight + endHeight) / 2.0;

      let distText = meters > 1000 ? (meters / 1000.0).toFixed(2) + " km" : meters.toFixed(1) + " m";
      let azText = azimuth !== undefined ? azimuth.toFixed(1) + "°" : "";
      const labelText = "Dist: " + distText + (azText ? "   Az: " + azText : "");

      const newLine = viewer.entities.add({
        polyline: {
          positions: [start, end],
          width: 3.5, // Increased width for better visibility
          arcType: Cesium.ArcType.GEODESIC,
          material: Cesium.Color.fromCssColorString("#00e5ff"), // Standard Cyan
          depthFailMaterial: Cesium.Color.fromCssColorString("#00e5ff").withAlpha(0.4),
          clampToGround: true, // CRITICAL FIX: Follow terrain
        },
      });

      const newLabel = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(labelLon, labelLat, labelHeight),
        label: {
          text: labelText,
          font: "bold 13px 'Segoe UI', 'Arial', sans-serif",
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 3,
          showBackground: true,
          backgroundColor: Cesium.Color.fromCssColorString("#08101c").withAlpha(0.7),
          backgroundPadding: new Cesium.Cartesian2(7, 5),
          horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          pixelOffset: new Cesium.Cartesian2(0, -14),
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          scale: 1.0,
        },
      });
      
      const pt1 = viewer.entities.add({
          position: start,
          point: {
            pixelSize: 3,
              color: Cesium.Color.fromCssColorString("#00e5ff"),
              outlineColor: Cesium.Color.TRANSPARENT,
            outlineWidth: 0,
              heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          }
      });
      const pt2 = viewer.entities.add({
          position: end,
          point: {
            pixelSize: 3,
              color: Cesium.Color.fromCssColorString("#00e5ff"),
              outlineColor: Cesium.Color.TRANSPARENT,
            outlineWidth: 0,
              heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          }
      });

      measurementPointEntities.push(newLine, newLabel, pt1, pt2);
      requestSceneRender();
    } catch (e) {
      log("error", "updateMeasurementEntities failed: " + e.message);
    }
  }

  function clearAnnotationEntities() {
    if (!viewer) {
      return;
    }
    hoveredAnnotationEditEntity = null;
    while (annotationEntities.length > 0) {
      const entity = annotationEntities.pop();
      if (entity) {
        viewer.entities.remove(entity);
      }
    }
    requestSceneRender();
  }

  function zoomBy(factor) {
    if (!viewer || !viewer.camera) return;
    const camera = viewer.camera;
    const scene = viewer.scene;

    // Use last known mouse position for anchoring if available
    let targetCartesian = null;
    if (lastMousePosition) {
      const ray = camera.getPickRay(lastMousePosition);
      if (ray) {
        targetCartesian = scene.globe.pick(ray, scene);
      }
    }

    if (!targetCartesian) {
        // Fallback to screen center
        const center = new Cesium.Cartesian2(
            scene.canvas.clientWidth / 2,
            scene.canvas.clientHeight / 2
        );
        const ray = camera.getPickRay(center);
        if (ray) {
            targetCartesian = scene.globe.pick(ray, scene);
        }
    }

    if (targetCartesian) {
        // Zoom towards the picked point
        const distance = Cesium.Cartesian3.distance(camera.positionWC, targetCartesian);
        const moveAmount = distance * (1.0 - factor);
        camera.zoomIn(moveAmount);
        log("debug", "zoomBy: mouse-anchored factor=" + factor.toFixed(4) + " move=" + moveAmount.toFixed(1) + "m");
    } else {
        // Fallback to simple altitude change
        const cartographic = Cesium.Cartographic.fromCartesian(camera.positionWC);
        const altitude = cartographic.height;
        const newAltitude = altitude * factor;
        const clampedAltitude = Math.max(10, Math.min(newAltitude, 100000000));
        camera.setView({
            destination: Cesium.Cartesian3.fromRadians(
                cartographic.longitude,
                cartographic.latitude,
                clampedAltitude
            ),
            orientation: {
                heading: camera.heading,
                pitch: camera.pitch,
                roll: camera.roll
            }
        });
        log("debug", "zoomBy: center-fallback factor=" + factor.toFixed(4) + " alt=" + clampedAltitude.toFixed(1) + "m");
    }
    requestSceneRender();
  }

  function stopFlyThrough() {
    if (typeof cancelFlyThroughPlaybackFrame === "function") {
      cancelFlyThroughPlaybackFrame();
    }
    flyThroughIsPlaying = false;
    flyThroughPlaybackPaused = false;
    flyThroughPlaybackProgress = 0.0;
    flyThroughPlaybackLastTimestamp = 0;
    if (viewer && viewer.camera) {
      viewer.camera.cancelFlight();
    }
    if (viewer && viewer.scene && viewer.scene.screenSpaceCameraController) {
      viewer.scene.screenSpaceCameraController.enableInputs = true;
    }
    flyThroughStopRequested = true;
    flyThroughModeEnabled = false;
    if (flyThroughOriginalView && viewer && viewer.camera) {
      try {
        viewer.camera.setView({
          destination: flyThroughOriginalView.destination,
          orientation: flyThroughOriginalView.orientation,
        });
        viewer.camera.frustum.fov = flyThroughOriginalView.fov;
      } catch (_) {}
      flyThroughOriginalView = null;
    }
    if (flyThroughPreviewLineEntity) {
      viewer.entities.remove(flyThroughPreviewLineEntity);
      flyThroughPreviewLineEntity = null;
    }
    if (flyThroughPathEntity) {
      viewer.entities.remove(flyThroughPathEntity);
      flyThroughPathEntity = null;
    }
    flyThroughPoints.length = 0;
    flyThroughPreviewEnd = null;
    if (typeof notifyFlyThroughPlaybackState === "function") {
      notifyFlyThroughPlaybackState("ended");
    }
    if (typeof notifyFlyThroughPlaybackProgress === "function") {
      notifyFlyThroughPlaybackProgress(0.0);
    }
    setStatus("Fly Through stopped.");
    log("info", "Fly Through stopped manually");
    requestSceneRender();
  }

  function resetNorthUp() {
    if (!viewer || !viewer.camera) {
      return;
    }
    const camera = viewer.camera;
    camera.cancelFlight();

    // Reset heading to north (0.0) while preserving current position and pitch
    camera.flyTo({
      destination: camera.position,
      orientation: {
        heading: 0.0,
        pitch: camera.pitch,
        roll: camera.roll,
      },
      duration: 0.85,
    });
    requestSceneRender();
  }

  function zoomToExtent() {
    if (!viewer) {
      return;
    }
    const bounds = activeTileBounds || lastLoadedBounds;
    if (!bounds) {
      try {
        if (viewer.camera && typeof viewer.camera.flyHome === "function") {
          viewer.camera.flyHome(0.9);
        }
      } catch (_) {}
      return;
    }
    try {
      if (currentSceneMode === "3d" || currentSceneMode === "morphing") {
        focusLoadedRegion3D(0.95);
      } else if (typeof focusLoadedRegion2D === "function") {
        focusLoadedRegion2D(0.65);
      } else {
        focusLoadedRegion(0.65);
      }
    } catch (err) {
      // Final fallback path to avoid dead zoom-to-extent behavior.
      try {
        focusLoadedRegion(0.7);
      } catch (_) {}
    }
    requestSceneRender();
  }

  Object.assign(window.offlineGIS, {
    setDistanceMeasureMode: function (enabled) {
      setDistanceMeasureMode(Boolean(enabled));
    },
    clearMeasurementEntities: function () {
      clearMeasurementEntities();
    },
    clearMeasurementPreviewEntities: function () {
      clearMeasurementPreviewEntities();
    },
    updateMeasurementPreview: function (
      startLon,
      startLat,
      endLon,
      endLat,
      meters,
      azimuth,
      startHeightOpt,
      endHeightOpt
    ) {
      updateMeasurementPreview(
        startLon,
        startLat,
        endLon,
        endLat,
        meters,
        azimuth,
        startHeightOpt,
        endHeightOpt
      );
    },
    updateMeasurementEntities: function (
      startLon,
      startLat,
      endLon,
      endLat,
      meters,
      azimuth,
      startHeightOpt,
      endHeightOpt
    ) {
      updateMeasurementEntities(
        startLon,
        startLat,
        endLon,
        endLat,
        meters,
        azimuth,
        startHeightOpt,
        endHeightOpt
      );
    },
    updateLineDrawPreview: function (startLon, startLat, endLon, endLat) {
      updateLineDrawPreview(startLon, startLat, endLon, endLat);
    },
    clearLineDrawPreview: function () {
      clearLineDrawPreview();
    },
  });

  // ═══════════════════════════════════════════════════════════════════════════
