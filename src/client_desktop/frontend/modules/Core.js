/**
 * Core.js - Shared state and Viewer initialization for the Distributed GIS
 */

window.OfflineGIS = (function() {
    let viewer = null;
    let bridge = null;
    
    const state = {
        activeImageryLayer: null,
        activeDemDrapeLayer: null,
        managedImageryLayers: new Map(),
        vectorLayerSources: new Map(),
        currentBasemapVisibility: false
    };

    function initViewer(containerId) {
        viewer = new Cesium.Viewer(containerId, {
            terrainProvider: new Cesium.EllipsoidTerrainProvider(),
            baseLayerPicker: false,
            animation: false,
            timeline: false,
            sceneModePicker: false,
            navigationHelpButton: false,
            homeButton: false
        });
        
        // Performance optimizations
        viewer.scene.debugShowFramesPerSecond = false;
        viewer.scene.requestRenderMode = true;
        
        return viewer;
    }

    return {
        initViewer: initViewer,
        getViewer: () => viewer,
        state: state,
        setBridge: (b) => { bridge = b; }
    };
})();
