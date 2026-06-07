function applyGlobalCesiumPatches() {
  if (!window.Cesium) return;
  
  // 1. Patch GlobeSurfaceTileProvider to cap level at 28
  // We can hook into Viewer creation.
  const origViewer = Cesium.Viewer;
  Cesium.Viewer = function() {
    const viewer = new origViewer(...arguments);
    if (viewer.scene && viewer.scene.globe && viewer.scene.globe._surface && viewer.scene.globe._surface._tileProvider) {
      const proto = viewer.scene.globe._surface._tileProvider.constructor.prototype;
      if (proto && !proto.__patchedMaxError) {
        const origMaxError = proto.getLevelMaximumGeometricError;
        proto.getLevelMaximumGeometricError = function(level) {
          if (level >= 28) return 0.0;
          return origMaxError.apply(this, arguments);
        };
        proto.__patchedMaxError = true;
        console.log("Patched GlobeSurfaceTileProvider.getLevelMaximumGeometricError to cap at level 28");
      }
    }
    return viewer;
  };
  Cesium.Viewer.prototype = origViewer.prototype;
}
