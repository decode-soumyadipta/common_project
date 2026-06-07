  // SECTION: Search Cursor & Cursor Utilities  →  future: modules/search.js
  // Functions are provided by modules/shared/cursor_controls.js
  // ═══════════════════════════════════════════════════════════════════════════

  function sceneDebug(message) {
    log("info", "[SCENE_DEBUG] " + message);
  }

  function looksLikeMissingLocalAssetError(error) {
    const errorTextParts = [
      String(error || ""),
      error && error.message ? String(error.message) : "",
      error && error.stack ? String(error.stack) : "",
    ];
    const text = errorTextParts.join("\n").toLowerCase();
    return (
      text.includes("failed to fetch") ||
      text.includes("404") ||
      text.includes("not found") ||
      text.includes("err_file_not_found") ||
      text.includes("an error occurred while accessing") ||
      (text.includes("file://") && text.includes("layer.json"))
    );
  }

  function createSolidPolarCapDataUrl() {
    const canvas = document.createElement("canvas");
    canvas.width = 2;
    canvas.height = 2;
    const context = canvas.getContext("2d");
    if (context) {
      context.fillStyle = "#1f4f7a";
      context.fillRect(0, 0, canvas.width, canvas.height);
    }
    return canvas.toDataURL("image/png");
  }

  function detectSceneMode() {
    if (!viewer || !viewer.scene) {
      return currentSceneMode;
    }
    if (viewer.scene.mode === Cesium.SceneMode.MORPHING) {
      return "morphing";
    }
    return viewer.scene.mode === Cesium.SceneMode.SCENE2D ? "2d" : "3d";
  }

  function normalizeLongitudeDegrees(value) {
    let normalized = ((Number(value) + 540) % 360) - 180;
    if (normalized === -180) {
      normalized = 180;
    }
    return normalized;
  }

  function formatLongitudeLabel(value) {
    if (!Number.isFinite(value)) {
      return "n/a";
    }
    const lon = normalizeLongitudeDegrees(value);
    const suffix = lon >= 0 ? "E" : "W";
    const absValue = Math.abs(lon);
    const decimals = absValue >= 100 ? 0 : absValue >= 10 ? 1 : 2;
    return `${absValue.toFixed(decimals)}°${suffix}`;
  }

  function formatLatitudeLabel(value) {
    if (!Number.isFinite(value)) {
      return "n/a";
    }
    const lat = Math.max(-90, Math.min(90, Number(value)));
    const suffix = lat >= 0 ? "N" : "S";
    const absValue = Math.abs(lat);
    const decimals = absValue >= 10 ? 1 : 2;
    return `${absValue.toFixed(decimals)}°${suffix}`;
  }

  function pickCartographicAtPixel(x, y) {
    if (!viewer) {
      return null;
    }
    const screenPoint = new Cesium.Cartesian2(x, y);
    const ray = viewer.camera.getPickRay(screenPoint);
    if (ray) {
      const cartesian = viewer.scene.globe.pick(ray, viewer.scene);
      if (cartesian) {
        return Cesium.Cartographic.fromCartesian(cartesian);
      }
    }
    const ellipsoidHit = viewer.camera.pickEllipsoid(screenPoint, viewer.scene.globe.ellipsoid);
    if (ellipsoidHit) {
      return Cesium.Cartographic.fromCartesian(ellipsoidHit);
    }
    return null;
  }

  function createSvgElement(tag, attrs, textContent) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      node.setAttribute(key, String(value));
    });
    if (typeof textContent === "string") {
      node.textContent = textContent;
    }
    return node;
  }

  function clearSvg(svg) {
    while (svg && svg.firstChild) {
      svg.removeChild(svg.firstChild);
    }
  }

  function clampPixel(value, minValue, maxValue) {
    return Math.max(minValue, Math.min(maxValue, value));
  }

  // ═══════════════════════════════════════════════════════════════════════════
