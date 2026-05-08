/**
 * Layers.js - Manages Imagery, DEMs, and Basemaps for the Distributed GIS
 */

window.OfflineGISLayers = (function() {
    const Core = window.OfflineGIS;
    
    function addImageryLayer(url, options = {}) {
        const viewer = Core.getViewer();
        const layer = viewer.imageryLayers.addImageryProvider(
            new Cesium.UrlTemplateImageryProvider({
                url: url,
                maximumLevel: options.maxLevel || 14,
                credit: options.credit || ""
            })
        );
        
        if (options.id) {
            Core.state.managedImageryLayers.set(options.id, layer);
        }
        return layer;
    }

    function toggleBasemap(visible) {
        const viewer = Core.getViewer();
        Core.state.currentBasemapVisibility = visible;
        
        // Example: Toggle OSM layer visibility
        const osmLayer = Core.state.managedImageryLayers.get("osm");
        if (osmLayer) {
            osmLayer.show = visible;
        }
    }

    function setLayerOpacity(id, opacity) {
        const layer = Core.state.managedImageryLayers.get(id);
        if (layer) {
            layer.alpha = opacity;
        }
    }

    return {
        addImageryLayer: addImageryLayer,
        toggleBasemap: toggleBasemap,
        setLayerOpacity: setLayerOpacity
    };
})();
