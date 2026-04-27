"""Legacy compatibility module for desktop icon registry imports.

Contains AST-visible icon manifest for toolbar contract tests and aliases runtime
imports to the migrated icon_registry module.
"""

import sys


ICON_MANIFEST: dict[str, str] = {
    "layer_compositor": "mActionShowAllLayers.svg",
    "comparator": "mActionSplitFeatures.svg",
    "measure_distance": "mActionMeasure.svg",
    "elevation_profile": "mActionNewElevationProfile.svg",
    "volume": "mActionCalculateField.svg",
    "slope_aspect": "mActionMeasureAngle.svg",
    "clear_last": "mActionUndo.svg",
    "clear_all": "mActionDeleteSelected.svg",
    "annotate_point": "mActionCapturePoint.svg",
    "annotate_polygon": "mActionCapturePolygon.svg",
    "save_annotations": "mActionSharingExport.svg",
    "pan": "mActionPan.svg",
    "zoom_in": "mActionZoomIn.svg",
    "zoom_out": "mActionZoomOut.svg",
    "zoom_extent": "mActionZoomFullExtent.svg",
    "open_vector": "mActionAddOgrLayer.svg",
    "open_raster": "mActionAddRasterLayer.svg",
    "save_project": "mActionFileSave.svg",
    "export_gpkg": "mActionSaveMapAsImage.svg",
}


from desktop_client.client_backend.desktop import icon_registry as _target

sys.modules[__name__] = _target
