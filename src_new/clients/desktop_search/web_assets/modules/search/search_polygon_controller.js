(function () {
  const root = (window.OfflineGISModules = window.OfflineGISModules || {});
  const search = (root.search = root.search || {});
  const geometry = search.geometry || {};

  function createSearchPolygonController(deps) {
    function debugLog(message) {
      const bridge = getBridge();
      if (bridge && typeof bridge.log === "function") {
        bridge.log("debug", message);
        return;
      }
      if (typeof console !== "undefined" && typeof console.debug === "function") {
        console.debug(message);
      }
    }

    function getViewer() {
      return deps.getViewer();
    }

    function getBridge() {
      return deps.getBridge();
    }

    function getCesium() {
      return deps.getCesium();
    }

    function getSearchPolygonPoints() {
      return deps.getSearchPolygonPoints();
    }

    function getSearchCursorPoint() {
      return deps.getSearchCursorPoint();
    }

    function getSearchOverlayVisible() {
      return deps.getSearchOverlayVisible();
    }

    function getPolygonVisibilityEnabled() {
      return deps.getPolygonVisibilityEnabled();
    }

    function getSearchPreviewLineEntity() {
      return deps.getSearchPreviewLineEntity();
    }

    function getSearchPreviewPolygonEntity() {
      return deps.getSearchPreviewPolygonEntity();
    }

    function getSearchAreaLabelEntity() {
      return deps.getSearchAreaLabelEntity();
    }

    function getSearchVertexEntities() {
      return deps.getSearchVertexEntities();
    }

    function getDrawnPolygons() {
      return deps.getDrawnPolygons();
    }

    function getComparatorModeEnabled() {
      return deps.getComparatorModeEnabled();
    }

    function getComparatorLeftViewer() {
      return deps.getComparatorLeftViewer();
    }

    function getSearchPolygonLocked() {
      return deps.getSearchPolygonLocked ? deps.getSearchPolygonLocked() : false;
    }

    function getIsAnnotationDrawing() {
      return deps.getIsAnnotationDrawing();
    }

    function emitSearchGeometry(type, payload) {
      if (geometry.emitSearchGeometry) {
        geometry.emitSearchGeometry(type, payload);
        return;
      }
      var serialized = typeof payload === "string" ? payload : JSON.stringify(payload || {});
      deps.emitSearchGeometry(type, serialized);
    }

    function getComparatorRightViewer() {
      return deps.getComparatorRightViewer();
    }

    function getSearchDrawMode() {
      return deps.getSearchDrawMode();
    }

    function setSearchDrawMode(value) {
      deps.setSearchDrawMode(value);
    }

    function setSearchCursorPoint(value) {
      deps.setSearchCursorPoint(value);
    }

    function setSearchPolygonLocked(value) {
      deps.setSearchPolygonLocked(value);
    }

    function setSearchOverlayVisible(value) {
      deps.setSearchOverlayVisible(value);
    }

    function setSearchPreviewLineEntity(value) {
      deps.setSearchPreviewLineEntity(value);
    }

    function setSearchPreviewPolygonEntity(value) {
      deps.setSearchPreviewPolygonEntity(value);
    }

    function setSearchAreaLabelEntity(value) {
      deps.setSearchAreaLabelEntity(value);
    }

    function setSearchVertexEntities(value) {
      deps.setSearchVertexEntities(value);
    }

    function setDrawnPolygons(value) {
      deps.setDrawnPolygons(value);
    }

    function setAoiPanelMinimized(value) {
      deps.setAoiPanelMinimized(value);
    }

    function getAoiPanelMinimized() {
      return deps.getAoiPanelMinimized();
    }

    function requestSceneRender() {
      deps.requestSceneRender();
    }

    function getGroundHeightAtLonLat(lon, lat) {
      const viewer = getViewer();
      const cesium = getCesium();
      if (!viewer || !viewer.scene || !viewer.scene.globe || !cesium) {
        return 0;
      }
      try {
        const height = viewer.scene.globe.getHeight(cesium.Cartographic.fromDegrees(lon, lat));
        return Number.isFinite(height) ? height : 0;
      } catch (_) {
        return 0;
      }
    }

    function measureTextWidth(text, font) {
      if (window.OfflineGISUtils && typeof window.OfflineGISUtils.measureTextWidth === "function") {
        return window.OfflineGISUtils.measureTextWidth(text, font);
      }
      if (!measureTextWidth._canvas) {
        measureTextWidth._canvas = document.createElement("canvas");
      }
      const context = measureTextWidth._canvas.getContext("2d");
      context.font = font || "14px sans-serif";
      return context.measureText(text || "").width;
    }

    function setSearchCursorEnabled(value) {
      deps.setSearchCursorEnabled(value);
    }

    function updateComparatorPolygons(value) {
      deps.updateComparatorPolygons(value);
    }

    function updateAoiPanel(points) {
      const bridge = getBridge();
      if (!Array.isArray(points) || points.length < 3) {
        if (bridge && bridge.on_aoi_stats_updated) {
          bridge.on_aoi_stats_updated(0, "0 m\u00b2");
        }
        return;
      }
      const area = geometry.computePolygonAreaSquareMeters
        ? geometry.computePolygonAreaSquareMeters(points)
        : 0;
      const areaText = geometry.formatArea ? geometry.formatArea(area) : "0 m\u00b2";
      if (bridge && bridge.on_aoi_stats_updated) {
        bridge.on_aoi_stats_updated(points.length, areaText);
      }
    }

    function toggleAoiPanelMinimize() {
      setAoiPanelMinimized(!getAoiPanelMinimized());
    }

    function updatePolygonDropdownUI() {
      const bridge = getBridge();
      if (bridge && bridge.on_polygon_list_updated) {
        const payload = getDrawnPolygons().map(function (poly) {
          return {
            id: poly.id,
            label: poly.label,
            points_count: poly.points.length,
            visible: poly.visible,
          };
        });
        bridge.on_polygon_list_updated(JSON.stringify(payload));
      }
    }

    var activeAoiEntity = null;

    function ensureSearchPreviewEntities() {
      const viewer = getViewer();
      const cesium = getCesium();
      if (!viewer || !cesium) return;

      function isPolygonDrawPreviewActive() {
        return getSearchDrawMode() === "polygon";
      }

      if (!getSearchPreviewLineEntity()) {
        setSearchPreviewLineEntity(
          viewer.entities.add({
            polyline: {
              positions: new cesium.CallbackProperty(function () {
                const points = getSearchPolygonPoints();
                const cursor = getSearchCursorPoint();
                const raw = geometry.getSearchPreviewPoints(points, cursor, true);
                if (raw.length < 2) return [];
                const res = raw.map(function (p) {
                  try {
                    const h = getGroundHeightAtLonLat(p.lon, p.lat);
                    return cesium.Cartesian3.fromDegrees(p.lon, p.lat, h + 0.1);
                  } catch (e) { return null; }
                }).filter(function(v) { return !!v; });
                if (!cursor && res.length >= 3) res.push(res[0]);
                return res;
              }, false),
              material: cesium.Color.YELLOW,
              depthFailMaterial: cesium.Color.YELLOW,
              width: 4,
              clampToGround: false,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              show: new cesium.CallbackProperty(function () {
                return isPolygonDrawPreviewActive() && getSearchPolygonPoints().length >= 1;
              }, false),
            },
          })
        );
      }

      if (!getSearchPreviewPolygonEntity()) {
        setSearchPreviewPolygonEntity(
          viewer.entities.add({
            polygon: {
              hierarchy: new cesium.CallbackProperty(function () {
                const points = getSearchPolygonPoints();
                const cursor = getSearchCursorPoint();
                const raw = geometry.getSearchPreviewPoints(points, cursor, true);
                if (raw.length < 3) return null;
                const res = raw.map(function (p) {
                  try {
                    return cesium.Cartesian3.fromDegrees(p.lon, p.lat, 0.0);
                  } catch (e) { return null; }
                }).filter(function(v) { return !!v; });
                return res.length >= 3 ? new cesium.PolygonHierarchy(res) : null;
              }, false),
              material: cesium.Color.YELLOW.withAlpha(0.22),
              fill: true,
              outline: false,
              classificationType: cesium.ClassificationType.BOTH,
              perPositionHeight: false,
              show: new cesium.CallbackProperty(function () {
                return isPolygonDrawPreviewActive() && getSearchPolygonPoints().length >= 2 && getSearchOverlayVisible() && !getIsAnnotationDrawing();
              }, false),
            },
          })
        );
      }

      if (!deps.getSearchCursorEntity()) {
        deps.setSearchCursorEntity(
          viewer.entities.add({
            position: new cesium.CallbackProperty(function () {
              const cursorPoint = getSearchCursorPoint();
              if (!cursorPoint) {
                return cesium.Cartesian3.fromDegrees(0, 0);
              }
              return cesium.Cartesian3.fromDegrees(cursorPoint.lon, cursorPoint.lat);
            }, false),
            point: {
              pixelSize: 8,
              color: cesium.Color.YELLOW,
              outlineColor: cesium.Color.BLACK.withAlpha(0.7),
              outlineWidth: 1,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
            },
            show: false, // Reverted to false to avoid showing dots
          })
        );
      }

      if (!getSearchAreaLabelEntity()) {
        setSearchAreaLabelEntity(
          viewer.entities.add({
            position: new cesium.CallbackProperty(function () {
                const points = geometry.getSearchPreviewPoints(
                getSearchPolygonPoints(),
                getSearchCursorPoint(),
                true
              );
              if (points.length < 3) {
                return cesium.Cartesian3.fromDegrees(0, 0);
              }
              const center = geometry.polygonLabelPosition(points);
              return center ? cesium.Cartesian3.fromDegrees(center.lon, center.lat) : cesium.Cartesian3.fromDegrees(0, 0);
            }, false),
            label: {
              text: new cesium.CallbackProperty(function () {
                const points = geometry.getSearchPreviewPoints(
                  getSearchPolygonPoints(),
                  getSearchCursorPoint(),
                  true
                );
                if (points.length < 3) {
                  return "";
                }
                const areaSquareMeters = geometry.computePolygonAreaSquareMeters(points);
                if (!Number.isFinite(areaSquareMeters) || areaSquareMeters <= 0) {
                  return "";
                }
                return "Area: " + geometry.formatArea(areaSquareMeters);
              }, false),
              font: "12px 'Segoe UI', sans-serif",
              fillColor: cesium.Color.WHITE,
              showBackground: true,
              backgroundColor: cesium.Color.BLACK.withAlpha(0.85),
              backgroundPadding: new cesium.Cartesian2(6, 3),
              style: cesium.LabelStyle.FILL,
              horizontalOrigin: cesium.HorizontalOrigin.CENTER,
              verticalOrigin: cesium.VerticalOrigin.CENTER,
              pixelOffset: new cesium.Cartesian2(0, 0),
              heightReference: cesium.HeightReference.CLAMP_TO_GROUND,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              scale: 0.75,
              show: new cesium.CallbackProperty(function () {
                const points = geometry.getSearchPreviewPoints(getSearchPolygonPoints(), getSearchCursorPoint(), true);
                return isPolygonDrawPreviewActive() && points.length >= 3;
              }, false),
            },
          })
        );
      }
    }

    function syncSearchVertexEntities() {
      // User strictly requested no vertex points/yellow dots.
      const searchVertexEntities = getSearchVertexEntities();
      while (searchVertexEntities.length > 0) {
        const ve = searchVertexEntities.pop();
        if (ve) {
          try { getViewer().entities.remove(ve); } catch(e) {}
        }
      }
    }

    function updateSearchPolygonPreview() {
      debugLog(
        "updateSearchPolygonPreview drawMode=" + getSearchDrawMode() + " points=" + getSearchPolygonPoints().length + " cursorPoint=" + (getSearchCursorPoint() ? "yes" : "no") + " locked=" + Boolean(getSearchPolygonLocked()) + " annotation=" + Boolean(getIsAnnotationDrawing())
      );
      ensureSearchPreviewEntities();
      syncSearchVertexEntities();
      requestSceneRender();
    }

    function toggleDrawnPolygonVisibility(polyId, visible) {
      const drawnPolygons = getDrawnPolygons();
      for (const poly of drawnPolygons) {
        if (poly.id !== polyId) {
          continue;
        }
        poly.visible = Boolean(visible);
        const overlayVisible = poly._isAnnotationPoly
          ? (deps.getAnnotationVisibilityEnabled ? deps.getAnnotationVisibilityEnabled() : true)
          : deps.getSearchOverlayVisible();
        const shouldShow = poly.visible && overlayVisible;
        if (poly.lineEntity) poly.lineEntity.show = shouldShow;
        if (poly.polygonEntity) poly.polygonEntity.show = shouldShow;
        if (poly.areaLabelEntity) poly.areaLabelEntity.show = shouldShow;
        if (poly.nameLabelEntity) poly.nameLabelEntity.show = shouldShow;
        if (poly.editEntity) poly.editEntity.show = shouldShow;
        if (poly.deleteEntity) poly.deleteEntity.show = shouldShow;
      }
      requestSceneRender();
    }

    function toggleAllDrawnPolygonsVisibility(visible) {
      // NOTE: Only toggles AOI/search polygons — NOT user annotation polygons.
      // User annotation polygons (drawnPolygons with _isAnnotationPoly=true) remain always visible.
      const drawnPolygons = getDrawnPolygons();
      const isVisible = Boolean(visible);
      for (const poly of drawnPolygons) {
        if (poly._isAnnotationPoly) continue; // Never hide user-drawn annotation polygons
        poly.visible = isVisible;
        const shouldShowAll = isVisible && getSearchOverlayVisible();
        if (poly.lineEntity) poly.lineEntity.show = shouldShowAll;
        if (poly.polygonEntity) poly.polygonEntity.show = shouldShowAll;
        if (poly.areaLabelEntity) poly.areaLabelEntity.show = shouldShowAll;
      }
      requestSceneRender();
    }

    function updateComparatorPolygons(visible) {
      const cesium = getCesium();
      const leftViewer = getComparatorLeftViewer();
      const rightViewer = getComparatorRightViewer();
      if (!getComparatorModeEnabled() || !leftViewer || !rightViewer) {
        return;
      }
      if (deps.getComparatorPolygonEntities) {
        const comparatorPolygonEntities = deps.getComparatorPolygonEntities();
        for (const ent of comparatorPolygonEntities.left) {
          leftViewer.entities.remove(ent);
        }
        for (const ent of comparatorPolygonEntities.right) {
          rightViewer.entities.remove(ent);
        }
        comparatorPolygonEntities.left = [];
        comparatorPolygonEntities.right = [];

        if (!visible) {
          return;
        }

        const addPolyToViewers = function (pts, color, isDrawn) {
          if (!pts || pts.length < 3) {
            return;
          }
          const degreesArray = pts.reduce(function (acc, point) {
            acc.push(point.lon, point.lat);
            return acc;
          }, []);
          const positions = cesium.Cartesian3.fromDegreesArray(degreesArray);
          const polylinePositions = cesium.Cartesian3.fromDegreesArray(
            degreesArray.concat([pts[0].lon, pts[0].lat])
          );
          const polylineDesc = {
            positions: polylinePositions,
            width: isDrawn ? 3.0 : 2.0,
            material: color,
            clampToGround: true,
          };
          const polygonDesc = {
            hierarchy: new cesium.PolygonHierarchy(positions),
            material: color.withAlpha(0.2),
          };
          comparatorPolygonEntities.left.push(
            leftViewer.entities.add({ polyline: polylineDesc, polygon: polygonDesc })
          );
          comparatorPolygonEntities.right.push(
            rightViewer.entities.add({ polyline: polylineDesc, polygon: polygonDesc })
          );
        };

        for (const poly of drawnPolygons) {
          addPolyToViewers(poly.points, cesium.Color.YELLOW, true);
        }
        const searchPolygonPoints = getSearchPolygonPoints();
        if (searchPolygonPoints && searchPolygonPoints.length >= 3) {
          addPolyToViewers(searchPolygonPoints, cesium.Color.CYAN, false);
        }
      }
    }

    // Unique color palette for polygons
    var POLYGON_COLORS = [
      "#31d18d", "#4a90d9", "#e67e22", "#9b59b6",
      "#e74c3c", "#1abc9c", "#f39c12", "#2ecc71",
    ];
    var EDIT_ICON = "data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%2720%27 height=%2720%27 viewBox=%270 0 20 20%27%3E%3Ccircle cx=%2710%27 cy=%2710%27 r=%279%27 fill=%27rgba(255%2C255%2C255%2C0.92)%27 stroke=%27rgba(0%2C0%2C0%2C0.38)%27 stroke-width=%271.1%27/%3E%3Cpath d=%27M6.1 12.9l.5-2.2L11.8 5.5a1.3 1.3 0 011.8 0l.8.8a1.3 1.3 0 010 1.8L9.1 13.3l-2.2.5a.6.6 0 01-.8-.7z%27 fill=%27%23282f39%27/%3E%3Cpath d=%27M10.9 6.4l2.7 2.7%27 stroke=%27%23ffffff%27 stroke-width=%271%27 stroke-linecap=%27round%27/%3E%3C/svg%3E";
    var DELETE_ICON = "data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%2720%27 height=%2720%27 viewBox=%270 0 20 20%27%3E%3Ccircle cx=%2710%27 cy=%2710%27 r=%279%27 fill=%27rgba(220%2C50%2C50%2C0.92)%27 stroke=%27rgba(0%2C0%2C0%2C0.38)%27 stroke-width=%271.1%27/%3E%3Cpath d=%27M6 6L14 14M14 6L6 14%27 stroke=%27%23ffffff%27 stroke-width=%272%27 stroke-linecap=%27round%27/%3E%3C/svg%3E";

    function finalizeSearchPolygon() {
      var cesium = getCesium();
      var viewer = getViewer();
      var searchPolygonPoints = getSearchPolygonPoints();
      if (!cesium || !viewer || searchPolygonPoints.length < 3) {
        return;
      }
      setSearchCursorPoint(null);
      var frozenPoints = searchPolygonPoints.slice();
      
      // Emit to Python
      emitSearchGeometry("polygon", { points: frozenPoints });

      var isAnnotation = getIsAnnotationDrawing();
      if (!isAnnotation) {
        if (window.offlineGIS && typeof window.offlineGIS.clearSearchResultMarkers === "function") {
          window.offlineGIS.clearSearchResultMarkers();
        }
      }
      
      if (isAnnotation) {
        // --- PERSISTENT ANNOTATION POLYGON (with icons) ---
        deps.incrementDrawnPolygonCounter();
        var polyId = deps.getDrawnPolygonCounter();
        var colorHex = POLYGON_COLORS[(polyId - 1) % POLYGON_COLORS.length];
        var polyColor = cesium.Color.fromCssColorString(colorHex);

      // --- Create STATIC entities ---
        var points3d = frozenPoints.map(function (p) {
          try {
            return p.cartesian ? cesium.Cartesian3.clone(p.cartesian) : cesium.Cartesian3.fromDegrees(p.lon, p.lat);
          } catch (e) { return null; }
        }).filter(function(v) { return !!v; });

        var points3dH = frozenPoints.map(function (p) {
          try {
            var h = getGroundHeightAtLonLat(p.lon, p.lat);
            return cesium.Cartesian3.fromDegrees(p.lon, p.lat, h + 0.1);
          } catch (e) { return null; }
        }).filter(function(v) { return !!v; });

        if (points3d.length < 3) return;

        var lineEntity = viewer.entities.add({
          polyline: {
            positions: points3dH.concat([points3dH[0]]),
            width: 4.5, // Strong hard sides
            material: polyColor,
            depthFailMaterial: polyColor,
            clampToGround: false,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });

        var polygonEntity = viewer.entities.add({
          polygon: {
            hierarchy: new cesium.PolygonHierarchy(points3d),
            material: polyColor.withAlpha(0.1), // Very faint fill if any
            fill: false, // User requested no fill strictly for annotations
            outline: false, // Polyline handles outline
            perPositionHeight: true,
          },
        });

        var vertexEntities = []; // No longer adding vertex points per user request

      // Area label at centroid
        var center = geometry.polygonLabelPosition(frozenPoints);
        var areaM2 = geometry.computePolygonAreaSquareMeters ? geometry.computePolygonAreaSquareMeters(frozenPoints) : 0;
        var areaText = areaM2 > 0 ? "Area " + (geometry.formatArea ? geometry.formatArea(areaM2) : areaM2.toFixed(0) + " m\u00b2") : "";
        var areaLabelEntity = null;
        if (center) {
          areaLabelEntity = viewer.entities.add({
            position: cesium.Cartesian3.fromDegrees(center.lon, center.lat, getGroundHeightAtLonLat(center.lon, center.lat)),
            label: {
              text: areaText,
              font: "13px 'Segoe UI', sans-serif",
              fillColor: cesium.Color.WHITE,
              showBackground: true,
              backgroundColor: cesium.Color.BLACK.withAlpha(0.82),
              heightReference: cesium.HeightReference.CLAMP_TO_GROUND,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              scaleByDistance: new cesium.NearFarScalar(2500.0, 0.8, 1700000.0, 0.4),
            },
          });
        }

        var anchorPos = points3d[0];
        const nameText = "Polygon " + polyId;
        
        var getScaleFactor = function() {
          if (!viewer || !anchorPos) return 1.0;
          var distance = cesium.Cartesian3.distance(viewer.camera.position, anchorPos);
          if (distance <= 2500.0) {
            return 1.0;
          } else if (distance >= 1700000.0) {
            return 0.5;
          } else {
            var t = (distance - 2500.0) / (1700000.0 - 2500.0);
            return 1.0 + t * (0.5 - 1.0);
          }
        };

        var nameLabelEntity = viewer.entities.add({
          position: anchorPos,
          label: {
            text: nameText,
            fillColor: cesium.Color.WHITE,
            showBackground: true,
            backgroundColor: cesium.Color.BLACK.withAlpha(0.62),
            backgroundPadding: new cesium.Cartesian2(10, 6),
            font: "500 12px Arial, Helvetica, sans-serif",
            pixelOffset: new cesium.CallbackProperty(function() {
              var s = getScaleFactor();
              return new cesium.Cartesian2(12 * s, -8 * s);
            }, false),
            horizontalOrigin: cesium.HorizontalOrigin.LEFT,
            verticalOrigin: cesium.VerticalOrigin.BOTTOM,
            heightReference: cesium.HeightReference.CLAMP_TO_GROUND,
            scaleByDistance: new cesium.NearFarScalar(2500.0, 1.0, 1700000.0, 0.5),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });
        nameLabelEntity._polyRecordId = polyId;
        nameLabelEntity._polyRole = "label";

      const nameWidth = measureTextWidth(nameText, "500 12px Arial, Helvetica, sans-serif");

      var editEntity = viewer.entities.add({
        position: anchorPos,
        billboard: {
          image: EDIT_ICON,
          width: 17, height: 17,
          color: cesium.Color.WHITE.withAlpha(0.42),
          pixelOffset: new cesium.CallbackProperty(function() {
            var s = getScaleFactor();
            return new cesium.Cartesian2((52 + nameWidth) * s, -14 * s);
          }, false),
          horizontalOrigin: cesium.HorizontalOrigin.CENTER,
          verticalOrigin: cesium.VerticalOrigin.CENTER,
          scaleByDistance: new cesium.NearFarScalar(2500.0, 1.0, 1700000.0, 0.5),
          heightReference: cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      editEntity._polyRecordId = polyId;
      editEntity._polyRole = "edit";

      var deleteEntity = viewer.entities.add({
        position: anchorPos,
        billboard: {
          image: DELETE_ICON,
          width: 17, height: 17,
          color: cesium.Color.WHITE.withAlpha(0.62),
          pixelOffset: new cesium.CallbackProperty(function() {
            var s = getScaleFactor();
            return new cesium.Cartesian2((72 + nameWidth) * s, -14 * s);
          }, false),
          horizontalOrigin: cesium.HorizontalOrigin.CENTER,
          verticalOrigin: cesium.VerticalOrigin.CENTER,
          scaleByDistance: new cesium.NearFarScalar(2500.0, 1.0, 1700000.0, 0.5),
          heightReference: cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });

      deleteEntity._polyRecordId = polyId;
      deleteEntity._polyRole = "delete";

      nameLabelEntity._editEntity = editEntity;
      nameLabelEntity._deleteEntity = deleteEntity;
      var showState = deps.getAnnotationVisibilityEnabled ? deps.getAnnotationVisibilityEnabled() : true;
      lineEntity.show = showState;
      polygonEntity.show = showState;
      if (areaLabelEntity) areaLabelEntity.show = showState;
      nameLabelEntity.show = showState;
      editEntity.show = showState;
      deleteEntity.show = showState;

      var polyRecord = {
        id: polyId,
        label: "Annotation " + polyId,
        points: frozenPoints,
        lineEntity: lineEntity,
        polygonEntity: polygonEntity,
        areaLabelEntity: areaLabelEntity,
        vertexEntities: vertexEntities,
        nameLabelEntity: nameLabelEntity,
        editEntity: editEntity,
        deleteEntity: deleteEntity,
        visible: true,
        _isAnnotationPoly: true,
      };
      var polys = getDrawnPolygons();
      polys.push(polyRecord);
      if (typeof window.syncAnnotationsToPython === "function") {
        window.syncAnnotationsToPython();
      }
      } else {
        // --- AOI SEARCH MODE ---
        if (activeAoiEntity) {
          try { viewer.entities.remove(activeAoiEntity); } catch(e) {}
        }
        var aoiPoints = frozenPoints.map(function (p) {
          try {
            return cesium.Cartesian3.fromDegrees(p.lon, p.lat, 10.0);
          } catch (e) { return null; }
        }).filter(function(v) { return !!v; });
        
        if (aoiPoints.length >= 3) {
          var flatAoiPoints = frozenPoints.map(function (p) {
            try {
              return cesium.Cartesian3.fromDegrees(p.lon, p.lat, 0.0);
            } catch (e) { return null; }
          }).filter(function (v) { return !!v; });

          var aoiPoints3d = frozenPoints.map(function (p) {
            try {
              var h = getGroundHeightAtLonLat(p.lon, p.lat);
              return cesium.Cartesian3.fromDegrees(p.lon, p.lat, h + 0.1);
            } catch (e) { return null; }
          }).filter(function (v) { return !!v; });

          // Compute area for label
          var areaSqM = geometry.computePolygonAreaSquareMeters ? geometry.computePolygonAreaSquareMeters(frozenPoints) : 0;
          var areaText = geometry.formatArea ? geometry.formatArea(areaSqM) : "0 m\u00b2";
          var labelPos = geometry.polygonLabelPosition ? geometry.polygonLabelPosition(frozenPoints) : null;
          var labelPosCartesian = labelPos
            ? cesium.Cartesian3.fromDegrees(labelPos.lon, labelPos.lat, 0.0)
            : flatAoiPoints[0];
          var aoiLabelText = "AOI" + (areaText ? "\n" + areaText : "");

          // Strict visibility: never create AOI entities unless overlay visible
          if (!deps.getSearchOverlayVisible()) {
            // still register & update panel but do not create globe entities
            updateAoiPanel(frozenPoints);
            deps.setStatus("Search AOI defined (hidden)");
          } else {
          activeAoiEntity = viewer.entities.add({
            position: labelPosCartesian,
            polyline: {
              positions: aoiPoints3d.concat([aoiPoints3d[0]]),
              width: 4.0,
              material: cesium.Color.CYAN,
              clampToGround: false,
              depthFailMaterial: cesium.Color.CYAN,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              show: new cesium.CallbackProperty(function() {
                return deps.getSearchOverlayVisible();
              }, false)
            },
            polygon: {
              hierarchy: new cesium.PolygonHierarchy(flatAoiPoints),
              material: cesium.Color.CYAN.withAlpha(0.22),
              fill: true,
              outline: false,
              classificationType: cesium.ClassificationType.BOTH,
              perPositionHeight: false,
              show: new cesium.CallbackProperty(function() {
                return deps.getSearchOverlayVisible();
              }, false)
            },
            label: {
              text: aoiLabelText,
              font: "bold 14px sans-serif",
              fillColor: cesium.Color.WHITE,
              outlineColor: cesium.Color.BLACK,
              outlineWidth: 3,
              style: cesium.LabelStyle.FILL_AND_OUTLINE,
              showBackground: true,
              backgroundColor: cesium.Color.BLACK.withAlpha(0.62),
              heightReference: cesium.HeightReference.CLAMP_TO_GROUND,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              show: new cesium.CallbackProperty(function() {
                return deps.getSearchOverlayVisible();
              }, false),
            }
          });
          }
        }
        
        // Register with backend for search
        if (geometry.emitSearchGeometry) {
          geometry.emitSearchGeometry("polygon", { points: frozenPoints });
        }
        
        updateAoiPanel(frozenPoints);
        deps.setStatus("Search AOI defined.");
        setSearchPolygonLocked(true);
      }

      // --- CLEANUP ---
      var previewLine = getSearchPreviewLineEntity();
      if (previewLine) { try { viewer.entities.remove(previewLine); } catch(e) {} setSearchPreviewLineEntity(null); }
      var previewPoly = getSearchPreviewPolygonEntity();
      if (previewPoly) { try { viewer.entities.remove(previewPoly); } catch(e) {} setSearchPreviewPolygonEntity(null); }
      var previewLabel = getSearchAreaLabelEntity();
      if (previewLabel) { try { viewer.entities.remove(previewLabel); } catch(e) {} setSearchAreaLabelEntity(null); }
      
      // Reset vertex entities used during drawing
      while (getSearchVertexEntities().length > 0) {
        var oldVe = getSearchVertexEntities().pop();
        if (oldVe) { try { viewer.entities.remove(oldVe); } catch(e) {} }
      }

      searchPolygonPoints.length = 0;
      setSearchCursorPoint(null);
      updateSearchPolygonPreview();
      deps.requestSceneRender();
    }

    function restoreAnnotationPolygon(points, id, label) {
      var cesium = getCesium();
      var viewer = getViewer();
      if (!cesium || !viewer || !points || points.length < 3) return;

      deps.incrementDrawnPolygonCounter();
      var polyId = deps.getDrawnPolygonCounter();
      var colorHex = POLYGON_COLORS[(polyId - 1) % POLYGON_COLORS.length];
      var polyColor = cesium.Color.fromCssColorString(colorHex);

      var normalizedPoints = [];
      var points3d = [];
      var EPS = 1e-8;
      var lastLon = null;
      var lastLat = null;
      for (var i = 0; i < points.length; i++) {
        var p = points[i];
        var lon = null;
        var lat = null;
        try {
          if (Array.isArray(p) && p.length >= 2) {
            lon = Number(p[0]);
            lat = Number(p[1]);
          } else if (p && typeof p === "object") {
            if (p.cartesian) {
              var carto = cesium.Cartographic.fromCartesian(p.cartesian);
              lon = cesium.Math.toDegrees(carto.longitude);
              lat = cesium.Math.toDegrees(carto.latitude);
            } else {
              lon = Number(p.lon);
              lat = Number(p.lat);
            }
          }

          if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
          if (lon < -180 || lon > 180 || lat < -90 || lat > 90) continue;
          if (
            Number.isFinite(lastLon) &&
            Number.isFinite(lastLat) &&
            Math.abs(lon - lastLon) <= EPS &&
            Math.abs(lat - lastLat) <= EPS
          ) {
            continue;
          }

          normalizedPoints.push({ lon: lon, lat: lat });
          points3d.push(cesium.Cartesian3.fromDegrees(lon, lat, getGroundHeightAtLonLat(lon, lat)));
          lastLon = lon;
          lastLat = lat;
        } catch (e) {
          continue;
        }
      }

      if (points3d.length < 3) return;

      var points3dH = normalizedPoints.map(function (p) {
        try {
          var h = getGroundHeightAtLonLat(p.lon, p.lat);
          return cesium.Cartesian3.fromDegrees(p.lon, p.lat, h + 0.1);
        } catch (e) { return null; }
      }).filter(function(v) { return !!v; });

      var lineEntity = viewer.entities.add({
        polyline: {
          positions: points3dH.concat([points3dH[0]]),
          width: 4.5,
          arcType: cesium.ArcType.GEODESIC,
          material: polyColor,
          depthFailMaterial: polyColor,
          clampToGround: false,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });

      var polygonEntity = viewer.entities.add({
        polygon: {
          hierarchy: new cesium.PolygonHierarchy(points3d),
          material: polyColor.withAlpha(0.1),
          fill: false,
          outline: false,
          perPositionHeight: true,
        },
      });

      var vertexEntities = [];

      var center = geometry.polygonLabelPosition(normalizedPoints);
      var areaM2 = geometry.computePolygonAreaSquareMeters ? geometry.computePolygonAreaSquareMeters(normalizedPoints) : 0;
      var areaText = areaM2 > 0 ? "Area " + (geometry.formatArea ? geometry.formatArea(areaM2) : areaM2.toFixed(0) + " m\u00b2") : "";
      var areaLabelEntity = null;
      if (center) {
        areaLabelEntity = viewer.entities.add({
          position: cesium.Cartesian3.fromDegrees(center.lon, center.lat, getGroundHeightAtLonLat(center.lon, center.lat)),
          label: {
            text: areaText,
            font: "13px 'Segoe UI', sans-serif",
            fillColor: cesium.Color.WHITE,
            showBackground: true,
            backgroundColor: cesium.Color.BLACK.withAlpha(0.82),
            heightReference: cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            scale: 0.8,
          },
        });
      }

      var anchorPos = points3d[0];
      var textLabel = label;
      if (!textLabel || textLabel.toLowerCase().indexOf("annotation") === 0) {
        textLabel = "Polygon " + polyId;
      }
      var getScaleFactor = function() {
        if (!viewer || !anchorPos) return 1.0;
        var distance = cesium.Cartesian3.distance(viewer.camera.position, anchorPos);
        if (distance <= 2500.0) {
          return 1.0;
        } else if (distance >= 1700000.0) {
          return 0.5;
        } else {
          var t = (distance - 2500.0) / (1700000.0 - 2500.0);
          return 1.0 + t * (0.5 - 1.0);
        }
      };

      var nameLabelEntity = viewer.entities.add({
        position: anchorPos,
        label: {
          text: textLabel,
          fillColor: cesium.Color.WHITE,
          showBackground: true,
          backgroundColor: cesium.Color.BLACK.withAlpha(0.62),
          backgroundPadding: new cesium.Cartesian2(10, 6),
          font: "500 12px Arial, Helvetica, sans-serif",
          pixelOffset: new cesium.CallbackProperty(function() {
            var s = getScaleFactor();
            return new cesium.Cartesian2(12 * s, -8 * s);
          }, false),
          horizontalOrigin: cesium.HorizontalOrigin.LEFT,
          verticalOrigin: cesium.VerticalOrigin.BOTTOM,
          heightReference: cesium.HeightReference.CLAMP_TO_GROUND,
          scaleByDistance: new cesium.NearFarScalar(2500.0, 1.0, 1700000.0, 0.5),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      nameLabelEntity._polyRecordId = polyId;
      nameLabelEntity._polyRole = "label";

      const restoredNameWidth = measureTextWidth(textLabel, "500 12px Arial, Helvetica, sans-serif");

      var editEntity = viewer.entities.add({
        position: anchorPos,
        billboard: {
          image: EDIT_ICON,
          width: 17, height: 17,
          color: cesium.Color.WHITE.withAlpha(0.42),
          pixelOffset: new cesium.CallbackProperty(function() {
            var s = getScaleFactor();
            return new cesium.Cartesian2((52 + restoredNameWidth) * s, -14 * s);
          }, false),
          horizontalOrigin: cesium.HorizontalOrigin.CENTER,
          verticalOrigin: cesium.VerticalOrigin.CENTER,
          scaleByDistance: new cesium.NearFarScalar(2500.0, 1.0, 1700000.0, 0.5),
          heightReference: cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      editEntity._polyRecordId = polyId;
      editEntity._polyRole = "edit";

      var deleteEntity = viewer.entities.add({
        position: anchorPos,
        billboard: {
          image: DELETE_ICON,
          width: 17, height: 17,
          color: cesium.Color.WHITE.withAlpha(0.62),
          pixelOffset: new cesium.CallbackProperty(function() {
            var s = getScaleFactor();
            return new cesium.Cartesian2((72 + restoredNameWidth) * s, -14 * s);
          }, false),
          horizontalOrigin: cesium.HorizontalOrigin.CENTER,
          verticalOrigin: cesium.VerticalOrigin.CENTER,
          scaleByDistance: new cesium.NearFarScalar(2500.0, 1.0, 1700000.0, 0.5),
          heightReference: cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });

      nameLabelEntity._editEntity = editEntity;
      nameLabelEntity._deleteEntity = deleteEntity;

      deleteEntity._polyRecordId = polyId;
      deleteEntity._polyRole = "delete";

      var showState = deps.getAnnotationVisibilityEnabled ? deps.getAnnotationVisibilityEnabled() : true;
      lineEntity.show = showState;
      polygonEntity.show = showState;
      if (areaLabelEntity) areaLabelEntity.show = showState;
      nameLabelEntity.show = showState;
      editEntity.show = showState;
      deleteEntity.show = showState;

      var polyRecord = {
        id: polyId,
        label: textLabel,
        points: normalizedPoints,
        lineEntity: lineEntity,
        polygonEntity: polygonEntity,
        areaLabelEntity: areaLabelEntity,
        vertexEntities: vertexEntities,
        nameLabelEntity: nameLabelEntity,
        editEntity: editEntity,
        deleteEntity: deleteEntity,
        visible: true,
        _isAnnotationPoly: true,
      };
      var polys = getDrawnPolygons();
      polys.push(polyRecord);
      updatePolygonDropdownUI();
      deps.requestSceneRender();
    }

    function clearSearchAoi() {
      var viewer = getViewer();
      if (!viewer) return;
      if (activeAoiEntity) {
        try { viewer.entities.remove(activeAoiEntity); } catch(e) {}
        activeAoiEntity = null;
      }
      updateAoiPanel([]);
      deps.requestSceneRender();
    }

    function clearAllData() {
      var viewer = getViewer();
      if (!viewer) return;
      if (activeAoiEntity) {
        try { viewer.entities.remove(activeAoiEntity); } catch(e) {}
        activeAoiEntity = null;
      }
      var polys = getDrawnPolygons();
      while (polys.length > 0) {
        var poly = polys.pop();
        if (poly.lineEntity) { try { viewer.entities.remove(poly.lineEntity); } catch(e) {} }
        if (poly.polygonEntity) { try { viewer.entities.remove(poly.polygonEntity); } catch(e) {} }
        if (poly.areaLabelEntity) { try { viewer.entities.remove(poly.areaLabelEntity); } catch(e) {} }
        if (poly.nameLabelEntity) { try { viewer.entities.remove(poly.nameLabelEntity); } catch(e) {} }
        if (poly.editEntity) { try { viewer.entities.remove(poly.editEntity); } catch(e) {} }
        if (poly.deleteEntity) { try { viewer.entities.remove(poly.deleteEntity); } catch(e) {} }
      }
      updateAoiPanel([]);
      updatePolygonDropdownUI();
      deps.requestSceneRender();
    }

    return {
      updateAoiPanel: updateAoiPanel,
      toggleAoiPanelMinimize: toggleAoiPanelMinimize,
      updatePolygonDropdownUI: updatePolygonDropdownUI,
      ensureSearchPreviewEntities: ensureSearchPreviewEntities,
      syncSearchVertexEntities: syncSearchVertexEntities,
      updateSearchPolygonPreview: updateSearchPolygonPreview,
      finalizeSearchPolygon: finalizeSearchPolygon,
      restoreAnnotationPolygon: restoreAnnotationPolygon,
      toggleDrawnPolygonVisibility: toggleDrawnPolygonVisibility,
      toggleAllDrawnPolygonsVisibility: toggleAllDrawnPolygonsVisibility,
      updateComparatorPolygons: updateComparatorPolygons,
      clearSearchAoi: clearSearchAoi,
      clearAllData: clearAllData,
    };
  }

  search.searchPolygonController = {
    createSearchPolygonController: createSearchPolygonController,
  };

  window.OfflineGISSearchPolygonController = search.searchPolygonController;
})();
