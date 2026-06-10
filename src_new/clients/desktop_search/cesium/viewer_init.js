/**
 * viewer_init.js
 * 
 * Cesium Viewer Initialization and Offline Configuration
 * 
 * This module handles:
 * - Cesium.Viewer instantiation with air-gapped configuration
 * - Disabling all external network requests (Cesium Ion, Bing Maps, terrain providers)
 * - WebGL context loss recovery for long-running desktop applications
 * - GPU detection and adaptive performance tuning (NVIDIA vs Intel)
 * - Critical patches for local file:// protocol compatibility
 * 
 * Requirements: 3.3, 3.5, 3.6, 8.3, 8.4, 16.3
 */

/**
 * Initialize Cesium Viewer with offline air-gapped configuration
 * 
 * @param {string} containerId - DOM element ID for Cesium container
 * @param {Object} options - Configuration options
 * @param {Function} options.log - Logging function
 * @param {Function} options.setStatus - Status update function
 * @returns {Cesium.Viewer|null} Initialized viewer or null on failure
 */
export function initializeViewer(containerId, options = {}) {
  const { log, setStatus } = options;
  
  if (!window.Cesium) {
    if (setStatus) {
      setStatus("Cesium.js not found. Add local Cesium assets under web_assets/cesium.");
    }
    if (log) {
      log("error", "Cesium runtime not found");
    }
    return null;
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
            if (log) {
              log("warn", "JSON.parse failed for local file (" + reqUrl + "): " + e.message);
            }
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
    if (log) {
      log("info", "Cesium.Resource.fetchJson patched for local file compatibility.");
    }
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
    if (log) {
      log("info", "Bypassed approximateTerrainHeights.json fetch to prevent clampToGround crashes.");
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // AIR-GAP COMPLIANCE: Disable all external network requests
  // ─────────────────────────────────────────────────────────────────────────
  // Disable Cesium Ion (cloud-based asset streaming)
  if (Cesium.Ion) {
    Cesium.Ion.defaultAccessToken = '';
  }
  
  // Create viewer with all external providers disabled
  const viewer = new Cesium.Viewer(containerId, {
    imageryProvider: false,  // No basemap - bare globe only (air-gap compliance)
    baseLayerPicker: false,  // Disable basemap picker (prevents Bing Maps, Cesium Ion requests)
    geocoder: false,         // Disable geocoder (prevents external API calls)
    navigationHelpButton: false,
    sceneModePicker: false,
    homeButton: false,
    fullscreenButton: false,
    infoBox: false,
    selectionIndicator: false,
    scene3DOnly: false,
    requestRenderMode: true,  // Globally enabled to reduce CPU/GPU overhead
    maximumRenderTimeChange: 0.0,  // Let smooth interaction manager control render timing
    timeline: false,
    animation: false,
    terrainProvider: new Cesium.EllipsoidTerrainProvider(),  // Local ellipsoid terrain (no external requests)
    orderIndependentTranslucency: false,
    contextOptions: {
      webgl: {
        alpha: false,
        depth: true,
        stencil: false,
        antialias: true,  // Enable antialiasing for high-quality visuals
        powerPreference: "high-performance",  // Use discrete GPU (NVIDIA) if available
        preserveDrawingBuffer: true,
        failIfMajorPerformanceCaveat: false,
        desynchronized: false,
      },
    },
    msaaSamples: 4,  // Enable MSAA for smooth edges
    useBrowserRecommendedResolution: false,
  });

  // GPU-accelerated rendering optimizations
  viewer.resolutionScale = 1.0;  // Full resolution for sharp rendering
  viewer.scene.postProcessStages.fxaa.enabled = true;  // Enable FXAA for high quality
  viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#2a3a4a");
  viewer.scene.backgroundColor = Cesium.Color.fromCssColorString("#0a0a0a");
  viewer.canvas.style.backgroundColor = "#0a0a0a";
  
  // Performance optimizations for ultra-smooth interaction
  viewer.useDefaultRenderLoop = true;
  viewer.scene.requestRenderMode = true; // Use requestRenderMode for performance
  viewer.scene.maximumRenderTimeChange = 0.0;
  viewer.scene.globe.maximumScreenSpaceError = 2.0; // Balanced high-quality terrain
  viewer.scene.globe.tileCacheSize = 800;  // Optimized cache for ultra-smooth panning
  viewer.scene.fog.enabled = false;  // Disable fog for performance
  viewer.scene.skyAtmosphere.show = false;  // Disable atmosphere for performance (air-gap compliance)
  viewer.scene.sun.show = false;  // Disable sun for performance
  viewer.scene.moon.show = false;  // Disable moon for performance
  viewer.scene.skyBox.show = false;  // Disable skybox for performance
  viewer.scene.globe.showGroundAtmosphere = false;  // Disable ground atmosphere
  viewer.scene.globe.enableLighting = false;  // Disable lighting for performance
  viewer.scene.globe.depthTestAgainstTerrain = true;  // Required for proper DEM layer sorting
  
  // Optimize tile loading for smoother experience
  viewer.scene.globe.preloadAncestors = true;  // Preload for smoother zooming
  viewer.scene.globe.preloadSiblings = true;  // Preload for smoother panning
  
  // Additional performance optimizations
  viewer.scene.fxaa = false;  // Disable FXAA post-processing
  viewer.scene.highDynamicRange = false;  // Disable HDR for performance
  viewer.scene.logarithmicDepthBuffer = false;  // Disabled to prevent GroundPolyline culling at high zoom levels
  viewer.scene.globe.showWaterEffect = false;  // Disable water effect
  viewer.scene.globe.showSkirts = true;  // Keep skirts to avoid gaps between tiles
  
  // Optimize rendering pipeline
  viewer.scene.pickTranslucentDepth = false;  // Disable translucent depth picking
  viewer.scene.useDepthPicking = false;  // Disable depth picking for performance
  
  if (log) {
    log("info", "Viewer initialized with GPU acceleration and ultra-smooth interaction settings");
  }
  
  // ═══════════════════════════════════════════════════════════════════════════
  // CRITICAL: GPU Detection for Intel vs NVIDIA performance tuning
  // ═══════════════════════════════════════════════════════════════════════════
  const gpuInfo = detectGPU(log);
  
  // Apply GPU-adaptive configuration
  applyGPUAdaptiveSettings(viewer, gpuInfo, log);
  
  // ═══════════════════════════════════════════════════════════════════════════
  // CRITICAL: WebGL Context Loss Recovery for Desktop Application
  // ═══════════════════════════════════════════════════════════════════════════
  setupContextLossRecovery(viewer, log, setStatus);
  
  // Set camera sensitivity for smooth performance
  viewer.camera.percentageChanged = 0.001;
  
  if (log) {
    log("info", "Cesium default camera controls enabled");
  }
  
  return viewer;
}

/**
 * Detect GPU renderer and determine if it's high-end (NVIDIA/AMD) or integrated (Intel)
 * 
 * @param {Function} log - Logging function
 * @returns {Object} GPU information { renderer: string, isHighEnd: boolean }
 */
function getGLRenderer() {
  try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    if (!gl) return null;
    const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
    if (!debugInfo) return null;
    return gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) || null;
  } catch (e) {
    return null;
  }
}

