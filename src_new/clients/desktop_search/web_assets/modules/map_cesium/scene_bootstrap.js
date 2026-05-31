(function () {
  const root = (window.OfflineGISModules = window.OfflineGISModules || {});
  const mapCesium = (root.mapCesium = root.mapCesium || {});

  function detectSceneMode(viewer) {
    if (!viewer || !viewer.scene || !window.Cesium) {
      return "3d";
    }
    return viewer.scene.mode === window.Cesium.SceneMode.SCENE2D ? "2d" : "3d";
  }

  function normalizeSceneMode(mode) {
    return String(mode || "3d").toLowerCase() === "2d" ? "2d" : "3d";
  }

  mapCesium.sceneBootstrap = {
    detectSceneMode: detectSceneMode,
    normalizeSceneMode: normalizeSceneMode,
  };
})();
