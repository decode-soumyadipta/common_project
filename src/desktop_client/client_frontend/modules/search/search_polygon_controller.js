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
        if (i < searchVertexEntities.length) {
          searchVertexEntities[i].position = cesium.Cartesian3.fromDegrees(point.lon, point.lat);
          searchVertexEntities[i].show = getPolygonVisibilityEnabled() && getSearchOverlayVisible();
        } else {
          const ve = viewer.entities.add({
            position: cesium.Cartesian3.fromDegrees(point.lon, point.lat),
            point: {
              pixelSize: 9,
              color: cesium.Color.fromCssColorString("#f4c430"),
              outlineColor: cesium.Color.fromCssColorString("#1a1a1a"),
              outlineWidth: 1.5,
              heightReference: cesium.HeightReference.CLAMP_TO_GROUND,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
            },
            show: getPolygonVisibilityEnabled() && getSearchOverlayVisible(),
          });
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
      const drawnPolygons = getDrawnPolygons();
      const isVisible = Boolean(visible);
      for (const poly of drawnPolygons) {
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

    function finalizeSearchPolygon() {
      const cesium = getCesium();
      const searchPolygonPoints = getSearchPolygonPoints();
      if (searchPolygonPoints.length < 3) {
        deps.log("warn", "Polygon draw requires at least 3 points");
        return;
      }
      setSearchCursorPoint(null);
      const searchPreviewLineEntity = getSearchPreviewLineEntity();
      if (searchPreviewLineEntity && searchPreviewLineEntity.polyline) {
        searchPreviewLineEntity.polyline.material = cesium.Color.fromCssColorString("#31d18d");
        searchPreviewLineEntity.polyline.show = true;
        searchPreviewLineEntity.polyline.depthFailMaterial = cesium.Color.fromCssColorString("#31d18d").withAlpha(0.6);
      }
      const searchPreviewPolygonEntity = getSearchPreviewPolygonEntity();
      if (searchPreviewPolygonEntity && searchPreviewPolygonEntity.polygon) {
        searchPreviewPolygonEntity.polygon.material = cesium.Color.fromCssColorString("#31d18d").withAlpha(0.28);
        searchPreviewPolygonEntity.polygon.show = true;
      }
      const searchAreaLabelEntity = getSearchAreaLabelEntity();
      if (searchAreaLabelEntity && searchAreaLabelEntity.label) {
        searchAreaLabelEntity.label.show = true;
      }
      for (const ve of getSearchVertexEntities()) {
        if (ve) {
          ve.show = true;
        }
      }
      updateSearchPolygonPreview();

      deps.incrementDrawnPolygonCounter();
      const polyRecord = {
        id: deps.getDrawnPolygonCounter(),
        label: "Polygon " + deps.getDrawnPolygonCounter(),
        points: searchPolygonPoints.slice(),
        lineEntity: searchPreviewLineEntity,
        polygonEntity: searchPreviewPolygonEntity,
        areaLabelEntity: searchAreaLabelEntity,
        vertexEntities: getSearchVertexEntities().slice(),
        visible: true,
      };
      const drawnPolygons = getDrawnPolygons();
      drawnPolygons.push(polyRecord);

      if (getComparatorModeEnabled()) {
        updateComparatorPolygons(true);
      }

      const polygonPayload = { points: searchPolygonPoints.slice() };
      setSearchDrawMode("none");
      setSearchPolygonLocked(true);
      setSearchOverlayVisible(true);
      setSearchCursorEnabled(false);
      updateAoiPanel(searchPolygonPoints);
      deps.setStatus("Search polygon ready");
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
