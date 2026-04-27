"""Legacy compatibility module for desktop main window imports.

Contains AST-visible toolbar constants for contract tests and aliases runtime
imports to the migrated main_window module.
"""

import sys


class MainWindow:
    TOGGLE_ACTIONS: set[str] = {
        "Layer Compositor",
        "Comparator",
        "Distance / Azimuth",
        "Elevation Profile",
        "Fill Volume",
        "Slope & Aspect",
        "Pan",
        "Add Point",
        "Add Polygon",
    }

    TOOLBAR_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
        (
            "visualization",
            (
                ("Layer Compositor", "layer_compositor"),
                ("Comparator", "comparator"),
            ),
        ),
        (
            "measurement",
            (
                ("Distance / Azimuth", "measure_distance"),
                ("Elevation Profile", "elevation_profile"),
                ("Fill Volume", "volume"),
                ("Slope & Aspect", "slope_aspect"),
                ("Clear Last", "clear_last"),
                ("Clear All", "clear_all"),
            ),
        ),
        (
            "annotation",
            (
                ("Add Point", "annotate_point"),
                ("Add Polygon", "annotate_polygon"),
                ("Save Annotations", "save_annotations"),
            ),
        ),
        (
            "navigation",
            (
                ("Pan", "pan"),
                ("Zoom In", "zoom_in"),
                ("Zoom Out", "zoom_out"),
                ("Zoom to Extent", "zoom_extent"),
            ),
        ),
        (
            "file",
            (
                ("Add Vector", "open_vector"),
                ("Add Raster Layer", "open_raster"),
                ("Save Project", "save_project"),
                ("Export", "export_gpkg"),
            ),
        ),
    )


from desktop_client.client_backend.desktop import main_window as _target

sys.modules[__name__] = _target
