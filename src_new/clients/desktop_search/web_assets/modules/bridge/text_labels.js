  window.offlineGIS = window.offlineGIS || {};
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
    for (let index = 0; index < searchResultMarkerEntities.length; index += 1) {
      const entity = searchResultMarkerEntities[index];
      if (entity) {
        entity.show = visible;
      }
    }
  }

  Object.assign(window.offlineGIS, {
      setSearchResultMarkers: function (markers) {
        if (!viewer) return;
        clearSearchResultMarkerEntities();
        const items = Array.isArray(markers) ? markers : [];
        let validCount = 0;
        for (let index = 0; index < items.length; index += 1) {
          const marker = items[index] || {};
          const lon = Number(marker.lon);
          const lat = Number(marker.lat);
          if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
            continue;
          }
          const labelText = String(marker.text || marker.file_name || "Tile").trim() || "Tile";
          const position = Cesium.Cartesian3.fromDegrees(lon, lat, 0.0);
          const displayed = Boolean(marker.displayed);
          validCount += 1;
          const iconEntity = viewer.entities.add({
            position: position,
            show: new Cesium.CallbackProperty(function () {
              return getSearchOverlayVisible();
            }, false),
            billboard: {
              image: displayed ? SEARCH_RESULT_MARKER_YELLOW : SEARCH_RESULT_MARKER_RED,
              width: 26,
              height: 26,
              verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
              horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
              heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1800000.0, 0.55),
            },
            label: {
              text: labelText,
              font: "600 11px 'Segoe UI', 'Helvetica Neue', sans-serif",
              fillColor: Cesium.Color.WHITE,
              outlineColor: Cesium.Color.BLACK,
              outlineWidth: 2,
              style: Cesium.LabelStyle.FILL_AND_OUTLINE,
              showBackground: true,
              backgroundColor: Cesium.Color.BLACK.withAlpha(0.72),
              backgroundPadding: new Cesium.Cartesian2(5, 3),
              pixelOffset: new Cesium.Cartesian2(0, -32),
              horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
              verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
              heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1800000.0, 0.6),
              translucencyByDistance: new Cesium.NearFarScalar(3000.0, 1.0, 2400000.0, 0.75),
            },
          });

          iconEntity._searchResultMarker = true;
          iconEntity._searchResultMarkerIndex = index;
          searchResultMarkerEntities.push(iconEntity);
        }
        requestSceneRender();
      },
      clearSearchResultMarkers: function () {
        clearSearchResultMarkerEntities();
        requestSceneRender();
      },
      addTextLabel: function (lon, lat, text) {
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
          const cartographic = Cesium.Cartographic.fromDegrees(Number(lon), Number(lat));
          const sampledHeight = viewer.scene && viewer.scene.globe ? viewer.scene.globe.getHeight(cartographic) : null;
          const height = Number.isFinite(sampledHeight) ? Number(sampledHeight) : 0.0;
          anchorPosition = Cesium.Cartesian3.fromDegrees(Number(lon), Number(lat), height);
        }
        lastMapClickCartesian = null;
        
        // Large white text label (no anchor point, just text)
        const labelEntity = viewer.entities.add({
          position: anchorPosition,
          label: {
            text: displayText,
            fillColor: Cesium.Color.WHITE,
            showBackground: true,
            backgroundColor: Cesium.Color.BLACK.withAlpha(0.5),
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 3,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            font: "bold 18px 'Segoe UI', 'Helvetica Neue', sans-serif",
            pixelOffset: new Cesium.Cartesian2(0, 0),
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            verticalOrigin: Cesium.VerticalOrigin.CENTER,
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.2, 1800000.0, 0.6),
            translucencyByDistance: new Cesium.NearFarScalar(3000.0, 1.0, 2400000.0, 0.7),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });
        labelEntity.show = annotationVisibilityEnabled;
        labelEntity._annotationId = annotationId;
        labelEntity._annotationRole = "text-label";
        
        // Edit button
        const editEntity = viewer.entities.add({
          position: anchorPosition,
          billboard: {
            image: ANNOTATION_EDIT_ICON_IMAGE,
            width: 18,
            height: 18,
            color: Cesium.Color.WHITE.withAlpha(0.5),
            pixelOffset: new Cesium.Cartesian2(-35, -25),
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            verticalOrigin: Cesium.VerticalOrigin.CENTER,
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1700000.0, 0.62),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });
        editEntity.show = annotationVisibilityEnabled;
        editEntity._annotationId = annotationId;
        editEntity._annotationRole = "edit";
        editEntity._annotationLabelEntity = labelEntity;
        
        // Delete button
        const deleteEntity = viewer.entities.add({
          position: anchorPosition,
          billboard: {
            image: ANNOTATION_DELETE_ICON_IMAGE,
            width: 18,
            height: 18,
            color: Cesium.Color.WHITE.withAlpha(0.7),
            pixelOffset: new Cesium.Cartesian2(35, -25),
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            verticalOrigin: Cesium.VerticalOrigin.CENTER,
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1700000.0, 0.62),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
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
        _clearFillVolumeEntities();
        window._fillVolumePrimitives = [];
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
        _clearFillVolumeEntities();
        window._fillVolumePrimitives = [];
        searchPolygonPoints.length = 0;
        searchPolygonLocked = false;
        searchCursorPoint = null;
        searchOverlayVisible = true;
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
        if (searchDrawMode === "polygon" && !searchPolygonLocked && searchPolygonPoints.length > 0) {
          searchPolygonPoints.length = 0;
          searchCursorPoint = null;
          if (window.OfflineGISRuntime && typeof window.OfflineGISRuntime.setSearchCursorPoint === "function") {
            window.OfflineGISRuntime.setSearchCursorPoint(null);
          }
          updateSearchPolygonPreview();
          setStatus("Polygon draw cancelled. Click points to start again.");
          log("info", "Cancel active polygon draw");
          cancelled = true;
        }
        if (searchDrawMode === "rectangle" && !searchRectangleLocked && (searchRectangleStartPoint || searchRectangleCurrentPoint)) {
          searchRectangleStartPoint = null;
          searchRectangleCurrentPoint = null;
          searchRectangleLocked = false;
          if (typeof searchRectangleEntity !== "undefined" && searchRectangleEntity && viewer) {
            viewer.entities.remove(searchRectangleEntity);
            searchRectangleEntity = null;
          }
          requestSceneRender();
          setStatus("Box draw cancelled. Drag to start again.");
          log("info", "Cancel active rectangle draw");
          cancelled = true;
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
        return cancelled;
      },
      zoomIn: function () {
        log("debug", "=== ZOOM IN BUTTON PRESSED ===");
        zoomBy(0.65);
        log("debug", "Zoom in button completed");
      },
      zoomOut: function () {
        log("debug", "=== ZOOM OUT BUTTON PRESSED ===");
        zoomBy(1.35);
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
          layer.alpha = numAlpha;
        } else if (activeDemContext && activeDemContext.layerKey === layerKey) {
          if (activeDemDrapeLayer) {
            activeDemDrapeLayer.alpha = numAlpha;
          }
          if (activeDemHillshadeLayer) {
            const scaledHillshade = Math.max(
              0.0,
              Math.min(1.0, demVisual.hillshadeAlpha * numAlpha)
            );
            activeDemHillshadeLayer.alpha = scaledHillshade;
            activeDemHillshadeLayer.show =
              (activeDemContext.visible !== false) && scaledHillshade > 0.01;
          }
        }
        requestSceneRender();
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
      setFlyThroughSpeed: function (value) {
        setFlyThroughSpeed(value);
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
        if (window._profileStartEntity) {
          try { viewer.entities.remove(window._profileStartEntity); } catch (_) {}
          window._profileStartEntity = null;
        }
        if (window._profileEndEntity) {
          try { viewer.entities.remove(window._profileEndEntity); } catch (_) {}
          window._profileEndEntity = null;
        }
        const cyan = Cesium.Color.fromCssColorString("#00e5ff");
        window._profileLineEntity = viewer.entities.add({
          polyline: {
            positions: [
              Cesium.Cartesian3.fromDegrees(Number(lon1), Number(lat1)),
              Cesium.Cartesian3.fromDegrees(Number(lon2), Number(lat2)),
            ],
            width: 2.5,
            arcType: Cesium.ArcType.GEODESIC,
            material: cyan,
            depthFailMaterial: cyan.withAlpha(0.5),
          },
        });
        // Start/end point markers
        window._profileStartEntity = viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(Number(lon1), Number(lat1)),
          point: { pixelSize: 8, color: cyan, outlineColor: Cesium.Color.BLACK, outlineWidth: 1, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        });
        window._profileEndEntity = viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(Number(lon2), Number(lat2)),
          point: { pixelSize: 8, color: cyan, outlineColor: Cesium.Color.BLACK, outlineWidth: 1, disableDepthTestDistance: Number.POSITIVE_INFINITY },
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
            // Interpolate along the true geodesic arc — pixel-accurate for any resolution
            const interp = _geodesicForCursor.interpolateUsingFraction(f);
            return Cesium.Cartesian3.fromRadians(interp.longitude, interp.latitude);
          }, false),
          point: {
            pixelSize: 10,
            color: yellow,
            outlineColor: Cesium.Color.fromCssColorString("#3a2800"),
            outlineWidth: 1.5,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
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
          point: { pixelSize: 9, color: cyan, outlineColor: Cesium.Color.BLACK, outlineWidth: 1.5, heightReference: Cesium.HeightReference.CLAMP_TO_GROUND, disableDepthTestDistance: Number.POSITIVE_INFINITY },
          label: {
            text: "A",
            font: "bold 11px sans-serif",
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            fillColor: Cesium.Color.WHITE,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
            pixelOffset: new Cesium.Cartesian2(10, -10),
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
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
          searchOverlayVisible = false;
          setSearchCursorEnabled(false);
          updatePolygonPreviewVisibility();
          // Removed DOM update
          setStatus("Search draw disabled");
          requestSceneRender();
          return;
        }
        searchDrawMode = mode;
        polygonVisibilityEnabled = true;
        searchCursorPoint = null;
        searchRectangleStartPoint = null;
        searchRectangleCurrentPoint = null;
        searchRectangleLocked = false;
        if (mode === "rectangle") {
          setPolygonPreviewVisible(false);
          setSearchCursorEnabled(false);
          setStatus("Box draw: drag on the map to define a search box");
        } else {
          setPolygonPreviewVisible(true);
          setSearchCursorEnabled(!searchPolygonLocked);
          if (searchPolygonLocked) {
            setStatus("Polygon restored. Clear geometry to start a new polygon.");
          } else {
            setStatus("Polygon draw: click points, right-click or Finish to close");
          }
        }
        // Removed DOM update
        requestSceneRender();
      },
      finishSearchPolygon: function () {
        finalizeSearchPolygon();
      },
      clearSearchGeometry: function () {
        searchDrawMode = "none";
        searchPolygonLocked = false;
        searchCursorPoint = null;
        searchPolygonPoints.length = 0;
        searchRectangleStartPoint = null;
        searchRectangleCurrentPoint = null;
        searchRectangleLocked = false;
        if (typeof searchRectangleEntity !== "undefined" && searchRectangleEntity && viewer) {
          viewer.entities.remove(searchRectangleEntity);
          searchRectangleEntity = null;
        }
        clearSearchEntities();
        if (typeof searchPolygonController !== "undefined" && searchPolygonController && typeof searchPolygonController.clearAllData === "function") {
          searchPolygonController.clearAllData();
        }
        clearSearchResultMarkerEntities();
        emitSearchGeometry("none", {});
        setPolygonPreviewVisible(true);
        setSearchCursorEnabled(false);
        // Removed DOM update
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
      clearFillVolumes: function () {
        _clearFillVolumeEntities();
        window._fillVolumePrimitives = [];
        requestSceneRender();
        log("debug", "Fill volume overlays cleared");
      },
      drawFillVolumes: function (regionsJson) {
        _clearFillVolumeEntities();
        var regions;
        try { regions = JSON.parse(regionsJson); } catch (e) { log("error", "drawFillVolumes: bad JSON"); return; }
        if (!Array.isArray(regions) || regions.length === 0) {
          log("debug", "drawFillVolumes: no regions to draw");
          return;
        }

        log("info", "Starting to draw " + regions.length + " fill volume regions");

        var distinctColors = [
          [255,  80,  40, 200],
          [ 40, 120, 255, 200],
          [ 40, 220, 100, 200],
          [255, 200,  40, 200],
          [180,  40, 255, 200],
          [255, 100, 180, 200],
          [ 40, 220, 220, 200],
          [255, 140,  40, 200],
        ];

        function getRegionColor(index) {
          var rgba = distinctColors[index % distinctColors.length];
          return new Cesium.Color(rgba[0]/255, rgba[1]/255, rgba[2]/255, rgba[3]/255);
        }

        var labelEntities = [];

        for (var ri = 0; ri < regions.length; ri++) {
          var r = regions[ri];
          var regionId = r.id || r.region_id || (ri + 1);

          if (!r.outline || r.outline.length < 3) {
            log("warn", "Region " + regionId + " has invalid outline, skipping");
            continue;
          }

          var fillColour = getRegionColor(ri);

          // Pure entity polygon — no GroundPrimitive, no GPU lifecycle, safe on macOS Metal + Windows NVIDIA.
          // No height — Cesium drapes on globe surface. arcType RHUMB gives pixel-accurate
          // edges for small sub-km polygons (avoids geodesic subdivision artifacts).
          var positions = r.outline.map(function(p) {
            return Cesium.Cartesian3.fromDegrees(p.lon, p.lat);
          });

          // Use the region's rim elevation + small offset so the flat polygon
          // sits just above the terrain surface and is never occluded at any zoom level.
          var polyHeight = (typeof r.rim_elevation_m === 'number' && isFinite(r.rim_elevation_m))
            ? r.rim_elevation_m + 2.0
            : 2.0;

          var regionEnt = viewer.entities.add({
            id: 'fill-region-ent-' + regionId,
            polygon: {
              hierarchy: new Cesium.PolygonHierarchy(positions),
              material: fillColour,
              height: polyHeight,
              arcType: Cesium.ArcType.RHUMB,
              outline: false,
              fill: true,
            },
          });
          window._fillVolumeEntities.push(regionEnt);

          var volStr = r.fill_volume_m3 >= 1000000000
            ? (r.fill_volume_m3 / 1000000000).toFixed(3) + " km\u00b3"
            : r.fill_volume_m3 >= 1000000
            ? (r.fill_volume_m3 / 1000000).toFixed(3) + " Mm\u00b3"
            : r.fill_volume_m3.toFixed(3) + " m\u00b3";
          var areaStr = r.area_m2 >= 10000
            ? (r.area_m2 / 10000).toFixed(2) + " ha"
            : r.area_m2.toFixed(0) + " m\u00b2";

          labelEntities.push({
            position: Cesium.Cartesian3.fromDegrees(r.centroid_lon, r.centroid_lat, polyHeight + 5.0),
            regionId: regionId,
            volStr: volStr,
            areaStr: areaStr,
            maxDepth: r.max_depth_m,
            meanDepth: r.mean_depth_m,
          });
        }

        for (var li = 0; li < labelEntities.length; li++) {
          var labelData = labelEntities[li];

          var labelEnt = viewer.entities.add({
            id: 'fill-label-' + labelData.regionId,
            position: labelData.position,
            label: {
              text: "\u25bc Region " + labelData.regionId,
              font: "bold 13px 'Segoe UI', Arial, sans-serif",
              style: Cesium.LabelStyle.FILL_AND_OUTLINE,
              fillColor: Cesium.Color.WHITE,
              outlineColor: Cesium.Color.BLACK,
              outlineWidth: 2.5,
              showBackground: true,
              backgroundColor: Cesium.Color.BLACK.withAlpha(0.85),
              backgroundPadding: new Cesium.Cartesian2(8, 5),
              horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
              verticalOrigin: Cesium.VerticalOrigin.TOP,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              pixelOffset: new Cesium.Cartesian2(0, -15),
              scale: 1.0,
            },
          });
          labelEnt.regionId = labelData.regionId;
          labelEnt.volume = labelData.volStr;
          labelEnt.area = labelData.areaStr;
          labelEnt.maxDepth = labelData.maxDepth.toFixed(2) + ' m';
          labelEnt.meanDepth = labelData.meanDepth.toFixed(2) + ' m';
          labelEnt.expanded = false;
          labelEnt.isRegionLabel = true;
          window._fillVolumeEntities.push(labelEnt);

          var detailsEnt = viewer.entities.add({
            id: 'fill-details-' + labelData.regionId,
            position: labelData.position,
            label: {
              text:
                'Volume: ' + labelData.volStr + '\n' +
                'Area: ' + labelData.areaStr + '\n' +
                'Max Depth: ' + labelData.maxDepth.toFixed(2) + ' m\n' +
                'Mean Depth: ' + labelData.meanDepth.toFixed(2) + ' m',
              font: "12px 'Segoe UI', Arial, sans-serif",
              style: Cesium.LabelStyle.FILL_AND_OUTLINE,
              fillColor: Cesium.Color.WHITE,
              outlineColor: Cesium.Color.BLACK,
              outlineWidth: 2,
              showBackground: true,
              backgroundColor: Cesium.Color.fromCssColorString('#1a1a1a').withAlpha(0.92),
              backgroundPadding: new Cesium.Cartesian2(10, 6),
              horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
              verticalOrigin: Cesium.VerticalOrigin.TOP,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              pixelOffset: new Cesium.Cartesian2(0, 15),
              scale: 0.95,
              show: false,
            },
          });
          detailsEnt.parentRegionId = labelData.regionId;
          detailsEnt.isDetails = true;
          window._fillVolumeEntities.push(detailsEnt);
          labelEnt.detailsEntity = detailsEnt;
        }

        requestSceneRender();
        log("info", "Fill volumes drawn: " + regions.length + " regions");
      },
  });
