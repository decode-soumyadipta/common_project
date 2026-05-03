(function () {
  const root = (window.OfflineGISModules = window.OfflineGISModules || {});
  const search = (root.search = root.search || {});
  const geometry = search.geometry || {};

  function createSearchPolygonController(deps) {
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

    function ensureSearchPreviewEntities() {
      const viewer = getViewer();
      const cesium = getCesium();
      if (!viewer) {
        return;
      }

      if (!getSearchPreviewLineEntity()) {
        setSearchPreviewLineEntity(
          viewer.entities.add({
            polyline: {
              positions: new cesium.CallbackProperty(function () {
                const points = geometry.getSearchPreviewPoints(
                  getSearchPolygonPoints(),
                  getSearchCursorPoint()
                );
                if (points.length < 2) {
                  return [];
                }
                const positions = points.map(function (point) {
                  return cesium.Cartesian3.fromDegrees(point.lon, point.lat);
                });
                if (!getSearchCursorPoint() && points.length >= 3) {
                  positions.push(positions[0]);
                }
                return positions;
              }, false),
              width: 2.5,
              material: cesium.Color.CYAN,
              clampToGround: true,
              depthFailMaterial: cesium.Color.CYAN.withAlpha(0.6),
              show: new cesium.CallbackProperty(function () {
                return (
                  getPolygonVisibilityEnabled() &&
                  getSearchOverlayVisible() &&
                  geometry.getSearchPreviewPoints(getSearchPolygonPoints(), getSearchCursorPoint()).length >= 2
                );
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
                const positions = geometry.getSearchPreviewCartesianPoints(
                  getSearchPolygonPoints(),
                  getSearchCursorPoint()
                );
                if (positions.length < 3) {
                  return null;
                }
                return new cesium.PolygonHierarchy(positions);
              }, false),
              material: cesium.Color.CYAN.withAlpha(0.25),
              fill: true,
              outline: true,
              outlineColor: cesium.Color.CYAN,
              outlineWidth: 2,
              perPositionHeight: false,
              height: 0,
              extrudedHeight: 0,
              show: new cesium.CallbackProperty(function () {
                return (
                  getPolygonVisibilityEnabled() &&
                  getSearchOverlayVisible() &&
                  geometry.getSearchPreviewPoints(getSearchPolygonPoints(), getSearchCursorPoint()).length >= 3
                );
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
              heightReference: cesium.HeightReference.CLAMP_TO_GROUND,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
            },
            show: new cesium.CallbackProperty(function () {
              return getPolygonVisibilityEnabled() && getSearchOverlayVisible() && Boolean(getSearchCursorPoint());
            }, false),
          })
        );
      }

      if (!getSearchAreaLabelEntity()) {
        setSearchAreaLabelEntity(
          viewer.entities.add({
            position: new cesium.CallbackProperty(function () {
              const points = geometry.getSearchPreviewPoints(
                getSearchPolygonPoints(),
                getSearchCursorPoint()
              );
              const center = geometry.polygonLabelPosition(points);
              if (!center) {
                return cesium.Cartesian3.fromDegrees(0, 0);
              }
              return cesium.Cartesian3.fromDegrees(center.lon, center.lat);
            }, false),
            label: {
              text: new cesium.CallbackProperty(function () {
                const points = geometry.getSearchPreviewPoints(
                  getSearchPolygonPoints(),
                  getSearchCursorPoint()
                );
                if (points.length < 3) {
                  return "";
                }
                const areaSquareMeters = geometry.computePolygonAreaSquareMeters(points);
                if (!Number.isFinite(areaSquareMeters) || areaSquareMeters <= 0) {
                  return "";
                }
                return "Area " + geometry.formatArea(areaSquareMeters);
              }, false),
              font: "13px 'Segoe UI', sans-serif",
              fillColor: cesium.Color.WHITE,
              showBackground: true,
              backgroundColor: cesium.Color.BLACK.withAlpha(0.82),
              backgroundPadding: new cesium.Cartesian2(8, 4),
              style: cesium.LabelStyle.FILL,
              horizontalOrigin: cesium.HorizontalOrigin.CENTER,
              verticalOrigin: cesium.VerticalOrigin.CENTER,
              pixelOffset: new cesium.Cartesian2(0, 0),
              heightReference: cesium.HeightReference.CLAMP_TO_GROUND,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              scale: 0.8,
              show: new cesium.CallbackProperty(function () {
                return (
                  getPolygonVisibilityEnabled() &&
                  getSearchOverlayVisible() &&
                  geometry.getSearchPreviewPoints(getSearchPolygonPoints(), getSearchCursorPoint()).length >= 3
                );
              }, false),
            },
          })
        );
      }
    }

    function syncSearchVertexEntities() {
      const viewer = getViewer();
      const cesium = getCesium();
      if (!viewer) {
        return;
      }
      const searchPolygonPoints = getSearchPolygonPoints();
      const searchVertexEntities = getSearchVertexEntities();
      while (searchVertexEntities.length > searchPolygonPoints.length) {
        const ve = searchVertexEntities.pop();
        if (ve) {
          viewer.entities.remove(ve);
        }
      }
      for (let i = 0; i < searchPolygonPoints.length; i += 1) {
        const point = searchPolygonPoints[i];
        // Use the original picked Cartesian3 if stored (exact terrain position)
        const pos = point.cartesian
          ? cesium.Cartesian3.clone(point.cartesian)
          : cesium.Cartesian3.fromDegrees(point.lon, point.lat, 0);
        if (i < searchVertexEntities.length) {
          searchVertexEntities[i].position = pos;
          searchVertexEntities[i].show = true;
        } else {
          const ve = viewer.entities.add({
            position: pos,
            point: {
              pixelSize: 9,
              color: cesium.Color.fromCssColorString("#f4c430"),
              outlineColor: cesium.Color.fromCssColorString("#1a1a1a"),
              outlineWidth: 1.5,
              heightReference: point.cartesian
                ? cesium.HeightReference.NONE
                : cesium.HeightReference.CLAMP_TO_GROUND,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
            },
            show: true,
          });
          ve._isAnnotationVertex = true;
          searchVertexEntities.push(ve);
        }
      }
    }

    function updateSearchPolygonPreview() {
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
        if (poly.lineEntity) poly.lineEntity.show = poly.visible;
        if (poly.polygonEntity) poly.polygonEntity.show = poly.visible;
        if (poly.areaLabelEntity) poly.areaLabelEntity.show = poly.visible;
        for (const ve of poly.vertexEntities || []) {
          if (ve) ve.show = poly.visible;
        }
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
        if (poly.lineEntity) poly.lineEntity.show = isVisible;
        if (poly.polygonEntity) poly.polygonEntity.show = isVisible;
        if (poly.areaLabelEntity) poly.areaLabelEntity.show = isVisible;
        for (const ve of poly.vertexEntities || []) {
          if (ve) ve.show = isVisible;
        }
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
            hierarchy: positions,
            material: color.withAlpha(0.2),
            classificationType: cesium.ClassificationType.TERRAIN,
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
      if (searchPolygonPoints.length < 3) {
        deps.log("warn", "Polygon draw requires at least 3 points");
        return;
      }
      setSearchCursorPoint(null);
      var frozenPoints = searchPolygonPoints.slice();
      deps.incrementDrawnPolygonCounter();
      var polyId = deps.getDrawnPolygonCounter();
      var colorHex = POLYGON_COLORS[(polyId - 1) % POLYGON_COLORS.length];
      var polyColor = cesium.Color.fromCssColorString(colorHex);

      // --- Create STATIC entities (not tied to CallbackProperty) ---
      // Polyline (closed)
      var linePositions = frozenPoints.map(function (p) {
        return cesium.Cartesian3.fromDegrees(p.lon, p.lat);
      });
      linePositions.push(linePositions[0]);
      var lineEntity = viewer.entities.add({
        polyline: {
          positions: linePositions,
          width: 2.5,
          material: polyColor,
          clampToGround: true,
          depthFailMaterial: polyColor.withAlpha(0.6),
        },
      });

      // Polygon fill
      var fillPositions = frozenPoints.map(function (p) {
        return cesium.Cartesian3.fromDegrees(p.lon, p.lat);
      });
      var polygonEntity = viewer.entities.add({
        polygon: {
          hierarchy: new cesium.PolygonHierarchy(fillPositions),
          material: polyColor.withAlpha(0.2),
          fill: true,
          outline: false,
          perPositionHeight: false,
          classificationType: cesium.ClassificationType.TERRAIN,
        },
      });

      // Vertex dots
      var vertexEntities = [];
      for (var i = 0; i < frozenPoints.length; i++) {
        var pos = frozenPoints[i].cartesian
          ? cesium.Cartesian3.clone(frozenPoints[i].cartesian)
          : cesium.Cartesian3.fromDegrees(frozenPoints[i].lon, frozenPoints[i].lat, 0);
        var ve = viewer.entities.add({
          position: pos,
          point: {
            pixelSize: 9,
            color: cesium.Color.fromCssColorString("#f4c430"),
            outlineColor: cesium.Color.fromCssColorString("#1a1a1a"),
            outlineWidth: 1.5,
            heightReference: frozenPoints[i].cartesian
              ? cesium.HeightReference.NONE
              : cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
          show: true,
        });
        vertexEntities.push(ve);
      }

      // Area label at centroid
      var center = geometry.polygonLabelPosition(frozenPoints);
      var areaM2 = geometry.computePolygonAreaSquareMeters
        ? geometry.computePolygonAreaSquareMeters(frozenPoints)
        : 0;
      var areaText = areaM2 > 0
        ? "Area " + (geometry.formatArea ? geometry.formatArea(areaM2) : areaM2.toFixed(0) + " m\u00b2")
        : "";
      var areaLabelEntity = null;
      if (center) {
        areaLabelEntity = viewer.entities.add({
          position: cesium.Cartesian3.fromDegrees(center.lon, center.lat),
          label: {
            text: areaText,
            font: "13px 'Segoe UI', sans-serif",
            fillColor: cesium.Color.WHITE,
            showBackground: true,
            backgroundColor: cesium.Color.BLACK.withAlpha(0.82),
            backgroundPadding: new cesium.Cartesian2(8, 4),
            style: cesium.LabelStyle.FILL,
            horizontalOrigin: cesium.HorizontalOrigin.CENTER,
            verticalOrigin: cesium.VerticalOrigin.CENTER,
            heightReference: cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            scale: 0.8,
          },
        });
      }

      // Name label + edit + delete at first vertex
      var anchorPos = vertexEntities.length > 0
        ? vertexEntities[0].position.getValue(cesium.JulianDate.now())
        : cesium.Cartesian3.fromDegrees(frozenPoints[0].lon, frozenPoints[0].lat);
      var polyLabel = "Polygon " + polyId;
      var nameLabelEntity = viewer.entities.add({
        position: anchorPos,
        label: {
          text: polyLabel,
          fillColor: cesium.Color.WHITE,
          showBackground: true,
          backgroundColor: cesium.Color.BLACK.withAlpha(0.62),
          outlineColor: cesium.Color.BLACK.withAlpha(0.9),
          outlineWidth: 2,
          style: cesium.LabelStyle.FILL_AND_OUTLINE,
          font: "500 12px 'Segoe UI', 'Helvetica Neue', sans-serif",
          pixelOffset: new cesium.Cartesian2(12, -8),
          horizontalOrigin: cesium.HorizontalOrigin.LEFT,
          verticalOrigin: cesium.VerticalOrigin.BOTTOM,
          scaleByDistance: new cesium.NearFarScalar(2500.0, 1.0, 1800000.0, 0.45),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      nameLabelEntity._polyRecordId = polyId;
      nameLabelEntity._polyRole = "label";

      var editEntity = viewer.entities.add({
        position: anchorPos,
        billboard: {
          image: EDIT_ICON,
          width: 17, height: 17,
          color: cesium.Color.WHITE.withAlpha(0.42),
          pixelOffset: new cesium.Cartesian2(12, -26),
          horizontalOrigin: cesium.HorizontalOrigin.LEFT,
          verticalOrigin: cesium.VerticalOrigin.BOTTOM,
          scaleByDistance: new cesium.NearFarScalar(2500.0, 1.0, 1700000.0, 0.62),
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
          pixelOffset: new cesium.Cartesian2(32, -26),
          horizontalOrigin: cesium.HorizontalOrigin.LEFT,
          verticalOrigin: cesium.VerticalOrigin.BOTTOM,
          scaleByDistance: new cesium.NearFarScalar(2500.0, 1.0, 1700000.0, 0.62),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      deleteEntity._polyRecordId = polyId;
      deleteEntity._polyRole = "delete";

      var polyRecord = {
        id: polyId,
        label: polyLabel,
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
      var drawnPolygons = getDrawnPolygons();
      drawnPolygons.push(polyRecord);

      // --- Remove dynamic preview entities (they were used during drawing) ---
      var previewLine = getSearchPreviewLineEntity();
      if (previewLine) { viewer.entities.remove(previewLine); }
      setSearchPreviewLineEntity(null);
      var previewPoly = getSearchPreviewPolygonEntity();
      if (previewPoly) { viewer.entities.remove(previewPoly); }
      setSearchPreviewPolygonEntity(null);
      var previewLabel = getSearchAreaLabelEntity();
      if (previewLabel) { viewer.entities.remove(previewLabel); }
      setSearchAreaLabelEntity(null);
      if (deps.getSearchCursorEntity) {
        var cursorEnt = deps.getSearchCursorEntity();
        if (cursorEnt) { viewer.entities.remove(cursorEnt); }
        deps.setSearchCursorEntity(null);
      }
      while (getSearchVertexEntities().length > 0) {
        var oldVe = getSearchVertexEntities().pop();
        if (oldVe) { viewer.entities.remove(oldVe); }
      }

      // Clear shared state for next polygon
      searchPolygonPoints.length = 0;
      setSearchCursorPoint(null);
      setSearchDrawMode("none");
      setSearchPolygonLocked(false);
      setSearchOverlayVisible(true);
      setSearchCursorEnabled(false);

      if (getComparatorModeEnabled()) {
        updateComparatorPolygons(true);
      }

      var polygonPayload = { points: frozenPoints };
      updateAoiPanel(frozenPoints);
      deps.setStatus("Polygon " + polyId + " saved.");
      window.requestAnimationFrame(function () {
        geometry.emitSearchGeometry("polygon", polygonPayload);
      });
      requestSceneRender();
    }

    return {
      updateAoiPanel: updateAoiPanel,
      toggleAoiPanelMinimize: toggleAoiPanelMinimize,
      updatePolygonDropdownUI: updatePolygonDropdownUI,
      ensureSearchPreviewEntities: ensureSearchPreviewEntities,
      syncSearchVertexEntities: syncSearchVertexEntities,
      updateSearchPolygonPreview: updateSearchPolygonPreview,
      finalizeSearchPolygon: finalizeSearchPolygon,
      toggleDrawnPolygonVisibility: toggleDrawnPolygonVisibility,
      toggleAllDrawnPolygonsVisibility: toggleAllDrawnPolygonsVisibility,
      updateComparatorPolygons: updateComparatorPolygons,
    };
  }

  search.searchPolygonController = {
    createSearchPolygonController: createSearchPolygonController,
  };

  window.OfflineGISSearchPolygonController = search.searchPolygonController;
})();
