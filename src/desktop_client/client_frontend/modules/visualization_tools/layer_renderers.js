(function () {
  const root = (window.OfflineGISModules = window.OfflineGISModules || {});
  const tools = (root.visualizationTools = root.visualizationTools || {});

  function applyImageryVisual(layer, settings) {
    if (!layer || !settings) {
      return;
    }
    if (Number.isFinite(settings.brightness)) {
      layer.brightness = Number(settings.brightness);
    }
    if (Number.isFinite(settings.contrast)) {
      layer.contrast = Number(settings.contrast);
    }
  }

  tools.layerRenderers = {
    applyImageryVisual: applyImageryVisual,
  };
})();