function checkHighEnd(r) {
  return r.includes("nvidia") || r.includes("rtx") || r.includes("gtx") ||
         r.includes("quadro") || (r.includes("amd") && r.includes("radeon rx")) ||
         r.includes("apple") || r.includes("m1") || r.includes("m2") ||
         r.includes("m3") || r.includes("m4") || r.includes("m5");
}

function checkEntryWorkstation(r) {
  if (!r.includes("quadro")) return false;
  const entryModels = [
    "quadro 1000",
    "quadro p1000",
    "quadro t1000",
    "quadro p620",
    "quadro p600",
    "quadro t600",
    "quadro t400",
    "quadro k620",
    "quadro k1200",
    "quadro m1200",
  ];
  return entryModels.some((model) => r.includes(model));
}

function detectGPU(log) {
  const gpuInfo = {
    renderer: "Unknown",
    isHighEnd: false,
    isEntryWorkstation: false
  };

  const renderer = getGLRenderer();
  if (renderer) {
    gpuInfo.renderer = renderer;
    const r = renderer.toLowerCase();
    gpuInfo.isHighEnd = checkHighEnd(r);
    gpuInfo.isEntryWorkstation = checkEntryWorkstation(r);
  }

  if (log) {
    const tier = gpuInfo.isEntryWorkstation ? "Entry Workstation" : (gpuInfo.isHighEnd ? "High-End" : "Integrated/Unknown");
    log("info", "GPU Detected: " + gpuInfo.renderer + " (" + tier + ")");
  }

  return gpuInfo;
}

/**
 * Apply GPU-adaptive viewer settings based on detected hardware
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {Object} gpuInfo - GPU information from detectGPU
 * @param {Function} log - Logging function
 */
