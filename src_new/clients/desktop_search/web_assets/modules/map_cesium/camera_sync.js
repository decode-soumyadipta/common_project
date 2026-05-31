(function () {
  const root = (window.OfflineGISModules = window.OfflineGISModules || {});
  const mapCesium = (root.mapCesium = root.mapCesium || {});

  function clampPitchRadians(pitch, minPitch, maxPitch, fallbackPitch) {
    if (!Number.isFinite(pitch)) {
      return fallbackPitch;
    }
    return Math.max(minPitch, Math.min(maxPitch, pitch));
  }

  mapCesium.cameraSync = {
    clampPitchRadians: clampPitchRadians,
  };
})();
