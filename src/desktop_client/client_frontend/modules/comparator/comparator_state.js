(function () {
  const root = (window.OfflineGISModules = window.OfflineGISModules || {});
  const comparator = (root.comparator = root.comparator || {});

  function createPaneVisualState(imageryDefaults, demDefaults) {
    const brightness = Number(imageryDefaults && imageryDefaults.brightness) || 1.0;
    const contrast = Number(imageryDefaults && imageryDefaults.contrast) || 1.0;
    const exaggeration = Number(demDefaults && demDefaults.exaggeration) || 1.0;
    const hillshadeAlpha = Number(demDefaults && demDefaults.hillshadeAlpha) || 0.35;

    return {
      left: {
        imagery: { brightness: brightness, contrast: contrast },
        dem: { exaggeration: exaggeration, hillshadeAlpha: hillshadeAlpha, colorMode: "gray" },
      },
      right: {
        imagery: { brightness: brightness, contrast: contrast },
        dem: { exaggeration: exaggeration, hillshadeAlpha: hillshadeAlpha, colorMode: "gray" },
      },
    };
  }

  function createCameraSyncState() {
    function emptyState() {
      return {
        lastSourceWidthRad: NaN,
        lastSourceHeightRad: NaN,
        lastSourceCameraHeightM: NaN,
        lastSourceCenterLon: NaN,
        lastSourceCenterLat: NaN,
      };
    }

    return {
      left: emptyState(),
      right: emptyState(),
    };
  }

  comparator.comparatorState = {
    createPaneVisualState: createPaneVisualState,
    createCameraSyncState: createCameraSyncState,
  };
})();
