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

  Object.assign(window.offlineGIS, {
      setSearchResultMarkers: function (markers) {
        if (!viewer) return;
        clearSearchResultMarkerEntities();
        const items = Array.isArray(markers) ? markers : [];
        let validCount = 0;
        
        const cartographics = [];
        const entityPairs = [];

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
          
          const billboardEntity = viewer.entities.add({
            position: position,
            show: false, // Keep hidden during elevation sampling to prevent misplacement
            billboard: {
              show: false, // Keep hidden during elevation sampling
              image: displayed ? SEARCH_RESULT_MARKER_YELLOW : SEARCH_RESULT_MARKER_RED,
              width: 26,
              height: 26,
              verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
              horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
              heightReference: Cesium.HeightReference.NONE, // No native clamping to prevent drifting
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1800000.0, 0.55),
            },
          });

          const labelEntity = viewer.entities.add({
            position: position,
            show: false, // Keep hidden during elevation sampling
            label: {
              show: false, // Keep hidden during elevation sampling
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
              heightReference: Cesium.HeightReference.NONE, // No native clamping to prevent drifting
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1800000.0, 0.6),
              translucencyByDistance: new Cesium.NearFarScalar(3000.0, 1.0, 2400000.0, 0.75),
            },
          });

          billboardEntity._searchResultMarker = true;
          billboardEntity._searchResultMarkerIndex = index;
          billboardEntity._assetFilePath = String(marker.file_path || "");
          billboardEntity._assetDisplayed = displayed;
          billboardEntity._originalScale = 1.0;
          searchResultMarkerEntities.push(billboardEntity);

          labelEntity._searchResultMarker = true;
          labelEntity._searchResultMarkerIndex = index;
          labelEntity._assetFilePath = String(marker.file_path || "");
          labelEntity._assetDisplayed = displayed;
          searchResultMarkerEntities.push(labelEntity);

          cartographics.push(Cesium.Cartographic.fromDegrees(lon, lat));
          entityPairs.push({
            billboard: billboardEntity,
            label: labelEntity,
            lon: lon,
            lat: lat
          });
        }

        // Asynchronously query the active terrain's true geodetic elevations
        if (cartographics.length > 0) {
          const terrainProvider = viewer.terrainProvider || new Cesium.EllipsoidTerrainProvider();
          Promise.resolve(Cesium.sampleTerrainMostDetailed(terrainProvider, cartographics))
            .then(function (updatedCartographics) {
              const visible = getSearchOverlayVisible();
              for (let i = 0; i < updatedCartographics.length; i++) {
                const cart = updatedCartographics[i];
                const height = Number.isFinite(cart.height) ? cart.height : 0.0;
                const pair = entityPairs[i];
                const newPos = Cesium.Cartesian3.fromDegrees(pair.lon, pair.lat, height);
                
                if (pair.billboard) {
                  pair.billboard.position = newPos;
                  pair.billboard.show = visible;
                  pair.billboard.billboard.show = new Cesium.CallbackProperty(function () {
                    return getSearchOverlayVisible();
                  }, false);
                }
                if (pair.label) {
                  pair.label.position = newPos;
                  pair.label.show = visible;
                  pair.label.label.show = new Cesium.CallbackProperty(function () {
                    return getSearchOverlayVisible();
                  }, false);
                }
              }
              requestSceneRender();
            })
            .catch(function () {
              // Fallback to ellipsoid level on error
              const visible = getSearchOverlayVisible();
              for (let i = 0; i < entityPairs.length; i++) {
                const pair = entityPairs[i];
                if (pair.billboard) {
                  pair.billboard.show = visible;
                  pair.billboard.billboard.show = new Cesium.CallbackProperty(function () {
                    return getSearchOverlayVisible();
                  }, false);
                }
                if (pair.label) {
                  pair.label.show = visible;
                  pair.label.label.show = new Cesium.CallbackProperty(function () {
                    return getSearchOverlayVisible();
                  }, false);
                }
              }
              requestSceneRender();
            });
        }
      },
      realignMarkersToTerrain: function () {
        if (!viewer || searchResultMarkerEntities.length === 0) return;
        
        log("info", "DEM_RENDER: Realigning " + searchResultMarkerEntities.length + " markers to new terrain provider...");
        
        const cartographics = [];
        const entityPairs = [];
        const groups = {};

        for (let i = 0; i < searchResultMarkerEntities.length; i++) {
          const entity = searchResultMarkerEntities[i];
          if (!entity) continue;
          
          // Hide immediately during transition to hide any visual drifting
          entity.show = false;
          
          const idx = entity._searchResultMarkerIndex;
          if (idx === undefined) continue;
          if (!groups[idx]) groups[idx] = {};
          
          if (entity.billboard) {
            groups[idx].billboard = entity;
          } else if (entity.label) {
            groups[idx].label = entity;
          }
        }
        
        Object.keys(groups).forEach(function (idx) {
          const g = groups[idx];
          if (g.billboard && g.billboard.position) {
            const cartographic = Cesium.Cartographic.fromCartesian(g.billboard.position.getValue(Cesium.JulianDate.now()));
            if (cartographic) {
              cartographics.push(cartographic);
              entityPairs.push({
                billboard: g.billboard,
                label: g.label,
                lon: Cesium.Math.toDegrees(cartographic.longitude),
                lat: Cesium.Math.toDegrees(cartographic.latitude)
              });
            }
          }
        });
        
        if (cartographics.length > 0) {
          const terrainProvider = viewer.terrainProvider || new Cesium.EllipsoidTerrainProvider();
          Promise.resolve(Cesium.sampleTerrainMostDetailed(terrainProvider, cartographics))
            .then(function (updatedCartographics) {
              const visible = getSearchOverlayVisible();
              for (let i = 0; i < updatedCartographics.length; i++) {
                const cart = updatedCartographics[i];
                const height = Number.isFinite(cart.height) ? cart.height : 0.0;
                const pair = entityPairs[i];
                const newPos = Cesium.Cartesian3.fromDegrees(pair.lon, pair.lat, height);
                
                if (pair.billboard) {
                  pair.billboard.position = newPos;
                  pair.billboard.show = visible;
                }
                if (pair.label) {
                  pair.label.position = newPos;
                  pair.label.show = visible;
                }
              }
              requestSceneRender();
            })
            .catch(function () {
              const visible = getSearchOverlayVisible();
              for (let i = 0; i < entityPairs.length; i++) {
                const pair = entityPairs[i];
                if (pair.billboard) pair.billboard.show = visible;
                if (pair.label) pair.label.show = visible;
              }
              requestSceneRender();
            });
        }
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
            backgroundPadding: new Cesium.Cartesian2(12, 8),
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 3,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            font: "bold 18px 'Segoe UI', 'Helvetica Neue', sans-serif",
            pixelOffset: new Cesium.Cartesian2(0, 0),
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            verticalOrigin: Cesium.VerticalOrigin.CENTER,
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1800000.0, 0.5),
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
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1800000.0, 0.5),
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
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1800000.0, 0.5),
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
        if (!state) return null;
        const easedProgress = Cesium.EasingFunction.QUADRATIC_IN_OUT(state.localProgress);
        const dest = Cesium.Cartesian3.lerp(
          state.startPos,
          state.endPos,
          easedProgress,
          new Cesium.Cartesian3()
        );
        const carto = Cesium.Cartographic.fromCartesian(dest);
        if (!carto) return null;
        return {
          lon: Cesium.Math.toDegrees(carto.longitude),
          lat: Cesium.Math.toDegrees(carto.latitude),
          height: carto.height
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
            // Interpolate along the true geodesic arc — pixel-accurate for any resolution
            const interp = _geodesicForCursor.interpolateUsingFraction(f);
            return Cesium.Cartesian3.fromRadians(interp.longitude, interp.latitude);
          }, false),
          point: {
            pixelSize: 8,
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
