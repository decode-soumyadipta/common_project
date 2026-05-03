(function () {
  const runtime = (window.OfflineGISRuntime = window.OfflineGISRuntime || {});
  const utils = window.OfflineGISUtils || {};
  const applyCursorStyle = utils.applyCursorStyle || function (element, cursorValue) {
    if (!element || !element.style) {
      return;
    }
    if (cursorValue) {
      element.style.setProperty("cursor", cursorValue, "important");
      return;
    }
    element.style.removeProperty("cursor");
  };

  const SEARCH_DRAW_CURSOR = "crosshair";

  let lastSearchCursorScreenPosition = null;
  let measureCursorStyleEl = null;

  function getViewer() {
    return runtime.viewer || null;
  }

  function getBridge() {
    return runtime.bridge || null;
  }

  function ensureSearchCursorOverlay() {
    // Overlay mechanism removed per user request for "windows default crosshair".
    // We now rely on native CSS 'crosshair' and Python-side 'Qt.CrossCursor'.
  }

  function updateSearchCursorOverlay(screenPosition) {
    // No-op: native cursor follows mouse automatically.
  }

  function setSearchCursorOverlayVisible(visible) {
    // No-op: native cursor visibility managed via CSS.
  }

  function setSearchCursorEnabled(enabled) {
    const viewer = getViewer();
    if (!viewer || !viewer.canvas) {
      return;
    }
    
    const nextCursor = enabled ? SEARCH_DRAW_CURSOR : "";
    applyCursorStyle(viewer.canvas, nextCursor);
    
    const mapElement = document.getElementById("cesiumContainer");
    if (mapElement) {
      applyCursorStyle(mapElement, nextCursor);
      mapElement.classList.toggle("search-draw-cursor-active", Boolean(enabled));
    }
    if (viewer.container) {
      applyCursorStyle(viewer.container, nextCursor);
    }

    // Trigger Python-side system cursor for maximum consistency
    setMeasurementCursorEnabled(enabled);
  }

  function ensureMeasureCursorOverlay() { /* no-op */ }
  function updateMeasureCursorOverlay() { /* no-op */ }
  function setMeasureCursorOverlayVisible() { /* no-op */ }

  function setMeasurementCursorEnabled(enabled) {
    const bridge = getBridge();
    if (bridge && bridge.on_measure_cursor) {
      bridge.on_measure_cursor(Boolean(enabled));
    }
    if (!measureCursorStyleEl) {
      measureCursorStyleEl = document.createElement("style");
      measureCursorStyleEl.id = "measureCursorOverride";
      document.head.appendChild(measureCursorStyleEl);
    }
    // Ensure all Cesium interaction elements respect the crosshair when enabled
    if (enabled) {
      measureCursorStyleEl.textContent = ".cesium-viewer { cursor: crosshair !important; }";
    } else {
      measureCursorStyleEl.textContent = "";
    }
  }

  function _enforceMeasureCursor(active) {
    setMeasurementCursorEnabled(active);
  }

  runtime.searchCursorControls = {
    get searchCursorOverlay() {
      return null;
    },
    set searchCursorOverlay(value) {
      // ignore
    },
    get lastSearchCursorScreenPosition() {
      return lastSearchCursorScreenPosition;
    },
    set lastSearchCursorScreenPosition(value) {
      lastSearchCursorScreenPosition = value;
    },
    setSearchCursorEnabled: setSearchCursorEnabled,
    updateSearchCursorOverlay: updateSearchCursorOverlay,
    setSearchCursorOverlayVisible: setSearchCursorOverlayVisible,
    setMeasurementCursorEnabled: setMeasurementCursorEnabled,
    _enforceMeasureCursor: _enforceMeasureCursor,
    ensureMeasureCursorOverlay: ensureMeasureCursorOverlay,
    updateMeasureCursorOverlay: updateMeasureCursorOverlay,
    setMeasureCursorOverlayVisible: setMeasureCursorOverlayVisible,
  };

  window.OfflineGISCursorControls = runtime.searchCursorControls;
})();
