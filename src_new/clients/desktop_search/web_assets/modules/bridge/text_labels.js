  window.offlineGIS = window.offlineGIS || {};
  function measureTextWidth(text, font) {
    if (window.OfflineGISUtils && typeof window.OfflineGISUtils.measureTextWidth === "function") {
      return window.OfflineGISUtils.measureTextWidth(text, font);
    }
    var canvas = measureTextWidth._canvas || (measureTextWidth._canvas = document.createElement("canvas"));
    var context = canvas.getContext("2d");
    context.font = font || "14px sans-serif";
    return context.measureText(text || "").width;
  }

  function readLabelText(labelEntity) {
    if (!labelEntity || !labelEntity.label) return "";
    var textVal = labelEntity.label.text;
    if (!textVal) return "";
    if (typeof textVal.getValue === "function") {
      var julianDate = (typeof Cesium !== "undefined" && Cesium.JulianDate) 
                       ? Cesium.JulianDate.now() 
                       : ((typeof cesium !== "undefined" && cesium.JulianDate) ? cesium.JulianDate.now() : null);
      return String(textVal.getValue(julianDate) || "");
    }
    return String(textVal || "");
  }

  const searchResultMarkerEntities = [];

  const SEARCH_RESULT_MARKER_RED = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath fill='%23e74c3c' d='M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z'/%3E%3C/svg%3E";
  const SEARCH_RESULT_MARKER_YELLOW = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath fill='%23f1c40f' d='M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z'/%3E%3C/svg%3E";

  function getSearchOverlayVisible() {
    return typeof window._offlineGISSearchOverlayVisible === "boolean"
      ? window._offlineGISSearchOverlayVisible
      : true;
  }

  function clearSearchResultMarkerEntities() {
    if (!viewer || !viewer.entities) {
      searchResultMarkerEntities.length = 0;
      return;
    }
    while (searchResultMarkerEntities.length > 0) {
      const entity = searchResultMarkerEntities.pop();
      try {
        viewer.entities.remove(entity);
      } catch (_) {}
    }
  }

  function syncSearchResultMarkerVisibility() {
    const visible = getSearchOverlayVisible();
    log("debug", "syncSearchResultMarkerVisibility overlayVisible=" + String(visible) + " markerCount=" + String(searchResultMarkerEntities.length));
    for (let index = 0; index < searchResultMarkerEntities.length; index += 1) {
      const entity = searchResultMarkerEntities[index];
      if (entity) {
        entity.show = visible;
      }
    }
  }

  let tileLoadListenerRegistered = false;
  function registerTileLoadListener() {
    if (tileLoadListenerRegistered || !viewer || !viewer.scene || !viewer.scene.globe) return;
    
    viewer.scene.globe.tileLoadProgressEvent.addEventListener(function (queueLength) {
      if (window.offlineGIS && typeof window.offlineGIS.realignMarkersToTerrain === "function") {
        window.offlineGIS.realignMarkersToTerrain();
      }
    });

    viewer.camera.moveEnd.addEventListener(function() {
      if (window.offlineGIS && typeof window.offlineGIS.realignMarkersToTerrain === "function") {
        window.offlineGIS.realignMarkersToTerrain();
      }
    });
    
    tileLoadListenerRegistered = true;
  }

  function createMarkerCanvas(labelText, displayed) {
    const font = "600 11px 'Segoe UI', 'Helvetica Neue', sans-serif";
    const textWidth = measureTextWidth(labelText, font);
    
    const pinWidth = 26;
    const pinHeight = 26;
    const paddingX = 6;
    const paddingY = 4;
    const fontSize = 11;
    const textBoxHeight = fontSize + paddingY * 2; // 19
    const textBoxWidth = textWidth + paddingX * 2;
    const spacing = 4;
    
    const canvasWidth = Math.max(textBoxWidth, pinWidth) + 4;
    const canvasHeight = textBoxHeight + spacing + pinHeight + 4;
    
    const canvas = document.createElement("canvas");
    canvas.width = canvasWidth;
    canvas.height = canvasHeight;
    const ctx = canvas.getContext("2d");
    
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    
    const centerX = canvasWidth / 2;
    
    // 1. Draw Text Box Background
    const boxWidth = textBoxWidth;
    const boxHeight = textBoxHeight;
    const boxX = centerX - boxWidth / 2;
    const boxY = 2;
    const radius = 4;
    
    ctx.fillStyle = "rgba(0, 0, 0, 0.72)";
    ctx.beginPath();
    ctx.moveTo(boxX + radius, boxY);
    ctx.lineTo(boxX + boxWidth - radius, boxY);
    ctx.quadraticCurveTo(boxX + boxWidth, boxY, boxX + boxWidth, boxY + radius);
    ctx.lineTo(boxX + boxWidth, boxY + boxHeight - radius);
    ctx.quadraticCurveTo(boxX + boxWidth, boxY + boxHeight, boxX + boxWidth - radius, boxY + boxHeight);
    ctx.lineTo(boxX + radius, boxY + boxHeight);
    ctx.quadraticCurveTo(boxX, boxY + boxHeight, boxX, boxY + boxHeight - radius);
    ctx.lineTo(boxX, boxY + radius);
    ctx.quadraticCurveTo(boxX, boxY, boxX + radius, boxY);
    ctx.closePath();
    ctx.fill();
    
    // 2. Draw Text
    ctx.font = font;
    ctx.fillStyle = "#ffffff";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(labelText, centerX, boxY + boxHeight / 2);
    
    // 3. Draw Pin
    const pinX = centerX - pinWidth / 2;
    const pinY = boxY + boxHeight + spacing;
    
    ctx.save();
    ctx.translate(pinX, pinY);
    ctx.scale(pinWidth / 24, pinHeight / 24);
    
    const path = new Path2D("M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z");
    ctx.fillStyle = displayed ? "#f1c40f" : "#e74c3c";
    ctx.fill(path);
    ctx.restore();
    
    return canvas;
  }

  Object.assign(window.offlineGIS, {
      setSearchResultMarkers: function (markers) {
        if (!viewer) return;
        clearSearchResultMarkerEntities();
        registerTileLoadListener();
        const items = Array.isArray(markers) ? markers : [];
        const visible = getSearchOverlayVisible();
        
        for (let index = 0; index < items.length; index += 1) {
          const marker = items[index] || {};
          const lon = Number(marker.lon);
          const lat = Number(marker.lat);
          if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
            continue;
          }
          const labelText = String(marker.text || marker.file_name || "Tile").trim() || "Tile";
          
          const cartographic = Cesium.Cartographic.fromDegrees(lon, lat);
          const sampledHeight = viewer.scene && viewer.scene.globe ? viewer.scene.globe.getHeight(cartographic) : null;
          const h = Number.isFinite(sampledHeight) ? Number(sampledHeight) : 0.0;
          const position = Cesium.Cartesian3.fromDegrees(lon, lat, h + 5.0);
          const displayed = Boolean(marker.displayed);
          
          const markerCanvas = createMarkerCanvas(labelText, displayed);
          
          const billboardEntity = viewer.entities.add({
            position: position,
            show: visible,
            billboard: {
              show: true,
              image: markerCanvas,
              verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
              horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
              heightReference: Cesium.HeightReference.NONE,
              // NOTE: disableDepthTestDistance intentionally NOT set here.
              // With depthTestAgainstTerrain=true on the globe, markers on the far
              // side of the DEM must be occluded. CLAMP_TO_GROUND keeps them on
              // the visible surface when on this side.
            },
          });

          billboardEntity._searchResultMarker = true;
          billboardEntity._searchResultMarkerIndex = index;
          billboardEntity._assetFilePath = String(marker.file_path || "");
          billboardEntity._assetDisplayed = displayed;
          billboardEntity._originalScale = 1.0;
          searchResultMarkerEntities.push(billboardEntity);
        }
        requestSceneRender();
      },
      realignMarkersToTerrain: function () {
        if (viewer && viewer.scene && viewer.scene.globe) {
          // Realign search result markers
          for (let index = 0; index < searchResultMarkerEntities.length; index += 1) {
            const entity = searchResultMarkerEntities[index];
            if (entity && entity.position) {
              const positionVal = entity.position.getValue(Cesium.JulianDate.now());
              if (positionVal) {
                const cartographic = Cesium.Cartographic.fromCartesian(positionVal);
                if (cartographic) {
                  const sampledHeight = viewer.scene.globe.getHeight(cartographic);
                  if (Number.isFinite(sampledHeight)) {
                    entity.position = Cesium.Cartesian3.fromDegrees(
                      Cesium.Math.toDegrees(cartographic.longitude),
                      Cesium.Math.toDegrees(cartographic.latitude),
                      Number(sampledHeight) + 5.0
                    );
                  }
                }
              }
            }
          }

          // Realign custom text labels (annotations)
          if (typeof annotationEntities !== "undefined" && Array.isArray(annotationEntities)) {
            for (let i = 0; i < annotationEntities.length; i++) {
              const entity = annotationEntities[i];
              if (entity && entity._annotationRole === "text-label" && entity.position) {
                const positionVal = entity.position.getValue(Cesium.JulianDate.now());
                if (positionVal) {
                  const cartographic = Cesium.Cartographic.fromCartesian(positionVal);
                  if (cartographic) {
                    const sampledHeight = viewer.scene.globe.getHeight(cartographic);
                    if (Number.isFinite(sampledHeight)) {
                      entity.position = Cesium.Cartesian3.fromDegrees(
                        Cesium.Math.toDegrees(cartographic.longitude),
                        Cesium.Math.toDegrees(cartographic.latitude),
                        Number(sampledHeight)
                      );
                    }
                  }
                }
              }
            }
          }
        }
        syncSearchResultMarkerVisibility();
        requestSceneRender();
      },
      clearSearchResultMarkers: function () {
        clearSearchResultMarkerEntities();
        requestSceneRender();
      },
      addTextLabel: function (lon, lat, text, optHeight) {
        if (!viewer) return;
        annotationCounter += 1;
        const annotationId = "text-label-" + String(annotationCounter);
        const displayText = String(text || "Label").trim() || "Label";
        
        let anchorPosition = null;
        if (lastMapClickCartesian) {
          const lastLonLat = cartesianToLonLat(lastMapClickCartesian);
          if (lastLonLat) {
            const lonDiff = Math.abs(Number(lastLonLat.lon) - Number(lon));
            const latDiff = Math.abs(Number(lastLonLat.lat) - Number(lat));
            if (lonDiff <= 0.00002 && latDiff <= 0.00002) {
              anchorPosition = Cesium.Cartesian3.clone(lastMapClickCartesian);
            }
          }
        }
        if (!anchorPosition) {
          // Use saved height if provided (restore path), otherwise sample terrain
          var h = 0.0;
          if (typeof optHeight === "number" && Number.isFinite(optHeight)) {
            h = optHeight;
          } else {
            const cartographic = Cesium.Cartographic.fromDegrees(Number(lon), Number(lat));
            const sampledHeight = viewer.scene && viewer.scene.globe ? viewer.scene.globe.getHeight(cartographic) : null;
            h = Number.isFinite(sampledHeight) ? Number(sampledHeight) : 0.0;
          }
          anchorPosition = Cesium.Cartesian3.fromDegrees(Number(lon), Number(lat), h);
        }
        lastMapClickCartesian = null;
        
        // ── Shared position callback — buttons are always co-located with the label ──────
        // Using a CallbackProperty that returns the label entity's *current* world
        // position ensures both buttons move in exact lock-step even when CLAMP_TO_GROUND
        // adjusts the label during terrain tile refinement. heightReference is NONE for
        // buttons because disableDepthTestDistance=INFINITY already makes them always
        // visible, so we must NOT have Cesium independently re-clamp each button entity.
        function makeBoundPositionCallback() {
          return new Cesium.CallbackProperty(function () {
            if (labelEntity && labelEntity.position) {
              var pos = labelEntity.position.getValue(Cesium.JulianDate.now());
              if (pos) return pos;
            }
            return anchorPosition;
          }, false);
        }

        // Large white text label (no anchor point, just text)
        const labelEntity = viewer.entities.add({
          position: anchorPosition,
          label: {
            text: displayText,
            fillColor: Cesium.Color.WHITE,
            showBackground: true,
            backgroundColor: Cesium.Color.BLACK.withAlpha(0.5),
            backgroundPadding: new Cesium.Cartesian2(12, 8),
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 3,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            font: "bold 18px 'Segoe UI', 'Helvetica Neue', sans-serif",
            pixelOffset: new Cesium.Cartesian2(0, 0),
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            verticalOrigin: Cesium.VerticalOrigin.CENTER,
            heightReference: (viewer && viewer.scene && viewer.scene.mode === Cesium.SceneMode.SCENE2D) ? Cesium.HeightReference.NONE : Cesium.HeightReference.CLAMP_TO_GROUND,
            scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1800000.0, 0.5),
            // No disableDepthTestDistance — DEM must occlude labels on far side of terrain.
          },
        });
        labelEntity.show = annotationVisibilityEnabled;
        labelEntity._annotationId = annotationId;
        labelEntity._annotationRole = "text-label";
        
        // Edit button
        const editEntity = viewer.entities.add({
          position: makeBoundPositionCallback(),
          billboard: {
            image: ANNOTATION_EDIT_ICON_IMAGE,
            width: 18,
            height: 18,
            color: Cesium.Color.WHITE.withAlpha(0.5),
            pixelOffset: new Cesium.CallbackProperty(function () {
              var w = measureTextWidth(readLabelText(labelEntity), "bold 18px 'Segoe UI', 'Helvetica Neue', sans-serif");
              var distance = Cesium.Cartesian3.distance(viewer.camera.position, anchorPosition);
              var scale = 1.0;
              if (distance <= 2500.0) {
                scale = 1.0;
              } else if (distance >= 1800000.0) {
                scale = 0.5;
              } else {
                var t = (distance - 2500.0) / (1800000.0 - 2500.0);
                scale = 1.0 + t * (0.5 - 1.0);
              }
              return new Cesium.Cartesian2((-24 - w / 2) * scale, 0);
            }, false),
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            verticalOrigin: Cesium.VerticalOrigin.CENTER,
            heightReference: Cesium.HeightReference.NONE,
            scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1800000.0, 0.5),
          },
        });
        editEntity.show = annotationVisibilityEnabled;
        editEntity._annotationId = annotationId;
        editEntity._annotationRole = "edit";
        editEntity._annotationLabelEntity = labelEntity;
        
        // Delete button
        const deleteEntity = viewer.entities.add({
          position: makeBoundPositionCallback(),
          billboard: {
            image: ANNOTATION_DELETE_ICON_IMAGE,
            width: 18,
            height: 18,
            color: Cesium.Color.WHITE.withAlpha(0.7),
            pixelOffset: new Cesium.CallbackProperty(function () {
              var w = measureTextWidth(readLabelText(labelEntity), "bold 18px 'Segoe UI', 'Helvetica Neue', sans-serif");
              var distance = Cesium.Cartesian3.distance(viewer.camera.position, anchorPosition);
              var scale = 1.0;
              if (distance <= 2500.0) {
                scale = 1.0;
              } else if (distance >= 1800000.0) {
                scale = 0.5;
              } else {
                var t = (distance - 2500.0) / (1800000.0 - 2500.0);
                scale = 1.0 + t * (0.5 - 1.0);
              }
              return new Cesium.Cartesian2((24 + w / 2) * scale, 0);
            }, false),
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            verticalOrigin: Cesium.VerticalOrigin.CENTER,
            heightReference: Cesium.HeightReference.NONE,
            scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1800000.0, 0.5),
          },
        });
        deleteEntity.show = annotationVisibilityEnabled;
        deleteEntity._annotationId = annotationId;
        deleteEntity._annotationRole = "delete";
        deleteEntity._annotationLabelEntity = labelEntity;
        deleteEntity._annotationEditEntity = editEntity;
        
        annotationEntities.push(labelEntity);
        annotationEntities.push(editEntity);
        annotationEntities.push(deleteEntity);
        if (typeof window.syncAnnotationsToPython === "function") {
          window.syncAnnotationsToPython();
        }
        syncSearchResultMarkerVisibility();
        requestSceneRender();
        log("info", "Text label added at lon=" + lon + " lat=" + lat);
      },
      clearMeasurements: function () {
        setDistanceMeasureMode(false);
        clickedPoints.length = 0;
        clearMeasurementEntities();
        clearMeasurementPreviewEntities();
        clearDistanceScaleOverlay();
        log("info", "Measurement overlays cleared");
      },
      clearMeasurementEntities: function () {
        clearMeasurementEntities();
        log("debug", "Measurement entities cleared");
      },
      clearOverlays: function () {
        clickedPoints.length = 0;
        setDistanceMeasureMode(false);
        clearMeasurementEntities();
        clearMeasurementPreviewEntities();
        clearDistanceScaleOverlay();
        clearAnnotationEntities();
        clearSearchEntities();
        searchPolygonPoints.length = 0;
        searchPolygonLocked = false;
        searchCursorPoint = null;
        emitSearchGeometry("none", {});
        setStatus("All overlays cleared");
        log("info", "All overlays cleared");
        requestSceneRender();
      },
      undoLastAction: function () {
        let undid = false;
        // Undo last annotation point
        if (annotationEntities.length > 0) {
          // Each annotation has 4 entities: anchor, label, edit, delete
          const last = annotationEntities[annotationEntities.length - 1];
          if (last && last._annotationRole) {
            const targetId = last._annotationId;
            const toRemove = [];
            for (let i = annotationEntities.length - 1; i >= 0; i--) {
              if (annotationEntities[i]._annotationId === targetId) {
                toRemove.push(i);
              }
            }
            for (let i = 0; i < toRemove.length; i++) {
              const entity = annotationEntities.splice(toRemove[i], 1)[0];
              if (entity) viewer.entities.remove(entity);
            }
            undid = true;
            setStatus("Undo: removed last annotation.");
            log("info", "Undo annotation id=" + targetId);
          }
        }
        if (!undid && searchDrawMode === "polygon" && !searchPolygonLocked && searchPolygonPoints.length > 0) {
          searchPolygonPoints.pop();
          searchCursorPoint = null;
          if (window.OfflineGISRuntime && typeof window.OfflineGISRuntime.setSearchCursorPoint === "function") {
            window.OfflineGISRuntime.setSearchCursorPoint(null);
          }
          updateSearchPolygonPreview();
          undid = true;
          setStatus("Undo: removed last polygon point. " + searchPolygonPoints.length + " points remain.");
          log("info", "Undo polygon point");
        }
        if (!undid && searchDrawMode === "rectangle" && !searchRectangleLocked && searchRectangleStartPoint) {
          searchRectangleStartPoint = null;
          searchRectangleCurrentPoint = null;
          undid = true;
          setStatus("Undo: cleared search box in progress.");
          log("info", "Undo rectangle draw");
        }
        if (!undid && distanceMeasureModeEnabled && distanceMeasureAnchor) {
          distanceMeasureAnchor = null;
          clearMeasurementPreviewEntities();
          undid = true;
          setStatus("Undo: removed measurement start point.");
          log("info", "Undo distance start");
        }
        requestSceneRender();
        return undid;
      },
      cancelActiveDraw: function () {
        let cancelled = false;
        if (lineDrawModeEnabled || lineDrawStart) {
          lineDrawStart = null;
          clearLineDrawPreview();
          setStatus("Line draw cancelled. Click start point to begin again.");
          log("info", "Cancel active line draw");
          cancelled = true;
        }
        if (distanceMeasureModeEnabled && distanceMeasureAnchor) {
          distanceMeasureAnchor = null;
          clearMeasurementPreviewEntities();
          setStatus("Distance draw cancelled. Click first point to begin again.");
          log("info", "Cancel active distance draw");
          cancelled = true;
        }
        if (searchDrawMode === "polygon" && !searchPolygonLocked) {
          searchPolygonPoints.length = 0;
          searchCursorPoint = null;
          if (window.OfflineGISRuntime && typeof window.OfflineGISRuntime.setSearchCursorPoint === "function") {
            window.OfflineGISRuntime.setSearchCursorPoint(null);
          }
          updateSearchPolygonPreview();
          searchDrawMode = "none";
          setSearchCursorEnabled(false);
          updatePolygonPreviewVisibility();
          emitSearchGeometry("none", {});
          setStatus("Polygon drawing cancelled.");
          log("info", "Cancel active polygon draw");
          cancelled = true;
          if (viewer && viewer.scene && viewer.scene.screenSpaceCameraController) {
            viewer.scene.screenSpaceCameraController.enableInputs = true;
          }
        }
        if (searchDrawMode === "rectangle" && !searchRectangleLocked) {
          searchRectangleStartPoint = null;
          searchRectangleCurrentPoint = null;
          searchRectangleLocked = false;
          if (window.searchRectangleEntity && viewer) {
            viewer.entities.remove(window.searchRectangleEntity);
            window.searchRectangleEntity = null;
          }
          searchDrawMode = "none";
          setSearchCursorEnabled(false);
          updatePolygonPreviewVisibility();
          emitSearchGeometry("none", {});
          setStatus("Box drawing cancelled.");
          log("info", "Cancel active rectangle draw");
          cancelled = true;
          if (viewer && viewer.scene && viewer.scene.screenSpaceCameraController) {
            viewer.scene.screenSpaceCameraController.enableInputs = true;
          }
          requestSceneRender();
        }
        if (flyThroughModeEnabled && flyThroughPoints.length > 0) {
          flyThroughPoints.length = 0;
          flyThroughPreviewEnd = null;
          if (flyThroughPreviewLineEntity) {
            viewer.entities.remove(flyThroughPreviewLineEntity);
            flyThroughPreviewLineEntity = null;
          }
          if (flyThroughPathEntity) {
            viewer.entities.remove(flyThroughPathEntity);
            flyThroughPathEntity = null;
          }
          requestSceneRender();
          setStatus("Fly Through cancelled. Click to add a new path.");
          log("info", "Cancel active fly through draw");
          cancelled = true;
        }
        if (viewer && viewer.scene && viewer.scene.screenSpaceCameraController) {
          viewer.scene.screenSpaceCameraController.enableInputs = true;
        }
        return cancelled;
      },
      zoomIn: function () {
        log("debug", "=== ZOOM IN BUTTON PRESSED ===");
        zoomBy(0.82);
        log("debug", "Zoom in button completed");
      },
      zoomOut: function () {
        log("debug", "=== ZOOM OUT BUTTON PRESSED ===");
        zoomBy(1.18);
        log("debug", "Zoom out button completed");
      },
      zoomToExtent: function () {
        zoomToExtent();
        log("debug", "Zoom to extent");
      },
      resetNorthUp: function () {
        resetNorthUp();
        log("debug", "North-up orientation reset");
      },

      setSwipeComparator: function (enabled) {
        setSwipeComparatorEnabled(Boolean(enabled));
        log("debug", "Comparator=" + String(Boolean(enabled)));
      },
      setLayerAlpha: function (layerKey, alpha) {
        if (!viewer || !viewer.imageryLayers) return;
        const numAlpha = Math.max(0.0, Math.min(1.0, Number(alpha) || 0.0));
        
        const layer = managedImageryLayers.get(layerKey);
        if (layer) {
          // Guard: the DEM drape and hillshade layers are stored in managedImageryLayers
          // for layer-ordering, but the compositor opacity slider must NEVER touch them.
          // Drape controls the DEM colorization and hillshade controls terrain shading —
          // those are managed by Display Settings, not the compositor.
          const isDemDrape      = (layer === activeDemDrapeLayer);
          const isDemHillshade  = (layer === activeDemHillshadeLayer);
          if (isDemDrape || isDemHillshade) {
            log("debug", "setLayerAlpha: skipping DEM layer " + (isDemDrape ? "drape" : "hillshade") + " key=" + layerKey);
            return;
          }
          layer.alpha = numAlpha;
        }
        requestSceneRender();
      },

      setQualitySettings: function (settings) {
        // settings = { sse, resolutionScale, tileCacheSize, loadingDescendantLimit }
        if (!viewer) return;
        const sse           = Number(settings.sse);
        const resSc         = Number(settings.resolutionScale);
        const cacheSize     = Number(settings.tileCacheSize);
        const descLimit     = Number(settings.loadingDescendantLimit);

        if (Number.isFinite(sse) && sse > 0 && viewer.scene.globe) {
          viewer.scene.globe.maximumScreenSpaceError = sse;
          // Also persist as the active DEM SSE baseline so DEM lock doesn't override
          window._userQualitySSE = sse;
        }
        if (Number.isFinite(resSc) && resSc > 0) {
          viewer.resolutionScale = resSc;
        }
        if (Number.isFinite(cacheSize) && cacheSize > 0 && viewer.scene.globe) {
          viewer.scene.globe.tileCacheSize = cacheSize;
        }
        if (Number.isFinite(descLimit) && descLimit > 0 && viewer.scene.globe) {
          viewer.scene.globe.loadingDescendantLimit = descLimit;
        }
        requestSceneRender();
        log("info", "Quality settings applied: SSE=" + sse + " res=" + resSc + " cache=" + cacheSize + " desc=" + descLimit);
      },

      setComparator: function (enabled) {
        setSwipeComparatorEnabled(Boolean(enabled));
        log("debug", "Comparator=" + String(Boolean(enabled)));
      },

      requestComparatorPaneState: function () {
        notifyComparatorPaneState(comparatorSelectedPane);
      },
      setSwipePosition: function (fraction) {
        setSwipePosition(Number(fraction));
        log("debug", "Comparator position=" + String(fraction));
      },
      setComparatorPosition: function (fraction) {
        setSwipePosition(Number(fraction));
        log("debug", "Comparator position=" + String(fraction));
      },
      setFlyThroughMode: function (enabled) {
        flyThroughModeEnabled = Boolean(enabled);
        if (!flyThroughModeEnabled) {
          flyThroughPoints.length = 0;
          if (flyThroughPreviewLineEntity) {
            viewer.entities.remove(flyThroughPreviewLineEntity);
            flyThroughPreviewLineEntity = null;
          }
          flyThroughPreviewEnd = null;
          flyThroughCursorCartesian = null;
        }
        reapplyLayerOrderIfKnown();
      },
      stopFlyThrough: function () {
        stopFlyThrough();
      },
      pauseFlyThroughPlaybackOnly: function () {
        if (typeof cancelFlyThroughPlaybackFrame === "function") {
          cancelFlyThroughPlaybackFrame();
        }
        flyThroughIsPlaying = false;
        flyThroughPlaybackPaused = true;
        if (typeof notifyFlyThroughPlaybackState === "function") {
          notifyFlyThroughPlaybackState("paused");
        }
      },
      endFlyThrough: function () {
        stopFlyThrough();
      },
      toggleFlyThroughPlayback: function () {
        toggleFlyThroughPlayback();
      },
      setFlyThroughPlaybackProgress: function (value) {
        setFlyThroughPlaybackProgress(value);
      },
      setFlyThroughPitch: function (value) {
        setFlyThroughPitch(value);
      },
      setFlyThroughHeight: function (value) {
        setFlyThroughHeight(value);
      },
      setFlyThroughSpeed: function (value) {
        setFlyThroughSpeed(value);
      },
      getFlyThroughDuration: function () {
        const plan = buildFlyThroughPlaybackPlan();
        return plan ? plan.totalDurationMs : 0;
      },
      getFlyThroughCoordsAtProgress: function (progress) {
        const normalized = Math.max(0, Math.min(1, Number(progress) || 0));
        const plan = buildFlyThroughPlaybackPlan();
        if (!plan) return null;
        const state = getFlyThroughStateForProgress(normalized, plan);
        if (!state || !state.groundPos) return null;
        const carto = Cesium.Cartographic.fromCartesian(state.groundPos);
        if (!carto) return null;
        const heightOffset = Math.max(1.0, Math.min(2000.0, Number(flyThroughPlaybackHeightMeters) || 900.0));
        return {
          lon: Cesium.Math.toDegrees(carto.longitude),
          lat: Cesium.Math.toDegrees(carto.latitude),
          height: carto.height + heightOffset
        };
      },
      setComparatorMode: function (enabled) {
        setSwipeComparatorEnabled(Boolean(enabled));
        reapplyLayerOrderIfKnown();
      },
      setDistanceMeasureMode: function (enabled) {
        setDistanceMeasureMode(Boolean(enabled));
        log("info", "Distance measure mode=" + String(Boolean(enabled)));
      },
      setMeasurementCursor: function (enabled) {
        log("info", "[CURSOR_DEBUG] setMeasurementCursor API called enabled=" + String(Boolean(enabled)));
        setMeasurementCursorEnabled(Boolean(enabled));
      },
      drawProfileLine: function (lon1, lat1, lon2, lat2) {
        if (!viewer) return;
        // Clear profile mode flag and preview line
        window._profileModeActive = false;
        if (window._profilePreviewEntity) {
          try { viewer.entities.remove(window._profilePreviewEntity); } catch (_) {}
          window._profilePreviewEntity = null;
        }
        // Remove any previous profile line and markers
        if (window._profileLineEntity) {
          try { viewer.entities.remove(window._profileLineEntity); } catch (_) {}
          window._profileLineEntity = null;
        }
        const cyan = Cesium.Color.fromCssColorString("#00e5ff");
        const h1 = getGroundHeightAtLonLat(Number(lon1), Number(lat1));
        const h2 = getGroundHeightAtLonLat(Number(lon2), Number(lat2));
        window._profileLineEntity = viewer.entities.add({
          polyline: {
            positions: [
              Cesium.Cartesian3.fromDegrees(Number(lon1), Number(lat1), h1 + 0.1),
              Cesium.Cartesian3.fromDegrees(Number(lon2), Number(lat2), h2 + 0.1),
            ],
            width: 2.5,
            arcType: Cesium.ArcType.GEODESIC,
            material: cyan,
            depthFailMaterial: cyan,
            clampToGround: false,
          },
        });
        requestSceneRender();
        log("debug", "Profile line drawn lon1=" + lon1 + " lat1=" + lat1 + " lon2=" + lon2 + " lat2=" + lat2);
        // Store endpoints for georeferenced cursor projection
        window._profileLineLon1 = Number(lon1);
        window._profileLineLat1 = Number(lat1);
        window._profileLineLon2 = Number(lon2);
        window._profileLineLat2 = Number(lat2);
        window._profileLineActive = true;
        // Create the moving cursor point on the globe (dull yellow, starts at midpoint)
        if (window._profileCursorGlobeEntity) {
          try { viewer.entities.remove(window._profileCursorGlobeEntity); } catch (_) {}
          window._profileCursorGlobeEntity = null;
        }
        const yellow = Cesium.Color.fromCssColorString("#c8a800").withAlpha(0.88);
        // Pre-compute the geodesic for accurate interpolation along the great-circle arc
        const _geodesicForCursor = new Cesium.EllipsoidGeodesic(
          Cesium.Cartographic.fromDegrees(Number(lon1), Number(lat1)),
          Cesium.Cartographic.fromDegrees(Number(lon2), Number(lat2))
        );
        window._profileCursorGlobeEntity = viewer.entities.add({
          position: new Cesium.CallbackProperty(function () {
            if (!window._profileLineActive) {
              return Cesium.Cartesian3.fromDegrees(Number(lon1), Number(lat1));
            }
            const f = (typeof window._profileCursorFrac === "number")
              ? Math.max(0.0, Math.min(1.0, window._profileCursorFrac))
              : 0.5;
            // Interpolate along the true geodesic arc
            const interp = _geodesicForCursor.interpolateUsingFraction(f);
            // Sample terrain height so the dot sits ON the DEM surface, not underground
            let terrainH = 0.0;
            try {
              if (viewer.scene.globe) {
                const cartoCursor = Cesium.Cartographic.fromRadians(interp.longitude, interp.latitude);
                const sampled = viewer.scene.globe.getHeight(cartoCursor);
                if (typeof sampled === "number" && Number.isFinite(sampled)) {
                  terrainH = sampled;
                }
              }
            } catch (_) {}
            return Cesium.Cartesian3.fromRadians(interp.longitude, interp.latitude, terrainH + 2.0);
          }, false),
          point: {
            pixelSize: 8,
            color: yellow,
            outlineColor: Cesium.Color.fromCssColorString("#3a2800"),
            outlineWidth: 1.5,
            heightReference: Cesium.HeightReference.NONE,
          },
        });

        window._profileCursorFrac = 0.5;
      },
      setProfileCursorMode: function (enabled) {
        const container = document.getElementById("cesiumContainer");
        if (container) {
          if (enabled) {
            container.classList.add("measure-profile-cursor-active");
          } else {
            container.classList.remove("measure-profile-cursor-active");
          }
        }
        log("debug", "Profile cursor mode=" + String(Boolean(enabled)));
      },
      drawProfileStartMarker: function (lon, lat) {
        if (!viewer) return;
        // Remove previous start marker if any
        if (window._profileStartEntity) {
          try { viewer.entities.remove(window._profileStartEntity); } catch (_) {}
          window._profileStartEntity = null;
        }
        // Clear any stale preview line
        if (window._profilePreviewEntity) {
          try { viewer.entities.remove(window._profilePreviewEntity); } catch (_) {}
          window._profilePreviewEntity = null;
        }
        // Clear the previous completed profile line and end marker
        if (window._profileLineEntity) {
          try { viewer.entities.remove(window._profileLineEntity); } catch (_) {}
          window._profileLineEntity = null;
        }
        if (window._profileEndEntity) {
          try { viewer.entities.remove(window._profileEndEntity); } catch (_) {}
          window._profileEndEntity = null;
        }
        
        const cyan = Cesium.Color.fromCssColorString("#00e5ff");
        window._profileStartEntity = viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(Number(lon), Number(lat)),
          point: { pixelSize: 9, color: cyan, outlineColor: Cesium.Color.BLACK, outlineWidth: 1.5, heightReference: (viewer && viewer.scene && viewer.scene.mode === Cesium.SceneMode.SCENE2D) ? Cesium.HeightReference.NONE : Cesium.HeightReference.CLAMP_TO_GROUND },
          label: {
            text: "A",
            font: "bold 11px sans-serif",
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            fillColor: Cesium.Color.WHITE,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
            pixelOffset: new Cesium.Cartesian2(10, -10),
            heightReference: (viewer && viewer.scene && viewer.scene.mode === Cesium.SceneMode.SCENE2D) ? Cesium.HeightReference.NONE : Cesium.HeightReference.CLAMP_TO_GROUND,
          },
        });
        // Store start coords — preview line is recreated on every mouse move
        window._profileStartLon = Number(lon);
        window._profileStartLat = Number(lat);
        window._profileModeActive = true;
        requestSceneRender();
        log("debug", "Profile start marker placed lon=" + lon + " lat=" + lat);
      },
      clearProfilePreview: function () {
        window._profileModeActive = false;
        window._profileStartLon = undefined;
        window._profileStartLat = undefined;
        
        if (window._profilePreviewEntity) {
          try { viewer.entities.remove(window._profilePreviewEntity); } catch (_) {}
          window._profilePreviewEntity = null;
        }
        if (window._profileStartEntity) {
          try { viewer.entities.remove(window._profileStartEntity); } catch (_) {}
          window._profileStartEntity = null;
        }
        requestSceneRender();
      },
      clearProfileLine: function () {
        window._profileModeActive = false;
        window._profileLineActive = false;
        window._profileLineLon1 = undefined;
        window._profileLineLat1 = undefined;
        window._profileLineLon2 = undefined;
        window._profileLineLat2 = undefined;
        window._profileCursorFrac = undefined;
        
        for (const key of ["_profilePreviewEntity", "_profileStartEntity", "_profileEndEntity", "_profileLineEntity", "_profileCursorGlobeEntity"]) {
          if (window[key]) {
            try { viewer.entities.remove(window[key]); } catch (_) {}
            window[key] = null;
          }
        }
        requestSceneRender();
        log("debug", "Profile line cleared from globe");
      },
      setPanMode: function (enabled) {
        setPanMode(Boolean(enabled));
        log("info", "Pan mode=" + String(Boolean(enabled)));
      },
      setSearchDrawMode: function (mode) {
        if (mode !== "polygon" && mode !== "rectangle") {
          searchDrawMode = "none";
          setSearchCursorEnabled(false);
          updatePolygonPreviewVisibility();
          if (viewer && viewer.scene && viewer.scene.screenSpaceCameraController) {
            viewer.scene.screenSpaceCameraController.enableInputs = true;
          }
          // Removed DOM update
          setStatus("Search draw disabled");
          requestSceneRender();
          return;
        }
        resetSearchDrawTransientState();
        if (typeof searchPolygonController !== "undefined" && searchPolygonController && typeof searchPolygonController.clearSearchAoi === "function") {
          searchPolygonController.clearSearchAoi();
        }
        if (window.searchAoiEntity && viewer) {
          try { viewer.entities.remove(window.searchAoiEntity); } catch (_) {}
          window.searchAoiEntity = null;
          window.searchAoiBounds = null;
        }
        searchDrawMode = mode;
        searchOverlayVisible = true;
        window._offlineGISSearchOverlayVisible = true;
        polygonVisibilityEnabled = true;
        if (mode === "rectangle") {
          setPolygonPreviewVisible(false);
          setSearchCursorEnabled(false);
          setStatus("Box draw: drag on the map to define a search box");
        } else {
          setPolygonPreviewVisible(true);
          setSearchCursorEnabled(true);
          setStatus("Polygon draw: click points, right-click or Finish to close");
        }
        // Removed DOM update
        requestSceneRender();
      },
      finishSearchPolygon: function () {
        finalizeSearchPolygon();
      },
      clearSearchGeometry: function () {
        resetSearchDrawTransientState();
        clearSearchEntities();
        if (typeof searchPolygonController !== "undefined" && searchPolygonController && typeof searchPolygonController.clearAllData === "function") {
          searchPolygonController.clearAllData();
        }
        if (window.offlineGIS && typeof window.offlineGIS.resetDrawnPolygonCounter === "function") {
          window.offlineGIS.resetDrawnPolygonCounter();
        }
        emitSearchGeometry("none", {});
        setPolygonPreviewVisible(true);
        setSearchCursorEnabled(false);
        setStatus("Search geometry cleared");
        requestSceneRender();
      },
      setPolygonPreviewVisible: function (visible) {
        setPolygonPreviewVisible(Boolean(visible));
      },
      setSearchOverlayVisible: function (visible) {
        searchOverlayVisible = Boolean(visible);
        window._offlineGISSearchOverlayVisible = searchOverlayVisible;
        syncSearchResultMarkerVisibility();
        updatePolygonPreviewVisibility();
        requestSceneRender();
      },
      syncSearchResultMarkerVisibility: function () {
        syncSearchResultMarkerVisibility();
      },
  });
