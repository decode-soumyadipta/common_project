(function () {
  const root = (window.OfflineGISModules = window.OfflineGISModules || {});
  const tools = (root.visualizationTools = root.visualizationTools || {});

  function demColorModeLabel(colorMode) {
    const normalized = String(colorMode || "gray").toLowerCase();
    if (normalized === "terrain") {
      return "Color relief";
    }
    if (normalized === "slope") {
      return "Slope map (deg)";
    }
    if (normalized === "aspect") {
      return "Aspect map (deg)";
    }
    return "White relief";
  }

  tools.legendAdapter = {
    demColorModeLabel: demColorModeLabel,
  };
})();
