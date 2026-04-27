(function () {
  const root = (window.OfflineGISModules = window.OfflineGISModules || {});
  const search = (root.search = root.search || {});

  function getSearchPreviewPoints(searchPolygonPoints, searchCursorPoint) {
    return searchCursorPoint
      ? searchPolygonPoints.concat([searchCursorPoint])
      : searchPolygonPoints.slice();
  }

  function getSearchPreviewCartesianPoints(searchPolygonPoints, searchCursorPoint) {
    return getSearchPreviewPoints(searchPolygonPoints, searchCursorPoint).map((point) =>
      Cesium.Cartesian3.fromDegrees(point.lon, point.lat)
    );
  }

  function computePolygonAreaSquareMeters(points) {
    if (!Array.isArray(points) || points.length < 3) {
      return 0.0;
    }
    const center = polygonLabelPosition(points);
    if (!center) {
      return 0.0;
    }

    const origin = Cesium.Cartesian3.fromDegrees(center.lon, center.lat, 0.0);
    const enuTransform = Cesium.Transforms.eastNorthUpToFixedFrame(origin);
    const worldToLocal = Cesium.Matrix4.inverseTransformation(enuTransform, new Cesium.Matrix4());

    const localPoints = points.map((point) => {
      const cartesian = Cesium.Cartesian3.fromDegrees(point.lon, point.lat, 0.0);
      const local = Cesium.Matrix4.multiplyByPoint(worldToLocal, cartesian, new Cesium.Cartesian3());
      return { x: local.x, y: local.y };
    });

    let twiceArea = 0.0;
    for (let i = 0; i < localPoints.length; i += 1) {
      const current = localPoints[i];
      const next = localPoints[(i + 1) % localPoints.length];
      twiceArea += current.x * next.y - next.x * current.y;
    }

    return Math.abs(twiceArea) * 0.5;
  }

  function polygonLabelPosition(points) {
    if (!Array.isArray(points) || points.length === 0) {
      return null;
    }
    const positions = points.map((point) => Cesium.Cartesian3.fromDegrees(point.lon, point.lat));
    if (!positions.length) {
      return null;
    }
    const sphere = Cesium.BoundingSphere.fromPoints(positions);
    const cartographic = Cesium.Cartographic.fromCartesian(sphere.center);
    if (!cartographic) {
      return { lon: points[0].lon, lat: points[0].lat };
    }
    return {
      lon: Cesium.Math.toDegrees(cartographic.longitude),
      lat: Cesium.Math.toDegrees(cartographic.latitude),
    };
  }

  function formatArea(squareMeters) {
    if (!Number.isFinite(squareMeters) || squareMeters <= 0) {
      return "0 m\u00b2";
    }
    if (squareMeters >= 1000000) {
      return (squareMeters / 1000000).toFixed(2) + " km\u00b2";
    }
    return Math.round(squareMeters) + " m\u00b2";
  }

  function emitSearchGeometry(type, payload) {
    const bridge = window.OfflineGISRuntime && window.OfflineGISRuntime.bridge;
    if (bridge && bridge.on_search_geometry) {
      bridge.on_search_geometry(type, JSON.stringify(payload));
    }
  }

  search.geometry = {
    getSearchPreviewPoints: getSearchPreviewPoints,
    getSearchPreviewCartesianPoints: getSearchPreviewCartesianPoints,
    computePolygonAreaSquareMeters: computePolygonAreaSquareMeters,
    polygonLabelPosition: polygonLabelPosition,
    formatArea: formatArea,
    emitSearchGeometry: emitSearchGeometry,
  };
})();
