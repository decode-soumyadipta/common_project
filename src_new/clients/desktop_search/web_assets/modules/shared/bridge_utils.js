(function () {
  const runtime = (window.OfflineGISRuntime = window.OfflineGISRuntime || {});
  if (typeof window.lonLat === "undefined") {
    window.lonLat = null;
  }

  function getBridge() {
    return runtime.bridge || null;
  }

  function getViewer() {
    return runtime.viewer || null;
  }

  function getComparatorViewers() {
    return runtime.comparatorViewers || null;
  }

  function log(level, message) {
    const fn = console[level] || console.log;
    fn("[offlineGIS]", message);
    const bridge = getBridge();
    if (bridge && bridge.js_log) {
      bridge.js_log(level, String(message));
    }
  }

  function setStatus(text) {
    const el = document.getElementById("status");
    if (el) el.textContent = text;
  }

  function emitMapClick(lon, lat) {
    const bridge = getBridge();
    if (bridge && bridge.on_map_click) {
      bridge.on_map_click(lon, lat);
    }
  }

  function emitMeasurementUpdated(meters) {
    const bridge = getBridge();
    if (bridge && bridge.on_measurement) {
      bridge.on_measurement(meters);
    }
  }

  function emitLoadingProgress(percent, message) {
    const bridge = getBridge();
    if (!bridge || !bridge.on_loading_progress) return;
    bridge.on_loading_progress(Math.round(percent), String(message || "Loading"));
  }

  function requestSceneRender() {
    const viewer = getViewer();
    if (viewer && viewer.scene && typeof viewer.scene.requestRender === "function") {
      viewer.scene.requestRender();
    }
    const comparatorViewers = getComparatorViewers();
    if (Array.isArray(comparatorViewers)) {
      comparatorViewers.forEach(function (v) {
        if (v && v.scene) {
          v.scene.requestRender();
        }
      });
    }
  }

  function setComparatorWindowsVisible(visible) {
    const root = document.getElementById("comparatorWindows");
    const map = document.getElementById("cesiumContainer");
    if (!root || !map) {
      return;
    }
    const enabled = Boolean(visible);
    root.classList.toggle("active", enabled);
    root.setAttribute("aria-hidden", enabled ? "false" : "true");
    map.style.display = enabled ? "none" : "block";

    if (enabled) {
      const comparatorViewers = getComparatorViewers();
      const resizeAndRender = function () {
        if (Array.isArray(comparatorViewers)) {
          comparatorViewers.forEach(function (v) {
            if (v && v.scene) {
              try {
                v.resize();
              } catch (_error) {}
              v.scene.requestRender();
            }
          });
        }
      };
      setTimeout(resizeAndRender, 50);
      setTimeout(resizeAndRender, 300);
      setTimeout(resizeAndRender, 800);
    }
  }

  function normalizeBounds(bounds) {
    if (!bounds || typeof bounds !== "object") {
      return null;
    }
    const west = Number(bounds.west);
    const south = Number(bounds.south);
    const east = Number(bounds.east);
    const north = Number(bounds.north);
    if (!Number.isFinite(west) || !Number.isFinite(south) || !Number.isFinite(east) || !Number.isFinite(north)) {
      return null;
    }
    return { west: west, south: south, east: east, north: north };
  }

  function createRectangle(bounds) {
    const normalized = normalizeBounds(bounds);
    if (!normalized || !window.Cesium) {
      return null;
    }
    return window.Cesium.Rectangle.fromDegrees(
      normalized.west,
      normalized.south,
      normalized.east,
      normalized.north
    );
  }

  function rectangleFromBounds(bounds) {
    return createRectangle(bounds);
  }

  function applyCursorStyle(element, cursorValue) {
    if (!element || !element.style) {
      return;
    }
    if (cursorValue) {
      element.style.setProperty("cursor", cursorValue, "important");
      return;
    }
    element.style.removeProperty("cursor");
  }

  function parseDemHeightRange(options) {
    const defaultRange = { min: -500.0, max: 9000.0 };
    const query = options && options.query ? options.query : null;
    if (!query || typeof query.rescale !== "string") {
      return defaultRange;
    }
    const parts = query.rescale.split(",").map((value) => Number(value.trim()));
    if (parts.length !== 2 || !Number.isFinite(parts[0]) || !Number.isFinite(parts[1]) || parts[1] <= parts[0]) {
      return defaultRange;
    }
    return { min: parts[0], max: parts[1] };
  }

  function _encodeParamValue(key, value) {
    // Use standard encoding for all parameters including 'url'.
    // Unencoding ':' and '/' can lead to mis-routing or parsing errors in some server environments.
    return encodeURIComponent(value);
  }

  function buildUrlWithQuery(url, extraQuery) {
    const splitIndex = url.indexOf("?");
    const base = splitIndex >= 0 ? url.slice(0, splitIndex) : url;
    const queryText = splitIndex >= 0 ? url.slice(splitIndex + 1) : "";

    const existingParams = {};
    if (queryText) {
      queryText.split("&").forEach(function (pair) {
        const eqIdx = pair.indexOf("=");
        if (eqIdx > 0) {
          const key = decodeURIComponent(pair.slice(0, eqIdx));
          const value = decodeURIComponent(pair.slice(eqIdx + 1));
          existingParams[key] = value;
        }
      });
    }

    const finalParams = Object.assign({}, existingParams, extraQuery || {});
    const paramPairs = Object.entries(finalParams)
      .map(function ([key, value]) {
        if (value === null || value === undefined) {
          return null;
        }
        if (Array.isArray(value)) {
          return value
            .map(function (item) {
              return encodeURIComponent(key) + "=" + _encodeParamValue(key, String(item));
            })
            .join("&");
        }
        return encodeURIComponent(key) + "=" + _encodeParamValue(key, String(value));
      })
      .filter(Boolean);

    const merged = paramPairs.join("&");
    return merged ? base + "?" + merged : base;
  }

  function formatDistance(meters) {
    const value = Number(meters);
    if (!Number.isFinite(value)) {
      return "n/a";
    }
    if (Math.abs(value) >= 1000.0) {
      return `${(value / 1000.0).toFixed(2)} km`;
    }
    return `${value.toFixed(2)} m`;
  }

  const rubberBandLineStates = new Map();

  function ensureRubberBandLine(key, positionsGetter, options) {
    const viewer = getViewer();
    if (!viewer || !viewer.entities) {
      return null;
    }

    const normalizedKey = String(key || "default");
    let state = rubberBandLineStates.get(normalizedKey);
    if (!state) {
      state = {
        entity: null,
        positionsGetter: null,
      };
      rubberBandLineStates.set(normalizedKey, state);
    }

    state.positionsGetter = typeof positionsGetter === "function" ? positionsGetter : function () {
      return [];
    };

    if (state.entity && !viewer.entities.contains(state.entity)) {
      state.entity = null;
    }

    const style = Object.assign(
      {
        width: 2,
        color: "#00e5ff",
        alpha: 0.85,
        clampToGround: true,
        arcType: window.Cesium ? window.Cesium.ArcType.GEODESIC : undefined,
      },
      options || {}
    );

    if (!state.entity) {
      state.entity = viewer.entities.add({
        polyline: {
          positions: new Cesium.CallbackProperty(function () {
            try {
              const positions = state.positionsGetter ? state.positionsGetter() : [];
              return Array.isArray(positions) ? positions.filter(Boolean) : [];
            } catch (_) {
              return [];
            }
          }, false),
          width: style.width,
          arcType: style.arcType || Cesium.ArcType.GEODESIC,
          material: Cesium.Color.fromCssColorString(style.color).withAlpha(style.alpha),
          clampToGround: Boolean(style.clampToGround),
          depthFailMaterial: Cesium.Color.fromCssColorString(style.color).withAlpha(style.alpha),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
    }

    requestSceneRender();
    return state.entity;
  }

  function clearRubberBandLine(key) {
    const viewer = getViewer();
    const normalizedKey = String(key || "default");
    const state = rubberBandLineStates.get(normalizedKey);
    if (state && state.entity && viewer && viewer.entities) {
      try {
        if (viewer.entities.contains(state.entity)) {
          viewer.entities.remove(state.entity);
        }
      } catch (_) {}
    }
    rubberBandLineStates.delete(normalizedKey);
    requestSceneRender();
  }

  window.OfflineGISUtils = {
    log: log,
    setStatus: setStatus,
    emitMapClick: emitMapClick,
    emitMeasurementUpdated: emitMeasurementUpdated,
    emitLoadingProgress: emitLoadingProgress,
    requestSceneRender: requestSceneRender,
    setComparatorWindowsVisible: setComparatorWindowsVisible,
    normalizeBounds: normalizeBounds,
    createRectangle: createRectangle,
    rectangleFromBounds: rectangleFromBounds,
    applyCursorStyle: applyCursorStyle,
    parseDemHeightRange: parseDemHeightRange,
    buildUrlWithQuery: buildUrlWithQuery,
    formatDistance: formatDistance,
    ensureRubberBandLine: ensureRubberBandLine,
    clearRubberBandLine: clearRubberBandLine,
  };
})();