function applyGPUAdaptiveSettings(viewer, gpuInfo, log) {
  // Shared: always disable expensive cosmetics
  viewer.scene.fog.enabled = false;
  viewer.scene.skyAtmosphere.show = false;
  viewer.scene.sun.show = false;
  viewer.scene.moon.show = false;
  viewer.scene.globe.enableLighting = false;
  viewer.scene.globe.showGroundAtmosphere = false;
  
  if (gpuInfo.isEntryWorkstation) {
    // ── BALANCED WORKSTATION (Entry Quadro) ──────────────────────────────
    viewer.resolutionScale = 1.0;
    viewer.scene.logarithmicDepthBuffer = false;
    viewer.scene.globe.depthTestAgainstTerrain = true;
    viewer.scene.globe.tileCacheSize = 600;
    viewer.scene.globe.maximumScreenSpaceError = 0.8; // High resolution base map for AOI stage
    viewer.scene.globe.preloadAncestors = true;
    viewer.scene.globe.preloadSiblings = true;
    viewer.scene.globe.loadingDescendantLimit = 6;

    if (log) {
      log("info", "[INIT BALANCED GPU CONFIG] Entry Quadro detected — balanced fidelity with high resolution base map");
    }
  } else if (gpuInfo.isHighEnd) {
    // ── MAX CONFIG (NVIDIA / Quadro RTX / AMD RX / Apple Silicon) ────────
    viewer.resolutionScale = 1.0;          // Full native resolution
    viewer.scene.logarithmicDepthBuffer = false;
    viewer.scene.globe.depthTestAgainstTerrain = true;
    viewer.scene.globe.tileCacheSize = 2500; // Large cache to prevent reload thrashing
    viewer.scene.globe.maximumScreenSpaceError = 0.5; // Force double subdivision precision for seamless mesh edges
    viewer.scene.globe.preloadAncestors = true;
    viewer.scene.globe.preloadSiblings = true;
    viewer.scene.globe.loadingDescendantLimit = 16; // Load parallel subdivisions faster
    
    // WebGL pipeline optimizations
    Cesium.RequestScheduler.maximumRequestsPerServer = 24;
    Cesium.RequestScheduler.maximumRequests = 100;
    Cesium.TaskProcessor.LIMIT = 12;
    
    // NVIDIA GL hint
    if (viewer.scene.context && viewer.scene.context._gl) {
      const gl = viewer.scene.context._gl;
      gl.hint(gl.GENERATE_MIPMAP_HINT, gl.FASTEST);
    }
    
    if (log) {
      log("info", "[INIT MAX GPU CONFIG] NVIDIA/Apple workstation GPU detected — Extreme fidelity and high resolution base map enabled");
    }
  } else {
    // ── SAFE CONFIG (Intel integrated / unknown) ──────────────────────────
    viewer.resolutionScale = 1.0;          // Full native resolution to maintain imagery quality
    viewer.scene.logarithmicDepthBuffer = false;
    viewer.scene.globe.depthTestAgainstTerrain = true; // Essential for true 3D fidelity
    viewer.scene.globe.tileCacheSize = 400;  // Optimized cache for smoother panning on Windows
    viewer.scene.globe.maximumScreenSpaceError = 0.8;  // High resolution base map for AOI stage
    viewer.scene.globe.preloadAncestors = true; // Enabled for smoother zoom transitions
    viewer.scene.globe.preloadSiblings = true;
    viewer.scene.globe.loadingDescendantLimit = 4;  // Faster tile loading
    
    if (log) {
      log("info", "[INIT SAFE INTEL CONFIG] Integrated GPU optimized for smooth performance (res=1.0 sse=3.0 cache=400)");
    }
  }
}

/**
 * Setup WebGL context loss recovery for long-running desktop applications
 * 
 * @param {Cesium.Viewer} viewer - Cesium viewer instance
 * @param {Function} log - Logging function
 * @param {Function} setStatus - Status update function
 */
function setupContextLossRecovery(viewer, log, setStatus) {
  let contextLostCount = 0;
  const MAX_CONTEXT_RECOVERY_ATTEMPTS = 3;
  
  // Listen for WebGL context loss events
  if (viewer.canvas) {
    viewer.canvas.addEventListener('webglcontextlost', function(event) {
      event.preventDefault();  // Prevent default behavior
      contextLostCount++;
      
      if (log) {
        log("error", "WebGL context lost (attempt " + contextLostCount + "/" + MAX_CONTEXT_RECOVERY_ATTEMPTS + ") - GPU may have been powered down or driver crashed");
      }
      
      // Show user-friendly message
      if (setStatus) {
        setStatus("Graphics context lost - attempting recovery...");
      }
      
      if (contextLostCount >= MAX_CONTEXT_RECOVERY_ATTEMPTS) {
        if (setStatus) {
          setStatus("Graphics recovery failed - please restart the application");
        }
        if (log) {
          log("error", "Max context recovery attempts reached - manual restart required");
        }
      }
    }, false);
    
    viewer.canvas.addEventListener('webglcontextrestored', function() {
      if (log) {
        log("info", "WebGL context restored successfully");
      }
      if (setStatus) {
        setStatus("Graphics context recovered");
      }
      
      // Reset counter on successful recovery
      contextLostCount = 0;
    }, false);
  }
}

/**
 * Get default startup camera position (centered on India)
 * 
 * @returns {Object} Camera position { lon, lat, height, heading, pitch }
 */
export function getDefaultStartupPosition() {
  return {
    lon: 78.0,   // India center longitude
    lat: 22.0,   // India center latitude
    height: 6000000.0,  // ~6000 km — shows full India + surrounding region
    heading: 0.0,
    pitch: -89.0  // Near top-down view
  };
}
