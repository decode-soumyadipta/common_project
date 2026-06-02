  // SECTION: Comparator Mode  →  future: modules/comparator.js
  // Functions: ensureComparatorViewers, refreshComparatorLayers,
  //   setComparatorWindowsVisible, updateComparatorPolygons,
  //   scheduleComparatorDemRefresh, comparator camera sync helpers,
  //   swipe comparator setup and management
  // ═══════════════════════════════════════════════════════════════════════════

  function refreshComparatorLayers(options) {
    if (!comparatorModeEnabled) return;
    const activeKeys = resolveComparatorLayerKeys();
    if (activeKeys.length < 2) return;

    ensureComparatorViewers(activeKeys.length);
    
    // ensureComparatorViewers already activated the correct panes/dividers.
    // Just make sure panes beyond the active count are hidden.
    for (var i = activeKeys.length; i < 4; i++) {
      var pane = document.getElementById("comparatorPane" + i);
      var div = document.getElementById("comparatorDivider" + i);
      if (pane) pane.classList.remove("active");
      if (div) div.classList.remove("active");
    }

    activeKeys.forEach((key, idx) => {
      const def = layerDefinitions.get(key);
      const viewer = comparatorViewers[idx];
      const pane = document.getElementById("comparatorPane" + idx);
      const div = document.getElementById("comparatorDivider" + idx);
      
      if (!def || !viewer || !pane) return;
      
      pane.classList.add("active");
      if (idx < activeKeys.length - 1 && div) div.classList.add("active");

      resetComparatorViewerLayers(viewer);
      applyLayerDefinitionToViewer(viewer, def, String(idx));
      
      const title = document.getElementById("comparatorTitle" + idx);
      if (title) title.textContent = def.label || ("Layer " + (idx + 1));
      
      viewer.resize();
    });

    syncComparatorTerrainProviders();
    setSelectedComparatorPane(comparatorSelectedPane, true);
    
    if (typeof window._currentBasemapVisibility !== 'undefined') {
      window.offlineGIS.setBasemapVisibility(window._currentBasemapVisibility);
    }
  }

  function scheduleComparatorDemRefresh(paneKey) {
    if (comparatorDemRefreshTimer !== null) {
      window.clearTimeout(comparatorDemRefreshTimer);
      comparatorDemRefreshTimer = null;
    }
    const targetPane = getComparatorPaneKeyForIndex(resolveComparatorPaneIndex(paneKey));
    comparatorDemRefreshTimer = window.setTimeout(function () {
      comparatorDemRefreshTimer = null;
      if (!comparatorModeEnabled) {
        return;
      }
      const paneLayerType = getComparatorPaneLayerType(targetPane);
      if (paneLayerType !== "dem") {
        return;
      }

      const targetViewer = getComparatorPaneViewer(targetPane);
      const paneState = getComparatorPaneVisual(targetPane);
      const layerKey = targetViewer && targetViewer.__comparatorLayerKey ? targetViewer.__comparatorLayerKey : null;
      const definition = layerKey ? layerDefinitions.get(layerKey) : null;
      if (!targetViewer || !paneState || !definition || String(definition.type || "") !== "dem") {
        return;
      }
      syncComparatorTerrainProviders();

      const rectangle = rectangleFromBounds(definition.bounds || null);
      const drapeUrl = buildComparatorDemDrapeUrl(definition, paneState.dem);
      const hillshadeUrl = buildComparatorDemHillshadeUrl(definition, paneState.dem);
      const oldPrimary = targetViewer.__comparatorPrimaryLayer || null;
      const oldHillshade = targetViewer.__comparatorHillshadeLayer || null;

      let insertIndex = targetViewer.imageryLayers.length;
      if (oldPrimary) {
        const primaryIndex = targetViewer.imageryLayers.indexOf(oldPrimary);
        if (primaryIndex >= 0) {
          insertIndex = primaryIndex;
        }
      }

      const demProvider = new Cesium.UrlTemplateImageryProvider({
        url: drapeUrl,
        maximumLevel: definition.maxLevel,
        minimumLevel: definition.minLevel,
        tilingScheme: new Cesium.WebMercatorTilingScheme(),
        enablePickFeatures: false,
        rectangle: rectangle,
      });
      const newPrimary = targetViewer.imageryLayers.addImageryProvider(demProvider, insertIndex);
      newPrimary.alpha = 1.0;
      newPrimary.show = true;

      let newHillshade = null;
      if (hillshadeUrl) {
        const hillshadeProvider = new Cesium.UrlTemplateImageryProvider({
          url: hillshadeUrl,
          maximumLevel: definition.maxLevel,
          minimumLevel: definition.minLevel,
          tilingScheme: new Cesium.WebMercatorTilingScheme(),
          enablePickFeatures: false,
          rectangle: rectangle,
        });
        newHillshade = targetViewer.imageryLayers.addImageryProvider(hillshadeProvider, insertIndex + 1);
        newHillshade.show = true;
      }

      const refreshKey = String(resolveComparatorPaneIndex(targetPane));
      const refreshVersion = (Number(comparatorDemStyleRefreshVersion[refreshKey]) || 0) + 1;
      comparatorDemStyleRefreshVersion[refreshKey] = refreshVersion;
      window.setTimeout(function () {
        const latestVersion = Number(comparatorDemStyleRefreshVersion[refreshKey]) || 0;
        const staleRefresh = latestVersion !== refreshVersion;
        const comparatorInactive = !comparatorModeEnabled || getComparatorPaneLayerType(targetPane) !== "dem";
        if (staleRefresh || comparatorInactive) {
          if (newHillshade && targetViewer.imageryLayers.indexOf(newHillshade) >= 0) {
            targetViewer.imageryLayers.remove(newHillshade, false);
          }
          if (targetViewer.imageryLayers.indexOf(newPrimary) >= 0) {
            targetViewer.imageryLayers.remove(newPrimary, false);
          }
          return;
        }

        targetViewer.__comparatorPrimaryLayer = newPrimary;
        targetViewer.__comparatorHillshadeLayer = newHillshade;
        applyComparatorPaneVisualState(targetPane);

        if (typeof setSearchBusy === "function") {
          setSearchBusy(false, "");
        }

        if (oldHillshade && targetViewer.imageryLayers.indexOf(oldHillshade) >= 0) {
          targetViewer.imageryLayers.remove(oldHillshade, false);
        }
        if (oldPrimary && targetViewer.imageryLayers.indexOf(oldPrimary) >= 0) {
          targetViewer.imageryLayers.remove(oldPrimary, false);
        }
        enforceComparatorDemLayerOrder(targetPane, targetViewer);
        logComparatorLayerStack(targetViewer, targetPane, "post-color-refresh");
        targetViewer.scene.requestRender();
      }, 48);
    }, COMPARATOR_DEM_REFRESH_DEBOUNCE_MS);
  }

  const comparatorViewers = [];
  runtime.comparatorViewers = comparatorViewers;
  function ensureComparatorViewers(count) {
    // CRITICAL (Windows/ANGLE): The comparatorPane divs must have display:block
    // BEFORE Cesium creates its canvas, otherwise the canvas gets zero size and
    // stays permanently black.  Activate all needed panes now, before any viewer
    // is constructed.
    var cwRoot = document.getElementById("comparatorWindows");
    if (cwRoot) cwRoot.setAttribute("data-pane-count", String(count));

    for (var pi = 0; pi < count; pi++) {
      var paneEl = document.getElementById("comparatorPane" + pi);
      if (paneEl) paneEl.classList.add("active");
      if (pi < count - 1) {
        var divEl = document.getElementById("comparatorDivider" + pi);
        if (divEl) divEl.classList.add("active");
      }
    }
    // Hide panes beyond the requested count
    for (var hi = count; hi < 4; hi++) {
      var hPane = document.getElementById("comparatorPane" + hi);
      var hDiv  = document.getElementById("comparatorDivider" + hi);
      if (hPane) hPane.classList.remove("active");
      if (hDiv)  hDiv.classList.remove("active");
    }

    // ── Tear down viewers beyond the requested count ───────────────────────────
    // This prevents ghost panes when switching from a larger to a smaller selection
    // (e.g., going from 4 panes to 2 panes). Cesium viewers are destroyed here
    // so their canvases are properly cleaned up before we build the new layout.
    for (var di = comparatorViewers.length - 1; di >= count; di--) {
      var dv = comparatorViewers[di];
      if (dv) {
        try { dv.destroy(); } catch (_) {}
      }
      comparatorViewers.splice(di, 1);
    }

    for (var i = 0; i < count; i++) {
      if (comparatorViewers[i]) continue;
      const vId = "comparatorViewer" + i;
      const v = new Cesium.Viewer(vId, {
        imageryProvider: false,
        baseLayerPicker: false,
        geocoder: false,
        navigationHelpButton: false,
        sceneModePicker: false,
        homeButton: false,
        fullscreenButton: false,
        infoBox: false,
        selectionIndicator: false,
        scene3DOnly: false,
        requestRenderMode: true,
        maximumRenderTimeChange: Infinity,
        timeline: false,
        animation: false,
        terrainProvider: new Cesium.EllipsoidTerrainProvider(),
      });
      v.resolutionScale = 1.0;
      v.useBrowserRecommendedResolution = false;
      v.scene.globe.baseColor = Cesium.Color.BLACK;
      v.scene.backgroundColor = Cesium.Color.BLACK;
      v.scene.globe.maximumScreenSpaceError = 1.0;
      v.scene.globe.tileCacheSize = 3000;
      v.scene.globe.preloadAncestors = true;
      v.scene.globe.preloadSiblings = true;
      v.scene.globe.loadingDescendantLimit = 16;
      v.scene.globe.loadingQueueThreshold = 100;
      v.scene.fxaa = true;
      // Start in 3D — use morphTo3D so the scene graph initialises correctly
      // on Windows/ANGLE (direct scene.mode assignment can leave it in a broken state)
      if (v.scene.mode !== Cesium.SceneMode.SCENE3D) {
        v.scene.morphTo3D(0.0);
      }
      v.camera.percentageChanged = 0.001;
      
      comparatorViewers[i] = v;
    }

    // Force resize on all viewers — Windows/ANGLE needs this even after the
    // panes are visible, because the flex layout may not have fully settled yet.
    function _forceResizeAll() {
      comparatorViewers.forEach(function(v) {
        if (!v) return;
        try { v.resize(); } catch(_) {}
        if (v.scene) v.scene.requestRender();
      });
    }
    setTimeout(_forceResizeAll, 0);
    setTimeout(_forceResizeAll, 80);
    setTimeout(_forceResizeAll, 250);
    setTimeout(_forceResizeAll, 600);
    setTimeout(_forceResizeAll, 1200);

    comparatorLeftViewer = comparatorViewers[0] || null;
    comparatorRightViewer = comparatorViewers[1] || null;
    bindComparatorPaneSelectionHandlers();
  }

  function getSwipeCandidateLayers() {
    const visibleLayers = [];
    for (const layer of managedImageryLayers.values()) {
      if (layer && layer.show) {
        visibleLayers.push(layer);
      }
    }
    if (activeDemDrapeLayer && activeDemDrapeLayer.show) {
      visibleLayers.push(activeDemDrapeLayer);
    }
    if (activeDemHillshadeLayer && activeDemHillshadeLayer.show && activeDemHillshadeLayer.alpha > 0.01) {
      visibleLayers.push(activeDemHillshadeLayer);
    }
    return visibleLayers;
  }

  function applySwipeComparatorSplit() {
    if (!viewer) {
      return;
    }
    if (comparatorModeEnabled) {
      return;
    }
    const candidates = getSwipeCandidateLayers();
    const resetLayers = Array.from(managedImageryLayers.values());
    if (activeDemDrapeLayer) {
      resetLayers.push(activeDemDrapeLayer);
    }
    if (activeDemHillshadeLayer) {
      resetLayers.push(activeDemHillshadeLayer);
    }
    for (const layer of resetLayers) {
      if (layer) {
        layer.splitDirection = Cesium.ImagerySplitDirection.NONE;
      }
    }

    if (!swipeComparatorEnabled || candidates.length === 0) {
      viewer.scene.imagerySplitPosition = 0.5;
      requestSceneRender();
      return;
    }

    if (candidates.length === 1) {
      candidates[0].splitDirection = Cesium.ImagerySplitDirection.LEFT;
    } else {
      const leftLayer = candidates[candidates.length - 1];
      const rightLayer = candidates[candidates.length - 2];
      leftLayer.splitDirection = Cesium.ImagerySplitDirection.LEFT;
      rightLayer.splitDirection = Cesium.ImagerySplitDirection.RIGHT;
    }
    viewer.scene.imagerySplitPosition = swipeComparatorPosition;
    requestSceneRender();
  }

  function updateSwipeDividerPosition() {
    if (!swipeDividerElement || !viewer || !viewer.canvas) {
      return;
    }
    const rect = viewer.canvas.getBoundingClientRect();
    swipeDividerElement.style.left = `${Math.round(rect.left + rect.width * swipeComparatorPosition)}px`;
    swipeDividerElement.style.top = `${Math.round(rect.top)}px`;
    swipeDividerElement.style.height = `${Math.round(rect.height)}px`;
  }

  function setSwipePosition(fraction) {
    const next = Number(fraction);
    if (!Number.isFinite(next)) {
      return;
    }
    swipeComparatorPosition = Math.min(0.98, Math.max(0.02, next));
    if (viewer) {
      viewer.scene.imagerySplitPosition = swipeComparatorPosition;
    }
    updateSwipeDividerPosition();
    requestSceneRender();
  }

  function ensureSwipeDivider() {
    if (swipeDividerElement || !document.body) {
      return;
    }
    const divider = document.createElement("div");
    divider.id = "swipeComparatorDivider";
    divider.style.position = "fixed";
    divider.style.width = "3px";
    divider.style.background = "#ffde59";
    divider.style.boxShadow = "0 0 0 1px rgba(0,0,0,0.35), 0 0 14px rgba(255,222,89,0.45)";
    divider.style.cursor = "ew-resize";
    divider.style.zIndex = "100001";
    divider.style.display = "none";
    divider.style.pointerEvents = "auto";
    document.body.appendChild(divider);
    swipeDividerElement = divider;

    let dragging = false;
    let lastSwipeMoveTime = 0;
    const SWIPE_MOVE_THROTTLE_MS = 16;  // ~60fps max
    divider.addEventListener("mousedown", function (event) {
      event.preventDefault();
      dragging = true;
    });
    window.addEventListener("mousemove", function (event) {
      if (!dragging || !viewer || !viewer.canvas) {
        return;
      }
      // Throttle swipe updates for smooth performance
      const now = Date.now();
      if (now - lastSwipeMoveTime < SWIPE_MOVE_THROTTLE_MS) {
        return;
      }
      lastSwipeMoveTime = now;
      
      const rect = viewer.canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const fraction = x / Math.max(1.0, rect.width);
      setSwipePosition(fraction);
    });
    window.addEventListener("mouseup", function () {
      dragging = false;
    });
    window.addEventListener("resize", function () {
      if (swipeComparatorEnabled) {
        updateSwipeDividerPosition();
      }
    });
  }

  function setSwipeComparatorEnabled(enabled) {
    const next = Boolean(enabled);
    swipeComparatorEnabled = next;
    comparatorModeEnabled = next;
    resetComparatorCameraSyncState(next ? "comparator-enabled" : "comparator-disabled");
    if (!next) {
      cancelComparatorCameraSyncSchedule();
    }
    if (comparatorDemRefreshTimer !== null) {
      window.clearTimeout(comparatorDemRefreshTimer);
      comparatorDemRefreshTimer = null;
    }
    const candidateCount = getSwipeCandidateLayers().length;
    ensureSwipeDivider();
    if (swipeDividerElement) {
      swipeDividerElement.style.display = "none";
    }
    if (next) {
      for (const paneKey of ["left", "right"]) {
        const paneState = getComparatorPaneVisual(paneKey);
        if (!paneState) {
          continue;
        }
        paneState.imagery.brightness = imageryVisual.brightness;
        paneState.imagery.contrast = imageryVisual.contrast;
        paneState.dem.exaggeration = demVisual.exaggeration;
        paneState.dem.hillshadeAlpha = demVisual.hillshadeAlpha;
        paneState.dem.colorMode = String(paneState.dem.colorMode || "gray");
      }
      // Show the window FIRST so divs have non-zero size, THEN create viewers.
      // On Windows/ANGLE, Cesium initialises with a zero-size canvas if the parent
      // div is display:none at creation time — causing a permanently black pane.
      setComparatorWindowsVisible(true);
      setSelectedComparatorPane(comparatorSelectedPane, false);

      // Wait for two animation frames so the browser has fully reflowed the
      // flex layout before Cesium measures the canvas dimensions.
      // On Windows this is more reliable than a fixed setTimeout.
      function _initComparatorAfterReflow() {
        var _cw = document.getElementById("comparatorWindows");
        var _cwW = _cw ? _cw.offsetWidth : 0;
        var _cwH = _cw ? _cw.offsetHeight : 0;

        // If the comparator window still has zero size (common on Windows Qt startup), fall back to window dims
        if (_cwW < 100) _cwW = window.innerWidth || 800;
        if (_cwH < 100) _cwH = window.innerHeight || 600;

        // Count actual active panes
        var _activeKeys = resolveComparatorLayerKeys();
        var _numPanes = _activeKeys.length || 2;

        log("debug", "Comparator init: cwSize=" + _cwW + "x" + _cwH + " panes=" + _numPanes);

        ensureComparatorViewers(_numPanes);
        refreshComparatorLayers();
        bindComparatorSyncHandlers();

        // DEBUG: log pane and canvas sizes immediately after creation
        function _debugPaneSizes(label) {
          for (var _di = 0; _di < _numPanes; _di++) {
            var _pane = document.getElementById("comparatorPane" + _di);
            var _vdiv = document.getElementById("comparatorViewer" + _di);
            var _cv = comparatorViewers[_di] && comparatorViewers[_di].canvas;
            log("debug", "COMP_DEBUG[" + label + "] pane" + _di +
              " pane=" + (_pane ? _pane.offsetWidth + "x" + _pane.offsetHeight : "null") +
              " active=" + (_pane ? _pane.classList.contains("active") : "?") +
              " vdiv=" + (_vdiv ? _vdiv.offsetWidth + "x" + _vdiv.offsetHeight : "null") +
              " canvas=" + (_cv ? _cv.width + "x" + _cv.height : "null") +
              " clientCanvas=" + (_cv ? _cv.clientWidth + "x" + _cv.clientHeight : "null"));
          }
          var _cw2 = document.getElementById("comparatorWindows");
          log("debug", "COMP_DEBUG[" + label + "] cwRoot=" +
            (_cw2 ? _cw2.offsetWidth + "x" + _cw2.offsetHeight + " display=" + getComputedStyle(_cw2).display : "null"));
        }

        _debugPaneSizes("immediate");
        setTimeout(function() { _debugPaneSizes("50ms"); }, 50);
        setTimeout(function() { _debugPaneSizes("300ms"); }, 300);

        // Force canvas to fill pane — Cesium initialises at 300x150 default if
        // it measures the container before the flex layout fully settles.
        function _forceCanvasFill(v, paneEl) {
          if (!v || !paneEl) return;
          var w = paneEl.offsetWidth;
          var h = paneEl.offsetHeight;
          if (w > 10 && h > 10 && v.canvas) {
            v.canvas.style.width  = w + "px";
            v.canvas.style.height = h + "px";
            v.canvas.width  = w;
            v.canvas.height = h;
          }
          try { v.resize(); } catch(_) {}
          if (v.scene) v.scene.requestRender();
        }

        function _resizeAllPanes() {
          for (var _ri = 0; _ri < _numPanes; _ri++) {
            var _rpane = document.getElementById("comparatorPane" + _ri);
            _forceCanvasFill(comparatorViewers[_ri], _rpane);
          }
        }

        // Multiple passes — Windows ANGLE needs several frames to settle
        setTimeout(_resizeAllPanes, 0);
        setTimeout(_resizeAllPanes, 80);
        setTimeout(function() { _resizeAllPanes(); _debugPaneSizes("100ms-post-resize"); }, 100);
        setTimeout(_resizeAllPanes, 250);
        setTimeout(_resizeAllPanes, 600);
        setTimeout(_resizeAllPanes, 1200);

        const bounds = activeTileBounds || lastLoadedBounds;
        if (bounds && typeof comparatorViewers !== "undefined") {
          const rect = Cesium.Rectangle.fromDegrees(bounds.west, bounds.south, bounds.east, bounds.north);
          comparatorViewers.forEach(function(v) {
            if (v) focusComparatorViewerToRectangle(v, "imagery", rect);
          });
        }
      }

      // Two rAF passes guarantee the browser has painted at least once
      requestAnimationFrame(function () {
        requestAnimationFrame(_initComparatorAfterReflow);
      });
    } else {
      setComparatorWindowsVisible(false);
      setStatus("Comparator disabled.");
    }
    applySwipeComparatorSplit();
  }

  // ═══════════════════════════════════════════════════════════════════════════
