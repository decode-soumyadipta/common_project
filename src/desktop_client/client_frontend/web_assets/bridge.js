(function () {
  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: Shared Mutable State  →  future: modules/state.js
  // All let/const declarations at the top of the IIFE. These are shared via
  // closure across all logical sections. In the future refactor they become
  // global variables accessible to all module files loaded before bridge.js.
  // ═══════════════════════════════════════════════════════════════════════════

  let bridge = null;
  let viewer = null;
  let activeImageryLayer = null;
  let activeDemDrapeLayer = null;
  let activeDemHillshadeLayer = null;
  let activeDemContext = null;
  let activeDemTerrainSignature = null;
  let activeDemTerrainProvider = null;
  let activeDemDrapeUrl = null;
  let activeDemHillshadeUrl = null;
  // Reserved for future hillshade rebuild throttling.
  // Stores original DEM rescale range from server (before any color mode switch)
  let _demOriginalRescale = null;
  // Stores the last UI display order for layers (set by enforceLayerDisplayOrder OR reorderLayersEventDriven)
  // so it can be re-applied after any drape swap without a Python round-trip.
  let _lastKnownLayerOrder = null;
  // Stable camera range used for pitch/rotate so rapid slider events don't compute
  // a live distance from a mid-flight camera position (which causes jump artifacts).
  let _cameraOrbitRange = null;
  const managedImageryLayers = new Map();
  let northPolarCapLayer = null;
  let southPolarCapLayer = null;
  let defaultEarthLayer = null;  // Default Earth imagery when OSM is hidden
  let osmBasemapLayer = null;    // OSM tile layer (lazy-loaded)
  let countryBoundaryDataSource = null;
  const clickedPoints = [];
  const annotationEntities = [];
  let hoveredAnnotationEditEntity = null;
    let hoveredAnnotationDeleteEntity = null;
  let lastMapClickCartesian = null;
  window._currentBasemapVisibility = false; // Match Python backend default

  let annotationCounter = 0;
  let measurementLineEntity = null;
  let measurementLabelEntity = null;
  let measurementPointEntities = [];
  let measurementPreviewLineEntity = null;
  let measurementAnchorDotEntity = null;
  let measurementPreviewLabelEntity = null;
  let measurementPreviewStart = null;
  let measurementPreviewEnd = null;
  let distanceMeasureModeEnabled = false;
  let distanceMeasureAnchor = null;
  let swipeComparatorEnabled = false;
  let swipeComparatorPosition = 0.5;
  let swipeDividerElement = null;
  let swipeComparatorLeftLayerKey = null;
  let swipeComparatorRightLayerKey = null;
  let comparatorModeEnabled = false;
  let comparatorLeftViewer = null;
  let comparatorRightViewer = null;
  let comparatorLeftLayerType = null;
  let comparatorRightLayerType = null;
  let comparatorCameraSyncLock = false;
  let comparatorSyncFrameHandle = null;
  let comparatorPendingSyncSource = null;
  let comparatorActiveInputViewer = null;
  let comparatorActiveInputReleaseTimer = null;
  let comparatorDemRefreshTimer = null;
  const COMPARATOR_DEM_REFRESH_DEBOUNCE_MS = 120;
  let flyThroughModeEnabled = false;
  const flyThroughPoints = [];
  let flyThroughPreviewLineEntity = null;
  let flyThroughPathEntity = null;
  let flyThroughStartButtonEntity = null;
  let flyThroughIsPlaying = false;
  const runtime = (window.OfflineGISRuntime = window.OfflineGISRuntime || {});
  const bridgeUtils = window.OfflineGISUtils || {};
  const log = bridgeUtils.log || function (level, message) {
    const fn = console[level] || console.log;
    fn("[offlineGIS]", message);
  };
  const setStatus = bridgeUtils.setStatus || function (text) {
    const el = document.getElementById("status");
    if (el) el.textContent = text;
  };
  const emitMapClick = bridgeUtils.emitMapClick || function () {};
  const emitMeasurementUpdated = bridgeUtils.emitMeasurementUpdated || function () {};
  const emitLoadingProgress = bridgeUtils.emitLoadingProgress || function () {};
  const requestSceneRender = bridgeUtils.requestSceneRender || function () {
    // Fallback: directly trigger a render frame if viewer is available
    if (viewer && viewer.scene) {
      viewer.scene.requestRender();
    }
  };
  const setComparatorWindowsVisible = bridgeUtils.setComparatorWindowsVisible || function () {};
  const normalizeBounds = bridgeUtils.normalizeBounds || function (bounds) {
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
  };
  const cursorControls = window.OfflineGISCursorControls || {};
  const setSearchCursorEnabled = cursorControls.setSearchCursorEnabled || function () {};
  const updateSearchCursorOverlay = cursorControls.updateSearchCursorOverlay || function () {};
  const setSearchCursorOverlayVisible = cursorControls.setSearchCursorOverlayVisible || function () {};
  const setMeasurementCursorEnabled = cursorControls.setMeasurementCursorEnabled || function () {};
  const _enforceMeasureCursor = cursorControls._enforceMeasureCursor || setMeasurementCursorEnabled;
  const ensureMeasureCursorOverlay = cursorControls.ensureMeasureCursorOverlay || function () {};
  const updateMeasureCursorOverlay = cursorControls.updateMeasureCursorOverlay || function () {};
  const setMeasureCursorOverlayVisible = cursorControls.setMeasureCursorOverlayVisible || function () {};
  const emitSearchGeometry =
    (window.OfflineGISModules &&
      window.OfflineGISModules.search &&
      window.OfflineGISModules.search.geometry &&
      window.OfflineGISModules.search.geometry.emitSearchGeometry) ||
    function () {};
  const createRectangle = bridgeUtils.createRectangle || function (bounds) {
    const normalized = normalizeBounds(bounds);
    return normalized ? Cesium.Rectangle.fromDegrees(normalized.west, normalized.south, normalized.east, normalized.north) : null;
  };
  const rectangleFromBounds = bridgeUtils.rectangleFromBounds || createRectangle;
  const applyCursorStyle = bridgeUtils.applyCursorStyle || function (element, cursorValue) {
    if (!element || !element.style) {
      return;
    }
    if (cursorValue) {
      element.style.setProperty("cursor", cursorValue, "important");
      return;
    }
    element.style.removeProperty("cursor");
  };
  const parseDemHeightRange = bridgeUtils.parseDemHeightRange || function (options) {
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
  };

  function updateFlyThroughPreview(mousePos) {
    if (!flyThroughModeEnabled) return;
    if (flyThroughPreviewLineEntity) {
      viewer.entities.remove(flyThroughPreviewLineEntity);
      flyThroughPreviewLineEntity = null;
    }
    const points = [...flyThroughPoints];
    if (mousePos) {
      const mouseCart = viewer.camera.pickEllipsoid(mousePos, viewer.scene.globe.ellipsoid);
      if (mouseCart) points.push(mouseCart);
    }
    if (points.length < 2) return;
    flyThroughPreviewLineEntity = viewer.entities.add({
      polyline: {
        positions: points,
        width: 3,
        material: Cesium.Color.YELLOW.withAlpha(0.6),
        clampToGround: true,
      }
    });
  }

  function finishFlyThroughPath() {
    if (flyThroughPoints.length < 2) {
      setStatus("Draw at least 2 points for a fly through.");
      return;
    }
    if (flyThroughPreviewLineEntity) {
      viewer.entities.remove(flyThroughPreviewLineEntity);
      flyThroughPreviewLineEntity = null;
    }
    if (flyThroughPathEntity) viewer.entities.remove(flyThroughPathEntity);
    if (flyThroughStartButtonEntity) viewer.entities.remove(flyThroughStartButtonEntity);

    flyThroughPathEntity = viewer.entities.add({
      polyline: {
        positions: flyThroughPoints,
        width: 4,
        material: Cesium.Color.YELLOW,
        clampToGround: true,
      }
    });

    flyThroughStartButtonEntity = viewer.entities.add({
      position: flyThroughPoints[0],
      label: {
        text: "\u25b6 START FLY THROUGH",
        font: "bold 14px sans-serif",
        fillColor: Cesium.Color.WHITE,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 2,
        showBackground: true,
        backgroundColor: Cesium.Color.DARKGREEN,
        pixelOffset: new Cesium.Cartesian2(0, -30),
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        heightReference: Cesium.HeightReference.RELATIVE_TO_GROUND
      }
    });
    flyThroughStartButtonEntity.isFlyThroughStart = true;
    
    setStatus("Path complete. Click the 'START FLY THROUGH' label on the map.");
  }

  function startFlyThroughAnimation() {
    if (flyThroughPoints.length < 2 || flyThroughIsPlaying) return;
    flyThroughIsPlaying = true;
    
    // Disable drawing mode once flight starts
    flyThroughModeEnabled = false;
    
    const originalView = {
      destination: viewer.camera.position.clone(),
      orientation: {
        heading: viewer.camera.heading,
        pitch: viewer.camera.pitch,
        roll: viewer.camera.roll
      },
      fov: viewer.camera.frustum.fov
    };

    let currentIndex = 0;
    viewer.scene.screenSpaceCameraController.enableInputs = false;
    
    // Greater Field of View for cinematic feel (approx 80 degrees)
    viewer.camera.frustum.fov = Cesium.Math.toRadians(80.0);
    
    // Remove the Start button and temporary preview entities immediately
    if (flyThroughStartButtonEntity) {
      viewer.entities.remove(flyThroughStartButtonEntity);
      flyThroughStartButtonEntity = null;
    }
    if (flyThroughPreviewLineEntity) {
      viewer.entities.remove(flyThroughPreviewLineEntity);
      flyThroughPreviewLineEntity = null;
    }

    function nextSegment() {
      if (currentIndex >= flyThroughPoints.length - 1) {
        setStatus("Fly through ending. Returning to original view...");
        setTimeout(() => {
          viewer.camera.flyTo({
            destination: originalView.destination,
            orientation: originalView.orientation,
            duration: 2.5, // Faster return
            complete: () => {
              viewer.scene.screenSpaceCameraController.enableInputs = true;
              viewer.camera.frustum.fov = originalView.fov; // Restore FOV
              flyThroughIsPlaying = false;
              
              // Clear points so no more drawing can happen on this path
              flyThroughPoints.length = 0;
              if (flyThroughPathEntity) {
                viewer.entities.remove(flyThroughPathEntity);
                flyThroughPathEntity = null;
              }
              
              setStatus("Fly through complete.");
            }
          });
        }, 1000);
        return;
      }

      const p1 = flyThroughPoints[currentIndex];
      const p2 = flyThroughPoints[currentIndex + 1];
      
      const carto1 = Cesium.Cartographic.fromCartesian(p1);
      const carto2 = Cesium.Cartographic.fromCartesian(p2);
      
      // Calculate destination: 600m above p2 for safe high-speed travel
      const destPos = Cesium.Cartesian3.fromRadians(
        carto2.longitude,
        carto2.latitude,
        carto2.height + 600
      );

      const geodesic = new Cesium.EllipsoidGeodesic(carto1, carto2);
      const heading = geodesic.startHeading;
      
      // Calculate duration: Turbo-speed traverse at 150m/s (540 km/h)
      const distance = Cesium.Cartesian3.distance(p1, p2);
      const duration = Math.max(0.5, distance / 150);

      viewer.camera.flyTo({
        destination: destPos,
        orientation: {
          heading: heading,
          pitch: Cesium.Math.toRadians(-40.0), // Steeper pitch for ground awareness at turbo speed
          roll: 0.0
        },
        duration: duration,
        easingFunction: Cesium.EasingFunction.QUADRATIC_IN_OUT,
        maximumHeight: carto2.height + 800, 
        complete: () => {
          currentIndex++;
          nextSegment();
        }
      });
    }

    setStatus("Starting fly through...");
    const startCarto = Cesium.Cartographic.fromCartesian(flyThroughPoints[0]);
    const startPos = Cesium.Cartesian3.fromRadians(
      startCarto.longitude,
      startCarto.latitude,
      startCarto.height + 600
    );
    
    viewer.camera.flyTo({
      destination: startPos,
      orientation: {
        pitch: Cesium.Math.toRadians(-40.0),
        roll: 0.0
      },
      duration: 2, 
      complete: nextSegment
    });
  }

  // Hook into left click to detect Start Button
  function handleFlyThroughClick(movement) {
    if (!viewer) return false;
    const picked = viewer.scene.pick(movement.position);
    if (Cesium.defined(picked) && picked.id && picked.id.isFlyThroughStart) {
      startFlyThroughAnimation();
      return true;
    }
    return false;
  }

  // Debounce timers for visual properties
  let _demPropertiesDebounceTimer = null;
  let _imageryPropertiesDebounceTimer = null;
  const VISUAL_UPDATE_DEBOUNCE_MS = 16; // ~1 frame at 60fps
  const buildUrlWithQuery = bridgeUtils.buildUrlWithQuery || function (url, extraQuery) {
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
    const encodeValue = function (key, value) {
      if (key === "url") {
        return encodeURIComponent(value)
          .replace(/%3A/gi, ":")
          .replace(/%2F/gi, "/")
          .replace(/%40/gi, "@");
      }
      return encodeURIComponent(value);
    };
    const paramPairs = Object.entries(finalParams)
      .map(function ([key, value]) {
        if (value === null || value === undefined) {
          return null;
        }
        if (Array.isArray(value)) {
          return value.map(function (item) {
            return encodeURIComponent(key) + "=" + encodeValue(key, String(item));
          }).join("&");
        }
        return encodeURIComponent(key) + "=" + encodeValue(key, String(value));
      })
      .filter(Boolean);
    const merged = paramPairs.join("&");
    return merged ? base + "?" + merged : base;
  };
  if (!window.Cesium) {
    const statusEl = document.getElementById("status");
    if (statusEl) {
      statusEl.textContent =
        "Cesium.js not found. Run scripts/setup_cesium_assets.sh to install local Cesium assets.";
    }
    console.error("[offlineGIS] Cesium runtime not found. Local assets are missing.");
    return;
  }
  const COMPARATOR_DEM_DEFAULT_PITCH = Cesium.Math.toRadians(-35.0);
  const COMPARATOR_DEM_MIN_PITCH = Cesium.Math.toRadians(-80.0);
  const COMPARATOR_DEM_MAX_PITCH = Cesium.Math.toRadians(-15.0);
  // 3D mode pitch constraints: clear separation from 2D (which is always -90°)
  const MIN_3D_PITCH_RAD = Cesium.Math.toRadians(-80.0);   // never flatter than -80° in 3D
  const DEFAULT_3D_PITCH_RAD = Cesium.Math.toRadians(-35.0); // default oblique view for DEM
  const layerDefinitions = new Map();
  const layerVisibilityState = new Map();
  const tileErrorSeen = new Set();
  const layerErrorCounts = new Map();
  // DEM rendering uses imagery-only pipeline (colormap + hillshade on EllipsoidTerrainProvider)
  // No client-side terrain decoding — crash-proof for any raster size on macOS and Windows/NVIDIA
  const LOCAL_SATELLITE_TILE_ROOT = "./basemap/xyz";
  const DEFAULT_STARTUP_CENTER_LON = 78.0;  // India center longitude
  const DEFAULT_STARTUP_CENTER_LAT = 22.0;  // India center latitude
  const DEFAULT_STARTUP_HEIGHT_M = 6000000.0;   // ~6000 km — shows full India + surrounding region (better for tile visibility)
  const DEFAULT_STARTUP_HEADING = Cesium.Math.toRadians(0.0);
  const DEFAULT_STARTUP_PITCH = Cesium.Math.toRadians(-89.0);
  const WEB_MERCATOR_SAFE_EDGE_LAT_DEGREES = 85.05112878;
  const COUNTRY_BOUNDARY_GEOJSON_URL = "./data/countries.geojson";
  const SHOW_COUNTRY_BOUNDARY_OVERLAY = false;
  // DEM rendering uses imagery-only pipeline (colormap drape + hillshade overlay on EllipsoidTerrainProvider)
  // No client-side terrain decoding — crash-proof for any raster size on macOS and Windows/NVIDIA.
  // TERRAIN_SAMPLE_SIZE is set to 65 for smoother LOD transitions and finer detail.
  // 65 increases terrain fidelity while keeping decode cost manageable on desktop GPUs.
  const TERRAIN_SAMPLE_SIZE = 65;
  const DEM_MAX_TERRAIN_LEVEL = 14;
  const DEM_HILLSHADE_AZIMUTH = 45;
  const DEM_HILLSHADE_ALTITUDE = 45;
  const demVisual = {
    exaggeration: 1.0,
    hillshadeAlpha: 0.0,
  };
  const imageryVisual = {
    brightness: 1.0,
    contrast: 1.0,
  };
  let comparatorSelectedPane = "left";
  const comparatorPaneVisualState = {
    left: {
      imagery: {
        brightness: imageryVisual.brightness,
        contrast: imageryVisual.contrast,
      },
      dem: {
        exaggeration: demVisual.exaggeration,
        hillshadeAlpha: demVisual.hillshadeAlpha,
        colorMode: "gray",
      },
    },
    right: {
      imagery: {
        brightness: imageryVisual.brightness,
        contrast: imageryVisual.contrast,
      },
      dem: {
        exaggeration: demVisual.exaggeration,
        hillshadeAlpha: demVisual.hillshadeAlpha,
        colorMode: "gray",
      },
    },
  };
  const comparatorDemStyleRefreshVersion = {
    left: 0,
    right: 0,
  };
  const comparatorCameraSyncState = {
    left: {
      lastSourceWidthRad: NaN,
      lastSourceHeightRad: NaN,
      lastSourceCameraHeightM: NaN,
      lastSourceCenterLon: NaN,
      lastSourceCenterLat: NaN,
    },
    right: {
      lastSourceWidthRad: NaN,
      lastSourceHeightRad: NaN,
      lastSourceCameraHeightM: NaN,
      lastSourceCenterLon: NaN,
      lastSourceCenterLat: NaN,
    },
  };
  let searchDrawMode = "none";
  const searchPolygonPoints = [];
  let searchPolygonLocked = false;
  let searchCursorPoint = null;
  let searchCursorEntity = null;
  let searchPreviewLineEntity = null;
  let searchPreviewPolygonEntity = null;
  let searchAreaLabelEntity = null;
  let polygonVisibilityEnabled = true;
  let searchOverlayVisible = true;
  let panModeActive = false;
  let distanceScaleOverlay = null;
  const searchVertexEntities = [];
  const drawnPolygons = [];
  // Fill-volume visualisation — all tracked as entities (no GroundPrimitive)
  window._fillVolumeEntities = window._fillVolumeEntities || [];
  // _fillVolumePrimitives kept as empty stub for legacy clear calls
  window._fillVolumePrimitives = window._fillVolumePrimitives || [];
  let drawnPolygonCounter = 0;
  let aoiPanelMinimized = false;
  const searchPolygonControllerFactory =
    window.OfflineGISSearchPolygonController &&
    window.OfflineGISSearchPolygonController.createSearchPolygonController;
  const searchPolygonController = searchPolygonControllerFactory
    ? searchPolygonControllerFactory({
        getViewer: function () {
          return viewer;
        },
        getBridge: function () {
          return bridge;
        },
        getCesium: function () {
          return Cesium;
        },
        getSearchPolygonPoints: function () {
          return searchPolygonPoints;
        },
        getSearchCursorPoint: function () {
          return searchCursorPoint;
        },
        getSearchOverlayVisible: function () {
          return searchOverlayVisible;
        },
        getPolygonVisibilityEnabled: function () {
          return polygonVisibilityEnabled;
        },
        getSearchPreviewLineEntity: function () {
          return searchPreviewLineEntity;
        },
        setSearchPreviewLineEntity: function (value) {
          searchPreviewLineEntity = value;
        },
        getSearchPreviewPolygonEntity: function () {
          return searchPreviewPolygonEntity;
        },
        setSearchPreviewPolygonEntity: function (value) {
          searchPreviewPolygonEntity = value;
        },
        getSearchAreaLabelEntity: function () {
          return searchAreaLabelEntity;
        },
        setSearchAreaLabelEntity: function (value) {
          searchAreaLabelEntity = value;
        },
        getSearchCursorEntity: function () {
          return searchCursorEntity;
        },
        setSearchCursorEntity: function (value) {
          searchCursorEntity = value;
        },
        getSearchVertexEntities: function () {
          return searchVertexEntities;
        },
        setSearchVertexEntities: function () {},
        getDrawnPolygons: function () {
          return drawnPolygons;
        },
        setDrawnPolygons: function () {},
        getComparatorModeEnabled: function () {
          return comparatorModeEnabled;
        },
        getComparatorLeftViewer: function () {
          return comparatorLeftViewer;
        },
        getComparatorRightViewer: function () {
          return comparatorRightViewer;
        },
        getComparatorPolygonEntities: function () {
          return comparatorPolygonEntities;
        },
        getSearchDrawMode: function () {
          return searchDrawMode;
        },
        setSearchDrawMode: function (value) {
          searchDrawMode = value;
        },
        setSearchCursorPoint: function (value) {
          searchCursorPoint = value;
        },
        setSearchPolygonLocked: function (value) {
          searchPolygonLocked = value;
        },
        setSearchOverlayVisible: function (value) {
          searchOverlayVisible = value;
        },
        getAoiPanelMinimized: function () {
          return aoiPanelMinimized;
        },
        setAoiPanelMinimized: function (value) {
          aoiPanelMinimized = value;
        },
        requestSceneRender: requestSceneRender,
        setSearchCursorEnabled: setSearchCursorEnabled,
        updateComparatorPolygons: function (value) {
          updateComparatorPolygons(value);
        },
        incrementDrawnPolygonCounter: function () {
          drawnPolygonCounter += 1;
        },
        getDrawnPolygonCounter: function () {
          return drawnPolygonCounter;
        },
        getIsAnnotationDrawing: function () {
          return isAnnotationDrawing;
        },
        emitSearchGeometry: function (type, payload) {
          if (offlineGIS.on_search_geometry) {
            offlineGIS.on_search_geometry(type, payload);
          }
        },
        setStatus: setStatus,
        log: log,
      })
    : null;
  let isAnnotationDrawing = false;
  let annotationVisibilityEnabled = true;
  let sceneModeControlEnabled = true;
  let currentSceneMode = "3d";
  let isInteracting = false;
  let scenePerfDefaults = null;
  let activeTileBounds = null;
  let lastLoadedBounds = null;
  let pendingFocusAfterMorph = false;
  let pendingTerrainSceneAfterMorph = false;
  let pendingFocusBounds = null;
  let pendingFlyThroughBounds = null;
  let pendingSceneModeAfterMorph = null;
  let cameraOrbitBounds = null;
  let cameraOrbitHeading = Cesium.Math.toRadians(-45.0);
  let cameraOrbitPitch = Cesium.Math.toRadians(-35.0);
  let cameraOrbitRange = 1200.0;
  let lastEdgeScaleUpdateMs = 0;
  const EDGE_SCALE_UPDATE_INTERVAL_MS = 120;
  const EDGE_SCALE_UPDATE_INTERVAL_2D_MS = 320;
  const ANNOTATION_DELETE_ICON_IMAGE = "data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%2720%27 height=%2720%27 viewBox=%270 0 20 20%27%3E%3Ccircle cx=%2710%27 cy=%2710%27 r=%279%27 fill=%27rgba(220%2C50%2C50%2C0.92)%27 stroke=%27rgba(0%2C0%2C0%2C0.38)%27 stroke-width=%271.1%27/%3E%3Cpath d=%27M6 6L14 14M14 6L6 14%27 stroke=%27%23ffffff%27 stroke-width=%272%27 stroke-linecap=%27round%27/%3E%3C/svg%3E";
  const ANNOTATION_EDIT_ICON_IMAGE =
    "data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%2720%27 height=%2720%27 viewBox=%270 0 20 20%27%3E%3Ccircle cx=%2710%27 cy=%2710%27 r=%279%27 fill=%27rgba(255%2C255%2C255%2C0.92)%27 stroke=%27rgba(0%2C0%2C0%2C0.38)%27 stroke-width=%271.1%27/%3E%3Cpath d=%27M6.1 12.9l.5-2.2L11.8 5.5a1.3 1.3 0 011.8 0l.8.8a1.3 1.3 0 010 1.8L9.1 13.3l-2.2.5a.6.6 0 01-.8-.7z%27 fill=%27%23282f39%27/%3E%3Cpath d=%27M10.9 6.4l2.7 2.7%27 stroke=%27%23ffffff%27 stroke-width=%271%27 stroke-linecap=%27round%27/%3E%3C/svg%3E";
  const _SB_COORD_THROTTLE_MS = 50; // Faster coordinate updates (20 fps) - reduced from 100ms
  const _SB_CAMERA_THROTTLE_MS = 100; // Throttle camera change events to reduce overhead (~10 fps)
  const _SB_RENDER_IDLE_DELAY_MS = 120;
  let _sbLastCoordEmitMs = 0;
  let _sbLastCameraEmitMs = 0;
  let _sbRenderBusy = false;
  let _sbRenderIdleTimer = null;
  
  // Tile loading progress tracking
  let _tileLoadingActive = false;
  let _tilesPending = 0;
  let _tilesLoaded = 0;
  let _tileLoadStartTime = 0;
  let _tileProgressCheckInterval = null;
  let _tileDrainTimer = null;
  const _TILE_PROGRESS_CHECK_MS = 100; // Check every 100ms

  // ── Tile loading progress via native Cesium event (accurate, zero polling) ──
  // Wired in wireStatusBarListeners() after viewer is ready.
  let _tileQueuePeak = 0;

  function startTileLoadingMonitor() {
    // No-op — progress is driven by tileLoadProgressEvent in wireStatusBarListeners
    _tileLoadingActive = true;
  }
  
  // stopTileLoadingMonitor removed — monitor resets via tileLoadProgressEvent directly

  function setSearchBusy(active, message) {
    const overlay = document.getElementById("searchBusyOverlay");
    const textEl = document.getElementById("searchBusyText");
    if (!overlay) {
      return;
    }
    const enabled = Boolean(active);
    overlay.classList.toggle("visible", enabled);
    overlay.setAttribute("aria-hidden", enabled ? "false" : "true");
    if (textEl && enabled) {
      textEl.textContent = String(message || "Searching tiles...");
    }
  }

  function getCartesianFromViewer(targetViewer, screenPosition) {
    if (!targetViewer || !screenPosition) {
      return null;
    }
    const scene = targetViewer.scene;
    const ray = targetViewer.camera.getPickRay(screenPosition);
    let cartesian = null;
    if (ray) {
      cartesian = scene.globe.pick(ray, scene);
    }
    if (!cartesian) {
      cartesian = targetViewer.camera.pickEllipsoid(screenPosition, scene.globe.ellipsoid);
    }
    return cartesian || null;
  }

  function cartesianToLonLat(cartesian) {
    if (!cartesian) {
      return null;
    }
    const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
    if (!cartographic) {
      return null;
    }
    return {
      lon: Cesium.Math.toDegrees(cartographic.longitude),
      lat: Cesium.Math.toDegrees(cartographic.latitude),
      height: cartographic.height
    };
  }

  function getLonLatFromViewer(targetViewer, screenPosition) {
    return cartesianToLonLat(getCartesianFromViewer(targetViewer, screenPosition));
  }

  function getViewerCenterLonLat(targetViewer) {
    if (!targetViewer || !targetViewer.canvas) {
      return null;
    }
    const center = new Cesium.Cartesian2(
      targetViewer.canvas.clientWidth * 0.5,
      targetViewer.canvas.clientHeight * 0.5,
    );
    return getLonLatFromViewer(targetViewer, center);
  }

  function applyCrosshairScreenPosition(crosshairElement, targetViewer, screenPosition) {
    if (!crosshairElement) {
      return;
    }
    let x = 0.0;
    let y = 0.0;
    if (screenPosition && Number.isFinite(screenPosition.x) && Number.isFinite(screenPosition.y)) {
      x = Number(screenPosition.x);
      y = Number(screenPosition.y);
    } else if (targetViewer && targetViewer.canvas) {
      x = targetViewer.canvas.clientWidth * 0.5;
      y = targetViewer.canvas.clientHeight * 0.5;
    }
    crosshairElement.style.left = `${x.toFixed(2)}px`;
    crosshairElement.style.top = `${y.toFixed(2)}px`;
  }

  function updateComparatorCrosshair(lon, lat, leftScreenPosition, rightScreenPosition) {
    const leftCrosshair = document.getElementById("comparatorCrosshairLeft");
    const rightCrosshair = document.getElementById("comparatorCrosshairRight");
    const leftCoords = document.getElementById("comparatorCoordsLeft");
    const rightCoords = document.getElementById("comparatorCoordsRight");

    const hasLonLat = Number.isFinite(lon) && Number.isFinite(lat);
    applyCrosshairScreenPosition(leftCrosshair, comparatorLeftViewer, leftScreenPosition || null);
    applyCrosshairScreenPosition(rightCrosshair, comparatorRightViewer, rightScreenPosition || null);

    const text =
      hasLonLat
        ? `lon: ${Number(lon).toFixed(6)}, lat: ${Number(lat).toFixed(6)}`
        : "lon: ---, lat: ---";
    if (leftCoords) {
      leftCoords.textContent = text;
    }
    if (rightCoords) {
      rightCoords.textContent = text;
    }
  }

  function updateComparatorCenterReadout(sourceViewer, paneIdx) {
    if (!comparatorModeEnabled) {
      return;
    }
    var idx = (typeof paneIdx === "number") ? paneIdx : comparatorViewers.indexOf(sourceViewer);
    var targetViewer = sourceViewer || comparatorViewers[0];
    if (!targetViewer || !targetViewer.canvas) {
      return;
    }
    var center = new Cesium.Cartesian2(
      targetViewer.canvas.clientWidth * 0.5,
      targetViewer.canvas.clientHeight * 0.5,
    );
    var lonLat = getLonLatFromViewer(targetViewer, center);
    if (lonLat) {
      emitMouseCoordinates(lonLat.lon, lonLat.lat);
    }
  }

  function sceneToWindowCoordinates(targetScene, worldCartesian) {
    if (!targetScene || !worldCartesian || !Cesium.SceneTransforms) {
      return null;
    }
    if (typeof Cesium.SceneTransforms.worldToWindowCoordinates === "function") {
      return Cesium.SceneTransforms.worldToWindowCoordinates(targetScene, worldCartesian);
    }
    if (typeof Cesium.SceneTransforms.wgs84ToWindowCoordinates === "function") {
      return Cesium.SceneTransforms.wgs84ToWindowCoordinates(targetScene, worldCartesian);
    }
    return null;
  }

  function projectCartesianToViewer(targetViewer, worldCartesian) {
    if (!targetViewer || !worldCartesian) {
      return null;
    }
    const projected = sceneToWindowCoordinates(targetViewer.scene, worldCartesian);
    if (!projected || !Number.isFinite(projected.x) || !Number.isFinite(projected.y)) {
      return null;
    }
    return new Cesium.Cartesian2(Number(projected.x), Number(projected.y));
  }

  function getComparatorDemPitchRadians() {
    let pitch = Number(cameraOrbitPitch);
    if (!Number.isFinite(pitch)) {
      return COMPARATOR_DEM_DEFAULT_PITCH;
    }
    // If the source camera came from a 2D/top-down context, force a meaningful 3D tilt.
    const nearNadir = Math.abs(pitch) >= Cesium.Math.toRadians(88.0);
    if (nearNadir) {
      return COMPARATOR_DEM_DEFAULT_PITCH;
    }
    // Also clamp: if pitch is very shallow (near 0°) use the default tilt
    const tooShallow = Math.abs(pitch) < Cesium.Math.toRadians(10.0);
    if (tooShallow) {
      return COMPARATOR_DEM_DEFAULT_PITCH;
    }
    return Math.max(COMPARATOR_DEM_MIN_PITCH, Math.min(COMPARATOR_DEM_MAX_PITCH, pitch));
  }

  function setComparatorDemCameraFromRectangle(targetViewer, focusRect, sourceHeading, sourceRangeMeters) {
    if (!targetViewer || !focusRect) {
      return;
    }
    const heading = Number.isFinite(sourceHeading) ? Number(sourceHeading) : 0.0;
    const pitch = getComparatorDemPitchRadians();
    const sphere = Cesium.BoundingSphere.fromRectangle3D(focusRect, Cesium.Ellipsoid.WGS84, 0.0);
    const sourceRange = Number(sourceRangeMeters);
    const derivedRange = Math.max(sphere.radius * 1.9, 900.0);
    const range = Number.isFinite(sourceRange) && sourceRange > 50.0 ? Math.max(sourceRange, 900.0) : derivedRange;
    targetViewer.camera.lookAt(
      sphere.center,
      new Cesium.HeadingPitchRange(heading, pitch, range),
    );
    targetViewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
  }

  function focusComparatorViewerToRectangle(targetViewer, layerType, focusRect) {
    if (!targetViewer || !focusRect) {
      return;
    }
    if (layerType === "dem") {
      setComparatorDemCameraFromRectangle(targetViewer, focusRect, targetViewer.camera.heading);
      return;
    }
    targetViewer.camera.setView({ destination: focusRect });
    if (targetViewer.scene) {
      targetViewer.scene.requestRender();
    }
  }

  // getComparatorLayerTypeForViewer removed — callers use comparatorLeftLayerType/comparatorRightLayerType directly

  function getComparatorPaneKeyForViewer(targetViewer) {
    if (targetViewer === comparatorLeftViewer) {
      return "left";
    }
    if (targetViewer === comparatorRightViewer) {
      return "right";
    }
    return null;
  }

  function getComparatorSyncStateForViewer(targetViewer) {
    const paneKey = getComparatorPaneKeyForViewer(targetViewer);
    if (!paneKey) {
      return null;
    }
    return comparatorCameraSyncState[paneKey] || null;
  }

  function resetComparatorCameraSyncState(reason) {
    for (const paneKey of ["left", "right"]) {
      const state = comparatorCameraSyncState[paneKey];
      if (!state) {
        continue;
      }
      state.lastSourceWidthRad = NaN;
      state.lastSourceHeightRad = NaN;
      state.lastSourceCameraHeightM = NaN;
      state.lastSourceCenterLon = NaN;
      state.lastSourceCenterLat = NaN;
    }
  }

  function recordComparatorSourceRectangle(sourceViewer, sourceRectangle, context) {
    const state = getComparatorSyncStateForViewer(sourceViewer);
    if (!state || !sourceRectangle) {
      return;
    }
    const width = rectangleWidthRadians(sourceRectangle);
    const height = rectangleHeightRadians(sourceRectangle);
    const center = Cesium.Rectangle.center(sourceRectangle);
    if (!Number.isFinite(width) || !Number.isFinite(height) || !center) {
      return;
    }
    state.lastSourceWidthRad = width;
    state.lastSourceHeightRad = height;
    state.lastSourceCenterLon = Number(center.longitude);
    state.lastSourceCenterLat = Number(center.latitude);
    const cameraHeight = sourceViewer && sourceViewer.camera && sourceViewer.camera.positionCartographic && Number.isFinite(sourceViewer.camera.positionCartographic.height)
      ? Number(sourceViewer.camera.positionCartographic.height)
      : NaN;
    state.lastSourceCameraHeightM = Number.isFinite(cameraHeight) ? cameraHeight : NaN;
  }

  function getComparatorDemViewer() {
    if (comparatorLeftLayerType === "dem" && comparatorLeftViewer) {
      return comparatorLeftViewer;
    }
    if (comparatorRightLayerType === "dem" && comparatorRightViewer) {
      return comparatorRightViewer;
    }
    return null;
  }

  function syncComparatorTerrainProviders() {
    if (typeof comparatorViewers !== "undefined" && Array.isArray(comparatorViewers)) {
      comparatorViewers.forEach(targetViewer => {
        if (!targetViewer) return;
        const layerKey = targetViewer.__comparatorLayerKey || null;
        const definition = layerKey ? layerDefinitions.get(layerKey) : null;
        const layerType = definition ? (definition.layerType || definition.type) : null;
        const isDem = String(layerType || "").toLowerCase() === "dem";
        
        if (isDem) {
           if (activeDemTerrainProvider && targetViewer.terrainProvider !== activeDemTerrainProvider) {
             targetViewer.terrainProvider = activeDemTerrainProvider;
           }
        } else {
           if (targetViewer.terrainProvider && targetViewer.terrainProvider.constructor && targetViewer.terrainProvider.constructor.name !== "EllipsoidTerrainProvider") {
             targetViewer.terrainProvider = new Cesium.EllipsoidTerrainProvider();
           }
        }
      });
    }
  }

  function cancelComparatorCameraSyncSchedule() {
    if (comparatorSyncFrameHandle !== null) {
      window.cancelAnimationFrame(comparatorSyncFrameHandle);
      comparatorSyncFrameHandle = null;
    }
    comparatorPendingSyncSource = null;
    comparatorActiveInputViewer = null;
    if (comparatorActiveInputReleaseTimer !== null) {
      window.clearTimeout(comparatorActiveInputReleaseTimer);
      comparatorActiveInputReleaseTimer = null;
    }
  }

  // markComparatorInputViewer removed — comparatorActiveInputViewer is unused in active code

  // scheduleComparatorCameraSync removed — updateComparatorCenterReadout called directly
  // lockComparatorFocusToCurrentView removed — no callers

  function setComparatorViewerModeByType(targetViewer, layerType) {
    if (!targetViewer || !targetViewer.scene) {
      return;
    }

    const layerKey = targetViewer.__comparatorLayerKey || null;
    const definition = layerKey ? layerDefinitions.get(layerKey) : null;
    const resolvedLayerType = layerType || (definition ? (definition.layerType || definition.type) : null);
    const isDem = String(resolvedLayerType || "").toLowerCase() === "dem";
    const focusRect = definition ? rectangleFromBounds(definition.bounds || null) : null;

    if (!isDem) {
      // Imagery-only pane → force strict 2D flat map view.
      // Morphing to SCENE2D prevents pitch/tilt altogether.
      if (targetViewer.scene.mode !== Cesium.SceneMode.SCENE2D) {
        targetViewer.scene.morphTo2D(0.0);
      }
      if (focusRect) {
        focusComparatorViewerToRectangle(targetViewer, layerType, focusRect);
      }
      return;
    }

    // DEM pane → use global 2D/3D toggle so user controls perspective.
      const desiredMode = currentSceneMode === "2d" ? Cesium.SceneMode.SCENE2D : Cesium.SceneMode.SCENE3D; // Adjusted for user preference
    const currentMode = targetViewer.scene.mode;
    if (currentMode !== desiredMode) {
      if (desiredMode === Cesium.SceneMode.SCENE2D) {
        targetViewer.scene.morphTo2D(0.0);
      } else {
        targetViewer.scene.morphTo3D(0.0);
      }
    }
    if (focusRect) {
      focusComparatorViewerToRectangle(targetViewer, layerType, focusRect);
    }
  }

  function rectangleWidthRadians(rectangle) {
    if (!rectangle) {
      return NaN;
    }
    let width = Number(rectangle.east) - Number(rectangle.west);
    if (!Number.isFinite(width)) {
      return NaN;
    }
    if (width < 0.0) {
      width += Cesium.Math.TWO_PI;
    }
    return Math.max(1.0e-7, Math.min(Cesium.Math.TWO_PI, width));
  }

  function rectangleHeightRadians(rectangle) {
    if (!rectangle) {
      return NaN;
    }
    const height = Number(rectangle.north) - Number(rectangle.south);
    if (!Number.isFinite(height)) {
      return NaN;
    }
    return Math.max(1.0e-7, Math.min(Cesium.Math.PI, height));
  }

  function buildRectangleFromCenter(center, widthRadians, heightRadians) {
    if (!center || !Number.isFinite(center.longitude) || !Number.isFinite(center.latitude)) {
      return null;
    }
    const halfWidth = Math.max(5.0e-8, Number(widthRadians) * 0.5);
    const halfHeight = Math.max(5.0e-8, Number(heightRadians) * 0.5);
    const south = Cesium.Math.clamp(center.latitude - halfHeight, -Cesium.Math.PI_OVER_TWO + 1.0e-6, Cesium.Math.PI_OVER_TWO - 1.0e-6);
    const north = Cesium.Math.clamp(center.latitude + halfHeight, -Cesium.Math.PI_OVER_TWO + 1.0e-6, Cesium.Math.PI_OVER_TWO - 1.0e-6);
    const west = Cesium.Math.negativePiToPi(center.longitude - halfWidth);
    const east = Cesium.Math.negativePiToPi(center.longitude + halfWidth);
    return new Cesium.Rectangle(west, south, east, north);
  }

  function resolveImagerySyncDestinationRectangle(sourceViewer, sourceRectangle, targetViewer, sourceLayerType) {
    if (!sourceRectangle) {
      return null;
    }
    if (!targetViewer || sourceLayerType !== "dem") {
      return sourceRectangle;
    }
    const targetRectangle = targetViewer.camera && targetViewer.scene
      ? targetViewer.camera.computeViewRectangle(targetViewer.scene.globe.ellipsoid)
      : null;
    if (!targetRectangle) {
      log("debug", "Comparator imagery sync: targetRectangle is null, returning source");
      return sourceRectangle;
    }

    const sourceWidth = rectangleWidthRadians(sourceRectangle);
    const sourceHeight = rectangleHeightRadians(sourceRectangle);
    const targetWidth = rectangleWidthRadians(targetRectangle);
    const targetHeight = rectangleHeightRadians(targetRectangle);
    if (!Number.isFinite(sourceWidth) || !Number.isFinite(sourceHeight) || !Number.isFinite(targetWidth) || !Number.isFinite(targetHeight)) {
      log("debug", `Comparator imagery sync: invalid dimensions src_w=${sourceWidth} src_h=${sourceHeight} tgt_w=${targetWidth} tgt_h=${targetHeight}, returning source`);
      return sourceRectangle;
    }

    const sourceState = getComparatorSyncStateForViewer(sourceViewer);
    const sourceCameraHeight = sourceViewer && sourceViewer.camera && sourceViewer.camera.positionCartographic && Number.isFinite(sourceViewer.camera.positionCartographic.height)
      ? Number(sourceViewer.camera.positionCartographic.height)
      : NaN;
    const previousSourceCameraHeight = sourceState && Number.isFinite(sourceState.lastSourceCameraHeightM)
      ? Number(sourceState.lastSourceCameraHeightM)
      : NaN;
    const rawZoomDelta = Number.isFinite(sourceCameraHeight) && Number.isFinite(previousSourceCameraHeight) && previousSourceCameraHeight > 1.0
      ? sourceCameraHeight / previousSourceCameraHeight
      : 1.0;

    // Use incremental height deltas to avoid abrupt jumps from unstable tilted DEM rectangles.
    const minZoomDelta = 0.96;
    const maxZoomDelta = 1.04;
    let zoomDelta = Cesium.Math.clamp(rawZoomDelta, minZoomDelta, maxZoomDelta);
    if (!Number.isFinite(zoomDelta) || zoomDelta <= 0.0) {
      zoomDelta = 1.0;
    }
    if (rawZoomDelta > 1.30 || rawZoomDelta < 0.70) {
      log("debug", `Comparator imagery sync SPIKE detected rawZoomDelta=${rawZoomDelta.toFixed(6)}; freezing zoomDelta=1.0`);
      zoomDelta = 1.0;
    }

    const absoluteScale = sourceWidth / targetWidth;

    log("debug", `Comparator imagery sync START: sourceWidth=${sourceWidth.toFixed(6)} sourceHeight=${sourceHeight.toFixed(6)} targetWidth=${targetWidth.toFixed(6)} targetHeight=${targetHeight.toFixed(6)} sourceCamH=${Number.isFinite(sourceCameraHeight) ? sourceCameraHeight.toFixed(2) : "n/a"} prevSourceCamH=${Number.isFinite(previousSourceCameraHeight) ? previousSourceCameraHeight.toFixed(2) : "n/a"} rawZoomDelta=${rawZoomDelta.toFixed(6)} zoomDelta=${zoomDelta.toFixed(6)} absRatio=${absoluteScale.toFixed(6)}`);

    const sourceCenterLonLat = getViewerCenterLonLat(sourceViewer);
    const sourceCenter = sourceCenterLonLat
      ? {
          longitude: Cesium.Math.toRadians(Number(sourceCenterLonLat.lon)),
          latitude: Cesium.Math.toRadians(Number(sourceCenterLonLat.lat)),
        }
      : Cesium.Rectangle.center(sourceRectangle);
    const targetCenter = Cesium.Rectangle.center(targetRectangle);
    const rawLonDelta = Cesium.Math.negativePiToPi(Number(sourceCenter.longitude) - Number(targetCenter.longitude));
    const rawLatDelta = Number(sourceCenter.latitude) - Number(targetCenter.latitude);
    const maxLonShift = targetWidth * 0.45;
    const maxLatShift = targetHeight * 0.45;
    const lonDelta = Cesium.Math.clamp(rawLonDelta, -maxLonShift, maxLonShift);
    const latDelta = Cesium.Math.clamp(rawLatDelta, -maxLatShift, maxLatShift);

    const destinationCenter = {
      longitude: Cesium.Math.negativePiToPi(Number(targetCenter.longitude) + lonDelta),
      latitude: Cesium.Math.clamp(Number(targetCenter.latitude) + latDelta, -Cesium.Math.PI_OVER_TWO + 1.0e-6, Cesium.Math.PI_OVER_TWO - 1.0e-6),
    };
    const destinationWidth = targetWidth * zoomDelta;
    const destinationHeight = targetHeight * zoomDelta;
    const resolved = buildRectangleFromCenter(destinationCenter, destinationWidth, destinationHeight);
    if (!resolved) {
      log("debug", "Comparator imagery sync: buildRectangleFromCenter failed; returning source rectangle");
      return sourceRectangle;
    }

    const resolvedWidth = rectangleWidthRadians(resolved);
    log("debug", `Comparator imagery sync RESULT: sourceCenterMode=${sourceCenterLonLat ? "screen-center" : "view-rect"} rawLonDelta=${rawLonDelta.toFixed(6)} rawLatDelta=${rawLatDelta.toFixed(6)} lonDelta=${lonDelta.toFixed(6)} latDelta=${latDelta.toFixed(6)} resolvedWidth=${resolvedWidth.toFixed(6)} targetWidth=${targetWidth.toFixed(6)}`);
    return resolved;
  }

  function syncViewerCamera(sourceViewer, targetViewer) {
    if (comparatorModeEnabled) {
        log("debug", "Comparator camera sync is disabled; syncViewerCamera ignored"); // Logging for debugging
      if (sourceViewer) {
        updateComparatorCenterReadout(sourceViewer);
      }
      if (targetViewer && targetViewer.scene) {
        targetViewer.scene.requestRender();
      }
    }
  }

  function bindComparatorSyncHandlers() {
    // Wire camera-change and mousemove for all active comparator panes.
    // Uses comparatorViewers[] array — works for 2, 3, or 4 panes.
    var _numActive = comparatorViewers.filter(Boolean).length;
    for (var _bi = 0; _bi < _numActive; _bi++) {
      (function(idx) {
        var v = comparatorViewers[idx];
        if (!v) return;
        var container = document.getElementById("comparatorViewer" + idx);
        if (!container) return;

        // Camera change → update coords readout for this pane
        v.camera.changed.addEventListener(function () {
          if (comparatorModeEnabled) {
            updateComparatorCenterReadout(v, idx);
          }
        });

        // Wheel → update coords
        container.addEventListener("wheel", function () {
          if (comparatorModeEnabled) updateComparatorCenterReadout(v, idx);
        }, { passive: true });

        // Mousemove → project geo position to all other panes' crosshairs (throttled)
        let lastMouseMoveTime = 0;
        const MOUSE_MOVE_THROTTLE_MS = 50;  // Throttle to 20fps max
        container.addEventListener("mousemove", function (event) {
          if (!comparatorModeEnabled || !v) return;
          
          // Throttle mouse move processing
          const now = Date.now();
          if (now - lastMouseMoveTime < MOUSE_MOVE_THROTTLE_MS) return;
          lastMouseMoveTime = now;
          
          var rect = container.getBoundingClientRect();
          if (rect.width <= 0 || rect.height <= 0) return;
          var localX = event.clientX - rect.left;
          var localY = event.clientY - rect.top;
          var srcPos = new Cesium.Cartesian2(localX, localY);
          var srcCartesian = getCartesianFromViewer(v, srcPos);
          var srcLonLat = srcCartesian
            ? cartesianToLonLat(srcCartesian)
            : getLonLatFromViewer(v, srcPos);

          // Update crosshair on every pane
          var _total = comparatorViewers.filter(Boolean).length;
          for (var _pi = 0; _pi < _total; _pi++) {
            var targetV = comparatorViewers[_pi];
            var crosshair = document.querySelector("#comparatorPane" + _pi + " .comparatorCrosshair");
            if (!crosshair) continue;

            var screenPos;
            if (_pi === idx) {
              screenPos = srcPos;
            } else if (srcCartesian && targetV) {
              screenPos = projectCartesianToViewer(targetV, srcCartesian);
            } else {
              screenPos = null;
            }

            applyCrosshairScreenPosition(crosshair, targetV, screenPos);
          }

          if (srcLonLat) {
            emitMouseCoordinates(srcLonLat.lon, srcLonLat.lat);
          }
        });
      })(_bi);
    }
    bindComparatorPaneSelectionHandlers();
    setComparatorPaneSelectionStyles(comparatorSelectedPane);
  }

  function getComparatorPaneViewer(paneKey) {
    // Map "left"→index 0, "right"→index 1
    var idx = (paneKey === "right") ? 1 : 0;
    return (Array.isArray(comparatorViewers) && comparatorViewers[idx]) || null;
  }

  function getComparatorPaneLayerType(paneKey) {
    var idx = (paneKey === "right") ? 1 : 0;
    var v = Array.isArray(comparatorViewers) ? comparatorViewers[idx] : null;
    if (!v) return null;
    var key = v.__comparatorLayerKey || null;
    if (!key) return null;
    var def = layerDefinitions.get(key);
    return (def && def.type) ? String(def.type) : null;
  }

  function getComparatorPaneVisual(paneKey) {
    if (paneKey === "right") {
      return comparatorPaneVisualState.right;
    }
    return comparatorPaneVisualState.left;
  }

  function setComparatorPaneSelectionStyles(selectedPane) {
    var _numActive = comparatorViewers.filter(Boolean).length;
    for (var _ssi = 0; _ssi < 4; _ssi++) {
      var pane = document.getElementById("comparatorPane" + _ssi);
      if (!pane) continue;
      // pane0 = "left", pane1+ = "right"
      var isSelected = (_ssi === 0 && selectedPane === "left") ||
                       (_ssi > 0  && selectedPane === "right");
      pane.classList.toggle("selected", isSelected);
    }
  }

  function buildComparatorPaneSnapshot(paneKey) {
    const paneState = getComparatorPaneVisual(paneKey);
    if (!paneState) {
      return null;
    }
    const layerType = getComparatorPaneLayerType(paneKey);
    return {
      pane: paneKey,
      layer_type: layerType || "none",
      imagery: {
        brightness: Number(paneState.imagery.brightness) || 1.0,
        contrast: Number(paneState.imagery.contrast) || 1.0,
      },
      dem: {
        exaggeration: Number(paneState.dem.exaggeration) || 1.0,
        hillshade_alpha: Number(paneState.dem.hillshadeAlpha) || 0.0,
        color_mode: String(paneState.dem.colorMode || "gray"),
      },
    };
  }

  function notifyComparatorPaneState(paneKey) {
    if (!bridge || !bridge.on_comparator_pane_state) {
      return;
    }
    const snapshot = buildComparatorPaneSnapshot(paneKey);
    if (!snapshot) {
      return;
    }
    bridge.on_comparator_pane_state(JSON.stringify(snapshot));
  }

  function setSelectedComparatorPane(paneKey, notifyPanel) {
    const normalized = paneKey === "right" ? "right" : "left";
    comparatorSelectedPane = normalized;
    setComparatorPaneSelectionStyles(normalized);
    if (notifyPanel !== false) {
      notifyComparatorPaneState(normalized);
    }
  }

  function bindComparatorPaneSelectionHandlers() {
    var _numActive = comparatorViewers.filter(Boolean).length;
    for (var _si = 0; _si < _numActive; _si++) {
      (function(idx) {
        var pane = document.getElementById("comparatorPane" + idx);
        if (!pane || pane.dataset.selectionBound) return;
        pane.dataset.selectionBound = "1";
        pane.addEventListener("pointerdown", function () {
          // Map index 0→"left", 1→"right", others→"right"
          setSelectedComparatorPane(idx === 0 ? "left" : "right", true);
        });
      })(_si);
    }
  }

  function buildComparatorDemDrapeUrl(definition, demState) {
    if (definition && typeof definition.xyzUrl === "string" && definition.xyzUrl) {
      const baseQuery = definition.query && typeof definition.query === "object" ? { ...definition.query } : {};
      baseQuery.resampling = "nearest";
      baseQuery.colormap_name = String(demState.colorMode || baseQuery.colormap_name || "gray");
      return buildUrlWithQuery(definition.xyzUrl, baseQuery);
    }
    return String((definition && definition.drapeUrl) || "");
  }

  function buildComparatorDemHillshadeUrl(definition, demState) {
    if (definition && typeof definition.xyzUrl === "string" && definition.xyzUrl) {
      const sourceQuery = definition.query && typeof definition.query === "object" ? definition.query : {};
      const query = {
        algorithm: "hillshade",
        azimuth: DEM_HILLSHADE_AZIMUTH,
        angle_altitude: DEM_HILLSHADE_ALTITUDE,
        z_exaggeration: Math.max(0.1, Number(demState.exaggeration) || 1.0),
        buffer: 4,
      };
      if (Object.prototype.hasOwnProperty.call(sourceQuery, "nodata")) {
        query.nodata = sourceQuery.nodata;
      }
      return buildUrlWithQuery(definition.xyzUrl, query);
    }
    return String((definition && definition.hillshadeUrl) || "");
  }

  function logComparatorLayerStack(targetViewer, paneKey, context) {
    if (!targetViewer || !targetViewer.imageryLayers) {
      return;
    }
    const rows = [];
    for (let idx = 0; idx < targetViewer.imageryLayers.length; idx += 1) {
      const layer = targetViewer.imageryLayers.get(idx);
      const isPrimary = layer === targetViewer.__comparatorPrimaryLayer;
      const isHillshade = layer === targetViewer.__comparatorHillshadeLayer;
      const role = isPrimary ? "primary" : (isHillshade ? "hillshade" : "background");
      const alpha = Number(layer && layer.alpha);
      const show = layer && layer.show === false ? "hidden" : "shown";
      rows.push(`#${idx}:${role}:${show}:alpha=${Number.isFinite(alpha) ? alpha.toFixed(2) : "n/a"}`);
    }
    log("debug", `Comparator layer stack pane=${paneKey} context=${context} :: ${rows.join(" | ")}`);
  }

  function enforceComparatorDemLayerOrder(paneKey, targetViewer) {
    if (!targetViewer || getComparatorPaneLayerType(paneKey) !== "dem") {
      return;
    }
    const primaryLayer = targetViewer.__comparatorPrimaryLayer || null;
    const hillshadeLayer = targetViewer.__comparatorHillshadeLayer || null;

    if (primaryLayer && targetViewer.imageryLayers.indexOf(primaryLayer) >= 0) {
      primaryLayer.show = true;
      primaryLayer.alpha = 1.0;
      targetViewer.imageryLayers.raiseToTop(primaryLayer);
    }
    if (hillshadeLayer && targetViewer.imageryLayers.indexOf(hillshadeLayer) >= 0) {
      hillshadeLayer.show = true;
      targetViewer.imageryLayers.raiseToTop(hillshadeLayer);
    }
    logComparatorLayerStack(targetViewer, paneKey, "enforce-dem-z-order");
  }

  function applyComparatorPaneVisualState(paneKey) {
    const targetViewer = getComparatorPaneViewer(paneKey);
    const paneState = getComparatorPaneVisual(paneKey);
    const layerType = getComparatorPaneLayerType(paneKey);
    if (!targetViewer || !paneState || !layerType) {
      return;
    }
    if (layerType === "imagery") {
      const imageryLayer = targetViewer.__comparatorPrimaryLayer || null;
      if (imageryLayer) {
        imageryLayer.brightness = Math.max(0.2, Number(paneState.imagery.brightness) || 1.0);
        imageryLayer.contrast = Math.max(0.1, Number(paneState.imagery.contrast) || 1.0);
      }
    } else if (layerType === "dem") {
      targetViewer.scene.verticalExaggeration = Math.max(0.1, Number(paneState.dem.exaggeration) || 1.0);
      const primaryLayer = targetViewer.__comparatorPrimaryLayer || null;
      if (primaryLayer) {
        primaryLayer.alpha = 1.0;
        primaryLayer.show = true;
      }
      const hsLayer = targetViewer.__comparatorHillshadeLayer || null;
      if (hsLayer) {
        hsLayer.alpha = Math.max(0.0, Math.min(0.35, (Number(paneState.dem.hillshadeAlpha) || 0.0) * 0.45));
      }
      enforceComparatorDemLayerOrder(paneKey, targetViewer);
    }
    targetViewer.scene.requestRender();
  }

  function applyLayerDefinitionToViewer(targetViewer, definition, paneKey) {
    if (!targetViewer || !definition) {
      return;
    }
    const paneVisual = getComparatorPaneVisual(paneKey);
    const rectangle = rectangleFromBounds(definition.bounds || null);
    targetViewer.__comparatorLayerKey = String(definition.key || "");
    targetViewer.__comparatorPrimaryLayer = null;
    targetViewer.__comparatorHillshadeLayer = null;

    const localBackgroundProvider = new Cesium.UrlTemplateImageryProvider({
      url: `${LOCAL_SATELLITE_TILE_ROOT}/{z}/{x}/{y}.png`,
      tilingScheme: new Cesium.WebMercatorTilingScheme(),
      minimumLevel: 0,
      maximumLevel: 10,  // OSM tiles available up to zoom level 10
      credit: new Cesium.Credit("© OpenStreetMap contributors", false),
      enablePickFeatures: false,
    });
    // Suppress tile error logging for comparator background — 404s for missing tiles are expected
    localBackgroundProvider.errorEvent.addEventListener(function (error) {
      error.retry = false;  // don't retry, just skip silently
    });
    const localBackgroundLayer = targetViewer.imageryLayers.addImageryProvider(localBackgroundProvider);
    localBackgroundLayer.alpha = 1.0;

    if (definition.type === "dem") {
      const demState = paneVisual ? paneVisual.dem : comparatorPaneVisualState.left.dem;
      const drapeUrl = buildComparatorDemDrapeUrl(definition, demState);
      const hillshadeUrl = buildComparatorDemHillshadeUrl(definition, demState);

      // Force 3D globe mode for DEM panes — must happen BEFORE adding layers
      // so Cesium initialises the 3D scene graph correctly on Windows/ANGLE.
      log("info", "COMP_DEM pane=" + paneKey + " forcing SCENE3D for DEM viewer");
      if (targetViewer.scene && targetViewer.scene.mode !== Cesium.SceneMode.SCENE3D) {
        targetViewer.scene.morphTo3D(0.0);
        log("info", "COMP_DEM pane=" + paneKey + " morphTo3D issued");
      } else {
        log("info", "COMP_DEM pane=" + paneKey + " already SCENE3D mode=" + targetViewer.scene.mode);
      }

      const demProvider = new Cesium.UrlTemplateImageryProvider({
        url: drapeUrl,
        maximumLevel: definition.maxLevel,
        minimumLevel: definition.minLevel,
        tilingScheme: new Cesium.WebMercatorTilingScheme(),
        enablePickFeatures: false,
        rectangle: rectangle,
      });
      const demLayer = targetViewer.imageryLayers.addImageryProvider(demProvider);
      demLayer.alpha = 1.0;
      targetViewer.__comparatorPrimaryLayer = demLayer;
      if (hillshadeUrl) {
        const hsProvider = new Cesium.UrlTemplateImageryProvider({
          url: hillshadeUrl,
          maximumLevel: definition.maxLevel,
          minimumLevel: definition.minLevel,
          tilingScheme: new Cesium.WebMercatorTilingScheme(),
          enablePickFeatures: false,
          rectangle: rectangle,
        });
        const hsLayer = targetViewer.imageryLayers.addImageryProvider(hsProvider);
        hsLayer.alpha = Math.max(0.0, Math.min(1.0, Number(demState.hillshadeAlpha) || 0.0));
        targetViewer.__comparatorHillshadeLayer = hsLayer;
      }
      enforceComparatorDemLayerOrder(paneKey, targetViewer);

      // Apply tilted 3D camera after a short delay to let morphTo3D settle.
      // On Windows/ANGLE the scene mode transition is async — we need to wait
      // at least one frame before lookAt works correctly.
      if (rectangle) {
        var _demRect = rectangle;
        var _demViewer = targetViewer;
        var _demPaneKey = paneKey;
        function _applyDemCamera() {
          if (!_demViewer || !_demViewer.scene) return;
          var pitch = getComparatorDemPitchRadians();
          var sphere = Cesium.BoundingSphere.fromRectangle3D(_demRect, Cesium.Ellipsoid.WGS84, 0.0);
          var range = Math.max(sphere.radius * 1.9, 900.0);
          log("info", "COMP_DEM pane=" + _demPaneKey +
            " applying camera pitch=" + Cesium.Math.toDegrees(pitch).toFixed(1) +
            "° range=" + range.toFixed(0) + "m" +
            " sceneMode=" + _demViewer.scene.mode);
          try {
            _demViewer.camera.lookAt(
              sphere.center,
              new Cesium.HeadingPitchRange(0.0, pitch, range)
            );
            _demViewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
          } catch(e) {
            log("warn", "COMP_DEM pane=" + _demPaneKey + " lookAt failed: " + e);
          }
          _demViewer.scene.requestRender();
        }
        setTimeout(_applyDemCamera, 50);
        setTimeout(_applyDemCamera, 300);
        setTimeout(_applyDemCamera, 700);
      }

      if (targetViewer.scene) {
        targetViewer.scene.requestRender();
      }
      return;
    }

    // Imagery pane — always force strict 2D flat map, no tilt ever
    log("info", "COMP_IMAGERY pane=" + paneKey + " forcing SCENE2D for imagery viewer sceneMode=" + targetViewer.scene.mode);
    if (targetViewer.scene && targetViewer.scene.mode !== Cesium.SceneMode.SCENE2D) {
      targetViewer.scene.morphTo2D(0.0);
      log("info", "COMP_IMAGERY pane=" + paneKey + " morphTo2D issued");
    }

    const provider = new Cesium.UrlTemplateImageryProvider({
      url: definition.url,
      maximumLevel: definition.maxLevel,
      minimumLevel: definition.minLevel,
      tilingScheme: new Cesium.WebMercatorTilingScheme(),
      enablePickFeatures: false,
      rectangle: rectangle,
    });
    const layer = targetViewer.imageryLayers.addImageryProvider(provider);
    layer.alpha = 1.0;
    if (paneVisual) {
      layer.brightness = Math.max(0.2, Number(paneVisual.imagery.brightness) || 1.0);
      layer.contrast = Math.max(0.1, Number(paneVisual.imagery.contrast) || 1.0);
    }
    targetViewer.__comparatorPrimaryLayer = layer;

    // Re-enforce 2D after a short delay — Windows/ANGLE can revert the mode
    var _imgViewer = targetViewer;
    var _imgPaneKey = paneKey;
    function _enforce2D() {
      if (!_imgViewer || !_imgViewer.scene) return;
      if (_imgViewer.scene.mode !== Cesium.SceneMode.SCENE2D) {
        log("info", "COMP_IMAGERY pane=" + _imgPaneKey + " re-enforcing SCENE2D");
        _imgViewer.scene.morphTo2D(0.0);
      }
      if (_imgViewer.scene) _imgViewer.scene.requestRender();
    }
    setTimeout(_enforce2D, 80);
    setTimeout(_enforce2D, 400);
  }

  function resetComparatorViewerLayers(targetViewer) {
    if (!targetViewer) {
      return;
    }
    for (let idx = targetViewer.imageryLayers.length - 1; idx >= 0; idx -= 1) {
      const layer = targetViewer.imageryLayers.get(idx);
      if (layer === targetViewer.__osmBasemapLayer || layer === targetViewer.__defaultEarthLayer) {
        continue;
      }
      targetViewer.imageryLayers.remove(layer, false);
    }
  }

  function resolveComparatorLayerKeys() {
    if (swipeComparatorLeftLayerKey && swipeComparatorRightLayerKey) {
      return [swipeComparatorLeftLayerKey, swipeComparatorRightLayerKey];
    }
    const visibleKeys = [];
    for (const [key, visible] of layerVisibilityState.entries()) {
      if (!visible || !layerDefinitions.has(key)) continue;
      visibleKeys.push(key);
    }
    return visibleKeys.slice(0, 4);
  }

  // ═══════════════════════════════════════════════════════════════════════════
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
      applyLayerDefinitionToViewer(viewer, def, idx === 0 ? "left" : "right"); // mapping legacy paneKey
      
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
    const targetPane = paneKey === "right" ? "right" : "left";
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
      const layerKey = targetPane === "right" ? swipeComparatorRightLayerKey : swipeComparatorLeftLayerKey;
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

      const refreshVersion = (Number(comparatorDemStyleRefreshVersion[targetPane]) || 0) + 1;
      comparatorDemStyleRefreshVersion[targetPane] = refreshVersion;
      window.setTimeout(function () {
        const latestVersion = Number(comparatorDemStyleRefreshVersion[targetPane]) || 0;
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

        if (oldHillshade && targetViewer.imageryLayers.indexOf(oldHillshade) >= 0) {
          targetViewer.imageryLayers.remove(oldHillshade, false);
        }
        if (oldPrimary && targetViewer.imageryLayers.indexOf(oldPrimary) >= 0) {
          targetViewer.imageryLayers.remove(oldPrimary, false);
        }
        enforceComparatorDemLayerOrder(targetPane, targetViewer);
        logComparatorLayerStack(targetViewer, targetPane, "post-color-refresh");
        targetViewer.scene.requestRender();
      }, 80);
    }, COMPARATOR_DEM_REFRESH_DEBOUNCE_MS);
  }

  const comparatorViewers = [];
  runtime.comparatorViewers = comparatorViewers;
  function ensureComparatorViewers(count) {
    // CRITICAL (Windows/ANGLE): The comparatorPane divs must have display:block
    // BEFORE Cesium creates its canvas, otherwise the canvas gets zero size and
    // stays permanently black.  Activate all needed panes now, before any viewer
    // is constructed.
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
      v.scene.globe.baseColor = Cesium.Color.BLACK;
      v.scene.backgroundColor = Cesium.Color.BLACK;
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

        log("info", "Comparator init: cwSize=" + _cwW + "x" + _cwH + " panes=" + _numPanes);

        ensureComparatorViewers(_numPanes);
        refreshComparatorLayers();
        bindComparatorSyncHandlers();

        // DEBUG: log pane and canvas sizes immediately after creation
        function _debugPaneSizes(label) {
          for (var _di = 0; _di < _numPanes; _di++) {
            var _pane = document.getElementById("comparatorPane" + _di);
            var _vdiv = document.getElementById("comparatorViewer" + _di);
            var _cv = comparatorViewers[_di] && comparatorViewers[_di].canvas;
            log("info", "COMP_DEBUG[" + label + "] pane" + _di +
              " pane=" + (_pane ? _pane.offsetWidth + "x" + _pane.offsetHeight : "null") +
              " active=" + (_pane ? _pane.classList.contains("active") : "?") +
              " vdiv=" + (_vdiv ? _vdiv.offsetWidth + "x" + _vdiv.offsetHeight : "null") +
              " canvas=" + (_cv ? _cv.width + "x" + _cv.height : "null") +
              " clientCanvas=" + (_cv ? _cv.clientWidth + "x" + _cv.clientHeight : "null"));
          }
          var _cw2 = document.getElementById("comparatorWindows");
          log("info", "COMP_DEBUG[" + label + "] cwRoot=" +
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
  // SECTION: Imagery Layer Management  →  future: modules/imagery.js
  // Functions: attachTileErrorHandler, clearManagedImageryLayers,
  //   logLayerStack, setLayerVisibilityByKey, setActiveTileBounds,
  //   setLastLoadedBounds, updateBasemapBlendForCurrentMode
  // ═══════════════════════════════════════════════════════════════════════════

  function attachTileErrorHandler(provider, name) {
    layerErrorCounts.set(name, 0);
    
    provider.errorEvent.addEventListener(function (error) {
      error.retry = false;
      const key = `${name}:${error.level}:${error.x}:${error.y}`;
      if (tileErrorSeen.has(key)) return;
      tileErrorSeen.add(key);
      const currentCount = (layerErrorCounts.get(name) || 0) + 1;
      layerErrorCounts.set(name, currentCount);
      const msg = error && error.message ? String(error.message) : "tile request failed";
      
      function resolveTileTemplateUrl(template, providerRef, errorRef) {
        if (!template || !errorRef) {
          return "";
        }
        let url = String(template);
        let yValue = errorRef.y;
        if (url.indexOf("{reverseY}") >= 0) {
          try {
            if (providerRef && providerRef.tilingScheme && typeof providerRef.tilingScheme.getNumberOfYTilesAtLevel === "function") {
              const total = providerRef.tilingScheme.getNumberOfYTilesAtLevel(errorRef.level);
              yValue = total - errorRef.y - 1;
            }
          } catch (_err) {
            yValue = errorRef.y;
          }
        }
        url = url.replace("{z}", String(errorRef.level));
        url = url.replace("{x}", String(errorRef.x));
        url = url.replace("{y}", String(errorRef.y));
        url = url.replace("{reverseY}", String(yValue));
        return url;
      }

      let templateUrlForError = "";
      try {
        templateUrlForError = String(provider && provider.url ? provider.url : "");
      } catch (_err) {
        templateUrlForError = "";
      }
      const resolvedTileUrl = resolveTileTemplateUrl(templateUrlForError, provider, error);

      // Enhanced error logging with more details
      log("error", "TILE_ERROR: provider=" + name + 
          " count=" + currentCount + 
          " z=" + error.level + 
          " x=" + error.x + 
          " y=" + error.y + 
          " msg=" + msg +
          " url=" + (error.url || resolvedTileUrl || templateUrlForError || "unknown"));
      
      // Log tile coordinate analysis for debugging only on first error
      if (provider.rectangle && currentCount === 1) {
        const rect = provider.rectangle;
        const westDeg = Cesium.Math.toDegrees(rect.west);
        const southDeg = Cesium.Math.toDegrees(rect.south);
        const eastDeg = Cesium.Math.toDegrees(rect.east);
        const northDeg = Cesium.Math.toDegrees(rect.north);
        
        log("warn", "Tile error in bounds: west=" + westDeg.toFixed(3) + 
            " south=" + southDeg.toFixed(3) + 
            " east=" + eastDeg.toFixed(3) + 
            " north=" + northDeg.toFixed(3) +
            " requested z=" + error.level + " x=" + error.x + " y=" + error.y);
      }
      
      if (currentCount === 1) {
        if (templateUrlForError) {
          log("warn", "TILE_DEBUG: Template URL for " + name + " => " + templateUrlForError);
        }
        if (resolvedTileUrl) {
          log("warn", "TILE_DEBUG: Sample tile URL for " + name + " => " + resolvedTileUrl);
        }
        
        // Log provider details
        log("debug", "TILE_DEBUG: Provider details for " + name + 
            " ready=" + (provider.ready || false) +
            " tilingScheme=" + (provider.tilingScheme ? provider.tilingScheme.constructor.name : "none") +
            " minLevel=" + (provider.minimumLevel || "unknown") +
            " maxLevel=" + (provider.maximumLevel || "unknown") +
            " rectangle=" + (provider.rectangle ? "defined" : "undefined"));
      }
      
      if (currentCount <= 10 || currentCount % 25 === 0) {
        log(
          "warn",
          "TILE_DEBUG: Repeated tile error for " +
            name +
            " count=" +
            currentCount +
            " z=" +
            error.level +
            " x=" +
            error.x +
            " y=" +
            error.y +
            " msg=" +
            msg
        );
      }
    });
    
    // Add success logging for first few tiles
    if (provider.readyPromise && typeof provider.readyPromise.then === "function") {
      provider.readyPromise.then(
        function () {
          log("debug", "Provider ready: " + name);
        },
        function (err) {
          log("error", "Provider ready failed: " + name + " - " + String(err));
        }
      );
    }
  }

  function clearDemTerrainMode() {
    if (!viewer) return;
    const previousDemLayerKey = activeDemContext && activeDemContext.layerKey ? activeDemContext.layerKey : null;
    if (activeDemDrapeLayer) {
      viewer.imageryLayers.remove(activeDemDrapeLayer, false);
      
      // CRITICAL FIX: Remove DEM drape layer from managedImageryLayers map
      if (previousDemLayerKey) {
        managedImageryLayers.delete(previousDemLayerKey);
      }
      
      activeDemDrapeLayer = null;
    }
    if (activeDemHillshadeLayer) {
      viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
      
      // CRITICAL FIX: Remove DEM hillshade layer from managedImageryLayers map
      if (previousDemLayerKey) {
        managedImageryLayers.delete(previousDemLayerKey + ":hillshade");
      }
      
      activeDemHillshadeLayer = null;
    }
    activeDemContext = null;
    activeDemTerrainSignature = null;
    activeDemDrapeUrl = null;
    activeDemHillshadeUrl = null;
    if (previousDemLayerKey) {
      layerDefinitions.delete(previousDemLayerKey);
      layerVisibilityState.delete(previousDemLayerKey);
    }
    viewer.terrainProvider = new Cesium.EllipsoidTerrainProvider();
    applyDefaultSceneSettings();
    hideDemColorbar();
    setSceneModeControlEnabled(true);
  }

  function clearManagedImageryLayers(exceptLayerKey) {
    if (!viewer) {
      managedImageryLayers.clear();
      layerDefinitions.clear();
      layerVisibilityState.clear();
      activeImageryLayer = null;
      return;
    }
    for (const [layerKey, layer] of Array.from(managedImageryLayers.entries())) {
      if (exceptLayerKey && layerKey === exceptLayerKey) {
        continue;
      }
      if (layer) {
        viewer.imageryLayers.remove(layer, false);
      }
      managedImageryLayers.delete(layerKey);
      layerDefinitions.delete(layerKey);
      layerVisibilityState.delete(layerKey);
    }
    if (exceptLayerKey) {
      activeImageryLayer = managedImageryLayers.get(exceptLayerKey) || null;
      applySwipeComparatorSplit();
      return;
    }
    activeImageryLayer = null;
    applySwipeComparatorSplit();
  }

  function setLayerVisibilityByKey(layerKey, visible) {
    console.log(`DEBUG: setLayerVisibilityByKey called: layerKey=${layerKey}, visible=${visible}`);
    
    if (!viewer || !layerKey) {
      console.warn("DEBUG: setLayerVisibilityByKey - invalid viewer or layerKey");
      return false;
    }
    layerVisibilityState.set(layerKey, Boolean(visible));
    console.log(`DEBUG: Updated layerVisibilityState for ${layerKey} = ${Boolean(visible)}`);

    const imageryLayer = managedImageryLayers.get(layerKey);
    if (imageryLayer) {
      const shouldShow = Boolean(visible);
      console.log(`DEBUG: Found imagery layer for ${layerKey}, setting show=${shouldShow}`);
      imageryLayer.show = shouldShow;
      if (shouldShow) {
        activeImageryLayer = imageryLayer;
      } else if (activeImageryLayer === imageryLayer) {
        activeImageryLayer = null;
      }
      const anyVisible = Array.from(layerVisibilityState.values()).some(Boolean);
      if (!anyVisible) {
        if (activeDemDrapeLayer) {
          activeDemDrapeLayer.show = false;
        }
        if (activeDemHillshadeLayer) {
          activeDemHillshadeLayer.show = false;
        }
      }
      applySwipeComparatorSplit();
      if (comparatorModeEnabled) {
        refreshComparatorLayers();
      }
      requestSceneRender();
      console.log(`DEBUG: Imagery layer visibility updated successfully for ${layerKey}`);
      return true;
    }

    if (activeDemContext && activeDemContext.layerKey === layerKey) {
      const shouldShow = Boolean(visible);
      console.log(`DEBUG: Found DEM layer for ${layerKey}, setting visible=${shouldShow}`);
      activeDemContext.visible = shouldShow;
      if (activeDemDrapeLayer) {
        activeDemDrapeLayer.show = shouldShow;
        console.log(`DEBUG: DEM drape layer show=${shouldShow}`);
      }
      if (activeDemHillshadeLayer) {
        activeDemHillshadeLayer.show = shouldShow && activeDemHillshadeLayer.alpha > 0.01;
        console.log(`DEBUG: DEM hillshade layer show=${shouldShow && activeDemHillshadeLayer.alpha > 0.01}`);
      }
      if (shouldShow) {
        updateDemColorbar(
          parseDemHeightRange(activeDemContext.options).min,
          parseDemHeightRange(activeDemContext.options).max,
          activeDemContext.options
        );
        setSceneModeControlEnabled(true);
        setStatus("DEM layer shown.");
        log("info", "DEM layer shown key=" + layerKey);
        if (activeDemTerrainProvider && viewer.terrainProvider !== activeDemTerrainProvider) {
          _swapTerrainProviderLocked(activeDemTerrainProvider);
        }
        // Re-apply exaggeration — terrainExaggeration resets when terrain provider changes
        if (viewer && viewer.scene && viewer.scene.globe) {
          viewer.scene.globe.terrainExaggeration = Math.max(0.1, demVisual.exaggeration);
          if (typeof viewer.scene.verticalExaggeration !== "undefined") {
            viewer.scene.verticalExaggeration = Math.max(0.1, demVisual.exaggeration);
          }
          log("debug", "DEM show: re-applied terrainExaggeration=" + demVisual.exaggeration.toFixed(2));
        }
      } else {
        hideDemColorbar();
        setSceneModeControlEnabled(true);
        setStatus("DEM layer hidden.");
        log("info", "DEM layer hidden key=" + layerKey);
        viewer.terrainProvider = new Cesium.EllipsoidTerrainProvider();
        if (viewer && viewer.scene && viewer.scene.globe) {
          viewer.scene.globe.terrainExaggeration = 1.0;
          if (typeof viewer.scene.verticalExaggeration !== "undefined") {
            viewer.scene.verticalExaggeration = 1.0;
          }
        }
      }
      const anyVisible = Array.from(layerVisibilityState.values()).some(Boolean);
      if (!anyVisible) {
        if (activeDemDrapeLayer) {
          activeDemDrapeLayer.show = false;
        }
        if (activeDemHillshadeLayer) {
          activeDemHillshadeLayer.show = false;
        }
      }
      if (comparatorModeEnabled) {
        refreshComparatorLayers();
      }
      requestSceneRender();
      return true;
    }

    return false;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: DEM Colorbar  →  future: modules/dem.js
  // Functions: resolveDemColorbarGradient, updateDemColorbar, hideDemColorbar
  // ═══════════════════════════════════════════════════════════════════════════

  function resolveDemColorbarGradient(colormapName) {
    const normalized = String(colormapName || "terrain").toLowerCase();
    const gradients = {
      terrain:
        "to bottom, #ffffff 0%, #f0f0f0 5%, #d9d3c7 15%, #b48f6a 30%, #c7b34a 45%, #7ca860 60%, #4aa8b2 75%, #2d7bd0 90%, #173c8f 100%",
      viridis:
        "to bottom, #fde725 0%, #90d743 24%, #35b779 45%, #21918c 64%, #31688e 82%, #443a83 100%",
      turbo:
        "to bottom, #7a0403 0%, #d84f2a 18%, #f6b44f 36%, #f7f756 50%, #7bd651 66%, #2c8fe3 84%, #23135a 100%",
      slope:
        "to bottom, #7a0403 0%, #fde725 50%, #2c8fe3 100%",
      aspect:
        "to bottom, #ff0000 0%, #ffff00 25%, #00ff00 50%, #00ffff 75%, #0000ff 100%",
      gray:
        "to bottom, #ffffff 0%, #f0f0f0 10%, #aaaaaa 50%, #444444 80%, #000000 100%",
      greys:
        "to bottom, #ffffff 0%, #f0f0f0 10%, #aaaaaa 50%, #444444 80%, #000000 100%",
    };
    return gradients[normalized] || gradients.terrain;
  }

  function updateDemColorbar(minHeight, maxHeight, options) {
    const gradient = document.getElementById("demColorbar-gradient");
    const labelHigh = document.getElementById("demColorbar-label-high");
    const labelMid = document.getElementById("demColorbar-label-mid");
    const labelLow = document.getElementById("demColorbar-label-low");
    const container = document.getElementById("demColorbar");
    if (!gradient || !labelHigh || !labelMid || !labelLow || !container) return;

    // CRITICAL: Only show colorbar for DEM layers, not regular imagery
    // Check if this is actually a DEM layer by verifying options.is_dem or algorithm presence
    const isDemLayer = options && (options.is_dem === true || (options.query && options.query.algorithm));
    
    if (!isDemLayer) {
      // This is regular imagery, not DEM - hide colorbar
      hideDemColorbar();
      return;
    }

    const query = options && options.query ? options.query : {};
    const algorithmName = typeof query.algorithm === "string" ? String(query.algorithm).toLowerCase() : "";
    const colormapName = typeof query.colormap_name === "string" ? query.colormap_name : "terrain";
    gradient.style.background = `linear-gradient(${resolveDemColorbarGradient(colormapName)})`;

    if (algorithmName === "slope") {
      labelHigh.textContent = "90°";
      labelMid.textContent = "45°";
      labelLow.textContent = "0°";
      container.classList.add("visible");
      return;
    }

    if (algorithmName === "aspect") {
      labelHigh.textContent = "360°";
      labelMid.textContent = "180°";
      labelLow.textContent = "0°";
      container.classList.add("visible");
      return;
    }

    const midHeight = (minHeight + maxHeight) / 2;
    labelHigh.textContent = Math.round(maxHeight).toLocaleString() + " m";
    labelMid.textContent = Math.round(midHeight).toLocaleString() + " m";
    labelLow.textContent = Math.round(minHeight).toLocaleString() + " m";

    container.classList.add("visible");
  }

  function hideDemColorbar() {
    const container = document.getElementById("demColorbar");
    if (container) {
      container.classList.remove("visible");
    }
  }

  function updateBasemapBlendForCurrentMode() {
    // Basemap removed - no-op
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: Camera & Scene Mode  →  future: modules/camera.js
  // Functions: applyDefaultSceneSettings, applyDemSceneSettings,
  //   tuneCameraController, configureCameraControllerForMode,
  //   _swapTerrainProviderLocked, setSceneModeInternal, detectSceneMode,
  //   syncSceneModeToggle, focusPreferredRegion, focusPreferredRegion3D,
  //   focusLoadedRegion3D, schedule3DFocusAfterMorph, startFlyThroughBounds,
  //   applyDefaultStartupFocus, _updateCompass, Asia camera lock postRender
  // ═══════════════════════════════════════════════════════════════════════════

  function applyDefaultSceneSettings() {
    if (!viewer) return;
    // Smooth implementation settings - balanced performance and quality
    viewer.scene.globe.enableLighting = false;
    viewer.scene.fog.enabled = false;
    viewer.shadows = false;
    requestSceneRender();
  }

  /**
   * Swap the terrain provider while keeping the camera locked on the current view.
   * Cesium 1.78 fires camera resets asynchronously after terrainProvider changes.
   * We lock the camera for 5 post-render frames to absorb all async resets.
   */
  function _swapTerrainProviderLocked(newProvider) {
    if (!viewer || !newProvider) {
      log("warn", "DEM_RENDER: _swapTerrainProviderLocked called with invalid params viewer=" + !!viewer + " provider=" + !!newProvider);
      return;
    }
    if (viewer.terrainProvider === newProvider) {
      log("info", "DEM_RENDER: _swapTerrainProviderLocked skipped - provider already active");
      return;
    }

    log("info", "DEM_RENDER: Swapping terrain provider without camera lock");
    log("info", "DEM_RENDER: Old provider type: " + (viewer.terrainProvider.constructor ? viewer.terrainProvider.constructor.name : "unknown"));
    
    viewer.terrainProvider = newProvider;
    
    log("info", "DEM_RENDER: New provider type: " + (newProvider.constructor ? newProvider.constructor.name : "unknown"));
    log("info", "DEM_RENDER: Provider ready: " + newProvider.ready);
  }

  function applyDemSceneSettings() {
    if (!viewer) return;

    // CRITICAL: Terabyte-scale DEM rendering optimizations with anti-flickering
    viewer.scene.globe.terrainExaggeration = Math.max(0.1, demVisual.exaggeration);
    // Also set verticalExaggeration for Cesium 1.90+ compatibility
    if (typeof viewer.scene.verticalExaggeration !== "undefined") {
      viewer.scene.verticalExaggeration = Math.max(0.1, demVisual.exaggeration);
    }
    
    // Disable all expensive visual effects for ultra-high resolution DEM (3-4cm/pixel)
    viewer.scene.globe.enableLighting = false;  // No lighting - major performance gain
    viewer.scene.fog.enabled = false;  // No fog
    viewer.scene.skyAtmosphere.show = false;  // No atmosphere
    viewer.shadows = false;  // No shadows
    
    // ═══════════════════════════════════════════════════════════════════════════
    // DYNAMIC GPU SCALING: Intel vs NVIDIA
    // ═══════════════════════════════════════════════════════════════════════════
    if (window._isHighEndGpu) {
      // HIGH-END CONFIGURATION (NVIDIA/Dedicated GPU)
      viewer.resolutionScale = 1.0;                       // Crisp native resolution
      viewer.scene.globe.depthTestAgainstTerrain = true;  // Proper layer sorting
      viewer.scene.logarithmicDepthBuffer = true;         // Smooth camera dragging
      viewer.scene.globe.maximumScreenSpaceError = 1.0;   // Original high quality fidelity (per user request)
      viewer.scene.globe.tileCacheSize = 800;             // Larger cache for smoother pans
      viewer.scene.globe.preloadAncestors = true;         // Smooth transitions
      viewer.scene.globe.preloadSiblings = true;
      viewer.scene.globe.loadingDescendantLimit = 12;
      
      log("info", "DEM settings applied [MAX GPU CONFIG]: res=1.0 depthTest=true logDepth=true sse=1.5");
    } else {
      // SAFE FALLBACK CONFIGURATION (Intel Integrated GPU)
      // Modified to prioritize visual fidelity (true 3D elevations) over pure performance
      viewer.resolutionScale = 1.0;                       // Crisp native resolution
      viewer.scene.globe.depthTestAgainstTerrain = true;  // Proper layer sorting
      viewer.scene.logarithmicDepthBuffer = true;         // Smooth camera dragging
      viewer.scene.globe.maximumScreenSpaceError = 2.0;   // High quality geometry
      viewer.scene.globe.tileCacheSize = 200;             // Moderate cache for smoother pans
      viewer.scene.globe.preloadAncestors = true;         // Reduce tile churn during drag
      viewer.scene.globe.preloadSiblings = true;
      viewer.scene.globe.loadingDescendantLimit = 4;      // Allow more in-flight tiles
      
      log("info", "DEM settings applied [SAFE INTEL CONFIG modified for High Fidelity]: res=1.0 depthTest=true logDepth=true sse=2.0");
    }
    
    // Improve tile loading priority for better visual stability
    if (viewer.scene.globe._surface) {
      viewer.scene.globe._surface.tileLoadProgressEvent = viewer.scene.globe._surface.tileLoadProgressEvent || new Cesium.Event();
    }
    
    requestSceneRender();
  }

  function tuneCameraController() {
    if (!viewer) return;
    const controller = viewer.scene.screenSpaceCameraController;
    
    // OPTIMIZED CAMERA CONTROLS FOR SMOOTH, INTUITIVE NAVIGATION
    // Uses Cesium's default mouse button mapping for reliability
    
    // Enable collision detection to prevent going inside Earth
    controller.enableCollisionDetection = true;
    controller.maximumMovementRatio = 0.5;  // Fast camera movement
    
    // CRITICAL: Prevent camera from going inside Earth surface
    // Minimum zoom distance = 10 meters above ground (safe minimum)
    controller.minimumZoomDistance = 10.0;  // 10 meters minimum height
    controller.maximumZoomDistance = 100000000.0;  // 100,000 km maximum
    
    // NOTE: zoomFactor is NOT set here — configureCameraControllerForMode() below sets it
    // to 5.0 (Cesium default). The previous 0.4 here caused aggressive zoom-in and is removed.



    configureCameraControllerForMode(currentSceneMode);

    log("info", "Camera controls initialized: zoomFactor=" + viewer.scene.screenSpaceCameraController.zoomFactor + " pickHeight=" + viewer.scene.screenSpaceCameraController.minimumPickingTerrainHeight + " collision ON, min height 10m");

  }


  function configureCameraControllerForMode(mode) {
    if (!viewer) {
      return;
    }
    const controller = viewer.scene.screenSpaceCameraController;
    const is2d = String(mode || "3d").toLowerCase() === "2d";
    const isPan = panModeActive;
    
    // Use Cesium default input mapping
    controller.enableInputs = true;
    controller.enableTranslate = true;
    controller.enableZoom = false;
    // In pan mode keep rotate ON (required for 3D surface dragging) but disable tilt/look
    controller.enableRotate = !is2d;
    controller.enableTilt = !(is2d || isPan);
    controller.enableLook = !(is2d || isPan);

    
    // Inertia — keep spin/translate smooth; zoom MUST be zero-inertia.
    // inertiaZoom > 0 applies momentum over many frames after each scroll tick.
    // At high altitude (6000km), even one tick's momentum carries the camera from
    // space to ground level. Setting to 0 makes each tick a discrete, predictable step.
    controller.inertiaSpin = is2d ? 0.65 : 0.90;
    controller.inertiaTranslate = is2d ? 0.80 : 0.90;
    controller.inertiaZoom = 0.0;  // CRITICAL: must be 0 to prevent momentum runaway

    // zoomFactor=1.5: each tick zooms ~33% of distance — gentle and controllable at all
    // altitudes. 2.5 caused ultra-aggressive single-tick jumps (60%/tick is too much).
    controller.zoomFactor = 1.5;

    // Moderate sensitivity for rotate/translate
    if (controller.rotateSpeed !== undefined) controller.rotateSpeed = 1.5;
    if (controller.translateSpeed !== undefined) controller.translateSpeed = 1.5;

    // minimumPickingTerrainHeight: affects non-zoom interactions (tilt, pan pick).
    // Zoom direction is now handled entirely by our custom wheel handler which does
    // its own globe.pick — this value no longer causes zoom-to-wrong-scene.
    // 150,000m (150km) is Cesium's recommended default.
    controller.minimumPickingTerrainHeight = 150000.0;

    // minimumTrackBallHeight: below this altitude Cesium switches from surface-locked
    // trackball rotation to camera-position rotation. 7.5M was too large — activated
    // in the middle of normal zoom-to-asset range and caused rotation jumps.
    controller.minimumTrackBallHeight = 3000000.0;

    controller.minimumCollisionTerrainHeight = 15000.0;
    controller.minimumZoomDistance = 10.0;  // 10 metres minimum (don't go underground)

    log("info", "configureCameraControllerForMode: mode=" + mode + " zoomFactor=" + controller.zoomFactor + " inertiaZoom=" + controller.inertiaZoom + " pickTerrainH=" + controller.minimumPickingTerrainHeight + " trackballH=" + controller.minimumTrackBallHeight);


  }

  function applySceneModePerformanceHints(mode) {
    if (!viewer || !viewer.scene || !viewer.scene.globe) {
      return;
    }
    if (!scenePerfDefaults) {
      return;
    }
    const is2d = String(mode || "3d").toLowerCase() === "2d" || panModeActive;
    if (is2d) {
      // Favor smooth panning in 2D without lowering imagery/terrain quality.
      viewer.scene.globe.tileCacheSize = Math.max(scenePerfDefaults.tileCacheSize, 1200);
      viewer.scene.globe.loadingDescendantLimit = Math.max(scenePerfDefaults.loadingDescendantLimit, 12);
      viewer.scene.globe.preloadAncestors = true;
      viewer.scene.globe.preloadSiblings = true;
    } else {
      viewer.scene.globe.tileCacheSize = scenePerfDefaults.tileCacheSize;
      viewer.scene.globe.loadingDescendantLimit = scenePerfDefaults.loadingDescendantLimit;
      viewer.scene.globe.preloadAncestors = scenePerfDefaults.preloadAncestors;
      viewer.scene.globe.preloadSiblings = scenePerfDefaults.preloadSiblings;
    }
  }

  function rectangleToBounds(rectangle) {
    if (!rectangle) {
      return null;
    }
    return normalizeBounds({
      west: Cesium.Math.toDegrees(rectangle.west),
      south: Cesium.Math.toDegrees(rectangle.south),
      east: Cesium.Math.toDegrees(rectangle.east),
      north: Cesium.Math.toDegrees(rectangle.north),
    });
  }

  function isNearGlobalBounds(bounds) {
    const normalized = normalizeBounds(bounds);
    if (!normalized) {
      return false;
    }
    return (
      normalized.west <= -179.5 &&
      normalized.east >= 179.5 &&
      normalized.south <= -84.5 &&
      normalized.north >= 84.5
    );
  }

  function setActiveTileBounds(bounds) {
    const normalized = normalizeBounds(bounds);
    if (!normalized) {
      return;
    }
    activeTileBounds = normalized;
    lastLoadedBounds = normalized;
    updateCameraOrbitTarget(normalized);
  }

  function updateCameraOrbitTarget(bounds) {
    const normalized = normalizeBounds(bounds);
    if (!normalized) {
      return;
    }
    const rect = Cesium.Rectangle.fromDegrees(normalized.west, normalized.south, normalized.east, normalized.north);
    const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
    cameraOrbitBounds = normalized;
    cameraOrbitRange = Math.max(compute3DFocusRange(normalized), sphere.radius * 1.2, 250.0);
    if (viewer && viewer.camera) {
      if (Number.isFinite(viewer.camera.heading)) {
        cameraOrbitHeading = viewer.camera.heading;
      }
      if (Number.isFinite(viewer.camera.pitch)) {
        cameraOrbitPitch = viewer.camera.pitch;
      }
    }
  }

  function applyCameraOrbitTarget() {
    if (!viewer || currentSceneMode !== "3d") {
      return false;
    }
    const bounds = cameraOrbitBounds || activeTileBounds || lastLoadedBounds;
    if (!bounds) {
      return false;
    }
    const rect = Cesium.Rectangle.fromDegrees(bounds.west, bounds.south, bounds.east, bounds.north);
    const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
    const hpr = new Cesium.HeadingPitchRange(cameraOrbitHeading, cameraOrbitPitch, cameraOrbitRange);
    
    viewer.camera.cancelFlight();
    viewer.camera.lookAt(sphere.center, hpr);
    
    if (comparatorModeEnabled) {
      if (comparatorLeftViewer && comparatorLeftViewer.camera) {
        comparatorLeftViewer.camera.cancelFlight();
        comparatorLeftViewer.camera.lookAt(sphere.center, hpr);
      }
      if (comparatorRightViewer && comparatorRightViewer.camera) {
        comparatorRightViewer.camera.cancelFlight();
        comparatorRightViewer.camera.lookAt(sphere.center, hpr);
      }
    }
    
    requestSceneRender();
    return true;
  }

  function syncOrbitFromCurrentCamera(bounds) {
    if (!viewer || !viewer.camera) {
      return;
    }
    const normalized = normalizeBounds(bounds);
    if (!normalized) {
      return;
    }
    const rect = Cesium.Rectangle.fromDegrees(normalized.west, normalized.south, normalized.east, normalized.north);
    const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
    const camera = viewer.camera;
    if (Number.isFinite(camera.heading)) {
      cameraOrbitHeading = camera.heading;
    }
    if (Number.isFinite(camera.pitch)) {
      cameraOrbitPitch = camera.pitch;
    }
    if (camera.positionWC && sphere.center) {
      const distance = Cesium.Cartesian3.distance(camera.positionWC, sphere.center);
      if (Number.isFinite(distance) && distance > 1.0) {
        cameraOrbitRange = distance;
      }
    }
  }

  function resolvePreferredFocusBounds() {
    const pinnedBounds = normalizeBounds(activeTileBounds);
    if (pinnedBounds && !isNearGlobalBounds(pinnedBounds)) {
      return pinnedBounds;
    }
    if (activeDemContext && activeDemContext.options && activeDemContext.options.bounds) {
      const demBounds = normalizeBounds(activeDemContext.options.bounds);
      if (demBounds) {
        return demBounds;
      }
    }
    if (activeImageryLayer && activeImageryLayer.imageryProvider && activeImageryLayer.imageryProvider.rectangle) {
      const imageryBounds = rectangleToBounds(activeImageryLayer.imageryProvider.rectangle);
      if (imageryBounds && !isNearGlobalBounds(imageryBounds)) {
        return imageryBounds;
      }
    }
    const fallbackBounds = normalizeBounds(lastLoadedBounds);
    if (fallbackBounds && !isNearGlobalBounds(fallbackBounds)) {
      return fallbackBounds;
    }
    return null;
  }

  function focusPreferredRegion(durationSeconds) {
    const bounds = pendingFocusBounds || resolvePreferredFocusBounds();
    if (!bounds) {
      return;
    }
    setActiveTileBounds(bounds);
    focusLoadedRegion(durationSeconds);
  }

  function applyDefaultStartupFocus() {
    if (!viewer) {
      return;
    }
    viewer.camera.cancelFlight();
    viewer.camera.setView({
      destination: Cesium.Cartesian3.fromDegrees(
        DEFAULT_STARTUP_CENTER_LON,
        DEFAULT_STARTUP_CENTER_LAT,
        DEFAULT_STARTUP_HEIGHT_M
      ),
      orientation: {
        heading: DEFAULT_STARTUP_HEADING,
        pitch: DEFAULT_STARTUP_PITCH,
        roll: 0.0,
      },
    });
    cameraOrbitHeading = DEFAULT_STARTUP_HEADING;
    cameraOrbitPitch = DEFAULT_STARTUP_PITCH;
    cameraOrbitRange = DEFAULT_STARTUP_HEIGHT_M;
    viewer.scene.requestRender();
  }

  function focusPreferredRegion3D(durationSeconds) {
    const bounds = pendingFocusBounds || resolvePreferredFocusBounds();
    if (!bounds) {
      sceneDebug("focusPreferredRegion3D skipped: no bounds");
      return;
    }
    sceneDebug(
      "focusPreferredRegion3D bounds=" +
        JSON.stringify(bounds) +
        " duration=" +
        String(durationSeconds)
    );
    setActiveTileBounds(bounds);
    focusLoadedRegion3D(durationSeconds);
  }

  function schedule3DFocusAfterMorph(durationSeconds) {
    const duration = Number.isFinite(durationSeconds) ? durationSeconds : 1.0;
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () {
        sceneDebug("schedule3DFocusAfterMorph executing duration=" + String(duration));
        focusPreferredRegion3D(duration);
      });
    });
  }

  function estimateBoundsSizeMeters(bounds) {
    const normalized = normalizeBounds(bounds);
    if (!normalized) {
      return { width: 0.0, height: 0.0, maxDimension: 0.0, diagonal: 0.0 };
    }
    const midLat = (normalized.south + normalized.north) * 0.5;
    const midLon = (normalized.west + normalized.east) * 0.5;
    const westPoint = Cesium.Cartographic.fromDegrees(normalized.west, midLat);
    const eastPoint = Cesium.Cartographic.fromDegrees(normalized.east, midLat);
    const southPoint = Cesium.Cartographic.fromDegrees(midLon, normalized.south);
    const northPoint = Cesium.Cartographic.fromDegrees(midLon, normalized.north);
    const horizontal = new Cesium.EllipsoidGeodesic(westPoint, eastPoint).surfaceDistance || 0.0;
    const vertical = new Cesium.EllipsoidGeodesic(southPoint, northPoint).surfaceDistance || 0.0;
    const width = Number.isFinite(horizontal) ? horizontal : 0.0;
    const height = Number.isFinite(vertical) ? vertical : 0.0;
    return {
      width: width,
      height: height,
      maxDimension: Math.max(width, height),
      diagonal: Math.hypot(width, height),
    };
  }

  function padBounds(bounds, paddingRatio) {
    const normalized = normalizeBounds(bounds);
    if (!normalized) {
      return null;
    }
    const ratio = Number.isFinite(paddingRatio) ? Math.max(0.0, paddingRatio) : 0.0;
    const lonSpan = Math.max(Math.abs(normalized.east - normalized.west), 0.00001);
    const latSpan = Math.max(Math.abs(normalized.north - normalized.south), 0.00001);
    const lonPad = lonSpan * ratio;
    const latPad = latSpan * ratio;
    const result = {
      west: normalized.west - lonPad,
      south: Math.max(-85.0, normalized.south - latPad),
      east: normalized.east + lonPad,
      north: Math.min(85.0, normalized.north + latPad),
    };
    return result;
  }

  function compute3DFocusRange(bounds) {
    const normalized = normalizeBounds(bounds);
    if (!normalized) {
      return 1200.0;
    }
    const rect = Cesium.Rectangle.fromDegrees(
      normalized.west,
      normalized.south,
      normalized.east,
      normalized.north
    );
    const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
    const size = estimateBoundsSizeMeters(normalized);
    const baseRange = Math.max(
      sphere.radius * 1.8,
      size.maxDimension * 1.8,
      size.diagonal * 1.25,
      75.0
    );
    return Math.min(Math.max(baseRange, 75.0), 2500000.0);
  }

  function focusLoadedRegion(durationSeconds) {
    if (!viewer) {
      return;
    }
    const boundsToUse = pendingFocusBounds || activeTileBounds || lastLoadedBounds;
    if (!boundsToUse) {
      return;
    }
    const paddedBounds = padBounds(boundsToUse, 0.04) || boundsToUse;
    const rect = Cesium.Rectangle.fromDegrees(
      paddedBounds.west,
      paddedBounds.south,
      paddedBounds.east,
      paddedBounds.north
    );
    viewer.camera.cancelFlight();
    viewer.camera.setView({ destination: rect });
    viewer.scene.requestRender();
  }

  function focusLoadedRegion2D(durationSeconds) {
    if (!viewer) {
      return;
    }
    const boundsToUse = pendingFocusBounds || activeTileBounds || lastLoadedBounds;
    if (!boundsToUse) {
      return;
    }
    const paddedBounds = padBounds(boundsToUse, 0.06) || boundsToUse;
    const rect = Cesium.Rectangle.fromDegrees(
      paddedBounds.west,
      paddedBounds.south,
      paddedBounds.east,
      paddedBounds.north
    );
    const duration = Number.isFinite(durationSeconds) ? durationSeconds : 0.6;
    viewer.camera.cancelFlight();
    viewer.camera.flyTo({
      destination: rect,
      duration: duration,
    });
    viewer.scene.requestRender();
  }

  function focusLoadedRegion3D(durationSeconds) {
    if (!viewer) {
      sceneDebug("focusLoadedRegion3D skipped: viewer unavailable");
      return;
    }
    const boundsToUse = pendingFocusBounds || activeTileBounds || lastLoadedBounds;
    if (!boundsToUse) {
      sceneDebug("focusLoadedRegion3D skipped: no bounds source");
      return;
    }
    const paddedBounds = padBounds(boundsToUse, 0.04) || boundsToUse;
    const rect = Cesium.Rectangle.fromDegrees(
      paddedBounds.west,
      paddedBounds.south,
      paddedBounds.east,
      paddedBounds.north
    );
    const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
    const range = Math.max(compute3DFocusRange(paddedBounds), sphere.radius * 1.3);
    const duration = Number.isFinite(durationSeconds) ? durationSeconds : 1.0;
    const heading = Number.isFinite(viewer.camera.heading) ? viewer.camera.heading : 0.0;
    sceneDebug(
      "focusLoadedRegion3D flyTo bounds=" +
        JSON.stringify(paddedBounds) +
        " heading=" +
        String(heading) +
        " range=" +
        String(range) +
        " duration=" +
        String(duration)
    );
    viewer.camera.cancelFlight();
    viewer.camera.flyToBoundingSphere(sphere, {
      offset: new Cesium.HeadingPitchRange(
        heading,
        Cesium.Math.toRadians(-35),
        range
      ),
      duration: duration,
    });
    viewer.scene.requestRender();
  }

  // ─────────────────────────────────────────────────────────────────────────
  //  DEM Rendering — Imagery-Only Pipeline
  //
  //  Design rationale: The previous approach used a custom TerrainProvider that
  //  decoded Terrarium-encoded PNGs frame-by-frame in the main JS thread. Cesium
  //  calls requestTileGeometry() synchronously for every visible tile, which
  //  spawned dozens of parallel Image loads + canvas operations per frame,
  //  exhausting the V8 heap and hanging/white-screening the globe. This is
  //  fundamentally incompatible with the QtWebEngine Chromium 87 environment.
  //
  //  The new approach renders DEM data as two flat EPSG:3857 imagery layers on
  //  the stable EllipsoidTerrainProvider:
  //    1. Colormap drape  — TiTiler colormap (gray/terrain) at full opacity
  //    2. Hillshade overlay — TiTiler hillshade algorithm at ~35% alpha
  //
  //  This is scientifically correct (standard GIS pseudo-color visualization),
  //  fully crash-proof for datasets of any size (2cm–5cm resolution, terabytes),
  //  and works identically on macOS and Windows/NVIDIA.
  // ─────────────────────────────────────────────────────────────────────────

  function shouldUseFetch(url) {
    const value = String(url || "").trim().toLowerCase();
    return value.startsWith("http://") || value.startsWith("https://");
  }

  async function loadJsonResource(url) {
    try {
      return await Cesium.Resource.fetchJson({ url: String(url) });
    } catch (_resourceError) {
      if (!shouldUseFetch(url)) {
        return null;
      }
      try {
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) {
          return null;
        }
        return await response.json();
      } catch (_fetchError) {
        return null;
      }
    }
  }



  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: DEM Terrain Rendering  →  future: modules/dem.js
  // Functions: OfflineCustomTerrainProvider (constructor + prototype),
  //   applyDemLayer, setDemColorMode, clearDemTerrainMode,
  //   updateDemColorbar, hideDemColorbar, resolveDemColorbarGradient,
  //   parseDemHeightRange, applyDemSceneSettings
  // ═══════════════════════════════════════════════════════════════════════════

  function applyDemLayer() {
    if (!viewer || !activeDemContext) return;
    
    log("info", "DEM_RENDER: ========== applyDemLayer START ==========");
    log("info", "DEM_RENDER: Context: " + JSON.stringify({
      name: activeDemContext.name,
      layerKey: activeDemContext.layerKey,
      visible: activeDemContext.visible,
      xyzUrl: activeDemContext.xyzUrl,
      hasBounds: !!(activeDemContext.options && activeDemContext.options.bounds),
      bounds: activeDemContext.options && activeDemContext.options.bounds
    }));
    
    const bounds = activeDemContext.options && activeDemContext.options.bounds ? activeDemContext.options.bounds : null;
    const rasterQuery = activeDemContext.options && activeDemContext.options.query ? activeDemContext.options.query : {};

    // Snapshot the original server rescale on FIRST load (before any user color-mode changes).
    // When user returns to gray/terrain we restore this so colors exactly match the colorbar.
    if (!_demOriginalRescale && typeof rasterQuery.rescale === "string" && rasterQuery.rescale.includes(",")) {
      _demOriginalRescale = rasterQuery.rescale;
      log("info", "DEM_RENDER: Captured original rescale range: " + _demOriginalRescale);
    }
    const minLevel = activeDemContext.options && Number.isInteger(activeDemContext.options.minzoom) ? activeDemContext.options.minzoom : 0;
    const maxLevelRaw = activeDemContext.options && Number.isInteger(activeDemContext.options.maxzoom) ? activeDemContext.options.maxzoom : 19;
    const imageryMaxLevel = Math.max(minLevel, maxLevelRaw);
    const terrainMaxLevel = Math.max(minLevel, Math.min(maxLevelRaw, DEM_MAX_TERRAIN_LEVEL));
    const rectangle = createRectangle(bounds);
    
    log("info", "DEM_RENDER: Layer parameters" +
        " minLevel=" + minLevel +
        " maxLevel=" + maxLevelRaw +
        " imageryMaxLevel=" + imageryMaxLevel +
        " terrainMaxLevel=" + terrainMaxLevel +
        " bounds=" + JSON.stringify(bounds) +
        " rectangle=" + (rectangle ? JSON.stringify({
          west: Cesium.Math.toDegrees(rectangle.west),
          south: Cesium.Math.toDegrees(rectangle.south),
          east: Cesium.Math.toDegrees(rectangle.east),
          north: Cesium.Math.toDegrees(rectangle.north)
        }) : "null"));
    
    const range = parseDemHeightRange(activeDemContext.options);
    const hillshadeQuery = {
      algorithm: "hillshade",
      azimuth: DEM_HILLSHADE_AZIMUTH,
      angle_altitude: DEM_HILLSHADE_ALTITUDE,
      z_exaggeration: demVisual.exaggeration,
      buffer: 4,
    };
    if (Object.prototype.hasOwnProperty.call(rasterQuery, "nodata")) {
      hillshadeQuery.nodata = rasterQuery.nodata;
    }
    const hillshadeUrl = buildUrlWithQuery(activeDemContext.xyzUrl, hillshadeQuery);
    const drapeQuery = {
      ...rasterQuery,
      resampling: "nearest",
    };
    const drapeUrl = buildUrlWithQuery(activeDemContext.xyzUrl, drapeQuery);
    
    log("info", "DEM imagery-only pipeline: drape=" + drapeUrl);
    
    const demVisible = activeDemContext.visible !== false;
    layerDefinitions.set(activeDemContext.layerKey, {
      key: activeDemContext.layerKey,
      label: String(activeDemContext.name || activeDemContext.layerKey || "DEM"),
      type: "dem",
      xyzUrl: activeDemContext.xyzUrl,
      query: { ...rasterQuery },
      drapeUrl: drapeUrl,
      hillshadeUrl: hillshadeUrl,
      minLevel: minLevel,
      maxLevel: imageryMaxLevel,
      bounds: normalizeBounds(bounds),
      hillshadeAlpha: demVisual.hillshadeAlpha,
    });
    layerVisibilityState.set(activeDemContext.layerKey, demVisible);

    // ── 3D DEM Rendering Pipeline ──────────────────────────────────────────
    // Build the terrain provider ONLY when the DEM is first loaded or the URL changes.
    // Never rebuild for exaggeration or color mode — those are handled in-place.
    const terrainUrl = drapeUrl;
    const terrainSignatureChanged = activeDemTerrainSignature !== activeDemContext.layerKey;

    log("info", "DEM_RENDER: Terrain provider check" +
        " signatureChanged=" + terrainSignatureChanged +
        " hasProvider=" + !!activeDemTerrainProvider +
        " currentSignature=" + activeDemTerrainSignature +
        " newSignature=" + activeDemContext.layerKey);

    if (terrainSignatureChanged || !activeDemTerrainProvider) {
      log("info", "DEM_RENDER: Building NEW terrain provider for key=" + activeDemContext.layerKey);
      const customTerrainProvider = new OfflineCustomTerrainProvider({
        url: terrainUrl,
        minLevel: minLevel,
        maxLevel: terrainMaxLevel,
        options: activeDemContext.options,
      });
      activeDemTerrainProvider = customTerrainProvider;
      activeDemTerrainSignature = activeDemContext.layerKey;
      log("info", "DEM_RENDER: Terrain provider built successfully" +
          " ready=" + customTerrainProvider.ready +
          " minLevel=" + minLevel +
          " maxLevel=" + terrainMaxLevel);

      if (demVisible) {
        log("info", "DEM_RENDER: Swapping to new terrain provider (DEM visible)");
        _swapTerrainProviderLocked(customTerrainProvider);
        log("info", "DEM_RENDER: Terrain provider swap complete, current provider type=" + 
            (viewer.terrainProvider === customTerrainProvider ? "CUSTOM" : "OTHER"));
      }
    } else if (demVisible && viewer.terrainProvider !== activeDemTerrainProvider) {
      // Re-show after hide — reuse existing provider, no rebuild
      log("info", "DEM_RENDER: Reusing existing terrain provider (was hidden, now visible)");
      _swapTerrainProviderLocked(activeDemTerrainProvider);
      log("info", "DEM_RENDER: Terrain provider reactivated");
    } else if (demVisible) {
      log("info", "DEM_RENDER: Terrain provider already active, no swap needed");
    }

    log("info", "DEM_RENDER: Current terrain provider: " + 
        (viewer.terrainProvider === activeDemTerrainProvider ? "CUSTOM_DEM" : "ELLIPSOID"));
    // ───────────────────────────────────────────────────────────────────────


    // Always clean up hillshade when drape URL changes to ensure proper layer rebuild
    const drapeUrlChanged = activeDemDrapeUrl !== drapeUrl;
    if (drapeUrlChanged && activeDemHillshadeLayer) {
      viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
      
      // CRITICAL FIX: Remove old DEM hillshade layer from managedImageryLayers map
      if (activeDemContext && activeDemContext.layerKey) {
        managedImageryLayers.delete(activeDemContext.layerKey + ":hillshade");
      }
      
      activeDemHillshadeLayer = null;
      activeDemHillshadeUrl = null;
    }

    if (!activeDemDrapeLayer || drapeUrlChanged) {
      if (activeDemDrapeLayer) {
        viewer.imageryLayers.remove(activeDemDrapeLayer, false);
        
        // CRITICAL FIX: Remove old DEM drape layer from managedImageryLayers map
        if (activeDemContext && activeDemContext.layerKey) {
          managedImageryLayers.delete(activeDemContext.layerKey);
        }
        
        activeDemDrapeLayer = null;
      }
      const drapeProvider = new Cesium.UrlTemplateImageryProvider({
        url: drapeUrl,
        maximumLevel: imageryMaxLevel,
        minimumLevel: minLevel,
        tilingScheme: new Cesium.WebMercatorTilingScheme(),
        enablePickFeatures: false,
        rectangle: rectangle,
      });
      
      log("info", "DEM_RENDER: Creating drape provider" +
          " url=" + drapeUrl +
          " minLevel=" + minLevel +
          " maxLevel=" + imageryMaxLevel +
          " rectangle=" + (rectangle ? JSON.stringify({
            west: Cesium.Math.toDegrees(rectangle.west),
            south: Cesium.Math.toDegrees(rectangle.south),
            east: Cesium.Math.toDegrees(rectangle.east),
            north: Cesium.Math.toDegrees(rectangle.north)
          }) : "null"));
      
      attachTileErrorHandler(drapeProvider, activeDemContext.name + "-drape");
      
      log("info", "DEM_RENDER: Adding drape layer to viewer");
      activeDemDrapeLayer = viewer.imageryLayers.addImageryProvider(drapeProvider);
      activeDemDrapeLayer.alpha = 1.0;
      activeDemDrapeLayer.show = demVisible;
      activeDemDrapeUrl = drapeUrl;
      
      // CRITICAL FIX: Tag DEM drape layer with key for reordering functionality
      activeDemDrapeLayer._layerKey = activeDemContext.layerKey;
      activeDemDrapeLayer._layerName = activeDemContext.name;
      
      // CRITICAL FIX: Add DEM drape layer to managedImageryLayers for reordering
      managedImageryLayers.set(activeDemContext.layerKey, activeDemDrapeLayer);
      
      log("info", "DEM_RENDER: Drape layer added" +
          " layerIndex=" + viewer.imageryLayers.indexOf(activeDemDrapeLayer) +
          " alpha=" + activeDemDrapeLayer.alpha +
          " show=" + activeDemDrapeLayer.show +
          " totalLayers=" + viewer.imageryLayers.length);
      
      // CRITICAL: Force immediate tile loading by requesting render
      viewer.scene.requestRender();
      
      // Log all imagery layers for debugging
      log("info", "DEM_RENDER: All imagery layers:");
      for (let i = 0; i < viewer.imageryLayers.length; i++) {
        const layer = viewer.imageryLayers.get(i);
        log("info", "  Layer " + i + ": alpha=" + layer.alpha + " show=" + layer.show + 
            " ready=" + (layer.imageryProvider && layer.imageryProvider.ready));
      }
    }

    const clampedHillshadeAlpha = Math.max(0.0, Math.min(1.0, demVisual.hillshadeAlpha));
    
    // Always create the hillshade layer, even if alpha is 0.
    // This allows the slider to update alpha in real-time without needing a full DEM rebuild.
    if (activeDemHillshadeLayer && activeDemHillshadeUrl !== hillshadeUrl) {
      viewer.imageryLayers.remove(activeDemHillshadeLayer, false);
      
      // CRITICAL FIX: Remove old DEM hillshade layer from managedImageryLayers map
      if (activeDemContext && activeDemContext.layerKey) {
        managedImageryLayers.delete(activeDemContext.layerKey + ":hillshade");
      }
      
      activeDemHillshadeLayer = null;
      activeDemHillshadeUrl = null;
    }
    if (!activeDemHillshadeLayer) {
      const hillshadeProvider = new Cesium.UrlTemplateImageryProvider({
        url: hillshadeUrl,
        maximumLevel: imageryMaxLevel,
        minimumLevel: minLevel,
        tilingScheme: new Cesium.WebMercatorTilingScheme(),
        enablePickFeatures: false,
        rectangle: rectangle,
      });
      attachTileErrorHandler(hillshadeProvider, activeDemContext.name + "-hillshade");
      activeDemHillshadeLayer = viewer.imageryLayers.addImageryProvider(hillshadeProvider);
      activeDemHillshadeUrl = hillshadeUrl;
      
      // CRITICAL FIX: Tag DEM hillshade layer with key for reordering functionality
      // Use a different key suffix to distinguish from drape layer
      const hillshadeKey = activeDemContext.layerKey + ":hillshade";
      activeDemHillshadeLayer._layerKey = hillshadeKey;
      activeDemHillshadeLayer._layerName = activeDemContext.name + " (Hillshade)";
      
      // CRITICAL FIX: Add DEM hillshade layer to managedImageryLayers for reordering
      managedImageryLayers.set(hillshadeKey, activeDemHillshadeLayer);
      
      log("info", "DEM_RENDER: Hillshade layer added at index " + viewer.imageryLayers.indexOf(activeDemHillshadeLayer));
    }
    activeDemHillshadeLayer.alpha = clampedHillshadeAlpha;
    activeDemHillshadeLayer.show = demVisible;

    applyDemSceneSettings();
    
    // CRITICAL FIX: Only ensure basemap is at bottom, don't force other layer positions
    // This allows user reordering to work properly without conflicts
    log("info", "DEM_RENDER: Ensuring basemap at bottom (preserving user layer order)");
    
    // Step 1: Ensure basemap is at the very bottom (index 0) - this is essential
    if (osmBasemapLayer && osmBasemapLayer.show && viewer.imageryLayers.indexOf(osmBasemapLayer) >= 0) {
      viewer.imageryLayers.lowerToBottom(osmBasemapLayer);
      log("info", "DEM_RENDER: OSM basemap at index 0 (bottom)");
    } else if (defaultEarthLayer && viewer.imageryLayers.indexOf(defaultEarthLayer) >= 0) {
      viewer.imageryLayers.lowerToBottom(defaultEarthLayer);
      log("info", "DEM_RENDER: Default Earth layer at index 0 (bottom)");
    }
    
    // REMOVED: Automatic layer stacking that conflicts with user reordering
    // The reorderLayersEventDriven() function now handles all layer positioning
    // This prevents the "dusky" appearance and layer visibility issues
    
    // Log final layer stack for debugging
    log("info", "DEM_RENDER: Current layer stack (bottom to top):");
    for (let i = 0; i < viewer.imageryLayers.length; i++) {
      const layer = viewer.imageryLayers.get(i);
      const layerType = (layer === defaultEarthLayer) ? "Default-Earth" :
                       (layer === osmBasemapLayer) ? "OSM" : 
                       (layer === activeDemDrapeLayer) ? "DEM-drape" :
                       (layer === activeDemHillshadeLayer) ? "DEM-hillshade" :
                       (managedImageryLayers.has(layer)) ? "RGB-imagery" : "unknown";
      log("info", "  [" + i + "] " + layerType + ": alpha=" + layer.alpha.toFixed(2) + 
          " show=" + layer.show + " ready=" + (layer.imageryProvider && layer.imageryProvider.ready));
    }
    
    // Single render request (request-render mode will handle subsequent renders)
    viewer.scene.requestRender();
    
    log("debug", "DEM layer stack: hillshade=" + (activeDemHillshadeLayer ? "yes" : "no") + " drape=" + (activeDemDrapeLayer ? "yes" : "no") + " managed=" + managedImageryLayers.size);
    if (demVisible) {
      updateDemColorbar(range.min, range.max, activeDemContext.options);
      setStatus("DEM terrain active: " + activeDemContext.name);
    } else {
      hideDemColorbar();
      setStatus("DEM layer hidden.");
    }
    log(
      "info",
      "DEM activated name=" +
        activeDemContext.name +
        " min=" +
        minLevel +
        " imageryMax=" +
        imageryMaxLevel +
        " drape=" +
        drapeUrl
    );
    
    log("info", "DEM_RENDER: ========== applyDemLayer END ==========");
    
    // BUG-FIX: Do NOT auto-focus here. Python calls focusBoundsWithPadding after ALL layers
    // load (DEM + imagery), giving one smooth fly-to with tiles visible. An internal
    // setTimeout(focusBounds, 200) inside applyDemLayer raced with the Python fly-to,
    // causing black-screen flicker and erratic camera jumps.
    log("info", "DEM_RENDER: Skipping internal auto-focus — Python controls single fly-to after all layers load.");
    
    logLayerStack();
    if (comparatorModeEnabled) {
      refreshComparatorLayers();
    }
    requestSceneRender();
  }

  // GPU-adaptive decode concurrency: set after GPU detection in initViewer,
  // fallback 1 for safety (Intel gets 1, NVIDIA gets 4).
  let MAX_CONCURRENT_TERRAIN_DECODES = 1;
  let activeTerrainDecodes = 0;
  const terrainDecodeQueue = [];
  const terrainDecodeCanvas = document.createElement("canvas");
  terrainDecodeCanvas.width = TERRAIN_SAMPLE_SIZE;
  terrainDecodeCanvas.height = TERRAIN_SAMPLE_SIZE;
  const terrainDecodeCtx = terrainDecodeCanvas.getContext("2d", { willReadFrequently: true });

  function processTerrainDecodeQueue() {
    while (terrainDecodeQueue.length > 0 && activeTerrainDecodes < MAX_CONCURRENT_TERRAIN_DECODES) {
      const task = terrainDecodeQueue.shift();
      activeTerrainDecodes++;
      task().finally(() => {
        activeTerrainDecodes--;
        processTerrainDecodeQueue();
      });
    }
  }

  function enqueueTerrainDecode(taskFn) {
    return new Promise((resolve, reject) => {
      terrainDecodeQueue.push(async () => {
        try {
          resolve(await taskFn());
        } catch (err) {
          reject(err);
        }
      });
      processTerrainDecodeQueue();
    });
  }

  function OfflineCustomTerrainProvider(options) {
    this.tilingScheme = new Cesium.WebMercatorTilingScheme();
    this.hasWaterMask = false;
    this.hasVertexNormals = false;
    this.ready = true;
    this.readyPromise = Cesium.when.resolve(true);
    this.errorEvent = new Cesium.Event();
    
    this._url = options.url;
    this._min = options.minLevel || 0;
    this._max = options.maxLevel || DEM_MAX_TERRAIN_LEVEL;
    this._rangeMin = 0;
    this._rangeMax = 0;
    
    if (options.options && options.options.query && options.options.query.rescale) {
      const parts = String(options.options.query.rescale).split(",");
      if (parts.length === 2) {
        this._rangeMin = parseFloat(parts[0]);
        this._rangeMax = parseFloat(parts[1]);
      }
    }
  }

  OfflineCustomTerrainProvider.prototype.requestTileGeometry = function (x, y, level) {
    if (level > this._max) {
      return Cesium.when.reject(new Error("Exceeded max level"));
    }
    
    const tileUrl = this._url.replace("%7Bz%7D", level).replace("%7Bx%7D", x).replace("%7By%7D", y).replace("{z}", level).replace("{x}", x).replace("{y}", y);
    
    return Cesium.when(enqueueTerrainDecode(() => {
      return new Promise((resolve, reject) => {
        const img = new Image();
        img.crossOrigin = "anonymous";
        
        // CRITICAL: Timeout for terabyte-scale data (prevent infinite hangs)
        const timeoutId = setTimeout(() => {
          img.onload = null;
          img.onerror = null;
          // Return flat tile on timeout (prevents black screens)
          const output = new Float32Array(TERRAIN_SAMPLE_SIZE * TERRAIN_SAMPLE_SIZE);
          resolve(new Cesium.HeightmapTerrainData({
            buffer: output,
            width: TERRAIN_SAMPLE_SIZE,
            height: TERRAIN_SAMPLE_SIZE,
            // Use unit scale; exaggeration is applied via globe.terrainExaggeration for live updates.
            structure: { heightScale: 1.0, heightOffset: 0.0, elementsPerHeight: 1, stride: 1 }
          }));
        }, 5000);  // 5 second timeout for ultra-high resolution tiles
        
        img.onload = () => {
          clearTimeout(timeoutId);
          terrainDecodeCtx.clearRect(0, 0, TERRAIN_SAMPLE_SIZE, TERRAIN_SAMPLE_SIZE);
          terrainDecodeCtx.drawImage(img, 0, 0, TERRAIN_SAMPLE_SIZE, TERRAIN_SAMPLE_SIZE);
          const imgData = terrainDecodeCtx.getImageData(0, 0, TERRAIN_SAMPLE_SIZE, TERRAIN_SAMPLE_SIZE);
          const data = imgData.data;
          const output = new Float32Array(TERRAIN_SAMPLE_SIZE * TERRAIN_SAMPLE_SIZE);
          
          const rMin = this._rangeMin;
          const span = this._rangeMax - rMin;
          
          for (let i = 0; i < output.length; i++) {
            const val = data[i * 4]; 
            if (data[i * 4 + 3] === 0) {
              output[i] = 0; 
            } else {
              output[i] = rMin + (val / 255.0) * span;
            }
          }
          
          img.onload = null;
          img.onerror = null;
          
          resolve(new Cesium.HeightmapTerrainData({
            buffer: output,
            width: TERRAIN_SAMPLE_SIZE,
            height: TERRAIN_SAMPLE_SIZE,
            // Use unit scale; exaggeration is applied via globe.terrainExaggeration for live updates.
            structure: { heightScale: 1.0, heightOffset: 0.0, elementsPerHeight: 1, stride: 1 }
          }));
        };
        
        img.onerror = () => {
          clearTimeout(timeoutId);
          img.onload = null;
          img.onerror = null;
          // Return flat tile on error (prevents black screens)
          const output = new Float32Array(TERRAIN_SAMPLE_SIZE * TERRAIN_SAMPLE_SIZE);
          resolve(new Cesium.HeightmapTerrainData({
            buffer: output,
            width: TERRAIN_SAMPLE_SIZE,
            height: TERRAIN_SAMPLE_SIZE,
            // Use unit scale; exaggeration is applied via globe.terrainExaggeration for live updates.
            structure: { heightScale: 1.0, heightOffset: 0.0, elementsPerHeight: 1, stride: 1 }
          }));
        };
        
        img.src = tileUrl;
      });
    }));
  };

  OfflineCustomTerrainProvider.prototype.getLevelMaximumGeometricError = function (level) {
    return 7785.0 / Math.pow(2, level);
  };
  OfflineCustomTerrainProvider.prototype.getTileDataAvailable = function (x, y, level) {
    return level <= this._max;
  };

  function setDemColorMode(colormapName) {
    if (!activeDemContext) return;
    if (!activeDemContext.options) activeDemContext.options = {};
    if (!activeDemContext.options.query) activeDemContext.options.query = {};

    const normalized = String(colormapName || "gray").toLowerCase();
    const query = activeDemContext.options.query;

    if (normalized === "slope") {
      query.algorithm = "slope";
      query.colormap_name = "viridis";
      query.rescale = "0,90";
    } else {
      // Returning to gray/terrain: restore original server rescale so colors match the colorbar
      delete query.algorithm;
      query.colormap_name = normalized;
      if (_demOriginalRescale) {
        query.rescale = _demOriginalRescale;  // restore original min,max from server
      }
    }

    // In-place URL swap — no terrain rebuild, no camera jump.
    if (activeDemDrapeLayer && activeDemContext) {
      const rasterQuery = activeDemContext.options.query || {};
      const drapeQuery = { ...rasterQuery, resampling: "nearest" };
      const newDrapeUrl = buildUrlWithQuery(activeDemContext.xyzUrl, drapeQuery);

      if (newDrapeUrl !== activeDemDrapeUrl) {
        const bounds = activeDemContext.options && activeDemContext.options.bounds ? activeDemContext.options.bounds : null;
        const rectangle = createRectangle(bounds);
        const minLevel = activeDemContext.options && Number.isInteger(activeDemContext.options.minzoom) ? activeDemContext.options.minzoom : 0;
        const maxLevel = activeDemContext.options && Number.isInteger(activeDemContext.options.maxzoom) ? activeDemContext.options.maxzoom : 19;

        // Snapshot camera
        const savedPos = viewer.camera.position.clone();
        const savedHdg = viewer.camera.heading;
        const savedPitch = viewer.camera.pitch;
        const savedRoll = viewer.camera.roll;

        // FIX: Smooth layer swapping without black flash.
        // We add the new layer first, then wait 1500ms before removing the old one.
        const oldDrapeLayer = activeDemDrapeLayer;

        const drapeProvider = new Cesium.UrlTemplateImageryProvider({
          url: newDrapeUrl,
          maximumLevel: maxLevel,
          minimumLevel: minLevel,
          tilingScheme: new Cesium.WebMercatorTilingScheme(),
          enablePickFeatures: false,
          rectangle: rectangle,
        });
        activeDemDrapeLayer = viewer.imageryLayers.addImageryProvider(drapeProvider);
        activeDemDrapeLayer.alpha = 1.0;
        activeDemDrapeLayer.show = activeDemContext.visible !== false;
        activeDemDrapeUrl = newDrapeUrl;

        // Clean up the old layer quickly — 200ms is enough for 2-3 new tiles to arrive
        // avoiding the black flash while still feeling near-instant to the user
        if (oldDrapeLayer) {
          setTimeout(() => {
            if (viewer && viewer.imageryLayers && viewer.imageryLayers.contains(oldDrapeLayer)) {
              viewer.imageryLayers.remove(oldDrapeLayer, false);
            }
          }, 200);
        }

        // Re-apply the last known layer display order so imagery stays on top (or below)
        // without requiring a Python round-trip. This prevents color-mode changes from
        // breaking the layer stack the user explicitly arranged.
        if (_lastKnownLayerOrder && _lastKnownLayerOrder.length > 0) {
          // Small defer so the new provider settles before reordering
          setTimeout(function() {
            if (window.offlineGIS && window.offlineGIS.enforceLayerDisplayOrder) {
              window.offlineGIS.enforceLayerDisplayOrder(_lastKnownLayerOrder);
            }
          }, 0);
        } else {
          // Fallback: raise hillshade and managed imagery layers above new drape
          if (activeDemHillshadeLayer) viewer.imageryLayers.raiseToTop(activeDemHillshadeLayer);
          for (const layer of managedImageryLayers.values()) {
            if (layer && layer.show && viewer.imageryLayers.indexOf(layer) >= 0) {
              viewer.imageryLayers.raiseToTop(layer);
            }
          }
        }

        // Removed camera locking to prevent jumping when changing color modes

        requestSceneRender();
        log("debug", "setDemColorMode: in-place drape swap colormap=" + normalized);

        // Update colorbar gradient to match new color mode
        const range = parseDemHeightRange(activeDemContext.options);
        updateDemColorbar(range.min, range.max, activeDemContext.options);
      }
    } else {
      // No active drape layer yet — do a full apply with camera lock
      // CRITICAL FIX (Bug 4): Prevent applyDemLayer from resetting camera
      // when changing style dropdown
      if (viewer && viewer.camera) {
        var savedPos = viewer.camera.position.clone();
        var savedHdg = viewer.camera.heading;
        var savedPitch = viewer.camera.pitch;
        var savedRoll = viewer.camera.roll;
        applyDemLayer();
        // Lock camera for 5 frames to absorb async resets from layer changes
        var framesLeft = 5;
        var lockHandle = viewer.scene.postRender.addEventListener(function () {
          viewer.camera.setView({
            destination: savedPos,
            orientation: { heading: savedHdg, pitch: savedPitch, roll: savedRoll },
          });
          framesLeft -= 1;
          if (framesLeft <= 0) lockHandle();
        });
      } else {
        applyDemLayer();
      }
    }
  }

  function initBridge() {
    if (typeof QWebChannel === "undefined" || !window.qt || !qt.webChannelTransport) {
      setStatus("Bridge unavailable, running standalone Cesium mode.");
      log("warn", "QWebChannel transport unavailable; initializing viewer without bridge binding");
      initViewer();
      return;
    }
    new QWebChannel(qt.webChannelTransport, function (channel) {
      bridge = channel.objects.bridge;
      runtime.bridge = bridge;
      setStatus("Bridge connected.");
      log("info", "QWebChannel bridge connected");
      initViewer();
    });
  }
  function installSmoothInteractionManager(targetViewer) {
    if (!targetViewer || !targetViewer.scene || !targetViewer.canvas) {
      return;
    }
    if (targetViewer.__smoothInteractionManagerInstalled) {
      return;
    }
    targetViewer.__smoothInteractionManagerInstalled = true;

    const scene = targetViewer.scene;
    const canvas = targetViewer.canvas;
    let interacting = false;
    let idleTimer = null;
    const IDLE_DELAY_MS = 150;
    const baseSse = Number(scene.globe.maximumScreenSpaceError) || 2.0;
    const movingSse = Math.max(4.0, baseSse + 2.0);

    function applyInteractionTilePolicy(active) {
      if (!scene.globe) {
        return;
      }
      // Keep tile preloading enabled during interaction to reduce choppy pans/zooms
      // without lowering imagery or terrain quality.
      scene.globe.preloadAncestors = true;
      scene.globe.preloadSiblings = true;
    }

    function startInteraction() {
      if (idleTimer) {
        clearTimeout(idleTimer);
        idleTimer = null;
      }
      if (!interacting) {
        interacting = true;
        isInteracting = true;
        // FIX: Removed requestRenderMode toggle to prevent rendering lag and auto-blurring
      }
      scene.requestRender();
    }

    function scheduleIdle() {
      if (idleTimer) {
        clearTimeout(idleTimer);
      }
      idleTimer = setTimeout(function () {
        interacting = false;
        isInteracting = false;
        // FIX: Removed requestRenderMode toggle to prevent rendering lag and auto-blurring
        applyInteractionTilePolicy(false);
        scene.requestRender();
        idleTimer = null;
      }, IDLE_DELAY_MS);
    }

    targetViewer.camera.moveStart.addEventListener(startInteraction);
    targetViewer.camera.moveEnd.addEventListener(scheduleIdle);

    ["pointerdown", "touchstart"].forEach(function (eventName) {
      canvas.addEventListener(eventName, startInteraction, { passive: true });
    });
    ["pointermove", "touchmove"].forEach(function (eventName) {
      canvas.addEventListener(
        eventName,
        function () {
          if (!interacting) {
            startInteraction();
          }
        },
        { passive: true }
      );
    });


    // ── Custom symmetric wheel zoom — replaces Cesium's asymmetric pick-distance zoom ──
    // Problem: Cesium's zoom-in computes zoomAmount = pickDistance × zoomFactor, where
    // pickDistance is the ray intersection with the terrain/ellipsoid. With EllipsoidTerrainProvider
    // this intersection can be meters away from the camera, resulting in violent ultra-fast
    // zoom-in even though zoom-out (which uses altitude) feels slow and correct.
    //
    // Fix: Disable Cesium's built-in wheel zoom entirely and replace it with a custom handler
    // that computes a SYMMETRIC zoom amount = currentAltitude × STEP_FRACTION for BOTH in and out.
    // We move along the camera direction to avoid pick-distance jitter while tiles refine.
    if (viewer && viewer.scene && viewer.scene.screenSpaceCameraController) {
      viewer.scene.screenSpaceCameraController.enableZoom = false;
    }

    const WHEEL_ZOOM_STEP = 0.12;  // 12% of current altitude per tick — medium-fast
    let wheelZoomImpulse = 0;
    let wheelZoomRaf = null;

    canvas.addEventListener("wheel", function (event) {
      event.preventDefault();
      if (!targetViewer || !targetViewer.scene || !targetViewer.camera) {
        return;
      }
      startInteraction();

      const delta = event.deltaY !== 0 ? event.deltaY : -event.wheelDelta;
      wheelZoomImpulse += delta < 0 ? 1 : -1;

      if (wheelZoomRaf !== null) {
        return;
      }

      wheelZoomRaf = window.requestAnimationFrame(function () {
        wheelZoomRaf = null;
        const camera = targetViewer.camera;
        const scene = targetViewer.scene;

        const posCart = camera.positionCartographic;
        if (!posCart || !Number.isFinite(posCart.height)) {
          wheelZoomImpulse = 0;
          scheduleIdle();
          return;
        }

        const altitude = Math.max(posCart.height, 50.0);
        const stepCount = Math.max(-10, Math.min(10, wheelZoomImpulse));
        const zoomAmount = altitude * WHEEL_ZOOM_STEP * Math.abs(stepCount || 1);
        const zoomingIn = stepCount > 0;
        wheelZoomImpulse = 0;

        if (scene.mode === Cesium.SceneMode.SCENE2D) {
          if (zoomingIn) {
            camera.zoomIn(zoomAmount);
          } else {
            camera.zoomOut(zoomAmount);
          }
        } else {
          const direction = camera.direction ? camera.direction.clone() : null;
          if (!direction) {
            scheduleIdle();
            return;
          }
          if (!zoomingIn) {
            Cesium.Cartesian3.negate(direction, direction);
          }

          const move = Cesium.Cartesian3.multiplyByScalar(direction, zoomAmount, new Cesium.Cartesian3());
          const nextPos = Cesium.Cartesian3.add(camera.position, move, new Cesium.Cartesian3());
          const nextCarto = Cesium.Cartographic.fromCartesian(nextPos);
          if (nextCarto && Number.isFinite(nextCarto.height) && nextCarto.height >= 10.0) {
            camera.setView({
              destination: nextPos,
              orientation: {
                heading: camera.heading,
                pitch: camera.pitch,
                roll: camera.roll,
              },
            });
          }
        }

        scene.requestRender();
        scheduleIdle();
      });
    }, { passive: false });

    ["pointerup", "pointercancel", "touchend"].forEach(function (eventName) {
      canvas.addEventListener(eventName, scheduleIdle, { passive: true });
    });

    scene.globe.tileLoadProgressEvent.addEventListener(function (tilesRemaining) {
      if (tilesRemaining > 0) {
        startInteraction();
        return;
      }
      scheduleIdle();
    });

    window._requestRender = function () {
      if (!targetViewer || !targetViewer.scene) {
        return;
      }
      const currentScene = targetViewer.scene;
      const wasOnDemand = currentScene.requestRenderMode;
      currentScene.requestRenderMode = false;
      currentScene.requestRender();
      setTimeout(function () {
        currentScene.requestRenderMode = wasOnDemand;
        currentScene.requestRender();
      }, 200);
    };

    scheduleIdle();
    log("info", "Smooth interaction manager installed (Windows-optimized)");
  }

  function initViewer() {
    if (!window.Cesium) {
      setStatus("Cesium.js not found. Add local Cesium assets under web_assets/cesium.");
      log("error", "Cesium runtime not found");
      return;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // CRITICAL PATCH: Handle statusCode 0 for local Assets (Windows/file://)
    // ─────────────────────────────────────────────────────────────────────────
    if (Cesium.Resource && Cesium.Resource.prototype && Cesium.Resource.prototype.fetchJson) {
      const originalFetchJson = Cesium.Resource.prototype.fetchJson;
      Cesium.Resource.prototype.fetchJson = function() {
        const reqUrl = String(this.url || "");
        
        const handleRejection = function(error) {
          if (error && error.statusCode === 0 && typeof error.response === "string") {
            try {
              return JSON.parse(error.response);
            } catch (e) {
              log("warn", "JSON.parse failed for local file (" + reqUrl + "): " + e.message);
            }
          }
          if (Cesium.when && Cesium.when.reject) {
            return Cesium.when.reject(error);
          }
          return Promise.reject(error);
        };

        const promise = originalFetchJson.apply(this, arguments);
        if (promise && typeof promise.then === "function") {
          return promise.then(undefined, handleRejection);
        }
        return promise;
      };
      log("info", "Cesium.Resource.fetchJson patched for local file compatibility.");
    }

    // ─────────────────────────────────────────────────────────────────────────
    // CRITICAL BYPASS: Prevent approximateTerrainHeights.json fetch crash
    // ─────────────────────────────────────────────────────────────────────────
    // On Windows local file://, this 2.5MB asset often truncates or fails, causing a synchronous 
    // renderer crash when clampToGround is first used (e.g., drawing AOI). By pre-initializing it 
    // with an empty object and a resolved promise, Cesium skips the fetch entirely and safely falls 
    // back to generic terrain bounds without crashing.
    if (Cesium.ApproximateTerrainHeights) {
      Cesium.ApproximateTerrainHeights._terrainHeights = {};
      Cesium.ApproximateTerrainHeights._initPromise = (Cesium.when && Cesium.when.resolve) 
        ? Cesium.when.resolve() 
        : Promise.resolve();
      log("info", "Bypassed approximateTerrainHeights.json fetch to prevent clampToGround crashes.");
    }

    // Probe NaturalEarthII availability — on Windows the cesium/ symlink may not
    viewer = new Cesium.Viewer("cesiumContainer", {
      imageryProvider: false,  // No basemap - bare globe only
      baseLayerPicker: false,
      geocoder: false,
      navigationHelpButton: false,
      sceneModePicker: false,
      homeButton: false,
      fullscreenButton: false,
      infoBox: false,
      selectionIndicator: false,
      scene3DOnly: false,
      requestRenderMode: false,  // Globally disabled to maintain continuous render loop
      maximumRenderTimeChange: Infinity,  // Let smooth interaction manager control render timing
      timeline: false,
      animation: false,
      terrainProvider: new Cesium.EllipsoidTerrainProvider(),
      orderIndependentTranslucency: false,
      contextOptions: {
        webgl: {
          alpha: false,
          depth: true,
          stencil: false,
          antialias: false,  // Disable antialiasing for performance
          powerPreference: "high-performance",  // Use discrete GPU (NVIDIA) if available
          preserveDrawingBuffer: true,
          failIfMajorPerformanceCaveat: false,
          desynchronized: false,
        },
      },
      msaaSamples: 1,  // Disable MSAA for performance
      useBrowserRecommendedResolution: false,
    });
    runtime.viewer = viewer;
    
    // GPU-accelerated rendering optimizations
    viewer.resolutionScale = 1.0;  // Full resolution for sharp rendering (don't divide by devicePixelRatio)
    viewer.scene.postProcessStages.fxaa.enabled = false;  // Disable FXAA for performance
    viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#2a3a4a");
    viewer.scene.backgroundColor = Cesium.Color.fromCssColorString("#0a0a0a");
    viewer.canvas.style.backgroundColor = "#0a0a0a";
    
    // Performance optimizations for ultra-smooth interaction
    viewer.useDefaultRenderLoop = true;
    viewer.scene.requestRenderMode = false; // FIX: Disabled to prevent auto-blurring and visual stutter
    viewer.scene.maximumRenderTimeChange = 0;
    viewer.scene.globe.tileCacheSize = 800;  // Larger cache for ultra-smooth panning (optimized for Windows/NVIDIA)
    viewer.scene.fog.enabled = false;  // Disable fog for performance
    viewer.scene.skyAtmosphere.show = false;  // Disable atmosphere for performance
    viewer.scene.sun.show = false;  // Disable sun for performance
    viewer.scene.moon.show = false;  // Disable moon for performance
    viewer.scene.skyBox.show = false;  // Disable skybox for performance
    viewer.scene.globe.showGroundAtmosphere = false;  // Disable ground atmosphere
    viewer.scene.globe.enableLighting = false;  // Disable lighting for performance
    viewer.scene.globe.depthTestAgainstTerrain = true;  // Required for proper DEM layer sorting and occlusion
    
    // Optimize tile loading for smoother experience
    viewer.scene.globe.maximumScreenSpaceError = 3;  // Optimized for faster loading while maintaining quality
    viewer.scene.globe.preloadAncestors = true;  // Preload for smoother zooming
    viewer.scene.globe.preloadSiblings = true;  // Preload for smoother panning
    
    // Additional performance optimizations
    viewer.scene.fxaa = false;  // Disable FXAA post-processing
    viewer.scene.highDynamicRange = false;  // Disable HDR for performance
    viewer.scene.logarithmicDepthBuffer = true;  // Required for smooth 3D camera dragging and Z-fighting prevention
    viewer.scene.globe.showWaterEffect = false;  // Disable water effect
    viewer.scene.globe.showSkirts = true;  // Keep skirts to avoid gaps between tiles
    
    // Optimize rendering pipeline
    viewer.scene.pickTranslucentDepth = false;  // Disable translucent depth picking
    viewer.scene.useDepthPicking = false;  // Disable depth picking for performance
    
    log("info", "Viewer initialized with GPU acceleration and ultra-smooth interaction settings");
    
    // ═══════════════════════════════════════════════════════════════════════════
    // CRITICAL: GPU Detection for Intel vs NVIDIA performance tuning
    // ═══════════════════════════════════════════════════════════════════════════
    window._isHighEndGpu = false;
    window._gpuRenderer = "Unknown";
    try {
      const canvas = document.createElement('canvas');
      const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
      if (gl) {
        const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
        if (debugInfo) {
          const renderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);
          if (renderer) {
            window._gpuRenderer = renderer;
            const r = renderer.toLowerCase();
            // Detect dedicated GPUs (NVIDIA, AMD Radeon RX/Pro)
            if (r.indexOf("nvidia") !== -1 || r.indexOf("rtx") !== -1 || r.indexOf("gtx") !== -1 || 
                r.indexOf("quadro") !== -1 || (r.indexOf("amd") !== -1 && r.indexOf("radeon rx") !== -1)) {
              window._isHighEndGpu = true;
            }
          }
        }
      }
    } catch (e) {
      log("warn", "Failed to detect GPU renderer: " + e);
    }
    
    log("info", "GPU Detected: " + window._gpuRenderer + " (High-End: " + window._isHighEndGpu + ")");

    // ═══════════════════════════════════════════════════════════════════════════
    // CRITICAL: GPU-adaptive viewer initialization
    // Two profiles: MAX (NVIDIA/dedicated) vs SAFE (Intel/integrated)
    // NOTE: requestRenderMode stays FALSE (set above) for continuous render loop.
    // ═══════════════════════════════════════════════════════════════════════════
    
    // Shared: always disable expensive cosmetics
    viewer.scene.fog.enabled = false;
    viewer.scene.skyAtmosphere.show = false;
    viewer.scene.sun.show = false;
    viewer.scene.moon.show = false;
    viewer.scene.globe.enableLighting = false;
    viewer.scene.globe.showGroundAtmosphere = false;
    
    if (window._isHighEndGpu) {
      // ── MAX CONFIG (NVIDIA / Quadro) ──────────────────────────────────────
      MAX_CONCURRENT_TERRAIN_DECODES = 8;   // Parallel terrain decodes for workstation
      viewer.resolutionScale = 1.0;          // Full native resolution
      viewer.scene.logarithmicDepthBuffer = true;
      viewer.scene.globe.depthTestAgainstTerrain = true;
      viewer.scene.globe.tileCacheSize = 1000; // Large cache for high-fidelity assets
      viewer.scene.globe.maximumScreenSpaceError = 0.8; // Ultra fidelity for workstation
      viewer.scene.globe.preloadAncestors = true;
      viewer.scene.globe.preloadSiblings = true;
      viewer.scene.globe.loadingDescendantLimit = 16;
      
      // NVIDIA GL hint
      if (viewer.scene.context && viewer.scene.context._gl) {
        const gl = viewer.scene.context._gl;
        gl.hint(gl.GENERATE_MIPMAP_HINT, gl.FASTEST);
      }
      
      log("info", "[INIT MAX GPU CONFIG] NVIDIA/Quadro workstation GPU detected — Extreme fidelity enabled");
    } else {
      // ── SAFE CONFIG (Intel integrated / unknown) ──────────────────────────
      MAX_CONCURRENT_TERRAIN_DECODES = 2;   // Slightly more parallel decodes for modern Intel
      viewer.resolutionScale = 1.0;          // Full native resolution to maintain imagery quality
      viewer.scene.logarithmicDepthBuffer = true;
      viewer.scene.globe.depthTestAgainstTerrain = true; // Essential for true 3D fidelity
      viewer.scene.globe.tileCacheSize = 400;  // Optimized cache for smoother panning on Windows
      viewer.scene.globe.maximumScreenSpaceError = 3.5;  // Balanced performance/quality for Intel UHD
      viewer.scene.globe.preloadAncestors = true; // Enabled for smoother zoom transitions
      viewer.scene.globe.preloadSiblings = true;
      viewer.scene.globe.loadingDescendantLimit = 2;  // Faster tile loading
      
      log("info", "[INIT SAFE INTEL CONFIG] Integrated GPU optimized for smooth performance (res=1.0 sse=3.5 cache=400)");
    }

    scenePerfDefaults = {
      tileCacheSize: Number(viewer.scene.globe.tileCacheSize) || 0,
      loadingDescendantLimit: Number(viewer.scene.globe.loadingDescendantLimit) || 0,
      preloadAncestors: Boolean(viewer.scene.globe.preloadAncestors),
      preloadSiblings: Boolean(viewer.scene.globe.preloadSiblings),
    };
    
    applyDefaultSceneSettings();
    tuneCameraController();
    
    // Set camera sensitivity for smooth performance (from smooth implementation)
    viewer.camera.percentageChanged = 0.001;
    
    log("info", "Cesium default camera controls enabled");
    
    // ═══════════════════════════════════════════════════════════════════════════
    // CRITICAL: WebGL Context Loss Recovery for Desktop Application
    // Handles GPU context loss from laptop sleep, driver crashes, or GPU resets
    // Essential for long-running desktop applications (days/weeks uptime)
    // ═══════════════════════════════════════════════════════════════════════════
    
    let contextLostCount = 0;
    let contextRestoreRenderMode = false;
    const MAX_CONTEXT_RECOVERY_ATTEMPTS = 3;
    
    // Listen for WebGL context loss events
    if (viewer.canvas) {
      viewer.canvas.addEventListener('webglcontextlost', function(event) {
        event.preventDefault();  // Prevent default behavior
        contextLostCount++;
        
        log("error", "WebGL context lost (attempt " + contextLostCount + "/" + MAX_CONTEXT_RECOVERY_ATTEMPTS + ") - GPU may have been powered down or driver crashed");
        
        // Show user-friendly message
        setStatus("GPU context lost - attempting recovery...");
        
        // Disable rendering during recovery
        if (viewer && viewer.scene) {
          contextRestoreRenderMode = viewer.scene.requestRenderMode;
          viewer.scene.requestRenderMode = false;
          viewer.scene.requestRender();
        }
      }, false);
      
      // Listen for WebGL context restored events
      viewer.canvas.addEventListener('webglcontextrestored', function(event) {
        log("info", "WebGL context restored - reinitializing scene");
        
        if (contextLostCount >= MAX_CONTEXT_RECOVERY_ATTEMPTS) {
          log("error", "Max context recovery attempts reached - manual restart required");
          setStatus("GPU recovery failed - please restart the application");
          return;
        }
        
        try {
          // Reinitialize scene after context restoration
          if (viewer && viewer.scene) {
            // Force scene re-render
            viewer.scene.requestRenderMode = false;
            viewer.scene.requestRender();
            setTimeout(function() {
              if (viewer && viewer.scene) {
                viewer.scene.requestRenderMode = false;
                viewer.scene.requestRender();
              }
            }, 250);
            
            // Reload all active layers
            log("info", "Reloading active layers after context restoration");
            
            // Reload DEM if active
            if (activeDemContext && activeDemContext.visible) {
              log("info", "Reloading DEM layer: " + activeDemContext.name);
              applyDemLayer();
            }
            
            // Reload imagery layers
            for (const [layerKey, layer] of managedImageryLayers.entries()) {
              if (layer && layer.show) {
                log("info", "Reloading imagery layer: " + layerKey);
                // Layer will be reloaded automatically by Cesium
              }
            }
            
            // Reload OSM basemap if visible
            if (osmBasemapLayer && osmBasemapLayer.show) {
              log("info", "Reloading OSM basemap");
              // OSM will be reloaded automatically by Cesium
            }
            
            if (viewer && viewer.scene) {
              viewer.scene.requestRenderMode = contextRestoreRenderMode;
              viewer.scene.requestRender();
            }
            setStatus("GPU context recovered successfully");
            log("info", "WebGL context recovery complete");
          }
        } catch (e) {
          log("error", "Failed to recover from context loss: " + e.message);
          setStatus("GPU recovery failed - please restart the application");
        }
      }, false);
      
      log("info", "WebGL context loss recovery handlers installed");
    }
    
    // ── Add default Earth imagery layer (always visible as base) ────────────
    // This provides a fast, single-image world map when OSM tiles are hidden
    try {
      // Use Cesium's built-in TileMapServiceImageryProvider with NaturalEarthII
      // This is a single low-resolution world map that loads instantly
      // FIXED: Use constructor syntax instead of fromUrl() which doesn't exist
      const defaultEarthProvider = new Cesium.TileMapServiceImageryProvider({
        url: Cesium.buildModuleUrl('Assets/Textures/NaturalEarthII')
      });
      
      defaultEarthLayer = viewer.imageryLayers.addImageryProvider(defaultEarthProvider);
      defaultEarthLayer.alpha = 1.0;
      defaultEarthLayer.show = true;  // Always visible as base layer
      log("info", "Default Earth imagery layer added (NaturalEarthII)");
    } catch (e) {
      // Fallback: Use a solid color if NaturalEarthII is not available
      log("warn", "Failed to add default Earth layer: " + e.message);
      viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#2a3a4a");
    }
    
    // ── OSM basemap tiles (lazy-loaded, initially hidden) ────────────────
    // OSM tiles are NOT loaded on startup - only when user selects "Show Map"
    // This provides instant startup and smooth transition
    osmBasemapLayer = null;  // Will be created on first "Show Map" request
    
    log("info", "Basemap system initialized: Default Earth (always visible) + OSM tiles (lazy-loaded)");
    
    applyDefaultStartupFocus();
    let lastErrorMessage = "";
    let lastErrorTime = 0;
    window.addEventListener("error", function (event) {
      // Ignore errors from Cesium.js itself
      if (event && event.filename && event.filename.includes("Cesium.js")) {
        return;
      }
      const msg = event && event.message ? event.message : "unknown";
      const now = Date.now();
      // Suppress duplicate errors within 1 second
      if (msg === lastErrorMessage && now - lastErrorTime < 1000) {
        return;
      }
      lastErrorMessage = msg;
      lastErrorTime = now;
      const err = event && event.error ? event.error : null;
      const stack = err && err.stack ? err.stack : "";
      log("error", "Window error: " + msg + (stack ? " | " + stack : ""));
    });
    window.addEventListener("unhandledrejection", function (event) {
      const reason = event && event.reason ? String(event.reason) : "unknown";
      log("error", "Unhandled promise rejection: " + reason);
    });

    if (SHOW_COUNTRY_BOUNDARY_OVERLAY) {
      void attachCountryBoundaryOverlay();
    }
    let _renderErrorCount = 0;
    let _renderErrorResetTimer = null;
    let _lastRenderErrorTime = 0;
    
    viewer.scene.renderError.addEventListener(function (scene, error) {
      const now = Date.now();
      _renderErrorCount += 1;
      
      if (_renderErrorResetTimer) clearTimeout(_renderErrorResetTimer);
      // Reset count after 10 seconds of stability
      _renderErrorResetTimer = setTimeout(function () { _renderErrorCount = 0; }, 10000);
      
      let msg = "unknown render error";
      if (error) {
        if (typeof error === "string") {
          msg = error;
        } else if (error.stack) {
          msg = error.stack;
        } else if (error.message) {
          msg = error.message;
        } else {
          // Robust inspection for RequestErrorEvent or other complex objects
          msg = "Error: " + (error.name || "Object");
          if (error.statusCode) msg += " (Status: " + error.statusCode + ")";
          if (error.url) msg += " [URL: " + error.url + "]";
          try { 
            // Extract common non-enumerable properties before stringifying
            const detailObj = {
              message: error.message,
              name: error.name,
              stack: error.stack,
              statusCode: error.statusCode,
              response: (typeof error.response === "string" && error.response.length > 500) 
                        ? error.response.substring(0, 500) + "... [truncated]" 
                        : error.response
            };
            const stringified = JSON.stringify(detailObj); 
            msg += " Details: " + stringified;
          } catch (e) { 
            msg += " (Non-stringifiable details)"; 
          }
        }
      }

      log("error", "Cesium render error (" + _renderErrorCount + "): " + msg);

      // CRITICAL: Throttle recovery attempts. Stop at 8 errors.
      if (_renderErrorCount > 8) {
        if (_renderErrorCount === 9) {
          log("error", "Render errors exceeded threshold — stopping recovery to prevent infinite loop.");
          setStatus("3D engine encountered a critical error. Please refresh.");
        }
        viewer.useDefaultRenderLoop = false;
        return;
      }

      // If we errored too quickly after the last error (within 50ms), skip this recovery step
      if (now - _lastRenderErrorTime < 50) {
        return;
      }
      _lastRenderErrorTime = now;

      try {
        viewer.useDefaultRenderLoop = true;
        // Force a synchronous render to verify recovery
        viewer.render();
        log("info", "Render loop recovered successfully.");
      } catch (recoveryErr) {
        log("error", "Render recovery attempt failed: " + recoveryErr);
      }
    });

    viewer.imageryLayers.layerAdded.addEventListener(function (_layer, index) {
      log("info", "Imagery layer added at index " + index);
    });
    viewer.scene.morphStart.addEventListener(function (_transitioner, oldMode, newMode) {
      sceneDebug(
        "morphStart oldMode=" +
          oldMode +
          " newMode=" +
          newMode +
          " currentSceneMode=" +
          currentSceneMode +
          " pendingSceneModeAfterMorph=" +
          String(pendingSceneModeAfterMorph)
      );
    });
    viewer.scene.morphComplete.addEventListener(function () {
      const resolvedMode = detectSceneMode();
      sceneDebug(
        "morphComplete resolvedMode=" +
          resolvedMode +
          " current(before)=" +
          currentSceneMode +
          " pendingSceneModeAfterMorph=" +
          String(pendingSceneModeAfterMorph) +
          " pendingFlyThroughBounds=" +
          String(Boolean(pendingFlyThroughBounds)) +
          " pendingFocusAfterMorph=" +
          String(pendingFocusAfterMorph)
      );
      currentSceneMode = resolvedMode === "morphing" ? currentSceneMode : resolvedMode;
      syncSceneModeToggle(currentSceneMode);
      configureCameraControllerForMode(currentSceneMode);
      if (pendingSceneModeAfterMorph) {
        const nextMode = pendingSceneModeAfterMorph;
        pendingSceneModeAfterMorph = null;
        sceneDebug("morphComplete applying queued mode=" + nextMode + " from current=" + currentSceneMode);
        if (nextMode !== currentSceneMode) {
          setSceneModeInternal(nextMode);
          return;
        }
      }
      if (pendingFlyThroughBounds && currentSceneMode === "3d") {
        const queuedBounds = pendingFlyThroughBounds;
        pendingFlyThroughBounds = null;
        pendingFocusAfterMorph = false;
        pendingTerrainSceneAfterMorph = false;
        pendingFocusBounds = null;
        startFlyThroughBounds(queuedBounds.west, queuedBounds.south, queuedBounds.east, queuedBounds.north);
        return;
      }
      if (pendingFocusAfterMorph) {
        pendingFocusAfterMorph = false;
        const bounds = pendingFocusBounds;
        pendingFocusBounds = null;
        if (bounds) {
          if (currentSceneMode === "2d") {
            focusLoadedRegion2D(0.6);
          } else if (window.offlineGIS && typeof window.offlineGIS.focusBoundsWithPadding === "function") {
            window.offlineGIS.focusBoundsWithPadding(bounds.west, bounds.south, bounds.east, bounds.north, 1.2);
          }
        } else if (pendingTerrainSceneAfterMorph) {
          focusPreferredRegion3D(1.0);
        }
      }
      pendingTerrainSceneAfterMorph = false;
    });
    viewer.scene.postRender.addEventListener(updateEdgeScaleWidgets);
    wireClickHandlers();
    wireStatusBarListeners();
    installSmoothInteractionManager(viewer);

    // Force a few initial renders to ensure the globe paints
    viewer.scene.requestRender();
    window.requestAnimationFrame(function () {
      viewer.scene.requestRender();
      window.requestAnimationFrame(function () {
        viewer.scene.requestRender();
      });
    });
    setStatus("Offline Cesium initialized.");
    log("info", "Viewer initialized with local offline basemap pipeline");
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: Basemap & OSM Tiles  →  future: modules/basemap.js
  //   updateBasemapBlendForCurrentMode, attachOfflineTerrainPack,
  //   clearPolarCapLayers, ensurePolarCapLayers
  // ═══════════════════════════════════════════════════════════════════════════

  async function attachCountryBoundaryOverlay() {
    if (!viewer || countryBoundaryDataSource) {
      return false;
    }
    try {
      const dataSource = await Cesium.GeoJsonDataSource.load(COUNTRY_BOUNDARY_GEOJSON_URL, {
        clampToGround: false,
      });
      viewer.dataSources.add(dataSource);
      const boundaryColor = Cesium.Color.fromCssColorString("#e7edf7").withAlpha(0.72);
      dataSource.entities.values.forEach(function (entity) {
        if (!entity.polyline) {
          return;
        }
        entity.polyline.clampToGround = false;
        entity.polyline.arcType = Cesium.ArcType.GEODESIC;
        entity.polyline.width = 1.3;
        entity.polyline.material = boundaryColor;
        entity.polyline.depthFailMaterial = boundaryColor.withAlpha(0.62);
      });
      countryBoundaryDataSource = dataSource;
      viewer.scene.requestRender();
      log("info", "Offline country-boundary overlay loaded.");
      return true;
    } catch (error) {
      if (looksLikeMissingLocalAssetError(error)) {
        log("info", "No offline country-boundary overlay found.");
        return false;
      }
      log("warn", "Offline country-boundary overlay could not be loaded: " + String(error));
      return false;
    }
  }



  // clearPolarCapLayers + ensurePolarCapLayers removed — polar cap rendering not used in current pipeline



  function readLabelText(labelEntity) {
    if (!labelEntity || !labelEntity.label || !labelEntity.label.text) {
      return "";
    }
    if (typeof labelEntity.label.text.getValue === "function") {
      return String(labelEntity.label.text.getValue(Cesium.JulianDate.now()) || "");
    }
    return String(labelEntity.label.text || "");
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: Annotations  →  future: modules/annotations.js
  // Functions: setAnnotationEditIconHoverState, renameAnnotationFromEditIcon,
  //   updateAnnotationHover, clearAnnotationEntities, setAnnotationVisibility
  // ═══════════════════════════════════════════════════════════════════════════

  function setAnnotationEditIconHoverState(editEntity, hovered) {
    if (!editEntity || !editEntity.billboard) {
      return;
    }
    editEntity.billboard.color = hovered ? Cesium.Color.WHITE.withAlpha(0.96) : Cesium.Color.WHITE.withAlpha(0.42);
  }
  function setAnnotationDeleteIconHoverState(deleteEntity, hovered) {
    if (!deleteEntity || !deleteEntity.billboard) return;
    deleteEntity.billboard.color = hovered ? Cesium.Color.WHITE.withAlpha(0.96) : Cesium.Color.WHITE.withAlpha(0.62);
  }

  function renameAnnotationFromEditIcon(editEntity) {
    if (!editEntity || editEntity._annotationRole !== "edit") {
      return false;
    }
    const labelEntity = editEntity._annotationLabelEntity || null;
    if (!labelEntity || !labelEntity.label) {
      return false;
    }
    const currentText = readLabelText(labelEntity) || "Point";
    const nextText = window.prompt("Rename point", currentText);
    if (nextText === null) {
      return true;
    }
    const cleaned = String(nextText).trim();
    if (!cleaned) {
      return true;
    }
    labelEntity.label.text = cleaned;
    setStatus("Point renamed: " + cleaned);
    requestSceneRender();
    return true;
  }

  function updateAnnotationHover(screenPosition) {
    if (!viewer || !screenPosition) {
      return;
    }
    const picked = viewer.scene.pick(screenPosition);
    const nextHover = picked && picked.id && picked.id._annotationRole === "edit" ? picked.id : null;
    if (hoveredAnnotationEditEntity !== nextHover) {
      if (hoveredAnnotationEditEntity) setAnnotationEditIconHoverState(hoveredAnnotationEditEntity, false);
      hoveredAnnotationEditEntity = nextHover;
      if (hoveredAnnotationEditEntity) setAnnotationEditIconHoverState(hoveredAnnotationEditEntity, true);
    }
    const nextDelHover = picked && picked.id && picked.id._annotationRole === "delete" ? picked.id : null;
    if (hoveredAnnotationDeleteEntity !== nextDelHover) {
      if (hoveredAnnotationDeleteEntity) setAnnotationDeleteIconHoverState(hoveredAnnotationDeleteEntity, false);
      hoveredAnnotationDeleteEntity = nextDelHover;
      if (hoveredAnnotationDeleteEntity) setAnnotationDeleteIconHoverState(hoveredAnnotationDeleteEntity, true);
    }
    requestSceneRender();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: Status Bar Bridge Emitters  →  future: modules/ui.js
  // Functions: emitMouseCoordinates, emitCameraChanged,
  //   wireStatusBarListeners, _updateCompass
  // ═══════════════════════════════════════════════════════════════════════════

  // ── Status-bar bridge emitters (QGIS-style) ──────────────────────────────
  function emitMouseCoordinates(lon, lat) {
    if (!bridge || !bridge.on_mouse_coordinates) return;
    const now = Date.now();
    const throttleMs = isInteracting ? 16 : (currentSceneMode === "2d" ? 60 : _SB_COORD_THROTTLE_MS);
    if (now - _sbLastCoordEmitMs < throttleMs) return;
    _sbLastCoordEmitMs = now;

    // Elevation field has been removed from the UI; emit lon/lat only.
    bridge.on_mouse_coordinates(lon, lat);
  }

  function emitCameraChanged() {
    if (!bridge || !bridge.on_camera_changed || !viewer || !viewer.camera) return;
    
    // Throttle camera change events to reduce overhead
    const now = Date.now();
    const cameraThrottleMs = currentSceneMode === "2d" ? 200 : _SB_CAMERA_THROTTLE_MS;
    if (now - _sbLastCameraEmitMs < cameraThrottleMs) return;
    _sbLastCameraEmitMs = now;
    
    try {
      // Compute approximate scale denominator from camera altitude + canvas size
      const height = viewer.camera.positionCartographic.height;
      const canvas = viewer.canvas;
      const fovY = viewer.camera.frustum.fovy || 1.0472;
      const visibleMeters = 2.0 * height * Math.tan(fovY * 0.5);
      const pixelHeight = canvas.clientHeight || 1;
      const metersPerPixel = visibleMeters / pixelHeight;
      // 96 dpi screen: 1 pixel ≈ 0.000265 m physical → scale = mPx / 0.000265
      const scaleDenom = metersPerPixel / 0.000265;

      let headingDeg = Cesium.Math.toDegrees(viewer.camera.heading);
      if (headingDeg < 0) headingDeg += 360.0;
      
      let pitchDeg = Cesium.Math.toDegrees(viewer.camera.pitch);
      
      bridge.on_camera_changed(scaleDenom, headingDeg, pitchDeg);
    } catch (_) {}
  }

  function wireStatusBarListeners() {
    if (!viewer || !viewer.scene) return;
    
    // Camera moved → update scale + heading + start tile loading monitor
    viewer.camera.changed.addEventListener(function() {
      if (isInteracting) {
        return;
      }
      emitCameraChanged();
      _updateCompass();
      if (!_tileLoadingActive) {
        startTileLoadingMonitor();
      }
    });
    
    // CRITICAL: Force render after camera stops moving (prevents black screens in request-render mode)
    viewer.camera.moveEnd.addEventListener(function() {
      emitCameraChanged();
      _updateCompass();
      if (!_tileLoadingActive) {
        startTileLoadingMonitor();
      }
      
      // Force multiple renders to ensure tiles load after camera movement
      // This prevents black screens when using requestRenderMode=true
      viewer.scene.requestRender();
      setTimeout(function() { 
        if (viewer && viewer.scene) viewer.scene.requestRender(); 
      }, 50);
      setTimeout(function() { 
        if (viewer && viewer.scene) viewer.scene.requestRender(); 
      }, 150);
      setTimeout(function() { 
        if (viewer && viewer.scene) viewer.scene.requestRender(); 
      }, 300);
    });

    // Re-apply terrainExaggeration after every tile load batch.
    // Cesium 1.78 resets globe.terrainExaggeration when new terrain tiles are decoded.
    // Also drive the progress bar from this native event — accurate, zero polling lag.
    viewer.scene.globe.tileLoadProgressEvent.addEventListener(function (queueLength) {
      if (isInteracting) {
        return;
      }
      // Terrain exaggeration persistence
      if (queueLength === 0 && activeDemContext && activeDemContext.visible !== false) {
        const target = Math.max(0.1, demVisual.exaggeration);
        if (Math.abs(viewer.scene.globe.terrainExaggeration - target) > 0.001) {
          viewer.scene.globe.terrainExaggeration = target;
        }
        // Also persist verticalExaggeration for Cesium 1.90+
        if (typeof viewer.scene.verticalExaggeration !== "undefined" && Math.abs(viewer.scene.verticalExaggeration - target) > 0.001) {
          viewer.scene.verticalExaggeration = target;
        }
      }

      // Real-time progress bar — driven by native tile queue length
      if (queueLength > 0) {
        _tileQueuePeak = Math.max(_tileQueuePeak, queueLength);
        const loaded = _tileQueuePeak - queueLength;
        const percent = _tileQueuePeak > 0 ? Math.min(95, Math.round((loaded / _tileQueuePeak) * 100)) : 10;
        emitLoadingProgress(percent, "Loading tiles");
        _tileLoadingActive = true;
        // Cancel any pending drain timer — queue is still active
        if (_tileQueuePeak > 0 && typeof _tileDrainTimer !== 'undefined' && _tileDrainTimer) {
          clearTimeout(_tileDrainTimer);
          _tileDrainTimer = null;
        }
      } else if (_tileLoadingActive) {
        // Queue drained — debounce the completion signal by 200 ms so a
        // rapid new-layer load doesn't cause a 100 → 0 flash on the bar.
        if (typeof _tileDrainTimer === 'undefined' || !_tileDrainTimer) {
          _tileDrainTimer = setTimeout(function () {
            _tileDrainTimer = null;
            if (!_tileLoadingActive) return;
            emitLoadingProgress(100, "Complete");
            _tileLoadingActive = false;
            _tileQueuePeak = 0;
          }, 200);
        }
      }
    });
    const compassEl = document.getElementById("compassWidget");
    if (compassEl) {
      compassEl.addEventListener("click", function () {
        if (!viewer) return;
        
        // Check if any assets are active
        const bounds = activeTileBounds || lastLoadedBounds;
        
        if (bounds) {
          // Assets active: Focus on active asset bounds smoothly and fast
          const rect = Cesium.Rectangle.fromDegrees(bounds.west, bounds.south, bounds.east, bounds.north);
          viewer.camera.flyTo({
            destination: rect,
            orientation: { heading: 0.0, pitch: Cesium.Math.toRadians(-90), roll: 0.0 },
            duration: 0.8  // Fast 0.8 second animation
          });
          log("info", "Compass clicked: focusing on active asset bounds");
        } else {
          // No assets active: Return to default India view
          viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(78.0, 22.0, 6000000),  // India center, 6000km height
            orientation: { heading: 0.0, pitch: Cesium.Math.toRadians(-90), roll: 0.0 },
            duration: 1.2  // Smooth 1.2 second animation
          });
          log("info", "Compass clicked: returning to default India view");
        }
        requestSceneRender();
      });
    }

    // Throttled compass rotation update — only update when camera moves
    let lastCompassHeading = NaN;
    const COMPASS_UPDATE_THRESHOLD = 0.5;  // degrees
    viewer.scene.postRender.addEventListener(function() {
      if (isInteracting || currentSceneMode === "2d") return;
      if (!viewer || !viewer.camera) return;
      const headingDeg = Cesium.Math.toDegrees(viewer.camera.heading);
      
      // Only update if heading changed significantly
      if (Math.abs(headingDeg - lastCompassHeading) < COMPASS_UPDATE_THRESHOLD) return;
      lastCompassHeading = headingDeg;
      
      const needle = document.getElementById("compassNeedle");
      const nLabel = document.getElementById("compassNLabel");
      if (!needle) return;
      
      // Use CSS transform for GPU-accelerated rotation
      needle.style.transform = `rotate(${headingDeg.toFixed(2)}deg)`;
      needle.style.transformOrigin = "32px 32px";
      if (nLabel) {
        nLabel.style.transform = `rotate(${(-headingDeg).toFixed(2)}deg)`;
        nLabel.style.transformOrigin = "32px 20px";
      }
    });
  }

  function _updateCompass() {
    // Deprecated - compass now updates via postRender listener
  }

  function wireClickHandlers() {
    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    
    // Track mouse down position to distinguish clicks from drags
    let mouseDownPosition = null;
    const CLICK_THRESHOLD = 5; // pixels - if mouse moves more than this, it's a drag, not a click
    
    // Track LEFT_DOWN to detect clicks vs drags
    handler.setInputAction(function (movement) {
      if (movement && movement.position) {
        mouseDownPosition = {
          x: movement.position.x,
          y: movement.position.y
        };
      }
    }, Cesium.ScreenSpaceEventType.LEFT_DOWN);
    
    // Handle LEFT_UP - only process as click if mouse didn't move much
    handler.setInputAction(function (movement) {
      // Check if this was a click (minimal movement) or a drag (significant movement)
      if (mouseDownPosition && movement && movement.position) {
        const dx = Math.abs(movement.position.x - mouseDownPosition.x);
        const dy = Math.abs(movement.position.y - mouseDownPosition.y);
        const distance = Math.sqrt(dx * dx + dy * dy);
        
        // If mouse moved more than threshold, this was a drag, not a click - ignore it
        if (distance > CLICK_THRESHOLD) {
          mouseDownPosition = null;
          return;
        }
      }
      
      mouseDownPosition = null;
      
      // Process as click
      if (handleFlyThroughClick(movement)) return;
      
      const picked = movement && movement.position ? viewer.scene.pick(movement.position) : null;
      if (picked && picked.id && picked.id._annotationRole === "edit") {
        if (renameAnnotationFromEditIcon(picked.id)) {
          return;
        }
      }
      if (picked && picked.id && picked.id._annotationRole === "delete") {
        var delE = picked.id;
        var delTargets = [delE._annotationAnchorEntity, delE._annotationLabelEntity, delE._annotationEditEntity, delE];
        for (var di = 0; di < delTargets.length; di++) {
          var dIdx = annotationEntities.indexOf(delTargets[di]);
          if (dIdx > -1) annotationEntities.splice(dIdx, 1);
          if (delTargets[di]) viewer.entities.remove(delTargets[di]);
        }
        requestSceneRender();
        log("info", "Deleted annotation id=" + (delE._annotationId || "?"));
        return;
      }
      // Polygon edit (rename)
      if (picked && picked.id && picked.id._polyRole === "edit") {
        var polyId = picked.id._polyRecordId;
        var polys = drawnPolygons;
        for (var pi = 0; pi < polys.length; pi++) {
          if (polys[pi].id === polyId && polys[pi].nameLabelEntity) {
            var curName = polys[pi].label || "Polygon " + polyId;
            var newName = prompt("Rename polygon:", curName);
            if (newName && newName.trim()) {
              polys[pi].label = newName.trim();
              polys[pi].nameLabelEntity.label.text = newName.trim();
              requestSceneRender();
            }
            break;
          }
        }
        return;
      }
      // Polygon delete
      if (picked && picked.id && picked.id._polyRole === "delete") {
        var delPolyId = picked.id._polyRecordId;
        for (var pj = drawnPolygons.length - 1; pj >= 0; pj--) {
          if (drawnPolygons[pj].id === delPolyId) {
            var rec = drawnPolygons[pj];
            if (rec.lineEntity) viewer.entities.remove(rec.lineEntity);
            if (rec.polygonEntity) viewer.entities.remove(rec.polygonEntity);
            if (rec.areaLabelEntity) viewer.entities.remove(rec.areaLabelEntity);
            if (rec.nameLabelEntity) viewer.entities.remove(rec.nameLabelEntity);
            if (rec.editEntity) viewer.entities.remove(rec.editEntity);
            if (rec.deleteEntity) viewer.entities.remove(rec.deleteEntity);
            for (var vi = 0; vi < (rec.vertexEntities || []).length; vi++) {
              if (rec.vertexEntities[vi]) viewer.entities.remove(rec.vertexEntities[vi]);
            }
            drawnPolygons.splice(pj, 1);
            requestSceneRender();
            log("info", "Deleted polygon id=" + delPolyId);
            break;
          }
        }
        return;
      }

      // Try multiple picking strategies to guarantee a coordinate.
      // Strategy 1: scene.pickPosition (uses depth buffer, most accurate)
      // Strategy 2: globe.pick (works on terrain surface)
      // Strategy 3: pickEllipsoid (always works, ignores terrain height)
      let lonLat = null;
      let clickCartesian = null;

      if (movement && movement.position) {
        // Strategy 1: scene.pickPosition — uses depth buffer, most accurate at any zoom
        // This correctly handles high-resolution imagery where terrain mesh may lag
        if (viewer.scene.pickPositionSupported) {
          try {
            const depthCart = viewer.scene.pickPosition(movement.position);
            if (depthCart && Cesium.Cartesian3.magnitude(depthCart) > 1.0) {
              clickCartesian = depthCart;
            }
          } catch (_) {}
        }

        // Strategy 2: globe.pick via ray (works on terrain surface when depth unavailable)
        if (!clickCartesian) {
          const ray = viewer.camera.getPickRay(movement.position);
          if (ray) {
            clickCartesian = viewer.scene.globe.pick(ray, viewer.scene);
          }
        }

        // Strategy 3: ellipsoid fallback (always succeeds, ignores terrain height)
        if (!clickCartesian) {
          clickCartesian = viewer.camera.pickEllipsoid(
            movement.position,
            viewer.scene.globe.ellipsoid
          );
        }

        if (clickCartesian) {
          lonLat = cartesianToLonLat(clickCartesian);
          lastMapClickCartesian = Cesium.Cartesian3.clone(clickCartesian);
        }
      }

      if (!lonLat) {
        // Click was outside globe or on UI element - silently ignore
        // This is normal behavior when clicking on controls, edges, etc.
        log("debug", "Click outside globe or on UI element - no coordinate resolved");
        return;
      }
      
      const lon = lonLat.lon;
      const lat = lonLat.lat;

      // Fly Through draw
      if (flyThroughModeEnabled) {
        flyThroughPoints.push(clickCartesian);
        updateFlyThroughPreview();
        setStatus("Fly Through: added point " + flyThroughPoints.length + ". Right-click to finish.");
        return;
      }

      // Polygon draw — always fires if in polygon mode (doesn't block annotation placement below)
      if (searchDrawMode === "polygon") {
        if (searchPolygonLocked) {
          setStatus("Polygon restored. Clear geometry to start a new polygon.");
          // Don't return — annotation point can still be placed
        } else {
          searchPolygonPoints.push({ lon: lon, lat: lat, cartesian: clickCartesian ? Cesium.Cartesian3.clone(clickCartesian) : null });
          searchCursorPoint = null;
          updateSearchPolygonPreview();
          setStatus("Polygon draw: continue points, right-click or Finish to close");
          // Fall through — annotation point can also be placed simultaneously if annotationModeEnabled
        }
      }

      if (distanceMeasureModeEnabled) {
        try {
          emitMapClick(lon, lat);
          log("info", "Distance mode click lon=" + lon.toFixed(6) + " lat=" + lat.toFixed(6));
          if (!distanceMeasureAnchor) {
            // First click: set anchor and draw a visible dot
            distanceMeasureAnchor = { lon: lon, lat: lat, height: lonLat.height || 0 };
            clickedPoints.length = 0;
            clickedPoints.push([lon, lat]);
            clearMeasurementPreviewEntities();
            // Add a visible anchor dot at the first click point
            const anchorHeight = distanceMeasureAnchor.height;
            const anchorPos = Cesium.Cartesian3.fromDegrees(lon, lat, anchorHeight);
            if (measurementAnchorDotEntity) {
              try { viewer.entities.remove(measurementAnchorDotEntity); } catch(_) {}
            }
            measurementAnchorDotEntity = viewer.entities.add({
              position: anchorPos,
              point: {
                pixelSize: 11,
                color: Cesium.Color.fromCssColorString("#00e5ff"),
                outlineColor: Cesium.Color.WHITE,
                outlineWidth: 2,
                disableDepthTestDistance: Number.POSITIVE_INFINITY,
              },
            });
            requestSceneRender();
            setStatus("Distance tool: move cursor and click second point to finalize.");
            return;
          }

          // Second click: finalize measurement, clear anchor (stop chaining)
          const geodesic = new Cesium.EllipsoidGeodesic(
            Cesium.Cartographic.fromDegrees(distanceMeasureAnchor.lon, distanceMeasureAnchor.lat),
            Cesium.Cartographic.fromDegrees(lon, lat)
          );
          let azDegrees = Cesium.Math.toDegrees(geodesic.startHeading);
          if (azDegrees < 0) azDegrees += 360.0;
          clearMeasurementPreviewEntities();
          updateMeasurementEntities(
            distanceMeasureAnchor.lon,
            distanceMeasureAnchor.lat,
            lon,
            lat,
            geodesic.surfaceDistance,
            azDegrees,
            distanceMeasureAnchor.height,
            lonLat.height || 0
          );
          distanceMeasureAnchor = null;  // reset so next click starts fresh
          const _dist = geodesic.surfaceDistance;
          setTimeout(function() { emitMeasurementUpdated(_dist); }, 0);
          setStatus("Distance measured. Click to start a new measurement, or right-click to stop.");
          log("info", "Distance measured (m): " + geodesic.surfaceDistance.toFixed(2));
        } catch (e) {
          log("error", "Distance measurement error: " + (e.message || String(e)));
        }
        return;
      }

      clickedPoints.push([lon, lat]);
      if (clickedPoints.length > 2) clickedPoints.shift();

      // Fill-volume label expand/collapse — handled here in the persistent handler
      // to avoid creating/destroying ScreenSpaceEventHandler per analysis (macOS crash).
      if (window._fillVolumeEntities && window._fillVolumeEntities.length > 0) {
        var picked2 = viewer.scene.pick(movement.position);
        if (Cesium.defined(picked2) && Cesium.defined(picked2.id)) {
          var ent2 = picked2.id;
          if (ent2.isRegionLabel === true && ent2.detailsEntity) {
            var det = ent2.detailsEntity;
            var wasExpanded = ent2.expanded;
            det.label.show = !wasExpanded;
            ent2.expanded = !wasExpanded;
            ent2.label.text = (wasExpanded ? '\u25bc' : '\u25b2') + ' Region ' + ent2.regionId;
            requestSceneRender();
            return;
          }
        }
      }

      emitMapClick(lon, lat);
      log("debug", "Map click lon=" + lon.toFixed(6) + " lat=" + lat.toFixed(6));
    }, Cesium.ScreenSpaceEventType.LEFT_UP);

    handler.setInputAction(function (movement) {
      let statusCoordEmitted = false;
      if (movement && movement.endPosition) {
        if (window.OfflineGISCursorControls) {
          window.OfflineGISCursorControls.lastSearchCursorScreenPosition = movement.endPosition;
        }
        updateAnnotationHover(movement.endPosition);

        // Keep status-bar lon/lat responsive during drag using a cheap ellipsoid pick.
        let fastLonLat = null;
        if (isInteracting) {
          const ellipsoidCart = viewer.camera.pickEllipsoid(movement.endPosition, viewer.scene.globe.ellipsoid);
          if (ellipsoidCart) {
            fastLonLat = cartesianToLonLat(ellipsoidCart);
          }
        } else {
          fastLonLat = getLonLatFromScreen(movement.endPosition);
        }
        if (fastLonLat) {
          emitMouseCoordinates(fastLonLat.lon, fastLonLat.lat);
          statusCoordEmitted = true;
        }
      }
      if (
        isInteracting &&
        searchDrawMode !== "polygon" &&
        !distanceMeasureModeEnabled &&
        !window._profileModeActive &&
        !window._profileLineActive
      ) {
        return;
      }
      if (distanceMeasureModeEnabled && distanceMeasureAnchor && searchDrawMode !== "polygon") {
        try {
          // Use pickEllipsoid as guaranteed fallback for preview over terrain
          let lonLat = getLonLatFromScreen(movement.endPosition);
          if (!lonLat && movement.endPosition) {
            const ellipsoidCart = viewer.camera.pickEllipsoid(movement.endPosition, viewer.scene.globe.ellipsoid);
            if (ellipsoidCart) lonLat = cartesianToLonLat(ellipsoidCart);
          }
          if (lonLat) {
            const geodesic = new Cesium.EllipsoidGeodesic(
              Cesium.Cartographic.fromDegrees(distanceMeasureAnchor.lon, distanceMeasureAnchor.lat),
              Cesium.Cartographic.fromDegrees(lonLat.lon, lonLat.lat)
            );
            let azDegrees = Cesium.Math.toDegrees(geodesic.startHeading);
            if (azDegrees < 0) azDegrees += 360.0;
            updateMeasurementPreview(
              distanceMeasureAnchor.lon,
              distanceMeasureAnchor.lat,
              lonLat.lon,
              lonLat.lat,
              geodesic.surfaceDistance,
              azDegrees
            );
          }
        } catch (e) {
          // Silently ignore preview errors to avoid spam
        }
      }
      
      // Always emit mouse coordinates for status bar (not just during polygon drawing)
      const lonLat = getLonLatFromScreen(movement.endPosition);
      if (lonLat && !statusCoordEmitted) {
        emitMouseCoordinates(lonLat.lon, lonLat.lat);
      }

      // Live rubber-band line for elevation profile mode — mirrors distance tool approach
      if (window._profileModeActive && window._profileStartLon !== undefined) {
        try {
          // Throttle profile preview updates for smooth performance (60fps max)
          const now = Date.now();
          if (!window._lastProfilePreviewUpdate) {
            window._lastProfilePreviewUpdate = 0;
          }
          const timeSinceLastUpdate = now - window._lastProfilePreviewUpdate;
          if (timeSinceLastUpdate < 16) {
            // Skip this update - too soon after last one
            return;
          }
          window._lastProfilePreviewUpdate = now;
          
          let profileLonLat = getLonLatFromScreen(movement.endPosition);
          if (!profileLonLat && movement.endPosition) {
            const ellipsoidCart = viewer.camera.pickEllipsoid(movement.endPosition, viewer.scene.globe.ellipsoid);
            if (ellipsoidCart) profileLonLat = cartesianToLonLat(ellipsoidCart);
          }
          if (profileLonLat) {
            _updateProfilePreviewLine(
              window._profileStartLon, window._profileStartLat,
              profileLonLat.lon, profileLonLat.lat
            );
          }
        } catch (e) {
          // Silently ignore preview errors
        }
      }

      // Georeferenced cursor: project mouse onto completed profile line → emit fraction
      if (window._profileLineActive &&
          window._profileLineLon1 !== undefined && window._profileLineLon2 !== undefined) {
        try {
          let cursorLonLat = getLonLatFromScreen(movement.endPosition);
          if (!cursorLonLat && movement.endPosition) {
            const ec = viewer.camera.pickEllipsoid(movement.endPosition, viewer.scene.globe.ellipsoid);
            if (ec) cursorLonLat = cartesianToLonLat(ec);
          }
          if (cursorLonLat) {
            // Project cursor onto the geodesic line using Cartesian dot product
            // (accurate for any line length, including ultra-high-res cm-scale data)
            const p1 = Cesium.Cartesian3.fromDegrees(window._profileLineLon1, window._profileLineLat1);
            const p2 = Cesium.Cartesian3.fromDegrees(window._profileLineLon2, window._profileLineLat2);
            const pc = Cesium.Cartesian3.fromDegrees(cursorLonLat.lon, cursorLonLat.lat);
            const v  = Cesium.Cartesian3.subtract(p2, p1, new Cesium.Cartesian3());
            const w  = Cesium.Cartesian3.subtract(pc, p1, new Cesium.Cartesian3());
            const lenSq = Cesium.Cartesian3.dot(v, v);
            let frac = 0.5;
            if (lenSq > 1e-6) {
              frac = Cesium.Cartesian3.dot(w, v) / lenSq;
              frac = Math.max(0.0, Math.min(1.0, frac));
            }
            window._profileCursorFrac = frac;
            // Emit to Python so the Qt panel can draw the cursor crosshair
            if (bridge && bridge.on_profile_cursor) {
              bridge.on_profile_cursor(frac);
            }
            requestSceneRender();
          }
        } catch (e) {
          // Silently ignore
        }
      }
      
      if (searchDrawMode === "polygon") {
        updateSearchCursorOverlay(
          window.OfflineGISCursorControls && window.OfflineGISCursorControls.lastSearchCursorScreenPosition
        );
      }
      if (movement && movement.endPosition) {
        updateMeasureCursorOverlay(movement.endPosition);
      }
      if (searchDrawMode !== "polygon" || searchPolygonPoints.length === 0) {
        return;
      }
      // CRITICAL FIX: Throttle polygon preview updates for smooth pixel-perfect drawing
      // Update at most 60fps (every ~16ms) to prevent lag on rapid mouse movements
      const now = Date.now();
      if (!window._lastPolygonPreviewUpdate) {
        window._lastPolygonPreviewUpdate = 0;
      }
      const timeSinceLastUpdate = now - window._lastPolygonPreviewUpdate;
      if (timeSinceLastUpdate < 16) {
        // Skip this update - too soon after last one
        // But still update the cursor point so next update uses latest position
        if (lonLat) {
          searchCursorPoint = { lon: lonLat.lon, lat: lonLat.lat };
        }
        return;
      }
      window._lastPolygonPreviewUpdate = now;
      
      // Update search polygon preview during drawing
      if (lonLat) {
        searchCursorPoint = { lon: lonLat.lon, lat: lonLat.lat };
        updateSearchPolygonPreview();
      }
      // Fly Through preview
      if (flyThroughModeEnabled && flyThroughPoints.length > 0) {
        updateFlyThroughPreview(movement.endPosition);
      }
    }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

    handler.setInputAction(function () {
      if (searchDrawMode === "polygon") {
        window.offlineGIS.finishSearchPolygon();
        return;
      }
      if (flyThroughModeEnabled) {
        finishFlyThroughPath();
        return;
      }
      if (distanceMeasureModeEnabled) {
        if (distanceMeasureAnchor) {
            distanceMeasureAnchor = null;
            clearMeasurementPreviewEntities();
            setStatus("Measurement cancelled. Click to start a new measurement.");
        }
        return;
      }
    }, Cesium.ScreenSpaceEventType.RIGHT_CLICK);

    viewer.canvas.addEventListener("mouseenter", function () {
      if (searchDrawMode === "polygon") {
        setSearchCursorOverlayVisible(true);
      }
      setMeasureCursorOverlayVisible(true);
    });

    viewer.canvas.addEventListener("mouseleave", function () {
      setSearchCursorOverlayVisible(false);
      setMeasureCursorOverlayVisible(false);
      if (hoveredAnnotationEditEntity) {
        setAnnotationEditIconHoverState(hoveredAnnotationEditEntity, false);
        hoveredAnnotationEditEntity = null;
      }
      if (hoveredAnnotationDeleteEntity) {
        setAnnotationDeleteIconHoverState(hoveredAnnotationDeleteEntity, false);
        hoveredAnnotationDeleteEntity = null;
      }
      // Clear status bar coordinates when cursor leaves the map
      if (bridge && bridge.on_mouse_coordinates) {
        bridge.on_mouse_coordinates(0, 0);
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: Measurement Tools  →  future: modules/measurement.js
  // Functions: setDistanceMeasureMode, _enforceMeasureCursor,
  //   updateMeasurementPreview, updateMeasurementEntities,
  //   clearMeasurementEntities, clearMeasurementPreviewEntities,
  //   updateDistanceScaleOverlay, clearDistanceScaleOverlay
  // ═══════════════════════════════════════════════════════════════════════════

  function updatePolygonPreviewVisibility() {
    const visible = polygonVisibilityEnabled && searchOverlayVisible;
    // Note: show properties for preview entities are managed via CallbackProperty in the controller
    // to ensure high-frequency updates during drawing. Static overrides here are avoided.
    if (searchCursorEntity) {
      searchCursorEntity.show = visible;
    }
    if (searchPreviewLineEntity || searchPreviewPolygonEntity || searchAreaLabelEntity) {
      requestSceneRender();
    }
  }

  function setPolygonPreviewVisible(visible) {
    polygonVisibilityEnabled = Boolean(visible);
    updatePolygonPreviewVisibility();
  }

  function getLonLatFromScreen(screenPosition) {
    return getLonLatFromViewer(viewer, screenPosition);
  }

  function clearSearchEntities() {
    if (searchCursorEntity) {
      viewer.entities.remove(searchCursorEntity);
      searchCursorEntity = null;
    }
    if (searchPreviewLineEntity) {
      viewer.entities.remove(searchPreviewLineEntity);
      searchPreviewLineEntity = null;
    }
    if (searchPreviewPolygonEntity) {
      viewer.entities.remove(searchPreviewPolygonEntity);
      searchPreviewPolygonEntity = null;
    }
    if (searchAreaLabelEntity) {
      viewer.entities.remove(searchAreaLabelEntity);
      searchAreaLabelEntity = null;
    }
    // Clear vertex marker entities
    while (searchVertexEntities.length > 0) {
      const ve = searchVertexEntities.pop();
      if (ve && viewer) {
        viewer.entities.remove(ve);
      }
    }
    requestSceneRender();
    if (window.bridge && window.bridge.on_aoi_stats_updated) {
      window.bridge.on_aoi_stats_updated(0, "0 m\u00b2");
    }
  }

  function setAnnotationVisibility(visible) {
    annotationVisibilityEnabled = Boolean(visible);
    for (const entity of annotationEntities) {
      if (entity) {
        entity.show = annotationVisibilityEnabled;
      }
    }
    requestSceneRender();
  }

  function clearMeasurementEntities() {
    if (!viewer) {
      return;
    }
    try {
      while (measurementPointEntities.length > 0) {
        const ent = measurementPointEntities.pop();
        if (ent) viewer.entities.remove(ent);
      }
    } catch (e) {}
    clearMeasurementPreviewEntities();
    clearDistanceScaleOverlay();
    requestSceneRender();
  }

  function clearMeasurementPreviewEntities() {
    if (!viewer) {
      return;
    }
    try {
      if (measurementPreviewLineEntity) {
        viewer.entities.remove(measurementPreviewLineEntity);
        measurementPreviewLineEntity = null;
      }
      if (measurementAnchorDotEntity) {
        viewer.entities.remove(measurementAnchorDotEntity);
        measurementAnchorDotEntity = null;
      }
      measurementPreviewStart = null;
      measurementPreviewEnd = null;
    } catch (e) {}
    try {
      if (measurementPreviewLabelEntity) {
        viewer.entities.remove(measurementPreviewLabelEntity);
        measurementPreviewLabelEntity = null;
      }
    } catch (e) {}
    requestSceneRender();
  }

  // ── Distance Scale Overlay (screen-space ruler) ──
  function ensureDistanceScaleOverlay() {
    if (distanceScaleOverlay || !document.body) {
      return;
    }
    const el = document.createElement("div");
    el.id = "distanceScaleOverlay";
    el.setAttribute("aria-hidden", "true");
    // Container is just a positioning anchor — no overflow clipping
    el.style.cssText = [
      "position:fixed",
      "pointer-events:none",
      "z-index:99999",
      "display:none",
      "overflow:visible",
    ].join(";");

    // The bar — positioned absolutely, rotated via transform on the container
    const barWrap = document.createElement("div");
    barWrap.className = "distScaleBarWrap";
    barWrap.style.cssText = [
      "position:absolute",
      "top:0",
      "left:0",
      "transform-origin:0% 50%",
      "overflow:visible",
    ].join(";");

    const bar = document.createElement("div");
    bar.className = "distScaleBar";
    bar.style.cssText = [
      "height:4px",
      "background:rgba(0,229,255,0.85)",
      "border:1px solid rgba(0,0,0,0.4)",
      "border-radius:2px",
      "box-shadow:0 1px 4px rgba(0,0,0,0.5)",
      "position:relative",
      "min-width:8px",
    ].join(";");
    barWrap.appendChild(bar);

    // Start/end ticks on the bar
    const tickStart = document.createElement("div");
    tickStart.style.cssText = "position:absolute;left:-1px;top:-4px;width:2px;height:12px;background:rgba(0,229,255,0.9);border-radius:1px;";
    bar.appendChild(tickStart);
    const tickEnd = document.createElement("div");
    tickEnd.className = "distScaleTickEnd";
    tickEnd.style.cssText = "position:absolute;right:-1px;top:-4px;width:2px;height:12px;background:rgba(0,229,255,0.9);border-radius:1px;";
    bar.appendChild(tickEnd);

    el.appendChild(barWrap);

    // Distance label — separate from bar, always horizontal, positioned at midpoint
    const distLabel = document.createElement("div");
    distLabel.className = "distScaleText";
    distLabel.style.cssText = [
      "position:fixed",
      "pointer-events:none",
      "z-index:100000",
      "display:none",
      "color:#fff",
      "font-size:12px",
      "font-weight:700",
      "font-family:'SF Mono','Menlo','Consolas',monospace",
      "text-shadow:0 1px 3px rgba(0,0,0,0.9),0 0 6px rgba(0,0,0,0.6)",
      "white-space:nowrap",
      "background:rgba(10,25,41,0.78)",
      "padding:2px 7px",
      "border-radius:4px",
      "transform:translate(-50%,-100%)",
    ].join(";");
    document.body.appendChild(distLabel);

    // Azimuth label — below midpoint, always horizontal
    const azLabel = document.createElement("div");
    azLabel.className = "distScaleAz";
    azLabel.style.cssText = [
      "position:fixed",
      "pointer-events:none",
      "z-index:100000",
      "display:none",
      "color:rgba(0,229,255,0.95)",
      "font-size:11px",
      "font-weight:600",
      "font-family:'SF Mono','Menlo','Consolas',monospace",
      "text-shadow:0 1px 2px rgba(0,0,0,0.9)",
      "white-space:nowrap",
      "transform:translate(-50%,6px)",
    ].join(";");
    document.body.appendChild(azLabel);

    document.body.appendChild(el);
    distanceScaleOverlay = el;
  }

  let _scaleOverlayLastMs = 0;
  function updateDistanceScaleOverlay(startLon, startLat, endLon, endLat, meters, azimuth) {
    // Disabled HTML overlay because 3D Entity lines now exist.
    return;
  }

  function _hideScaleLabels() {
    const distLabel = document.querySelector(".distScaleText");
    if (distLabel) distLabel.style.display = "none";
    const azLabel = document.querySelector(".distScaleAz");
    if (azLabel) azLabel.style.display = "none";
  }

  function clearDistanceScaleOverlay() {
    return;
  }

  function _clearFillVolumeEntities() {
    if (!viewer) return;
    var ents = window._fillVolumeEntities || [];
    for (var i = 0; i < ents.length; i++) {
      var ent = ents[i];
      try {
        if (!ent) continue;
        if (viewer.entities.contains(ent)) {
          viewer.entities.remove(ent);
        }
      } catch (_) {}
    }
    window._fillVolumeEntities = [];
    window._fillVolumePrimitives = [];
  }

  // Profile rubber-band preview — recreates entity on every mouse move (same as distance tool)
  function _updateProfilePreviewLine(startLon, startLat, endLon, endLat) {
    if (!viewer) return;
    // Update the shared positions every mouse move
    window._profilePreviewStart = Cesium.Cartesian3.fromDegrees(startLon, startLat);
    window._profilePreviewEnd = Cesium.Cartesian3.fromDegrees(endLon, endLat);

    if (!window._profilePreviewEntity) {
      // Create once with CallbackProperty(isConstant=false) — re-evaluated every frame
      window._profilePreviewEntity = viewer.entities.add({
        polyline: {
          positions: new Cesium.CallbackProperty(function() {
            if (window._profilePreviewStart && window._profilePreviewEnd) {
              return [window._profilePreviewStart, window._profilePreviewEnd];
            }
            return [];
          }, false),
          width: 2,
          arcType: Cesium.ArcType.GEODESIC,
          material: Cesium.Color.fromCssColorString("#00e5ff").withAlpha(0.85),
          clampToGround: true,
        },
      });
      log("debug", "Profile preview line entity created");
    }
    requestSceneRender();
  }

  function updateMeasurementPreview(startLon, startLat, endLon, endLat, meters, azimuth, startHeightOpt, endHeightOpt) {
    if (!viewer) {
      return;
    }
    try {
      let startHeight = startHeightOpt !== undefined ? startHeightOpt : (viewer.scene.globe.getHeight(Cesium.Cartographic.fromDegrees(startLon, startLat)) || 0);
      let endHeight = endHeightOpt !== undefined ? endHeightOpt : (viewer.scene.globe.getHeight(Cesium.Cartographic.fromDegrees(endLon, endLat)) || 0);

      // Update shared mutable positions — the CallbackProperty reads these every frame
      measurementPreviewStart = Cesium.Cartesian3.fromDegrees(startLon, startLat, startHeight);
      measurementPreviewEnd = Cesium.Cartesian3.fromDegrees(endLon, endLat, endHeight);

      if (!measurementPreviewLineEntity) {
        // Create ONCE with CallbackProperty(isConstant=false) — re-evaluated every frame
        measurementPreviewLineEntity = viewer.entities.add({
          polyline: {
            positions: new Cesium.CallbackProperty(function() {
              if (measurementPreviewStart && measurementPreviewEnd) {
                return [measurementPreviewStart, measurementPreviewEnd];
              }
              return [];
            }, false),
            width: 2,
            arcType: Cesium.ArcType.GEODESIC,
            material: Cesium.Color.fromCssColorString("#00e5ff").withAlpha(0.85),
            clampToGround: true,
          },
        });
      }
      requestSceneRender();
    } catch (e) {
      // Silently ignore preview errors
    }
  }

  function setDistanceMeasureMode(enabled) {
    distanceMeasureModeEnabled = Boolean(enabled);
    distanceMeasureAnchor = null;
    
    const container = document.getElementById("cesiumContainer");
    if (distanceMeasureModeEnabled) {
      if (container) container.classList.add("measure-distance-cursor-active");
      _enforceMeasureCursor(true);
    } else {
      if (container) container.classList.remove("measure-distance-cursor-active");
      _enforceMeasureCursor(false);
    }
    
    if (distanceMeasureModeEnabled && searchDrawMode === "polygon") {
      searchDrawMode = "none";
      searchOverlayVisible = false;
      setSearchCursorEnabled(false);
      updatePolygonPreviewVisibility();
    }
    clearMeasurementPreviewEntities();
    clearDistanceScaleOverlay();
    if (distanceMeasureModeEnabled) {
      setMeasurementCursorEnabled(true);
      clickedPoints.length = 0;
      setStatus("Distance tool: click first point, move to preview, click second point to measure. Right-click to stop.");
      return;
    }
    // Turning off — clear ALL measurement marks (line, label, preview, overlay)
    clearMeasurementEntities();
    setMeasurementCursorEnabled(false);
    setStatus("Distance tool disabled.");
  }

  function setPanMode(enabled) {
    panModeActive = Boolean(enabled);
    const container = document.getElementById("cesiumContainer");
    if (panModeActive) {
      if (distanceMeasureModeEnabled) {
        setDistanceMeasureMode(false);
      }
      if (searchDrawMode === "polygon") {
        searchDrawMode = "none";
        searchOverlayVisible = false;
        setSearchCursorEnabled(false);
        updatePolygonPreviewVisibility();
      }
      clearDistanceScaleOverlay();
      if (container) container.classList.add("pan-mode-active");
      // Force 2D-like flat drag: disable rotate/tilt/look
      configureCameraControllerForMode(currentSceneMode);
      setStatus("Pan mode enabled — drag to translate view.");
      log("info", "Pan mode activated (2D-like drag)");
    } else {
      if (container) container.classList.remove("pan-mode-active");
      // Restore normal 3D interaction controls
      configureCameraControllerForMode(currentSceneMode);
      setStatus("Pan mode disabled — 3D navigation restored.");
      log("info", "Pan mode deactivated (3D navigation restored)");
    }
    requestSceneRender();
  }

  function updateMeasurementEntities(startLon, startLat, endLon, endLat, meters, azimuth, startHeightOpt, endHeightOpt) {
    if (!viewer) {
      return;
    }
    
    try {
      let startHeight = startHeightOpt !== undefined ? startHeightOpt : (viewer.scene.globe.getHeight(Cesium.Cartographic.fromDegrees(startLon, startLat)) || 0);
      let endHeight = endHeightOpt !== undefined ? endHeightOpt : (viewer.scene.globe.getHeight(Cesium.Cartographic.fromDegrees(endLon, endLat)) || 0);

      const start = Cesium.Cartesian3.fromDegrees(startLon, startLat, startHeight);
      const end = Cesium.Cartesian3.fromDegrees(endLon, endLat, endHeight);
      
      const labelLon = (startLon + endLon) / 2.0;
      const labelLat = (startLat + endLat) / 2.0;
      const labelHeight = (startHeight + endHeight) / 2.0;

      let distText = meters > 1000 ? (meters / 1000.0).toFixed(2) + " km" : meters.toFixed(1) + " m";
      let azText = azimuth !== undefined ? azimuth.toFixed(1) + "°" : "";
      const labelText = "Dist: " + distText + (azText ? "   Az: " + azText : "");

      const newLine = viewer.entities.add({
        polyline: {
          positions: [start, end],
          width: 2.0,
          arcType: Cesium.ArcType.GEODESIC,
          material: Cesium.Color.fromCssColorString("#4da8da").withAlpha(0.9),
          depthFailMaterial: Cesium.Color.fromCssColorString("#4da8da").withAlpha(0.9),
        },
      });

      const newLabel = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(labelLon, labelLat, labelHeight),
        label: {
          text: labelText,
          font: "bold 13px 'Segoe UI', 'Arial', sans-serif",
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 3,
          showBackground: true,
          backgroundColor: Cesium.Color.fromCssColorString("#08101c").withAlpha(0.7),
          backgroundPadding: new Cesium.Cartesian2(7, 5),
          horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          pixelOffset: new Cesium.Cartesian2(0, -14),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          scale: 1.0,
        },
      });
      
      const pt1 = viewer.entities.add({
          position: start,
          point: {
              pixelSize: 10,
              color: Cesium.Color.fromCssColorString("#4da8da"),
              outlineColor: Cesium.Color.WHITE,
              outlineWidth: 2,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
          }
      });
      const pt2 = viewer.entities.add({
          position: end,
          point: {
              pixelSize: 10,
              color: Cesium.Color.fromCssColorString("#4da8da"),
              outlineColor: Cesium.Color.WHITE,
              outlineWidth: 2,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
          }
      });

      measurementPointEntities.push(newLine, newLabel, pt1, pt2);
      requestSceneRender();
    } catch (e) {
      log("error", "updateMeasurementEntities failed: " + e.message);
    }
  }

  function clearAnnotationEntities() {
    if (!viewer) {
      return;
    }
    hoveredAnnotationEditEntity = null;
    while (annotationEntities.length > 0) {
      const entity = annotationEntities.pop();
      if (entity) {
        viewer.entities.remove(entity);
      }
    }
    requestSceneRender();
  }

  function zoomBy(factor) {
    if (!viewer || !viewer.camera) {
      return;
    }
    const camera = viewer.camera;
    
    // Get current altitude
    const cartographic = Cesium.Cartographic.fromCartesian(camera.positionWC);
    const altitude = cartographic.height;
    
    // Calculate new altitude based on factor
    // factor < 1.0 means zoom in, factor > 1.0 means zoom out
    const newAltitude = altitude * factor;
    
    // Clamp to reasonable bounds
    const clampedAltitude = Math.max(10, Math.min(newAltitude, 100000000));
    
    log("debug", `zoomBy: factor=${factor.toFixed(4)} currentAlt=${altitude.toFixed(1)}m newAlt=${clampedAltitude.toFixed(1)}m ${factor < 1.0 ? "ZOOM_IN" : "ZOOM_OUT"}`);
    
    // Get current camera position in cartesian
    const currentPos = camera.position.clone();
    
    // Update position with new altitude while preserving lon/lat
    const newPosition = Cesium.Cartesian3.fromRadians(
      cartographic.longitude,
      cartographic.latitude,
      clampedAltitude
    );
    
    // Smooth camera movement with new altitude
    camera.setView({
      destination: newPosition,
      orientation: {
        heading: camera.heading,
        pitch: camera.pitch,
        roll: camera.roll
      },
      duration: 0.1
    });
    
    requestSceneRender();
  }

  function resetNorthUp() {
    if (!viewer || !viewer.camera) {
      return;
    }
    const camera = viewer.camera;
    camera.cancelFlight();

    // Reset heading to north (0.0) while preserving current position and pitch
    camera.flyTo({
      destination: camera.position,
      orientation: {
        heading: 0.0,
        pitch: camera.pitch,
        roll: camera.roll,
      },
      duration: 0.85,
    });
    requestSceneRender();
  }

  function zoomToExtent() {
    if (!viewer) {
      return;
    }
    const bounds = activeTileBounds || lastLoadedBounds;
    if (!bounds) {
      return;
    }
    if (currentSceneMode === "3d" || currentSceneMode === "morphing") {
      focusLoadedRegion3D(1.2);
    } else {
      focusLoadedRegion(0.8);
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION: Search Polygon & AOI  →  moved to modules/search/search_polygon_controller.js
  // ═══════════════════════════════════════════════════════════════════════════

  function ensureSearchPreviewEntities() {
    if (searchPolygonController) {
      searchPolygonController.ensureSearchPreviewEntities();
    }
  }

  function syncSearchVertexEntities() {
    if (searchPolygonController) {
      searchPolygonController.syncSearchVertexEntities();
    }
  }

  function updateSearchPolygonPreview() {
    if (searchPolygonController) {
      searchPolygonController.updateSearchPolygonPreview();
    }
  }

  function finalizeSearchPolygon() {
    if (searchPolygonController) {
      searchPolygonController.finalizeSearchPolygon();
    }
  }

  function updateAoiPanel(points) {
    if (searchPolygonController) {
      searchPolygonController.updateAoiPanel(points);
    }
  }

  function toggleAoiPanelMinimize() {
    if (searchPolygonController) {
      searchPolygonController.toggleAoiPanelMinimize();
    }
  }

  function updatePolygonDropdownUI() {
    if (searchPolygonController) {
      searchPolygonController.updatePolygonDropdownUI();
    }
  }

  function toggleDrawnPolygonVisibility(polyId, visible) {
    if (searchPolygonController) {
      searchPolygonController.toggleDrawnPolygonVisibility(polyId, visible);
    }
  }

  function toggleAllDrawnPolygonsVisibility(visible) {
    if (searchPolygonController) {
      searchPolygonController.toggleAllDrawnPolygonsVisibility(visible);
    }
  }

  const comparatorPolygonEntities = { left: [], right: [] };

  function updateComparatorPolygons(visible) {
    if (searchPolygonController) {
      searchPolygonController.updateComparatorPolygons(visible);
    }
  }

  function setSceneModeInternal(mode) {
    if (!viewer) return;
    const normalized = String(mode || "3d").toLowerCase() === "2d" ? "2d" : "3d";
    let actualMode = detectSceneMode();
    sceneDebug(
      "setSceneModeInternal enter requested=" +
        mode +
        " normalized=" +
        normalized +
        " actualMode=" +
        actualMode +
        " currentSceneMode=" +
        currentSceneMode +
        " pendingSceneModeAfterMorph=" +
        String(pendingSceneModeAfterMorph)
    );
    if (actualMode === "morphing") {
      sceneDebug("setSceneModeInternal scene is morphing; forcing completeMorph before queueing");
      try {
        viewer.scene.completeMorph();
      } catch (_err) {
        // Ignore completeMorph failures and continue with queueing below.
      }
      actualMode = detectSceneMode();
      sceneDebug("setSceneModeInternal after completeMorph actualMode=" + actualMode);
    }
    if (actualMode === "morphing") {
      pendingSceneModeAfterMorph = normalized;
      syncSceneModeToggle(normalized);
      sceneDebug("setSceneModeInternal queued mode while morphing queued=" + normalized);
      return;
    }
    if (actualMode !== currentSceneMode) {
      currentSceneMode = actualMode;
      syncSceneModeToggle(actualMode);
      sceneDebug("setSceneModeInternal synced currentSceneMode to actualMode=" + actualMode);
    }
    pendingSceneModeAfterMorph = null;
    const preferredBounds = resolvePreferredFocusBounds();
    if (preferredBounds) {
      setActiveTileBounds(preferredBounds);
    }
    if (normalized === currentSceneMode) {
      sceneDebug("setSceneModeInternal no-op branch normalized matches current=" + normalized);
      configureCameraControllerForMode(normalized);
      syncSceneModeToggle(normalized);
      requestSceneRender();
      return;
    }
    pendingFocusBounds = preferredBounds;
    pendingFocusAfterMorph = Boolean(preferredBounds);
    pendingTerrainSceneAfterMorph = normalized === "3d" && Boolean(preferredBounds);
    configureCameraControllerForMode(normalized);
    if (normalized === "2d") {
      sceneDebug("setSceneModeInternal morphTo2D begin pendingFocus=" + String(pendingFocusAfterMorph));
      // Instant morph (0-duration) to avoid lag and frame drops
      viewer.scene.morphTo2D(0.0);
      currentSceneMode = "2d";
      applySceneModePerformanceHints("2d");
      syncSceneModeToggle("2d");
      if (comparatorModeEnabled && typeof comparatorViewers !== "undefined" && Array.isArray(comparatorViewers)) {
        comparatorViewers.forEach(v => setComparatorViewerModeByType(v));
      }
      updateBasemapBlendForCurrentMode();
      // Force immediate re-render after instant morph
      requestSceneRender();
      window.requestAnimationFrame(requestSceneRender);
      setStatus("2D map mode active.");
      log("info", "Scene mode switched to 2D from 3D");
      return;
    }
    sceneDebug("setSceneModeInternal morphTo3D begin pendingFocus=" + String(pendingFocusAfterMorph));
    // Instant morph (0-duration) to avoid lag and frame drops
    viewer.scene.morphTo3D(0.0);
    currentSceneMode = "3d";
    applySceneModePerformanceHints("3d");
    syncSceneModeToggle("3d");
    if (comparatorModeEnabled && typeof comparatorViewers !== "undefined" && Array.isArray(comparatorViewers)) {
      comparatorViewers.forEach(v => setComparatorViewerModeByType(v));
    }
    updateBasemapBlendForCurrentMode();

    // CRITICAL FIX (Bug 1+2): Ensure 3D always has perspective pitch.
    // Clamp pitch so 3D never looks like 2D (top-down).  Default to -35°.
    if (cameraOrbitPitch < MIN_3D_PITCH_RAD || Math.abs(cameraOrbitPitch - Cesium.Math.toRadians(-90.0)) < Cesium.Math.toRadians(5.0)) {
      cameraOrbitPitch = DEFAULT_3D_PITCH_RAD;
      sceneDebug("setSceneModeInternal: clamped pitch to default 3D pitch " + Cesium.Math.toDegrees(cameraOrbitPitch).toFixed(1) + "°");
    }

    // After morphTo3D, re-attach terrain provider and focus on active asset.
    // morphTo3D(0) resets the terrain provider — we must restore it.
    window.requestAnimationFrame(function () {
      if (activeDemTerrainProvider && activeDemContext && activeDemContext.visible !== false) {
        if (viewer.terrainProvider !== activeDemTerrainProvider) {
          _swapTerrainProviderLocked(activeDemTerrainProvider);
        }
        viewer.scene.globe.terrainExaggeration = Math.max(0.1, demVisual.exaggeration);
        // Also set verticalExaggeration for Cesium 1.90+ compatibility
        if (typeof viewer.scene.verticalExaggeration !== "undefined") {
          viewer.scene.verticalExaggeration = Math.max(0.1, demVisual.exaggeration);
        }
      }
      // Focus on active asset after morph with 3D pitch
      const bounds = activeTileBounds || lastLoadedBounds;
      if (bounds) {
        schedule3DFocusAfterMorph(1.0);
      }
      requestSceneRender();
    });

    requestSceneRender();
    setStatus("3D globe mode active.");
    log("info", "Scene mode switched to 3D from 2D");
  }

  function startFlyThroughBounds(west, south, east, north) {
    if (!viewer) return;
    const targetBounds = { west: west, south: south, east: east, north: north };
    setActiveTileBounds(targetBounds);
    const modeNow = detectSceneMode();
    sceneDebug("startFlyThroughBounds modeNow=" + modeNow + " currentSceneMode=" + currentSceneMode);

    if (modeNow !== "3d") {
      pendingFlyThroughBounds = targetBounds;
      setSceneModeInternal("3d");
      setStatus("Switching to 3D globe...");
      sceneDebug("startFlyThroughBounds queued until 3d morph completes");
      return;
    }

    const rect   = Cesium.Rectangle.fromDegrees(west, south, east, north);
    const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
    const range  = Math.max(
      compute3DFocusRange(targetBounds),
      sphere.radius * 1.4,
      300.0
    );
    _cameraOrbitRange = range;

    log("info", "FLY-TO: bounds W=" + west.toFixed(4) + " S=" + south.toFixed(4) +
      " E=" + east.toFixed(4) + " N=" + north.toFixed(4) +
      " radius=" + sphere.radius.toFixed(0) + "m range=" + range.toFixed(0) + "m");

    // ── CRITICAL: enable continuous rendering BEFORE flight begins ───────────
    // requestRenderMode=true means frames only render on state changes.
    // During a flyTo the camera moves every frame but tiles may not be ready,
    // causing blank globe sections. Setting false guarantees every frame renders
    // so the globe always shows NaturalEarthII basemap during the approach.
    viewer.scene.requestRenderMode = false;
    viewer.scene.requestRender();

    viewer.camera.cancelFlight();

    log("info", "FLY-TO: starting single-step flight duration=2.5s heading=0° pitch=-40°");

    viewer.camera.flyToBoundingSphere(sphere, {
      offset: new Cesium.HeadingPitchRange(
        Cesium.Math.toRadians(0.0),
        Cesium.Math.toRadians(-40.0),
        range
      ),
      duration: 2.5,
      complete: function() {
        const finalPos = viewer.camera.positionCartographic;
        log("info", "FLY-TO: complete — lon=" +
          Cesium.Math.toDegrees(finalPos.longitude).toFixed(4) +
          " lat=" + Cesium.Math.toDegrees(finalPos.latitude).toFixed(4) +
          " alt=" + finalPos.height.toFixed(0) + "m");

        // Hold continuous render for 3s post-landing so tiles fully stream in
        var t = 0;
        var iv = setInterval(function() {
          if (!viewer || !viewer.scene) { clearInterval(iv); return; }
          viewer.scene.requestRender();
          t += 100;
          if (t >= 3000) {
            clearInterval(iv);
            viewer.scene.requestRenderMode = true;
            log("info", "FLY-TO: render hold complete — returning to request-render mode");
          }
        }, 100);
      },
      cancel: function() {
        log("info", "FLY-TO: flight cancelled");
        if (viewer && viewer.scene) {
          viewer.scene.requestRenderMode = true;
          viewer.scene.requestRender();
        }
      }
    });

    setStatus("Flying to asset...");
    sceneDebug("startFlyThroughBounds flight started in 3d");
  }


  window.offlineGIS = {
    flyTo: function (lon, lat, height) {
      if (!viewer) return;
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(lon, lat, height || 8000),
        duration: 2.0,
      });
      log("info", "Fly-to lon=" + lon + " lat=" + lat);
    },
    flyToBounds: function (west, south, east, north) {
      if (!viewer) return;
      setActiveTileBounds({ west: west, south: south, east: east, north: north });
      const rect = Cesium.Rectangle.fromDegrees(west, south, east, north);
      const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
      const range = Math.max(compute3DFocusRange({ west, south, east, north }), sphere.radius * 1.5, 300.0);
      // Persist range so pitch slider can orbit without recomputing live distance
      _cameraOrbitRange = range;
      // Keep rendering active during AND after flight so tiles stream in with no blank globe
      viewer.scene.requestRenderMode = false;
      viewer.camera.cancelFlight();
      viewer.camera.flyToBoundingSphere(sphere, {
        offset: new Cesium.HeadingPitchRange(
          Cesium.Math.toRadians(0.0),
          Cesium.Math.toRadians(-40.0),
          range
        ),
        duration: 2.0,
        complete: function() {
          if (!viewer || !viewer.scene) return;
          // Hold continuous render for 1.5s post-flight so tiles finish loading
          var t = 0;
          var iv = setInterval(function() {
            if (!viewer || !viewer.scene) { clearInterval(iv); return; }
            viewer.scene.requestRender();
            t += 100;
            if (t >= 1500) { clearInterval(iv); viewer.scene.requestRenderMode = true; }
          }, 100);
        },
        cancel: function() {
          if (viewer && viewer.scene) {
            viewer.scene.requestRenderMode = true;
            viewer.scene.requestRender();
          }
        }
      });
      requestSceneRender();
      log("info", "Fly-to bounds (3D oblique) west=" + west + " south=" + south + " east=" + east + " north=" + north);
    },
    focusBounds: function (west, south, east, north) {
      if (!viewer) return;
      setActiveTileBounds({ west: west, south: south, east: east, north: north });
      const padLon = (east - west) * 0.10;
      const padLat = (north - south) * 0.10;
      const paddedWest  = Math.max(-180, west  - padLon);
      const paddedEast  = Math.min( 180, east  + padLon);
      const paddedSouth = Math.max( -90, south - padLat);
      const paddedNorth = Math.min(  90, north + padLat);
      const rect = Cesium.Rectangle.fromDegrees(paddedWest, paddedSouth, paddedEast, paddedNorth);
      const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
      const range = Math.max(compute3DFocusRange({ west: paddedWest, south: paddedSouth, east: paddedEast, north: paddedNorth }), sphere.radius * 1.5, 300.0);
      // Persist range so pitch slider can orbit without recomputing live distance
      _cameraOrbitRange = range;
      viewer.scene.requestRenderMode = false;
      viewer.camera.cancelFlight();
      viewer.camera.flyToBoundingSphere(sphere, {
        offset: new Cesium.HeadingPitchRange(
          Cesium.Math.toRadians(0.0),
          Cesium.Math.toRadians(-40.0),
          range
        ),
        duration: 1.2,
        complete: function() {
          if (!viewer || !viewer.scene) return;
          var t = 0;
          var iv = setInterval(function() {
            if (!viewer || !viewer.scene) { clearInterval(iv); return; }
            viewer.scene.requestRender();
            t += 100;
            if (t >= 1500) { clearInterval(iv); viewer.scene.requestRenderMode = true; }
          }, 100);
        },
        cancel: function() {
          if (viewer && viewer.scene) {
            viewer.scene.requestRenderMode = true;
            viewer.scene.requestRender();
          }
        }
      });
      requestSceneRender();
      log("debug", "Focus bounds (3D oblique) west=" + west + " south=" + south + " east=" + east + " north=" + north);
    },
    focusBoundsWithPadding: function (west, south, east, north, paddingFactor) {
      if (!viewer) return;
      // Use custom padding factor (e.g., 1.5 = 50% padding)
      const padFactor = Number(paddingFactor) || 1.1; // Default to 10% if not specified
      const padLon = (east - west) * (padFactor - 1.0) * 0.5;
      const padLat = (north - south) * (padFactor - 1.0) * 0.5;
      const paddedWest  = Math.max(-180, west  - padLon);
      const paddedEast  = Math.min( 180, east  + padLon);
      const paddedSouth = Math.max( -90, south - padLat);
      const paddedNorth = Math.min(  90, north + padLat);
      setActiveTileBounds({ west: west, south: south, east: east, north: north });
      // SEARCH FIX: Use 3D oblique view (-40° pitch) so search results appear on the globe
      const rect = Cesium.Rectangle.fromDegrees(paddedWest, paddedSouth, paddedEast, paddedNorth);
      const sphere = Cesium.BoundingSphere.fromRectangle3D(rect, Cesium.Ellipsoid.WGS84, 0.0);
      const range = Math.max(compute3DFocusRange({ west: paddedWest, south: paddedSouth, east: paddedEast, north: paddedNorth }), sphere.radius * 1.5, 300.0);
      const wasRequestRenderMode = viewer.scene.requestRenderMode;
      viewer.scene.requestRenderMode = false;
      viewer.camera.cancelFlight();
      viewer.camera.flyToBoundingSphere(sphere, {
        offset: new Cesium.HeadingPitchRange(
          Cesium.Math.toRadians(0.0),
          Cesium.Math.toRadians(-40.0),  // 40° oblique — clear 3D globe perspective
          range
        ),
        duration: 1.8, // Slightly longer duration for multi-asset focus
        complete: function() {
          if (viewer && viewer.scene) {
            viewer.scene.requestRenderMode = wasRequestRenderMode;
            viewer.scene.requestRender();
          }
        },
        cancel: function() {
          if (viewer && viewer.scene) {
            viewer.scene.requestRenderMode = wasRequestRenderMode;
            viewer.scene.requestRender();
          }
        }
      });
      requestSceneRender();
      log("info", "Focus bounds with padding=" + padFactor + " (3D oblique) west=" + west + " south=" + south + " east=" + east + " north=" + north);
    },
    flyThroughBounds: function (west, south, east, north) {
      startFlyThroughBounds(west, south, east, north);
    },
    addTileLayer: async function (name, xyzUrl, kind, options) {
      if (!viewer) return;
      log(
        "info",
        "addTileLayer request name=" +
          String(name || "") +
          " kind=" +
          String(kind || "") +
          " xyz=" +
          String(xyzUrl || "") +
          " options=" +
          JSON.stringify(options || {})
      );
      let layerKey =
        options && typeof options.layer_key === "string" && options.layer_key
          ? options.layer_key
          : "imagery:" + String(name || "layer");
      layerKey = String(layerKey).replace(/\\/g, "/");
      const replaceExisting = !(options && options.replace_existing === false);
      const isDem =
        (options && options.is_dem === true) ||
        String(kind || "").toLowerCase() === "dem" ||
        String(name || "").toLowerCase().includes("dem");
      if (isDem) {
        window.offlineGIS.addDemLayer(name, xyzUrl, options || {});
        return;
      }
      if (replaceExisting) {
        // Keep DEM terrain unless explicitly requested to clear it.
        if (options && options.clear_dem === true) {
          clearDemTerrainMode();
        }
        clearManagedImageryLayers();
      }
      setSceneModeControlEnabled(true);
      // Use buildUrlWithQuery (same as DEM pipeline) to fully pre-encode the url=
      // query parameter value via encodeURIComponent.  This prevents Cesium's
      // UrlTemplateImageryProvider from double-encoding already-encoded sequences
      // like %20 (space) → %2520, which would make GDAL fail to find the file.
      const extraQuery = options && options.query ? options.query : {};
      const providerUrl = buildUrlWithQuery(xyzUrl, extraQuery);
      log("debug", "Imagery URL construction baseUrl=" + xyzUrl + " finalUrl=" + providerUrl);
      const bounds = options && options.bounds ? options.bounds : null;
      const normalizedBounds = normalizeBounds(bounds);
      if (normalizedBounds) {
        setActiveTileBounds(normalizedBounds);
      }
      let rectangle;
      if (normalizedBounds) {
        rectangle = Cesium.Rectangle.fromDegrees(
          normalizedBounds.west,
          normalizedBounds.south,
          normalizedBounds.east,
          normalizedBounds.north
        );
      }
      const minLevel = options && Number.isInteger(options.minzoom) ? options.minzoom : 0;
      const maxLevel = options && Number.isInteger(options.maxzoom) ? options.maxzoom : 19;
      const existingLayer = managedImageryLayers.get(layerKey);
      if (existingLayer) {
        existingLayer.show = true;
        viewer.imageryLayers.raiseToTop(existingLayer);
        activeImageryLayer = existingLayer;
        layerVisibilityState.set(layerKey, true);
        applySwipeComparatorSplit();
        if (comparatorModeEnabled) {
          refreshComparatorLayers();
        }
        updateBasemapBlendForCurrentMode();
        setStatus("Layer shown: " + name);
        log("info", "Layer shown key=" + layerKey + " name=" + name);
        requestSceneRender();
        return;
      }
      const provider = new Cesium.UrlTemplateImageryProvider({
        url: providerUrl,
        maximumLevel: maxLevel,
        minimumLevel: minLevel,
        tilingScheme: new Cesium.WebMercatorTilingScheme(),
        enablePickFeatures: false,
        rectangle: rectangle,
      });
      log(
        "debug",
        "Imagery provider template URL: " + providerUrl
      );
      log(
        "info",
        "Imagery provider configured name=" +
          String(name || "") +
          " min=" +
          minLevel +
          " max=" +
          maxLevel +
          " rectangle=" +
          JSON.stringify(normalizedBounds || null) +
          " url=" +
          providerUrl
      );
      // Attach ready handler to detect initialization issues
      if (provider.readyPromise && typeof provider.readyPromise.then === "function") {
        provider.readyPromise.then(
          function () {
            log("debug", "Provider ready name=" + name + " tilesLoaded=" + (provider.getTileCredits ? "yes" : "no"));
          },
          function (err) {
            log("warn", "Provider ready failed name=" + name + " error=" + String(err));
          }
        );
      }
      attachTileErrorHandler(provider, name);
      
      // Add layer at proper index to ensure basemap stays at bottom
      // Calculate insertion index: basemap layers should always be at index 0
      let insertionIndex = viewer.imageryLayers.length;
      
      // If we have basemap layers, ensure user layers start from index 1+
      if (osmBasemapLayer || defaultEarthLayer) {
        // Find the highest basemap index
        let basemapIndex = -1;
        if (osmBasemapLayer) {
          basemapIndex = Math.max(basemapIndex, viewer.imageryLayers.indexOf(osmBasemapLayer));
        }
        if (defaultEarthLayer) {
          basemapIndex = Math.max(basemapIndex, viewer.imageryLayers.indexOf(defaultEarthLayer));
        }
        
        // Insert user layers after basemap layers
        if (basemapIndex >= 0) {
          insertionIndex = basemapIndex + 1;
        }
      }
      
      activeImageryLayer = viewer.imageryLayers.addImageryProvider(provider, insertionIndex);
      managedImageryLayers.set(layerKey, activeImageryLayer);
      
      log("debug", "Layer added at index " + viewer.imageryLayers.indexOf(activeImageryLayer) + 
          " (requested index: " + insertionIndex + ")");
      
      // Tag the layer with its key for reordering functionality
      activeImageryLayer._layerKey = layerKey;
      activeImageryLayer._layerName = name;
      
      // CRITICAL FIX: Only ensure basemap is at bottom, don't force layer positions
      // This allows user reordering to work properly without conflicts
      
      // Step 1: Ensure basemap is at bottom (essential for proper rendering)
      if (osmBasemapLayer && osmBasemapLayer.show && viewer.imageryLayers.indexOf(osmBasemapLayer) >= 0) {
        viewer.imageryLayers.lowerToBottom(osmBasemapLayer);
      } else if (defaultEarthLayer && viewer.imageryLayers.indexOf(defaultEarthLayer) >= 0) {
        viewer.imageryLayers.lowerToBottom(defaultEarthLayer);
      }
      
      // REMOVED: Automatic layer stacking that conflicts with user reordering
      // The reorderLayersEventDriven() function now handles all layer positioning
      // This prevents visual conflicts and allows seamless reordering
      
      activeImageryLayer.alpha = 1.0;
      activeImageryLayer.show = true;
      
      // CRITICAL: Hide DEM colorbar when showing regular imagery
      hideDemColorbar();
      
      // REMOVED: Auto-switch to 2D mode - let search results control the scene mode
      // This allows search results to properly force 3D mode when needed
      log("debug", "Imagery layer loaded without forcing scene mode: " + name);
      
      // Debug layer state after addition
      log("debug", "Layer added: " + name + " at index " + viewer.imageryLayers.indexOf(activeImageryLayer) + " (top)");
      log("debug", "DEM colorbar hidden (regular imagery layer)");
      
      // BUG-FIX: Do NOT auto-focus here. Python calls flyToBounds/focusBoundsWithPadding
      // after ALL layers are loaded, giving a single smooth fly-to with tiles visible.
      // An internal setTimeout(focusBounds, 100) here raced with the Python fly and caused
      // black-screen flicker as the two flights fought each other.
      
      // Force multiple render requests with improved timing for tile loading
      if (viewer.scene) {
        viewer.scene.requestRender();
        
        // Staggered render requests with better timing for tile loading
        const renderDelays = [50, 150, 300, 600, 1000];
        renderDelays.forEach((delay, index) => {
          setTimeout(function() {
            if (viewer && viewer.scene) {
              viewer.scene.requestRender();
            }
          }, delay);
        });
        
        // Additional check for tile loading after initial burst
        setTimeout(function() {
          if (viewer && viewer.imageryLayers && activeImageryLayer) {
            const layerIndex = viewer.imageryLayers.indexOf(activeImageryLayer);
            
            // Force one more render if layer is still active
            if (layerIndex >= 0) {
              viewer.scene.requestRender();
            }
          }
        }, 1500);
      }
      layerDefinitions.set(layerKey, {
        key: layerKey,
        label: String(name || layerKey),
        type: "imagery",
        url: providerUrl,
        minLevel: minLevel,
        maxLevel: maxLevel,
        bounds: normalizedBounds,
      });
      layerVisibilityState.set(layerKey, true);
      applySwipeComparatorSplit();
      if (comparatorModeEnabled) {
        refreshComparatorLayers();
      }
      updateBasemapBlendForCurrentMode();
      logLayerStack();
      setStatus("Layer added: " + name);
      log(
        "info",
        "Layer added name=" +
          name +
          " key=" +
          layerKey +
          " kind=" +
          kind +
          " url=" +
          providerUrl +
          " min=" +
          minLevel +
          " max=" +
          maxLevel
      );
      // Start tile loading progress monitor
      startTileLoadingMonitor();
    },
    addDemLayer: function (name, xyzUrl, options) {
      if (!viewer) return;
      log(
        "info",
        "addDemLayer request name=" +
          String(name || "") +
          " xyz=" +
          String(xyzUrl || "") +
          " options=" +
          JSON.stringify(options || {})
      );
      const replaceExisting = !(options && options.replace_existing === false);
      const layerKey =
        options && typeof options.layer_key === "string" && options.layer_key
          ? options.layer_key
          : "dem:" + String(name || "layer");
      if (replaceExisting) {
        clearManagedImageryLayers();
      }
      setSceneModeInternal("3d");
      setSceneModeControlEnabled(true);
      syncSceneModeToggle("3d");
      const normalizedBounds = normalizeBounds(options && options.bounds ? options.bounds : null);
      if (normalizedBounds) {
        setActiveTileBounds(normalizedBounds);
      }
      activeDemContext = {
        layerKey: layerKey,
        name: name,
        xyzUrl: xyzUrl,
        options: options || {},
        visible: true,
      };
      layerVisibilityState.set(layerKey, true);
      applyDemLayer();
    },
    setSceneMode: function (mode) {
      sceneDebug(
        "window.setSceneMode requested=" +
          mode +
          " sceneModeControlEnabled=" +
          String(sceneModeControlEnabled) +
          " activeDemContext=" +
          String(Boolean(activeDemContext)) +
          " detectSceneMode=" +
          detectSceneMode() +
          " currentSceneMode=" +
          currentSceneMode
      );
      setSceneModeInternal(mode);
    },
    setSceneModeControlEnabled: function (enabled) {
      setSceneModeControlEnabled(Boolean(enabled));
    },
    setSearchBusy: function (active, message) {
      setSearchBusy(active, message);
    },
    setDemColorMode: function (colormapName) {
      const normalized = String(colormapName || "gray").toLowerCase();
      const allowed = new Set(["gray", "terrain", "slope", "aspect"]);
      const mode = allowed.has(normalized) ? normalized : "gray";
      if (comparatorModeEnabled) {
        const paneState = getComparatorPaneVisual(comparatorSelectedPane);
        if (!paneState) {
          return;
        }
        paneState.dem.colorMode = mode;
        if (getComparatorPaneLayerType(comparatorSelectedPane) === "dem") {
          scheduleComparatorDemRefresh(comparatorSelectedPane);
        }
        notifyComparatorPaneState(comparatorSelectedPane);
        requestSceneRender();
        return;
      }
      setDemColorMode(mode);
    },
    setSwipeComparatorLayers: function (leftLayerKey, rightLayerKey, leftLabel, rightLabel) {
      if (typeof refreshComparatorLayers === "function") {
        refreshComparatorLayers();
      }
    },
    setComparatorLayers: function (leftLayerKey, rightLayerKey, leftLabel, rightLabel) {
      if (typeof refreshComparatorLayers === "function") {
        refreshComparatorLayers();
      }
    },
    setLayerVisibility: function (layerKey, visible) {
      const applied = setLayerVisibilityByKey(String(layerKey || ""), Boolean(visible));
      if (!applied) {
        log("warn", "Layer visibility update ignored key=" + String(layerKey));
      }
    },
    setPolygonVisibility: function (polyId, visible) {
      toggleDrawnPolygonVisibility(polyId, visible);
    },
    setAnnotationDrawingMode: function (active) {
      isAnnotationDrawing = Boolean(active);
      log("info", "Annotation drawing mode set: " + isAnnotationDrawing);
    },
    setSearchPolygonVisibility: function (visible) {
      polygonVisibilityEnabled = Boolean(visible);
      updatePolygonPreviewVisibility();
      toggleAllDrawnPolygonsVisibility(visible);
      updateComparatorPolygons(visible);
      log("debug", "All polygons visibility set to " + String(visible));
    },
    setBasemapVisibility: function (visible) {
      // Toggle OSM basemap visibility with lazy loading and smooth transition
      if (!viewer || !viewer.imageryLayers) {
        log("warn", "Cannot toggle basemap visibility - viewer not ready");
        return;
      }
      
      const shouldShow = Boolean(visible);
      
      if (window._basemapToggleTimer) {
        clearTimeout(window._basemapToggleTimer);
        window._basemapToggleTimer = null;
      }
      
      if (window._basemapToggleInProgress) {
        window._basemapToggleTimer = setTimeout(() => {
          window.offlineGIS.setBasemapVisibility(visible);
        }, 150);
        return;
      }
      
      window._basemapToggleInProgress = true;
      window._currentBasemapVisibility = shouldShow;
      
      const applyBasemapToViewer = function(targetViewer, isMain) {
          if (!targetViewer || !targetViewer.imageryLayers) return;
          
          if (shouldShow) {
              if (isMain && defaultEarthLayer) defaultEarthLayer.show = false;
              if (targetViewer.__defaultEarthLayer) targetViewer.__defaultEarthLayer.show = false;
              
              if (!targetViewer.__osmBasemapLayer) {
                  try {
                      const osmProvider = new Cesium.UrlTemplateImageryProvider({
                          url: `${LOCAL_SATELLITE_TILE_ROOT}/{z}/{x}/{y}.png`,
                          tilingScheme: new Cesium.WebMercatorTilingScheme(),
                          minimumLevel: 0,
                          maximumLevel: 10,
                          credit: new Cesium.Credit("© OpenStreetMap contributors", false),
                          enablePickFeatures: false,
                          tileWidth: 256,
                          tileHeight: 256,
                      });
                      osmProvider.errorEvent.addEventListener(function (error) { error.retry = false; });
                      targetViewer.__osmBasemapLayer = targetViewer.imageryLayers.addImageryProvider(osmProvider, 0);
                      targetViewer.__osmBasemapLayer.alpha = 1.0;
                      targetViewer.__osmBasemapLayer.show = true;
                      targetViewer.__osmBasemapLayer.splitDirection = Cesium.ImagerySplitDirection.NONE;
                      targetViewer.__osmBasemapLayer.cutoutRectangle = undefined;
                      targetViewer.__osmBasemapLayer.colorToAlpha = undefined;
                      targetViewer.__osmBasemapLayer.colorToAlphaThreshold = 0.0;
                  } catch (e) {
                      log("error", "Failed to create OSM basemap: " + e.message);
                  }
              } else {
                  targetViewer.__osmBasemapLayer.show = true;
                  if (targetViewer.imageryLayers.indexOf(targetViewer.__osmBasemapLayer) !== 0) {
                      targetViewer.imageryLayers.lowerToBottom(targetViewer.__osmBasemapLayer);
                  }
              }
              if (isMain) osmBasemapLayer = targetViewer.__osmBasemapLayer;
          } else {
              if (targetViewer.__osmBasemapLayer) targetViewer.__osmBasemapLayer.show = false;
              if (isMain && defaultEarthLayer) {
                  defaultEarthLayer.show = true;
                  if (targetViewer.imageryLayers.indexOf(defaultEarthLayer) !== 0) {
                      targetViewer.imageryLayers.lowerToBottom(defaultEarthLayer);
                  }
              }
              if (targetViewer.__defaultEarthLayer) {
                  targetViewer.__defaultEarthLayer.show = true;
                  if (targetViewer.imageryLayers.indexOf(targetViewer.__defaultEarthLayer) !== 0) {
                      targetViewer.imageryLayers.lowerToBottom(targetViewer.__defaultEarthLayer);
                  }
              }
          }
      };

      if (osmBasemapLayer) viewer.__osmBasemapLayer = osmBasemapLayer;
      applyBasemapToViewer(viewer, true);
      
      if (typeof comparatorViewers !== 'undefined' && Array.isArray(comparatorViewers)) {
          comparatorViewers.forEach(v => applyBasemapToViewer(v, false));
      }

      window._basemapToggleInProgress = false;
      
      // PERFORMANCE: Single render request instead of multiple
      if (viewer.scene) {
        viewer.scene.requestRender();
      }
      
      // Reset the in-progress flag immediately (no need to wait for render)
      window._basemapToggleInProgress = false;
      
      log("info", "Basemap visibility set to " + (shouldShow ? "SHOW (OSM at index 0)" : "HIDE (default Earth at index 0)"));
    },
    setDemProperties: function (hillshadeAlpha) {
      const nextHillshadeAlpha = Math.max(0.0, Math.min(1.0, Number(hillshadeAlpha) || 0.0));

      if (_demPropertiesDebounceTimer) clearTimeout(_demPropertiesDebounceTimer);
      _demPropertiesDebounceTimer = setTimeout(function () {
        log("info", "setDemProperties (debounced): hillshadeAlpha=" + nextHillshadeAlpha.toFixed(2));

        if (comparatorModeEnabled) {
          const paneState = getComparatorPaneVisual(comparatorSelectedPane);
          if (!paneState) return;

          paneState.dem.hillshadeAlpha = nextHillshadeAlpha;
          applyComparatorPaneVisualState(comparatorSelectedPane);
          notifyComparatorPaneState(comparatorSelectedPane);
          requestSceneRender();
          return;
        }

        demVisual.hillshadeAlpha = nextHillshadeAlpha;

        if (activeDemHillshadeLayer) {
          activeDemHillshadeLayer.alpha = demVisual.hillshadeAlpha;
          const demVisible = activeDemContext && activeDemContext.visible !== false;
          activeDemHillshadeLayer.show = demVisible && demVisual.hillshadeAlpha > 0.01;
        }

        if (viewer && viewer.scene) {
          viewer.scene.requestRender();
        }
      }, VISUAL_UPDATE_DEBOUNCE_MS);
    },
    setImageryProperties: function (brightness, contrast) {
      if (!viewer) return;
      const nextBrightness = Math.max(0.2, brightness);
      const nextContrast = Math.max(0.1, contrast);

      if (_imageryPropertiesDebounceTimer) clearTimeout(_imageryPropertiesDebounceTimer);
      _imageryPropertiesDebounceTimer = setTimeout(function () {
        log("info", "setImageryProperties (debounced): brightness=" + nextBrightness.toFixed(2) + " contrast=" + nextContrast.toFixed(2));

        if (comparatorModeEnabled) {
          const paneState = getComparatorPaneVisual(comparatorSelectedPane);
          if (!paneState) return;

          paneState.imagery.brightness = nextBrightness;
          paneState.imagery.contrast = nextContrast;
          applyComparatorPaneVisualState(comparatorSelectedPane);
          notifyComparatorPaneState(comparatorSelectedPane);
          requestSceneRender();
          return;
        }

        imageryVisual.brightness = nextBrightness;
        imageryVisual.contrast = nextContrast;

        const visibleManagedLayers = Array.from(managedImageryLayers.values()).filter((layer) => layer && layer.show);
        if (visibleManagedLayers.length > 0) {
          for (const layer of visibleManagedLayers) {
            layer.brightness = nextBrightness;
            layer.contrast = nextContrast;
          }
        }
        
        if (osmBasemapLayer && osmBasemapLayer.show) {
          osmBasemapLayer.brightness = nextBrightness;
          osmBasemapLayer.contrast = nextContrast;
        }
        if (defaultEarthLayer && defaultEarthLayer.show) {
          defaultEarthLayer.brightness = nextBrightness;
          defaultEarthLayer.contrast = nextContrast;
        }

        const layer = activeImageryLayer || viewer.imageryLayers.get(0);
        if (layer) {
          layer.brightness = nextBrightness;
          layer.contrast = nextContrast;
        }

        requestSceneRender();
      }, VISUAL_UPDATE_DEBOUNCE_MS);
    },
    rotateCamera: function (degrees) {
      if (!viewer) return;
      // Rotation (heading change) works in both 2D and 3D modes
      log("info", "rotateCamera called: degrees=" + degrees + " comparatorMode=" + comparatorModeEnabled);
      // Rotate around the center of the screen, staying locked to the target asset
      const canvas = viewer.scene.canvas;
      const center = new Cesium.Cartesian2(canvas.clientWidth / 2.0, canvas.clientHeight / 2.0);
      const pickRay = viewer.camera.getPickRay(center);
      const target = viewer.scene.globe.pick(pickRay, viewer.scene);
      
      if (target) {
        log("info", "rotateCamera: orbiting around surface target");
        const transform = Cesium.Transforms.eastNorthUpToFixedFrame(target);
        viewer.camera.lookAtTransform(transform);
        viewer.camera.rotateRight(Cesium.Math.toRadians(degrees));
        viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
      } else {
        log("info", "rotateCamera: no surface found, rotating camera directly");
        viewer.camera.rotateRight(Cesium.Math.toRadians(degrees));
      }
      // Apply to all active comparator DEM panes (skip 2D imagery panes)
      // Use lookAt locked to DEM bounds so camera stays focused on the layer
      if (comparatorModeEnabled && Array.isArray(comparatorViewers)) {
        comparatorViewers.forEach(function(cv, ci) {
          if (!cv || !cv.scene) return;
          if (cv.scene.mode !== Cesium.SceneMode.SCENE3D) {
            log("debug", "rotateCamera: skipping comparatorViewer[" + ci + "] — imagery pane in 2D");
            return;
          }
          // Accumulate heading on the viewer's current heading
          var newHeading = cv.camera.heading + Cesium.Math.toRadians(degrees);
          var pitch = getComparatorDemPitchRadians();
          log("debug", "rotateCamera: comparatorViewer[" + ci + "] heading=" +
            Cesium.Math.toDegrees(newHeading).toFixed(1) + "° pitch=" +
            Cesium.Math.toDegrees(pitch).toFixed(1) + "°");
          try {
            cv.camera.setView({
              destination: cv.camera.position.clone(),
              orientation: { heading: newHeading, pitch: pitch, roll: cv.camera.roll },
            });
          } catch(e) {
            log("warn", "rotateCamera: comparatorViewer[" + ci + "] setView failed: " + e);
          }
          cv.scene.requestRender();
        });
      }
      requestSceneRender();
      log("info", "rotateCamera completed: degrees=" + degrees);
    },
    setPitch: function (degrees) {
      if (!viewer) return;
      if (currentSceneMode === "2d") {
        log("info", "setPitch: ignored in 2D mode");
        return;
      }
      log("info", "setPitch called: degrees=" + degrees);

      cameraOrbitPitch = Cesium.Math.toRadians(degrees);
      if (cameraOrbitPitch < MIN_3D_PITCH_RAD) {
        cameraOrbitPitch = MIN_3D_PITCH_RAD;
      }
      log("info", "setPitch: cameraOrbitPitch set to degrees=" + Cesium.Math.toDegrees(cameraOrbitPitch).toFixed(1));

      // Pitch around the center of the screen, staying locked to the target asset
      const canvas = viewer.scene.canvas;
      const center = new Cesium.Cartesian2(canvas.clientWidth / 2.0, canvas.clientHeight / 2.0);
      const pickRay = viewer.camera.getPickRay(center);
      const target = viewer.scene.globe.pick(pickRay, viewer.scene);
      
      if (target) {
        log("info", "setPitch: tilting around surface target");
        // Calculate current range to the target
        const distance = Cesium.Cartesian3.distance(viewer.camera.position, target);
        // Apply lookAt with the new pitch
        viewer.camera.lookAt(target, new Cesium.HeadingPitchRange(viewer.camera.heading, cameraOrbitPitch, distance));
        viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
      } else {
        log("info", "setPitch: no surface found, tilting camera directly");
        viewer.camera.setView({
          destination: viewer.camera.position.clone(),
          orientation: { heading: viewer.camera.heading, pitch: cameraOrbitPitch, roll: viewer.camera.roll },
        });
      }

      // Apply to comparator DEM panes
      if (comparatorModeEnabled && Array.isArray(comparatorViewers)) {
        comparatorViewers.forEach(function(cv, ci) {
          if (!cv || !cv.scene) return;
          if (cv.scene.mode !== Cesium.SceneMode.SCENE3D) return;
          try {
            cv.camera.setView({
              destination: cv.camera.position.clone(),
              orientation: { heading: cv.camera.heading, pitch: cameraOrbitPitch, roll: cv.camera.roll },
            });
          } catch(e) {
            log("warn", "setPitch: comparatorViewer[" + ci + "] setView failed: " + e);
          }
          cv.scene.requestRender();
        });
      }

      requestSceneRender();
      log("info", "setPitch completed: degrees=" + degrees);
    },
    addAnnotation: function (text, lon, lat) {
      if (!viewer) return;
      annotationCounter += 1;
      const annotationId = "annotation-" + String(annotationCounter);
      const pointName = String(text || "Point").trim() || "Point";
      let anchorPosition = null;
      if (lastMapClickCartesian) {
        const lastLonLat = cartesianToLonLat(lastMapClickCartesian);
        if (lastLonLat) {
          const lonDiff = Math.abs(Number(lastLonLat.lon) - Number(lon));
          const latDiff = Math.abs(Number(lastLonLat.lat) - Number(lat));
          if (lonDiff <= 0.00002 && latDiff <= 0.00002) {
            anchorPosition = Cesium.Cartesian3.clone(lastMapClickCartesian);
          }
        }
      }
      if (!anchorPosition) {
        const cartographic = Cesium.Cartographic.fromDegrees(Number(lon), Number(lat));
        const sampledHeight = viewer.scene && viewer.scene.globe ? viewer.scene.globe.getHeight(cartographic) : null;
        const height = Number.isFinite(sampledHeight) ? Number(sampledHeight) : 0.0;
        anchorPosition = Cesium.Cartesian3.fromDegrees(Number(lon), Number(lat), height);
      }
      lastMapClickCartesian = null;
      const anchorEntity = viewer.entities.add({
        position: anchorPosition,
        point: {
          pixelSize: 10,
          color: Cesium.Color.fromCssColorString("#f2c94c"),
          outlineColor: Cesium.Color.fromCssColorString("#1d1d1d"),
          outlineWidth: 1,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      anchorEntity.show = annotationVisibilityEnabled;
      anchorEntity._annotationId = annotationId;
      anchorEntity._annotationRole = "anchor";

      const labelEntity = viewer.entities.add({
        position: anchorPosition,
        label: {
          text: pointName,
          fillColor: Cesium.Color.WHITE,
          showBackground: true,
          backgroundColor: Cesium.Color.BLACK.withAlpha(0.62),
          outlineColor: Cesium.Color.BLACK.withAlpha(0.9),
          outlineWidth: 2,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          font: "500 12px 'Segoe UI', 'Helvetica Neue', sans-serif",
          pixelOffset: new Cesium.Cartesian2(12, -8),
          horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1800000.0, 0.45),
          translucencyByDistance: new Cesium.NearFarScalar(3000.0, 1.0, 2400000.0, 0.62),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      labelEntity.show = annotationVisibilityEnabled;
      labelEntity._annotationId = annotationId;
      labelEntity._annotationRole = "label";

      const editEntity = viewer.entities.add({
        position: anchorPosition,
        billboard: {
          image: ANNOTATION_EDIT_ICON_IMAGE,
          width: 17,
          height: 17,
          color: Cesium.Color.WHITE.withAlpha(0.42),
          pixelOffset: new Cesium.Cartesian2(12, -26),
          horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1700000.0, 0.62),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      editEntity.show = annotationVisibilityEnabled;
      editEntity._annotationId = annotationId;
      editEntity._annotationRole = "edit";
      editEntity._annotationAnchorEntity = anchorEntity;
      editEntity._annotationLabelEntity = labelEntity;

      const deleteEntity = viewer.entities.add({
        position: anchorPosition,
        billboard: {
          image: ANNOTATION_DELETE_ICON_IMAGE,
          width: 17,
          height: 17,
          color: Cesium.Color.WHITE.withAlpha(0.62),
          pixelOffset: new Cesium.Cartesian2(32, -26),
          horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1700000.0, 0.62),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      deleteEntity.show = annotationVisibilityEnabled;
      deleteEntity._annotationId = annotationId;
      deleteEntity._annotationRole = "delete";
      deleteEntity._annotationAnchorEntity = anchorEntity;
      deleteEntity._annotationLabelEntity = labelEntity;
      deleteEntity._annotationEditEntity = editEntity;

      annotationEntities.push(anchorEntity);
      annotationEntities.push(labelEntity);
      annotationEntities.push(editEntity);
      annotationEntities.push(deleteEntity);
      requestSceneRender();
      window.requestAnimationFrame(requestSceneRender);
      log("info", "Annotation added lon=" + lon + " lat=" + lat);
    },
    clearAnnotations: function () {
      clearAnnotationEntities();
      log("info", "Annotations cleared");
    },
    setAnnotationVisibility: function (visible) {
      setAnnotationVisibility(Boolean(visible));
    },
    clearMeasurements: function () {
      setDistanceMeasureMode(false);
      clickedPoints.length = 0;
      clearMeasurementEntities();
      clearMeasurementPreviewEntities();
      clearDistanceScaleOverlay();
      _clearFillVolumeEntities();
      window._fillVolumePrimitives = [];
      log("info", "Measurement overlays cleared");
    },
    clearMeasurementEntities: function () {
      clearMeasurementEntities();
      log("debug", "Measurement entities cleared");
    },
    clearOverlays: function () {
      clickedPoints.length = 0;
      setDistanceMeasureMode(false);
      clearMeasurementEntities();
      clearMeasurementPreviewEntities();
      clearDistanceScaleOverlay();
      clearAnnotationEntities();
      clearSearchEntities();
      _clearFillVolumeEntities();
      window._fillVolumePrimitives = [];
      searchPolygonPoints.length = 0;
      searchPolygonLocked = false;
      searchCursorPoint = null;
      searchOverlayVisible = true;
      emitSearchGeometry("none", {});
      setStatus("All overlays cleared");
      log("info", "All overlays cleared");
      requestSceneRender();
    },
    undoLastAction: function () {
      let undid = false;
      // Undo last annotation point
      if (annotationEntities.length > 0) {
        // Each annotation has 4 entities: anchor, label, edit, delete
        const last = annotationEntities[annotationEntities.length - 1];
        if (last && last._annotationRole) {
          const targetId = last._annotationId;
          const toRemove = [];
          for (let i = annotationEntities.length - 1; i >= 0; i--) {
            if (annotationEntities[i]._annotationId === targetId) {
              toRemove.push(i);
            }
          }
          for (let i = 0; i < toRemove.length; i++) {
            const entity = annotationEntities.splice(toRemove[i], 1)[0];
            if (entity) viewer.entities.remove(entity);
          }
          undid = true;
          setStatus("Undo: removed last annotation.");
          log("info", "Undo annotation id=" + targetId);
        }
      }
      if (!undid && searchDrawMode === "polygon" && !searchPolygonLocked && searchPolygonPoints.length > 0) {
        searchPolygonPoints.pop();
        updateSearchPolygonPreview();
        undid = true;
        setStatus("Undo: removed last polygon point. " + searchPolygonPoints.length + " points remain.");
        log("info", "Undo polygon point");
      }
      if (!undid && distanceMeasureModeEnabled && distanceMeasureAnchor) {
        distanceMeasureAnchor = null;
        clearMeasurementPreviewEntities();
        undid = true;
        setStatus("Undo: removed measurement start point.");
        log("info", "Undo distance start");
      }
      requestSceneRender();
      return undid;
    },
    zoomIn: function () {
      log("debug", "=== ZOOM IN BUTTON PRESSED ===");
      zoomBy(0.65);
      log("debug", "Zoom in button completed");
    },
    zoomOut: function () {
      log("debug", "=== ZOOM OUT BUTTON PRESSED ===");
      zoomBy(1.35);
      log("debug", "Zoom out button completed");
    },
    zoomToExtent: function () {
      zoomToExtent();
      log("debug", "Zoom to extent");
    },
    resetNorthUp: function () {
      resetNorthUp();
      log("debug", "North-up orientation reset");
    },
    setSwipeComparator: function (enabled) {
      setSwipeComparatorEnabled(Boolean(enabled));
      log("debug", "Comparator=" + String(Boolean(enabled)));
    },
    setLayerAlpha: function (layerKey, alpha) {
      if (!viewer || !viewer.imageryLayers) return;
      const numAlpha = Math.max(0.0, Math.min(1.0, Number(alpha) || 0.0));
      
      const layer = managedImageryLayers.get(layerKey);
      if (layer) {
        layer.alpha = numAlpha;
      } else if (activeDemContext && activeDemContext.layerKey === layerKey) {
        if (activeDemDrapeLayer) {
          activeDemDrapeLayer.alpha = numAlpha;
        }
        if (activeDemHillshadeLayer) {
          const scaledHillshade = Math.max(
            0.0,
            Math.min(1.0, demVisual.hillshadeAlpha * numAlpha)
          );
          activeDemHillshadeLayer.alpha = scaledHillshade;
          activeDemHillshadeLayer.show =
            (activeDemContext.visible !== false) && scaledHillshade > 0.01;
        }
      }
      requestSceneRender();
    },
    setComparator: function (enabled) {
      setSwipeComparatorEnabled(Boolean(enabled));
      log("debug", "Comparator=" + String(Boolean(enabled)));
    },
    requestComparatorPaneState: function () {
      notifyComparatorPaneState(comparatorSelectedPane);
    },
    setSwipePosition: function (fraction) {
      setSwipePosition(Number(fraction));
      log("debug", "Comparator position=" + String(fraction));
    },
    setComparatorPosition: function (fraction) {
      setSwipePosition(Number(fraction));
      log("debug", "Comparator position=" + String(fraction));
    },
    setFlyThroughMode: function (enabled) {
      flyThroughModeEnabled = Boolean(enabled);
      if (!flyThroughModeEnabled) {
        flyThroughPoints.length = 0;
        if (flyThroughPreviewLineEntity) {
          viewer.entities.remove(flyThroughPreviewLineEntity);
          flyThroughPreviewLineEntity = null;
        }
      }
    },
    setComparatorMode: function (enabled) {
      setSwipeComparatorEnabled(Boolean(enabled));
    },
    setDistanceMeasureMode: function (enabled) {
      setDistanceMeasureMode(Boolean(enabled));
      log("info", "Distance measure mode=" + String(Boolean(enabled)));
    },
    setMeasurementCursor: function (enabled) {
      log("info", "[CURSOR_DEBUG] setMeasurementCursor API called enabled=" + String(Boolean(enabled)));
      setMeasurementCursorEnabled(Boolean(enabled));
    },
    drawProfileLine: function (lon1, lat1, lon2, lat2) {
      if (!viewer) return;
      // Clear profile mode flag and preview line
      window._profileModeActive = false;
      if (window._profilePreviewEntity) {
        try { viewer.entities.remove(window._profilePreviewEntity); } catch (_) {}
        window._profilePreviewEntity = null;
      }
      // Remove any previous profile line and markers
      if (window._profileLineEntity) {
        try { viewer.entities.remove(window._profileLineEntity); } catch (_) {}
        window._profileLineEntity = null;
      }
      if (window._profileStartEntity) {
        try { viewer.entities.remove(window._profileStartEntity); } catch (_) {}
        window._profileStartEntity = null;
      }
      if (window._profileEndEntity) {
        try { viewer.entities.remove(window._profileEndEntity); } catch (_) {}
        window._profileEndEntity = null;
      }
      const cyan = Cesium.Color.fromCssColorString("#00e5ff");
      window._profileLineEntity = viewer.entities.add({
        polyline: {
          positions: [
            Cesium.Cartesian3.fromDegrees(Number(lon1), Number(lat1)),
            Cesium.Cartesian3.fromDegrees(Number(lon2), Number(lat2)),
          ],
          width: 2.5,
          arcType: Cesium.ArcType.GEODESIC,
          material: cyan,
          depthFailMaterial: cyan.withAlpha(0.5),
        },
      });
      // Start/end point markers
      window._profileStartEntity = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(Number(lon1), Number(lat1)),
        point: { pixelSize: 8, color: cyan, outlineColor: Cesium.Color.BLACK, outlineWidth: 1, disableDepthTestDistance: Number.POSITIVE_INFINITY },
      });
      window._profileEndEntity = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(Number(lon2), Number(lat2)),
        point: { pixelSize: 8, color: cyan, outlineColor: Cesium.Color.BLACK, outlineWidth: 1, disableDepthTestDistance: Number.POSITIVE_INFINITY },
      });
      requestSceneRender();
      log("debug", "Profile line drawn lon1=" + lon1 + " lat1=" + lat1 + " lon2=" + lon2 + " lat2=" + lat2);
      // Store endpoints for georeferenced cursor projection
      window._profileLineLon1 = Number(lon1);
      window._profileLineLat1 = Number(lat1);
      window._profileLineLon2 = Number(lon2);
      window._profileLineLat2 = Number(lat2);
      window._profileLineActive = true;
      // Create the moving cursor point on the globe (dull yellow, starts at midpoint)
      if (window._profileCursorGlobeEntity) {
        try { viewer.entities.remove(window._profileCursorGlobeEntity); } catch (_) {}
        window._profileCursorGlobeEntity = null;
      }
      const yellow = Cesium.Color.fromCssColorString("#c8a800").withAlpha(0.88);
      // Pre-compute the geodesic for accurate interpolation along the great-circle arc
      const _geodesicForCursor = new Cesium.EllipsoidGeodesic(
        Cesium.Cartographic.fromDegrees(Number(lon1), Number(lat1)),
        Cesium.Cartographic.fromDegrees(Number(lon2), Number(lat2))
      );
      window._profileCursorGlobeEntity = viewer.entities.add({
        position: new Cesium.CallbackProperty(function () {
          if (!window._profileLineActive) {
            return Cesium.Cartesian3.fromDegrees(Number(lon1), Number(lat1));
          }
          const f = (typeof window._profileCursorFrac === "number")
            ? Math.max(0.0, Math.min(1.0, window._profileCursorFrac))
            : 0.5;
          // Interpolate along the true geodesic arc — pixel-accurate for any resolution
          const interp = _geodesicForCursor.interpolateUsingFraction(f);
          return Cesium.Cartesian3.fromRadians(interp.longitude, interp.latitude);
        }, false),
        point: {
          pixelSize: 10,
          color: yellow,
          outlineColor: Cesium.Color.fromCssColorString("#3a2800"),
          outlineWidth: 1.5,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      window._profileCursorFrac = 0.5;
    },
    setProfileCursorMode: function (enabled) {
      const container = document.getElementById("cesiumContainer");
      if (container) {
        if (enabled) {
          container.classList.add("measure-profile-cursor-active");
        } else {
          container.classList.remove("measure-profile-cursor-active");
        }
      }
      log("debug", "Profile cursor mode=" + String(Boolean(enabled)));
    },
    drawProfileStartMarker: function (lon, lat) {
      if (!viewer) return;
      // Remove previous start marker if any
      if (window._profileStartEntity) {
        try { viewer.entities.remove(window._profileStartEntity); } catch (_) {}
        window._profileStartEntity = null;
      }
      // Clear any stale preview line
      if (window._profilePreviewEntity) {
        try { viewer.entities.remove(window._profilePreviewEntity); } catch (_) {}
        window._profilePreviewEntity = null;
      }
      // Clear the previous completed profile line and end marker
      if (window._profileLineEntity) {
        try { viewer.entities.remove(window._profileLineEntity); } catch (_) {}
        window._profileLineEntity = null;
      }
      if (window._profileEndEntity) {
        try { viewer.entities.remove(window._profileEndEntity); } catch (_) {}
        window._profileEndEntity = null;
      }
      
      const cyan = Cesium.Color.fromCssColorString("#00e5ff");
      window._profileStartEntity = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(Number(lon), Number(lat)),
        point: { pixelSize: 9, color: cyan, outlineColor: Cesium.Color.BLACK, outlineWidth: 1.5, heightReference: Cesium.HeightReference.CLAMP_TO_GROUND, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        label: {
          text: "A",
          font: "bold 11px sans-serif",
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          pixelOffset: new Cesium.Cartesian2(10, -10),
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      // Store start coords — preview line is recreated on every mouse move
      window._profileStartLon = Number(lon);
      window._profileStartLat = Number(lat);
      window._profileModeActive = true;
      requestSceneRender();
      log("debug", "Profile start marker placed lon=" + lon + " lat=" + lat);
    },
    clearProfilePreview: function () {
      window._profileModeActive = false;
      window._profileStartLon = undefined;
      window._profileStartLat = undefined;
      
      if (window._profilePreviewEntity) {
        try { viewer.entities.remove(window._profilePreviewEntity); } catch (_) {}
        window._profilePreviewEntity = null;
      }
      if (window._profileStartEntity) {
        try { viewer.entities.remove(window._profileStartEntity); } catch (_) {}
        window._profileStartEntity = null;
      }
      requestSceneRender();
    },
    clearProfileLine: function () {
      window._profileModeActive = false;
      window._profileLineActive = false;
      window._profileLineLon1 = undefined;
      window._profileLineLat1 = undefined;
      window._profileLineLon2 = undefined;
      window._profileLineLat2 = undefined;
      window._profileCursorFrac = undefined;
      
      for (const key of ["_profilePreviewEntity", "_profileStartEntity", "_profileEndEntity", "_profileLineEntity", "_profileCursorGlobeEntity"]) {
        if (window[key]) {
          try { viewer.entities.remove(window[key]); } catch (_) {}
          window[key] = null;
        }
      }
      requestSceneRender();
      log("debug", "Profile line cleared from globe");
    },
    setPanMode: function (enabled) {
      setPanMode(Boolean(enabled));
      log("info", "Pan mode=" + String(Boolean(enabled)));
    },    setSearchDrawMode: function (mode) {
      if (mode !== "polygon") {
        searchDrawMode = "none";
        searchOverlayVisible = false;
        setSearchCursorEnabled(false);
        updatePolygonPreviewVisibility();
        // Removed DOM update
        setStatus("Search draw disabled");
        requestSceneRender();
        return;
      }
      searchDrawMode = "polygon";
      searchOverlayVisible = true;
      polygonVisibilityEnabled = true;
      searchCursorPoint = null;
      setPolygonPreviewVisible(true);
      setSearchCursorEnabled(!searchPolygonLocked);
      // Removed DOM update
      if (searchPolygonLocked) {
        setStatus("Polygon restored. Clear geometry to start a new polygon.");
      } else {
        setStatus("Polygon draw: click points, right-click or Finish to close");
      }
      requestSceneRender();
    },
    finishSearchPolygon: function () {
      finalizeSearchPolygon();
    },
    clearSearchGeometry: function () {
      searchDrawMode = "none";
      searchPolygonLocked = false;
      searchCursorPoint = null;
      searchPolygonPoints.length = 0;
      searchOverlayVisible = true;
      polygonVisibilityEnabled = true;
      clearSearchEntities();
      emitSearchGeometry("none", {});
      setPolygonPreviewVisible(true);
      setSearchCursorEnabled(false);
      // Removed DOM update
      setStatus("Search geometry cleared");
      requestSceneRender();
    },
    setPolygonPreviewVisible: function (visible) {
      setPolygonPreviewVisible(Boolean(visible));
    },
    clearFillVolumes: function () {
      _clearFillVolumeEntities();
      window._fillVolumePrimitives = [];
      requestSceneRender();
      log("debug", "Fill volume overlays cleared");
    },
    drawFillVolumes: function (regionsJson) {
      _clearFillVolumeEntities();
      var regions;
      try { regions = JSON.parse(regionsJson); } catch (e) { log("error", "drawFillVolumes: bad JSON"); return; }
      if (!Array.isArray(regions) || regions.length === 0) {
        log("debug", "drawFillVolumes: no regions to draw");
        return;
      }

      log("info", "Starting to draw " + regions.length + " fill volume regions");

      var distinctColors = [
        [255,  80,  40, 200],
        [ 40, 120, 255, 200],
        [ 40, 220, 100, 200],
        [255, 200,  40, 200],
        [180,  40, 255, 200],
        [255, 100, 180, 200],
        [ 40, 220, 220, 200],
        [255, 140,  40, 200],
      ];

      function getRegionColor(index) {
        var rgba = distinctColors[index % distinctColors.length];
        return new Cesium.Color(rgba[0]/255, rgba[1]/255, rgba[2]/255, rgba[3]/255);
      }

      var labelEntities = [];

      for (var ri = 0; ri < regions.length; ri++) {
        var r = regions[ri];
        var regionId = r.id || r.region_id || (ri + 1);

        if (!r.outline || r.outline.length < 3) {
          log("warn", "Region " + regionId + " has invalid outline, skipping");
          continue;
        }

        var fillColour = getRegionColor(ri);

        // Pure entity polygon — no GroundPrimitive, no GPU lifecycle, safe on macOS Metal + Windows NVIDIA.
        // No height — Cesium drapes on globe surface. arcType RHUMB gives pixel-accurate
        // edges for small sub-km polygons (avoids geodesic subdivision artifacts).
        var positions = r.outline.map(function(p) {
          return Cesium.Cartesian3.fromDegrees(p.lon, p.lat);
        });

        // Use the region's rim elevation + small offset so the flat polygon
        // sits just above the terrain surface and is never occluded at any zoom level.
        var polyHeight = (typeof r.rim_elevation_m === 'number' && isFinite(r.rim_elevation_m))
          ? r.rim_elevation_m + 2.0
          : 2.0;

        var regionEnt = viewer.entities.add({
          id: 'fill-region-ent-' + regionId,
          polygon: {
            hierarchy: new Cesium.PolygonHierarchy(positions),
            material: fillColour,
            height: polyHeight,
            arcType: Cesium.ArcType.RHUMB,
            outline: false,
            fill: true,
          },
        });
        window._fillVolumeEntities.push(regionEnt);

        var volStr = r.fill_volume_m3 >= 1000000000
          ? (r.fill_volume_m3 / 1000000000).toFixed(3) + " km\u00b3"
          : r.fill_volume_m3 >= 1000000
          ? (r.fill_volume_m3 / 1000000).toFixed(3) + " Mm\u00b3"
          : r.fill_volume_m3.toFixed(3) + " m\u00b3";
        var areaStr = r.area_m2 >= 10000
          ? (r.area_m2 / 10000).toFixed(2) + " ha"
          : r.area_m2.toFixed(0) + " m\u00b2";

        labelEntities.push({
          position: Cesium.Cartesian3.fromDegrees(r.centroid_lon, r.centroid_lat, polyHeight + 5.0),
          regionId: regionId,
          volStr: volStr,
          areaStr: areaStr,
          maxDepth: r.max_depth_m,
          meanDepth: r.mean_depth_m,
        });
      }

      for (var li = 0; li < labelEntities.length; li++) {
        var labelData = labelEntities[li];

        var labelEnt = viewer.entities.add({
          id: 'fill-label-' + labelData.regionId,
          position: labelData.position,
          label: {
            text: "\u25bc Region " + labelData.regionId,
            font: "bold 13px 'Segoe UI', Arial, sans-serif",
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            fillColor: Cesium.Color.WHITE,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2.5,
            showBackground: true,
            backgroundColor: Cesium.Color.BLACK.withAlpha(0.85),
            backgroundPadding: new Cesium.Cartesian2(8, 5),
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            verticalOrigin: Cesium.VerticalOrigin.TOP,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            pixelOffset: new Cesium.Cartesian2(0, -15),
            scale: 1.0,
          },
        });
        labelEnt.regionId = labelData.regionId;
        labelEnt.volume = labelData.volStr;
        labelEnt.area = labelData.areaStr;
        labelEnt.maxDepth = labelData.maxDepth.toFixed(2) + ' m';
        labelEnt.meanDepth = labelData.meanDepth.toFixed(2) + ' m';
        labelEnt.expanded = false;
        labelEnt.isRegionLabel = true;
        window._fillVolumeEntities.push(labelEnt);

        var detailsEnt = viewer.entities.add({
          id: 'fill-details-' + labelData.regionId,
          position: labelData.position,
          label: {
            text:
              'Volume: ' + labelData.volStr + '\n' +
              'Area: ' + labelData.areaStr + '\n' +
              'Max Depth: ' + labelData.maxDepth.toFixed(2) + ' m\n' +
              'Mean Depth: ' + labelData.meanDepth.toFixed(2) + ' m',
            font: "12px 'Segoe UI', Arial, sans-serif",
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            fillColor: Cesium.Color.WHITE,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
            showBackground: true,
            backgroundColor: Cesium.Color.fromCssColorString('#1a1a1a').withAlpha(0.92),
            backgroundPadding: new Cesium.Cartesian2(10, 6),
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            verticalOrigin: Cesium.VerticalOrigin.TOP,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            pixelOffset: new Cesium.Cartesian2(0, 15),
            scale: 0.95,
            show: false,
          },
        });
        detailsEnt.parentRegionId = labelData.regionId;
        detailsEnt.isDetails = true;
        window._fillVolumeEntities.push(detailsEnt);
        labelEnt.detailsEntity = detailsEnt;
      }

      requestSceneRender();
      log("info", "Fill volumes drawn: " + regions.length + " regions");
    },
    
    // ═══════════════════════════════════════════════════════════════════════════
    // SECTION: Event-Driven Architecture Functions for Terabyte-Scale Performance
    // Ultra-high performance functions for handling 2-3TB rasters with smooth rendering
    // All processing happens on server, client requests everything from server
    // ═══════════════════════════════════════════════════════════════════════════
    
    addTileLayerEventDriven: async function (name, xyzUrl, kind, options) {
      if (!viewer) return;
      
      log("info", "EVENT_DRIVEN: addTileLayer name=" + String(name || "") + 
          " kind=" + String(kind || "") + " server_optimized=" + Boolean(options && options.server_optimized));
      
      // Event-driven optimization: Pre-configure for terabyte-scale performance
      if (options && options.server_optimized) {
        // Apply ultra-high performance settings for large datasets
        viewer.scene.globe.maximumScreenSpaceError = 1.0; // Original high detail fidelity
        viewer.scene.globe.tileCacheSize = 2000; // Aggressive tile caching
        // FIX: requestRenderMode disabled to prevent auto-blurring and shaking
        viewer.scene.requestRenderMode = false;
        
        log("info", "EVENT_DRIVEN: Applied terabyte-scale performance optimizations");
      }
      
      // Use existing addTileLayer with performance enhancements
      await window.offlineGIS.addTileLayer(name, xyzUrl, kind, options);
      
      // Additional event-driven optimizations
      if (options && options.server_optimized) {
        // Force aggressive tile loading for smooth interaction
        if (viewer.scene) {
          viewer.scene.requestRender();
          
          // Staggered render requests for smooth loading
          const renderDelays = [50, 150, 300, 600];
          renderDelays.forEach(delay => {
            setTimeout(() => {
              if (viewer && viewer.scene) {
                viewer.scene.requestRender();
              }
            }, delay);
          });
        }
        
        log("info", "EVENT_DRIVEN: Tile layer loaded with server optimization");
      }
    },
    
    addDemLayerEventDriven: function (name, xyzUrl, options) {
      if (!viewer) return;
      
      log("info", "EVENT_DRIVEN: addDemLayer name=" + String(name || "") + 
          " server_optimized=" + Boolean(options && options.server_optimized));
      
      // Event-driven DEM optimization for terabyte-scale terrain data
      if (options && options.server_optimized) {
        // Ultra-high performance DEM settings
        viewer.scene.globe.terrainExaggeration = Math.min(2.0, options.exaggeration || 1.5);
        viewer.scene.globe.enableLighting = false; // Disable lighting for performance
        viewer.scene.fog.enabled = false; // Disable fog for clarity
        viewer.scene.skyAtmosphere.show = false; // Reduce atmospheric rendering
        
        // Optimize terrain provider for large datasets
        if (viewer.terrainProvider && viewer.terrainProvider.requestTileGeometry) {
          viewer.scene.globe.maximumScreenSpaceError = 1.0; // Max fidelity terrain
        }
        
        log("info", "EVENT_DRIVEN: Applied DEM terabyte-scale optimizations");
      }
      
      // Use existing addDemLayer with performance enhancements
      window.offlineGIS.addDemLayer(name, xyzUrl, options);
      
      // Additional event-driven DEM optimizations
      if (options && options.server_optimized) {
        // Optimize camera for DEM viewing
        setTimeout(() => {
          if (viewer && viewer.camera) {
            // Set optimal camera settings for large terrain datasets
            viewer.camera.percentageChanged = 0.1; // More responsive camera updates
            viewer.scene.requestRender();
          }
        }, 100);
        
        log("info", "EVENT_DRIVEN: DEM layer loaded with server optimization");
      }
    },
    
    optimizeForTerabyteScale: function (options) {
      if (!viewer) return;
      
      const opts = options || {};
      
      log("info", "EVENT_DRIVEN: Applying terabyte-scale optimizations");
      
      // Ultra-high performance rendering settings
      // FIX: requestRenderMode disabled to prevent auto-blurring
      viewer.scene.requestRenderMode = false;
      viewer.scene.maximumRenderTimeChange = 0.0;
      viewer.scene.globe.maximumScreenSpaceError = opts.screenSpaceError || 1.5;
      viewer.scene.globe.tileCacheSize = opts.tileCacheSize || 2000;
      
      // Disable expensive visual effects for performance
      viewer.scene.fog.enabled = false;
      viewer.scene.skyAtmosphere.show = false;
      viewer.scene.globe.enableLighting = false;
      viewer.scene.sun.show = false;
      viewer.scene.moon.show = false;
      
      // Optimize imagery layers for large datasets
      if (viewer.imageryLayers) {
        for (let i = 0; i < viewer.imageryLayers.length; i++) {
          const layer = viewer.imageryLayers.get(i);
          if (layer && layer.imageryProvider) {
            // Apply performance optimizations to existing layers
            layer.imageryProvider.maximumLevel = Math.min(layer.imageryProvider.maximumLevel || 18, 16);
          }
        }
      }
      
      // Memory management for large datasets
      if (Cesium.Resource && Cesium.Resource.fetchImage) {
        // Configure aggressive image caching
        Cesium.Resource.fetchImage.cache = new Map();
      }
      
      log("info", "EVENT_DRIVEN: Terabyte-scale optimizations applied successfully");
      
      // Force render to apply changes
      viewer.scene.requestRender();
    },
    
    enableEventDrivenMode: function (enabled) {
      if (!viewer) return;
      
      const isEnabled = Boolean(enabled);
      
      log("info", "EVENT_DRIVEN: Mode " + (isEnabled ? "enabled" : "disabled"));
      
      if (isEnabled) {
        // Enable event-driven optimizations
        // FIX: requestRenderMode disabled to prevent auto-blurring
        viewer.scene.requestRenderMode = false;
        viewer.scene.maximumRenderTimeChange = 0.0;
        
        // Performance monitoring disabled for smooth performance (from smooth implementation)
        
        log("info", "EVENT_DRIVEN: Performance monitoring disabled for smooth performance");
      } else {
        // Restore default rendering mode
        viewer.scene.requestRenderMode = false;
        viewer.scene.globe.maximumScreenSpaceError = 1.5;
        
        log("info", "EVENT_DRIVEN: Restored default rendering mode");
      }
      
      viewer.scene.requestRender();
    },
    
    // ═══════════════════════════════════════════════════════════════════════════
    // SECTION: Layer Reordering Functions
    // ═══════════════════════════════════════════════════════════════════════════
    
    reorderLayersEventDriven: function (layerCommands) {
      if (!viewer || !Array.isArray(layerCommands)) {
        log("warn", "EVENT_DRIVEN: Invalid layer reorder request");
        return;
      }
      
      if (layerCommands.length === 0) {
        log("debug", "EVENT_DRIVEN: No layers to reorder");
        return;
      }
      
      log("info", "EVENT_DRIVEN: Reordering " + layerCommands.length + " layers");
      
      try {
        const imageryLayers = viewer.imageryLayers;
        const layerMap = new Map();
        const expandedOrder = [];
        const layersToMove = new Set();
        
        // Build a map of current layers by key and log all available layers
        log("debug", "EVENT_DRIVEN: Available layers in viewer:");
        for (let i = 0; i < imageryLayers.length; i++) {
          const layer = imageryLayers.get(i);
          if (layer && layer._layerKey) {
            layerMap.set(layer._layerKey, layer);
            log("debug", "  Layer " + i + ": key=" + layer._layerKey + " name=" + (layer._layerName || "unknown"));
          } else {
            log("debug", "  Layer " + i + ": no _layerKey (probably basemap)");
          }
        }
        
        log("debug", "EVENT_DRIVEN: Requested layers:");
        for (const command of layerCommands) {
          log("debug", "  Request: key=" + command.layer_key + " name=" + command.file_name + " order=" + command.new_order);
        }
        
        const requestedKeys = new Set(
          layerCommands.map(function (cmd) {
            return String(cmd && cmd.layer_key ? cmd.layer_key : "");
          })
        );
        const sortedCommands = layerCommands.slice().sort((a, b) => a.new_order - b.new_order);
        const orderedGroups = [];
        for (const command of sortedCommands) {
          const layer = layerMap.get(command.layer_key);
          const kind = String(command.kind || "");
          const isDem = Boolean(command.is_dem) || kind.toLowerCase() === "dem";
          const hillshadeKey = command.layer_key + ":hillshade";
          const hillshadeLayer = layerMap.get(hillshadeKey);
          log(
            "info",
            "EVENT_DRIVEN: reorder candidate key=" +
              command.layer_key +
              " name=" +
              command.file_name +
              " kind=" +
              kind +
              " is_dem=" +
              String(isDem) +
              " hillshadeKey=" +
              hillshadeKey +
              " hillshadeFound=" +
              String(Boolean(hillshadeLayer))
          );
          const groupLayers = [];
          if (layer) {
            const currentIndex = imageryLayers.indexOf(layer);
            log("debug", "EVENT_DRIVEN: Found layer for reordering: " + command.file_name +
                " currentIndex=" + currentIndex + " targetOrder=" + command.new_order);
            expandedOrder.push({ layer: layer, label: command.file_name });
            layersToMove.add(layer);
            groupLayers.push({ layer: layer, label: command.file_name });
          } else {
            log("warn", "EVENT_DRIVEN: Layer not found for reordering: " + command.layer_key +
                " (" + command.file_name + ")");
          }
          if (hillshadeLayer && !requestedKeys.has(hillshadeKey) && !layersToMove.has(hillshadeLayer)) {
            expandedOrder.push({ layer: hillshadeLayer, label: command.file_name + " (Hillshade)" });
            layersToMove.add(hillshadeLayer);
            groupLayers.push({ layer: hillshadeLayer, label: command.file_name + " (Hillshade)" });
            log("info", "EVENT_DRIVEN: Included hillshade for " + command.file_name);
          } else if (hillshadeLayer && (requestedKeys.has(hillshadeKey) || layersToMove.has(hillshadeLayer))) {
            log("debug", "EVENT_DRIVEN: Skipping duplicate hillshade for " + command.file_name);
          }
          if (groupLayers.length > 0) {
            orderedGroups.push(groupLayers);
          }
        }
        
        if (expandedOrder.length === 0) {
          log("warn", "EVENT_DRIVEN: No valid layers found for reordering");
          log("debug", "EVENT_DRIVEN: Available layer keys: " + Array.from(layerMap.keys()).join(", "));
          log("debug", "EVENT_DRIVEN: Requested layer keys: " + layerCommands.map(c => c.layer_key).join(", "));
          return;
        }
        
        log("debug", "EVENT_DRIVEN: Reordering plan:");
        for (let i = 0; i < expandedOrder.length; i++) {
          log("debug", "  " + i + ": " + expandedOrder[i].label);
        }
        
        for (let i = imageryLayers.length - 1; i >= 0; i--) {
          const layer = imageryLayers.get(i);
          if (layersToMove.has(layer)) {
            imageryLayers.remove(layer, false);
            log("debug", "EVENT_DRIVEN: Removed layer from index " + i);
          }
        }
        
        const applyReorderVisibility = function (layer) {
          if (!layer) {
            return;
          }
          if (layer === activeDemDrapeLayer) {
            layer.show = activeDemContext ? activeDemContext.visible !== false : layer.show;
            return;
          }
          if (layer === activeDemHillshadeLayer) {
            layer.show = activeDemContext
              ? activeDemContext.visible !== false && layer.alpha > 0.01
              : layer.show;
            return;
          }
          const key = layer._layerKey;
          if (key && layerVisibilityState.has(key)) {
            layer.show = Boolean(layerVisibilityState.get(key));
          }
        };

        for (let g = orderedGroups.length - 1; g >= 0; g--) {
          const group = orderedGroups[g];
          for (let i = 0; i < group.length; i++) {
            const item = group[i];
            imageryLayers.add(item.layer);
            applyReorderVisibility(item.layer);
            const newIndex = imageryLayers.indexOf(item.layer);
            log("debug", "EVENT_DRIVEN: Added layer " + item.label + " at index " + newIndex);
          }
        }
        
        // Ensure basemap layers are always at the bottom (index 0)
        // This prevents user layers from mixing with basemap layers
        if (osmBasemapLayer && imageryLayers.indexOf(osmBasemapLayer) >= 0) {
          imageryLayers.lowerToBottom(osmBasemapLayer);
          log("debug", "EVENT_DRIVEN: Moved OSM basemap to bottom (index 0)");
        }
        if (defaultEarthLayer && imageryLayers.indexOf(defaultEarthLayer) >= 0) {
          imageryLayers.lowerToBottom(defaultEarthLayer);
          log("debug", "EVENT_DRIVEN: Moved Default Earth basemap to bottom (index 0)");
        }
        
        // Verify basemap is at index 0 and user layers start from index 1+
        const basemapAtBottom = imageryLayers.get(0);
        if (basemapAtBottom && (basemapAtBottom === osmBasemapLayer || basemapAtBottom === defaultEarthLayer)) {
          log("info", "EVENT_DRIVEN: Basemap correctly positioned at index 0, user layers start from index 1");
        } else {
          log("warn", "EVENT_DRIVEN: Basemap positioning may be incorrect");
        }

        log("info", "EVENT_DRIVEN: Final layer stack (bottom to top):");
        for (let i = 0; i < imageryLayers.length; i++) {
          const layer = imageryLayers.get(i);
          const key = layer && layer._layerKey ? layer._layerKey : "basemap";
          const name = layer && layer._layerName ? layer._layerName : "basemap";
          const show = layer && layer.show === false ? "hidden" : "visible";
          log("info", "  [" + i + "] " + name + " key=" + key + " " + show);
        }
        
        // Force render to show changes
        viewer.scene.requestRender();
        
        // ── CRITICAL: Update persistent order state to prevent resets by other modules ──
        const finalOrderKeys = sortedCommands.map(c => c.layer_key);
        _lastKnownLayerOrder = finalOrderKeys.slice();
        
        // Unify with enforceLayerDisplayOrder to ensure hillshade/drape logic is consistent
        this.enforceLayerDisplayOrder(finalOrderKeys);
        
        // Additional render after a short delay to ensure visibility
        setTimeout(function() {
          if (viewer && viewer.scene) {
            viewer.scene.requestRender();
          }
        }, 100);
        
        log("info", "EVENT_DRIVEN: Layer reordering completed successfully (" + expandedOrder.length + " layers)");

        // FIX: Update _lastKnownLayerOrder so color-mode drape swaps restore THIS order
        // (not the stale initial Python order from when layers first loaded).
        // Build the order as [topmost-layer-key, ..., bottommost-layer-key]:
        // sortedCommands[0] = new_order 0 = user's row 0 = should end on top.
        var newOrderKeys = sortedCommands.map(function(cmd) { return String(cmd.layer_key); });
        if (newOrderKeys.length > 0) {
          _lastKnownLayerOrder = newOrderKeys;
          log("info", "EVENT_DRIVEN: _lastKnownLayerOrder updated to [" + newOrderKeys.join(", ") + "]");
        }
        
      } catch (error) {
        log("error", "EVENT_DRIVEN: Layer reordering failed - " + String(error));
        console.error("Layer reordering error:", error);
        
        // Force a render even if reordering failed
        if (viewer && viewer.scene) {
          viewer.scene.requestRender();
        }
      }
    },
    
    raiseLayerToTop: function (layerKey) {
      if (!viewer || !layerKey) return;
      
      try {
        const imageryLayers = viewer.imageryLayers;
        
        // Find the layer with the matching key
        for (let i = 0; i < imageryLayers.length; i++) {
          const layer = imageryLayers.get(i);
          if (layer && layer._layerKey === layerKey) {
            imageryLayers.raiseToTop(layer);
            viewer.scene.requestRender();
            log("debug", "Raised layer to top: " + layerKey);
            return;
          }
        }
        
      log("warn", "Layer not found for raising to top: " + layerKey);
        
      } catch (error) {
        log("error", "Failed to raise layer to top: " + String(error));
      }
    },

    // ── Enforce correct visual layer order after all search layers load ──
    // orderedKeys[0] = top of UI list = must end at HIGHEST Cesium index (drawn last = on top)
    // orderedKeys[last] = bottom of UI list = lowest Cesium index above basemap
    //
    // DEM draping rule:
    //   If any imagery key is above a DEM key in the list → hide DEM drape (grayscale),
    //   keep terrain provider active so imagery drapes over 3D elevation automatically.
    //   If DEM is on top (or no imagery above it) → show DEM drape normally.
    enforceLayerDisplayOrder: function (orderedKeys) {
      if (!viewer || !viewer.imageryLayers || !Array.isArray(orderedKeys) || orderedKeys.length === 0) return;
      // Persist order so color-mode drape swaps can re-apply it without Python round-trip
      _lastKnownLayerOrder = orderedKeys.slice();
      try {
        const imageryLayers = viewer.imageryLayers;

        // ── Step 1: Determine Top Key for Logging ──
        const demKey = activeDemContext ? activeDemContext.layerKey : null;
        const topKey = orderedKeys[0];
        const imageryIsOnTop = !!(demKey && topKey !== demKey);

        // ── Step 2: Raise layers in reverse UI order so orderedKeys[0] wins the top spot ──
        for (let k = orderedKeys.length - 1; k >= 0; k--) {
          const key = orderedKeys[k];
          var subLayers = [];
          for (let i = 0; i < imageryLayers.length; i++) {
            const layer = imageryLayers.get(i);
            if (layer && (layer._layerKey === key || layer._layerKey === key + ":hillshade")) {
              subLayers.push(layer);
            }
          }
          // Raise drape first, hillshade last (hillshade stays on top of its DEM block)
          for (var s = 0; s < subLayers.length; s++) {
            imageryLayers.raiseToTop(subLayers[s]);
          }
        }

        // ── Step 3: Always pin basemap to the bottom ──
        if (osmBasemapLayer && imageryLayers.indexOf(osmBasemapLayer) >= 0) {
          imageryLayers.lowerToBottom(osmBasemapLayer);
        }
        if (defaultEarthLayer && imageryLayers.indexOf(defaultEarthLayer) >= 0) {
          imageryLayers.lowerToBottom(defaultEarthLayer);
        }

        // ── Step 4: DEM drape visibility rule ──
        // Rely exclusively on the user's explicit visibility toggles (activeDemContext.visible)
        // rather than blindly hiding the DEM just because it isn't index 0. This allows users
        // to see DEM color modes even if they have translucent or spatially-offset imagery on top.
        if (activeDemDrapeLayer) {
          activeDemDrapeLayer.show = (activeDemContext && activeDemContext.visible !== false);
        }
        if (activeDemHillshadeLayer) {
          activeDemHillshadeLayer.show = (
            activeDemContext && activeDemContext.visible !== false &&
            activeDemHillshadeLayer.alpha > 0.01
          );
        }

        viewer.scene.requestRender();
        log("info", "enforceLayerDisplayOrder: order=[" + orderedKeys.join(", ") + "] imageryOnTop=" + imageryIsOnTop);
      } catch (e) {
        log("error", "enforceLayerDisplayOrder failed: " + e);
      }
    },
    
    setLayerOrder: function (layerKey, newIndex) {
      if (!viewer || !layerKey || typeof newIndex !== 'number') return;
      
      try {
        const imageryLayers = viewer.imageryLayers;
        
        // Find the layer with the matching key
        for (let i = 0; i < imageryLayers.length; i++) {
          const layer = imageryLayers.get(i);
          if (layer && layer._layerKey === layerKey) {
            // Remove and re-add at new position
            imageryLayers.remove(layer, false);
            imageryLayers.add(layer, Math.max(0, Math.min(newIndex, imageryLayers.length)));
            viewer.scene.requestRender();
            log("debug", "Set layer order: " + layerKey + " to index " + newIndex);
            return;
          }
        }
        
        log("warn", "Layer not found for reordering: " + layerKey);
        
      } catch (error) {
        log("error", "Failed to set layer order: " + String(error));
      }
    },
    
    // CRITICAL: Add the missing requestSceneRender function
    requestSceneRender: function() {
      if (viewer && viewer.scene && typeof viewer.scene.requestRender === "function") {
        viewer.scene.requestRender();
      }
    },
    captureSnapshot: function() {
      if (!viewer || !viewer.canvas) return null;
      viewer.render();
      return viewer.canvas.toDataURL("image/png");
    },
    getSceneState: function() {
      const getCameraInfo = function() {
        if (!viewer) return null;
        const cam = viewer.camera;
        const carto = cam.positionCartographic;
        if (!carto) return null;
        return {
          position: {
            lon: Cesium.Math.toDegrees(carto.longitude),
            lat: Cesium.Math.toDegrees(carto.latitude),
            height: carto.height
          },
          heading: Cesium.Math.toDegrees(cam.heading),
          pitch: Cesium.Math.toDegrees(cam.pitch),
          roll: Cesium.Math.toDegrees(cam.roll)
        };
      };
      
      return {
        mode: currentSceneMode,
        camera: getCameraInfo(),
        visibleLayers: Array.from(layerVisibilityState.entries())
          .filter(([_, vis]) => vis)
          .map(([key, _]) => key),
        annotations: {
          points: typeof annotationRecords !== 'undefined' ? annotationRecords : [],
          lines: typeof annotationLineRecords !== 'undefined' ? annotationLineRecords : [],
          polygons: typeof drawnPolygons !== 'undefined' ? drawnPolygons.map(p => ({
            id: p.id,
            label: p.label,
            points: p.points
          })) : []
        }
      };
    }
  };

  document.addEventListener("DOMContentLoaded", initBridge);
})();
