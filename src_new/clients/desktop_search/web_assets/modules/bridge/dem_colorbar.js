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
