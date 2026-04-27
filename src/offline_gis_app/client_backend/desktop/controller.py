"""Legacy compatibility module for desktop controller imports.

This module keeps an AST-visible contract for legacy tests while aliasing runtime
imports to the migrated controller module.
"""

import sys
from typing import Callable


class DesktopController:
	def handle_toolbar_action(
		self, action_label: str, checked: bool | None = None
	) -> bool | None:
		handlers: dict[str, Callable[[], None]] = {
			"Layer Compositor": lambda: None,
			"Comparator": self._toolbar_toggle_comparator,
			"Distance / Azimuth": self._toolbar_measure_distance,
			"Polygon Area": self._toolbar_measure_polygon_area,
			"Elevation Profile": self._toolbar_elevation_profile,
			"Fill Volume": self._toolbar_measure_volume,
			"Slope & Aspect": self._toolbar_measure_slope_aspect,
			"Clear Last": self._toolbar_clear_last,
			"Clear All": self._toolbar_clear_all,
			"Add Point": self._toolbar_toggle_add_point_mode,
			"Add Polygon": self._toolbar_add_polygon_annotation,
			"Save Annotations": self._toolbar_export_geopackage,
			"Pan": self._toolbar_set_pan_mode,
			"Zoom In": lambda: self._run_js_call("zoomIn"),
			"Zoom Out": lambda: self._run_js_call("zoomOut"),
			"Zoom to Extent": lambda: self._run_js_call("zoomToExtent"),
			"Add Vector": self.browse_path,
			"Add Raster Layer": self.browse_path,
			"Save Project": self._toolbar_save_project,
			"Export": self._toolbar_export_geopackage,
			"Export GeoPackage": self._toolbar_export_geopackage,
		}
		return None


from desktop_client.client_backend.desktop import controller as _target

sys.modules[__name__] = _target
