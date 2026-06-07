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
