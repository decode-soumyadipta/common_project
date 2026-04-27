(function () {
  const root = (window.OfflineGISModules = window.OfflineGISModules || {});
  const tools = (root.visualizationTools = root.visualizationTools || {});

  const DEM_COLOR_MODES = new Set(["gray", "terrain", "slope", "aspect"]);

  function normalizeDemColorMode(value, fallbackMode) {
    const fallback = DEM_COLOR_MODES.has(String(fallbackMode || "").toLowerCase())
      ? String(fallbackMode).toLowerCase()
      : "gray";
    const normalized = String(value || "").toLowerCase();
    return DEM_COLOR_MODES.has(normalized) ? normalized : fallback;
  }

  function clampImagerySettings(brightness, contrast) {
    return {
      brightness: Math.max(0.2, Number(brightness) || 1.0),
      contrast: Math.max(0.1, Number(contrast) || 1.0),
    };
  }

  function clampDemSettings(exaggeration, hillshadeAlpha) {
    return {
      exaggeration: Math.max(0.1, Number(exaggeration) || 1.0),
      hillshadeAlpha: Math.max(0.0, Math.min(1.0, Number(hillshadeAlpha) || 0.0)),
    };
  }

  tools.stylePresets = {
    normalizeDemColorMode: normalizeDemColorMode,
    clampImagerySettings: clampImagerySettings,
    clampDemSettings: clampDemSettings,
  };
})();
