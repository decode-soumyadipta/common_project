  // SECTION: UI Widgets (compass, scale bar, status bar)  →  future: modules/ui.js
  // Functions: updateEdgeScaleWidgets, syncSceneModeToggle,
  //   setSceneModeControlEnabled, parseDemHeightRange, createRectangle,
  //   buildUrlWithQuery
  // ═══════════════════════════════════════════════════════════════════════════

  function updateEdgeScaleWidgets() {
    if (!viewer) {
      return;
    }
    if (isInteracting) {
      return;
    }
    const now = performance.now();
    const intervalMs = currentSceneMode === "2d" ? EDGE_SCALE_UPDATE_INTERVAL_2D_MS : EDGE_SCALE_UPDATE_INTERVAL_MS;
    if (now - lastEdgeScaleUpdateMs < intervalMs) {
      return;
    }
    lastEdgeScaleUpdateMs = now;

    const topSvg = document.getElementById("edgeScaleTopSvg");
    const leftSvg = document.getElementById("edgeScaleLeftSvg");
    if (!topSvg || !leftSvg) {
      return;
    }
    if (!viewer.canvas) {
      return;
    }

    const canvasRect = viewer.canvas.getBoundingClientRect();
    if (canvasRect.width <= 0 || canvasRect.height <= 0) {
      return;
    }

    const topRect = topSvg.getBoundingClientRect();
    const leftRect = leftSvg.getBoundingClientRect();

    const topWidth = topSvg.clientWidth || 0;
    const topHeight = topSvg.clientHeight || 0;
    const leftWidth = leftSvg.clientWidth || 0;
    const leftHeight = leftSvg.clientHeight || 0;
    if (topWidth <= 0 || topHeight <= 0 || leftWidth <= 0 || leftHeight <= 0) {
      return;
    }

    topSvg.setAttribute("viewBox", `0 0 ${topWidth} ${topHeight}`);
    leftSvg.setAttribute("viewBox", `0 0 ${leftWidth} ${leftHeight}`);
    clearSvg(topSvg);
    clearSvg(leftSvg);

    const topPad = 14;
    const topTickCount = 8;
    const topAxisY = 10;
    let topValidLabels = 0;
    topSvg.appendChild(createSvgElement("line", { class: "axis", x1: topPad, y1: topAxisY, x2: topWidth - topPad, y2: topAxisY }));
    for (let i = 0; i <= topTickCount; i += 1) {
      const x = topPad + ((topWidth - topPad * 2) * i) / topTickCount;
      topSvg.appendChild(createSvgElement("line", { class: "tick", x1: x, y1: topAxisY, x2: x, y2: topAxisY + 8 }));
      const sampleX = clampPixel(topRect.left - canvasRect.left + x, 0, Math.max(0, canvasRect.width - 1));
      const sampleY = clampPixel(topRect.bottom - canvasRect.top + 2, 0, Math.max(0, canvasRect.height - 1));
      const sample = pickCartographicAtPixel(sampleX, sampleY);
      if (!sample) {
        continue;
      }
      topValidLabels += 1;
      const lonDeg = Cesium.Math.toDegrees(sample.longitude);
      topSvg.appendChild(
        createSvgElement("text", { class: "label", x: x, y: topAxisY + 21, "text-anchor": "middle" }, formatLongitudeLabel(lonDeg))
      );
    }
    if (topValidLabels < 2) {
      topSvg.appendChild(
        createSvgElement("text", { class: "label", x: topWidth / 2, y: topAxisY + 21, "text-anchor": "middle" }, "Longitude scale: n/a")
      );
    }

    const leftPad = 10;
    const leftTickCount = 8;
    const leftAxisX = leftWidth - 12;
    let leftValidLabels = 0;
    leftSvg.appendChild(createSvgElement("line", { class: "axis", x1: leftAxisX, y1: leftPad, x2: leftAxisX, y2: leftHeight - leftPad }));
    for (let i = 0; i <= leftTickCount; i += 1) {
      const y = leftPad + ((leftHeight - leftPad * 2) * i) / leftTickCount;
      leftSvg.appendChild(createSvgElement("line", { class: "tick", x1: leftAxisX - 8, y1: y, x2: leftAxisX, y2: y }));
      const sampleX = clampPixel(leftRect.right - canvasRect.left + 2, 0, Math.max(0, canvasRect.width - 1));
      const sampleY = clampPixel(leftRect.top - canvasRect.top + y, 0, Math.max(0, canvasRect.height - 1));
      const sample = pickCartographicAtPixel(sampleX, sampleY);
      if (!sample) {
        continue;
      }
      leftValidLabels += 1;
      const latDeg = Cesium.Math.toDegrees(sample.latitude);
      leftSvg.appendChild(
        createSvgElement("text", { class: "label", x: 3, y: y + 4, "text-anchor": "start" }, formatLatitudeLabel(latDeg))
      );
    }
    if (leftValidLabels < 2) {
      leftSvg.appendChild(createSvgElement("text", { class: "label", x: 3, y: leftHeight / 2, "text-anchor": "start" }, "Lat n/a"));
    }
  }

  function syncSceneModeToggle(mode) {
    // Moved to Python Qt UI
  }

  function setSceneModeControlEnabled(enabled) {
    sceneModeControlEnabled = Boolean(enabled);
    // Moved to Python Qt UI
  }

  function logLayerStack() {
    if (!viewer || !viewer.imageryLayers) {
      return;
    }
    const rows = [];
    for (let idx = 0; idx < viewer.imageryLayers.length; idx += 1) {
      const layer = viewer.imageryLayers.get(idx);
      const show = layer && layer.show === false ? "HIDDEN" : "VISIBLE";
      
      // FIX: Check if alpha is a finite number, fallback to 1.0, then format.
      const rawAlpha = layer && typeof layer.alpha === "number" ? layer.alpha : 1.0;
      const alpha = (Number.isFinite(rawAlpha) ? rawAlpha : 1.0).toFixed(2);
      
      let desc = "layer#" + idx + ":" + show + ":alpha=" + alpha;
      if (layer === activeDemDrapeLayer) {
        desc += ":DEM-DRAPE";
      } else if (layer === activeDemHillshadeLayer) {
        desc += ":DEM-HILLSHADE";
      } else if (layer === activeImageryLayer) {
        desc += ":ACTIVE-IMAGERY";
      } else if (managedImageryLayers.has(Array.from(managedImageryLayers.entries()).find(([_, l]) => l === layer)?.[0] || "")) {
        const key = Array.from(managedImageryLayers.entries()).find(([_, l]) => l === layer)?.[0] || "unknown";
        desc += ":MANAGED-IMAGERY:" + key;
      }
      rows.push(desc);
    }
    log("debug", "Layer stack: " + viewer.imageryLayers.length + " layers");
  }

  // requestLayerStackDump removed — call logLayerStack() directly when needed

  // ═══════════════════════════════════════════════════════════════════════════
