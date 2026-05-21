(function () {
  window.offlineGIS = window.offlineGIS || {};

  const bridgeModules = [
    "./modules/bridge/core.js",
    "./modules/bridge/comparator.js",
    "./modules/bridge/search_cursor.js",
    "./modules/bridge/ui.js",
    "./modules/bridge/imagery.js",
    "./modules/bridge/dem_colorbar.js",
    "./modules/bridge/camera.js",
    "./modules/bridge/dem_terrain.js",
    "./modules/bridge/basemap.js",
    "./modules/bridge/annotations.js",
    "./modules/bridge/status_emitters.js",
    "./modules/bridge/measurement.js",
    "./modules/bridge/search_aoi.js",
    "./modules/bridge/navigation.js",
    "./modules/bridge/text_labels.js",
    "./modules/bridge/event_driven.js",
    "./modules/bridge/layer_reordering.js",
    "./modules/bridge/raster_stretching.js",
  ];

  function fetchModuleText(path) {
    const moduleUrl = new URL(path, document.baseURI || window.location.href).href;
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("GET", moduleUrl, true);
      xhr.overrideMimeType("text/plain");
      xhr.onload = function () {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(xhr.responseText);
          return;
        }
        if (xhr.status === 0 && xhr.responseText) {
          resolve(xhr.responseText);
          return;
        }
        reject(new Error(`Failed to load ${path}: ${xhr.status}`));
      };
      xhr.onerror = function () {
        reject(new Error(`Failed to load ${path}`));
      };
      xhr.send();
    });
  }

  function bootBridge() {
    if (typeof window.__offlineGISInitBridge === "function") {
      window.__offlineGISInitBridge();
      return;
    }
    if (typeof initBridge === "function") {
      initBridge();
      return;
    }
    console.error("[offlineGIS] initBridge not found after loading bridge modules");
  }

  async function loadBridgeModules() {
    const moduleTexts = [];
    for (const modulePath of bridgeModules) {
      const text = await fetchModuleText(modulePath);
      moduleTexts.push(text);
    }

    const combined = [
      "(function () {",
      moduleTexts.join("\n\n"),
      "\nwindow.__offlineGISInitBridge = typeof initBridge === 'function' ? initBridge : null;",
      "})();",
    ].join("\n");

    (0, eval)(combined);
    bootBridge();
  }

  document.addEventListener("DOMContentLoaded", () => {
    loadBridgeModules().catch((error) => {
      console.error("[offlineGIS] Failed to load bridge modules:", error);
    });
  });
})();
