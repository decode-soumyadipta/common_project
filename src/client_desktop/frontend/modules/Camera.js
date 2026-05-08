/**
 * Camera.js - Manages Camera Movement and View Synchronization
 */

window.OfflineGISCamera = (function() {
    const Core = window.OfflineGIS;

    function flyTo(lon, lat, height = 2000, heading = 0, pitch = -45) {
        const viewer = Core.getViewer();
        viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(lon, lat, height),
            orientation: {
                heading: Cesium.Math.toRadians(heading),
                pitch: Cesium.Math.toRadians(pitch),
                roll: 0.0
            },
            duration: 2.0
        });
    }

    function syncView(otherViewer) {
        // Implementation for split-screen synchronization
        const master = Core.getViewer();
        if (!master || !otherViewer) return;

        master.camera.changed.addEventListener(() => {
            otherViewer.camera.setView({
                destination: master.camera.position,
                orientation: {
                    heading: master.camera.heading,
                    pitch: master.camera.pitch,
                    roll: master.camera.roll
                }
            });
        });
    }

    return {
        flyTo: flyTo,
        syncView: syncView
    };
})();
