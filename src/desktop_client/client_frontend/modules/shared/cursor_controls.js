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

  const SEARCH_PENCIL_CURSOR_IMAGE =
    "data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2220%22 height=%2220%22 viewBox=%220 0 24 24%22%3E%3Cpath fill=%22%23f4c430%22 stroke=%22%231a1a1a%22 stroke-width=%221.4%22 d=%22M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25z%22/%3E%3Cpath fill=%22%231a1a1a%22 d=%22M20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83l3.75 3.75z%22/%3E%3C/svg%3E";
  const SEARCH_PENCIL_CURSOR = `url("${SEARCH_PENCIL_CURSOR_IMAGE}") 2 18, crosshair`;

  let searchCursorOverlay = null;
  let lastSearchCursorScreenPosition = null;
  let measureCursorStyleEl = null;

  function getViewer() {
    return runtime.viewer || null;
  }

  function getBridge() {
    return runtime.bridge || null;
  }

  function ensureSearchCursorOverlay() {
    if (searchCursorOverlay || !document.body) {
      return;
    }
    const overlay = document.createElement("div");
    overlay.id = "searchCursorOverlay";
    overlay.setAttribute("aria-hidden", "true");
    overlay.style.position = "fixed";
    overlay.style.left = "0px";
    overlay.style.top = "0px";
    overlay.style.width = "20px";
    overlay.style.height = "20px";
    overlay.style.pointerEvents = "none";
    overlay.style.zIndex = "100000";
    overlay.style.display = "none";
    overlay.style.backgroundRepeat = "no-repeat";
    overlay.style.backgroundSize = "20px 20px";
    overlay.style.backgroundImage = `url("${SEARCH_PENCIL_CURSOR_IMAGE}")`;
    overlay.style.transform = "translate(-2px, -18px)";
    document.body.appendChild(overlay);
    searchCursorOverlay = overlay;
  }

  function updateSearchCursorOverlay(screenPosition) {
    const viewer = getViewer();
    if (!viewer || !viewer.canvas || !searchCursorOverlay || !screenPosition) {
      return;
    }
    const x = Number(screenPosition.x);
    const y = Number(screenPosition.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      return;
    }
    const rect = viewer.canvas.getBoundingClientRect();
    searchCursorOverlay.style.left = `${rect.left + x}px`;
    searchCursorOverlay.style.top = `${rect.top + y}px`;
  }

  function setSearchCursorOverlayVisible(visible) {
    if (!searchCursorOverlay) {
      return;
    }
    if (!visible || !lastSearchCursorScreenPosition) {
      searchCursorOverlay.style.display = "none";
      return;
    }
    searchCursorOverlay.style.display = "block";
    updateSearchCursorOverlay(lastSearchCursorScreenPosition);
  }

  function setSearchCursorEnabled(enabled) {
    const viewer = getViewer();
    if (!viewer || !viewer.canvas) {
      return;
    }
    ensureSearchCursorOverlay();
    const nextCursor = enabled ? (searchCursorOverlay ? "none" : SEARCH_PENCIL_CURSOR) : "";
    applyCursorStyle(viewer.canvas, nextCursor);
    const mapElement = document.getElementById("cesiumContainer");
    if (mapElement) {
      applyCursorStyle(mapElement, nextCursor);
      mapElement.classList.toggle("search-draw-cursor-active", Boolean(enabled));
    }
    if (viewer.container) {
      applyCursorStyle(viewer.container, nextCursor);
    }
    setSearchCursorOverlayVisible(Boolean(enabled));
  }

  function ensureMeasureCursorOverlay() { /* no-op — cursor handled by Qt */ }
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
    measureCursorStyleEl.textContent = "";
  }

  function _enforceMeasureCursor(active) {
    setMeasurementCursorEnabled(active);
  }

  runtime.searchCursorControls = {
    get searchCursorOverlay() {
      return searchCursorOverlay;
    },
    set searchCursorOverlay(value) {
      searchCursorOverlay = value;
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
