from __future__ import annotations

from typing import Callable


class SignalCoordinator:
    """Encapsulate all signal/slot connections for the desktop controller."""

    def __init__(self, controller):
        self._controller = controller

    def connect_all_signals(self) -> None:
        """Connect all UI signals to controller methods."""
        c = self._controller

        # File selection buttons
        self._connect_button(
            c.panel.browse_files_btn.clicked, "Browse Files", c.browse_files
        )
        self._connect_button(
            c.panel.clear_selection_btn.clicked,
            "Clear Selection",
            c.clear_file_selection,
        )
        self._connect_button(
            c.panel.ingest_btn.clicked, "Ingest Files", c.enqueue_selected_files
        )

        # Asset management
        self._connect_button(
            c.panel.refresh_assets_btn.clicked, "Refresh Assets", c.refresh_assets
        )
        # add_layer_btn was removed; no connection needed

        # Asset deletion
        c.panel.asset_delete_requested.connect(c.delete_asset)

        # Display controls
        c.panel.brightness_slider.valueChanged.connect(
            c._on_visual_slider_changed
        )
        c.panel.contrast_slider.valueChanged.connect(c._on_visual_slider_changed)
        c.panel.stretch_mode_combo.currentIndexChanged.connect(
            c._on_stretch_mode_changed
        )
        if hasattr(c.panel, "dem_stretch_mode_combo"):
            c.panel.dem_stretch_mode_combo.currentIndexChanged.connect(
                c._on_dem_stretch_mode_changed
            )
        c.panel.dem_hillshade_slider.valueChanged.connect(
            c._on_dem_slider_changed
        )
        c.panel.dem_color_mode_combo.currentIndexChanged.connect(
            c._on_dem_color_mode_changed
        )
        self._connect_button(
            c.panel.apply_rgb_view_mode_btn.clicked,
            "Apply RGB View Mode",
            c.apply_rgb_view_mode,
        )
        self._connect_button(
            c.panel.rotate_left_btn.clicked,
            "Rotate Left",
            lambda: c.rotate_camera(-10.0),
        )
        self._connect_button(
            c.panel.rotate_right_btn.clicked,
            "Rotate Right",
            lambda: c.rotate_camera(10.0),
        )
        c.panel.pitch_slider.valueChanged.connect(c.set_pitch)
        self._connect_button(
            c.panel.search_point_btn.clicked,
            "Search by Coordinate",
            c.search_assets_by_coordinate,
        )
        self._connect_button(
            c.panel.search_draw_polygon_btn.clicked,
            "Draw Search Polygon",
            lambda: c.set_search_draw_mode(
                c.panel.search_draw_mode if c.panel.search_draw_polygon_btn.isChecked() else "none"
            ),
        )
        c.panel.search_draw_mode_changed.connect(
            lambda mode: c.set_search_draw_mode(mode)
        )
        self._connect_button(
            c.panel.search_finish_polygon_btn.clicked,
            "Finish Search Polygon",
            c.finish_search_polygon,
        )
        self._connect_button(
            c.panel.search_clear_geometry_btn.clicked,
            "Clear Search Geometry",
            c.clear_search_geometry,
        )
        self._connect_button(
            c.panel.search_from_draw_btn.clicked,
            "Search from Drawn Geometry",
            c.search_assets_from_drawn_geometry,
        )
        c.panel.search_result_visibility_toggled.connect(
            c.toggle_search_result_visibility
        )
        c.panel.search_results_visibility_batch_toggled.connect(
            c.toggle_search_results_visibility_batch
        )
        c.panel.search_layers_reordered.connect(c.reorder_search_result_layers)
        c.panel.asset_focus_requested.connect(c._toolbar_zoom_to_asset)
        c.panel.vector_layer_visibility_toggled.connect(
            c.set_vector_layer_visibility
        )
        c.panel.vector_layer_delete_requested.connect(c.remove_vector_layer)
        c.bridge.mapClicked.connect(c.on_map_click)
        c.bridge.measurementUpdated.connect(c.on_measurement)
        c.bridge.jsLogReceived.connect(c.on_js_log)
        c.bridge.searchGeometryChanged.connect(c.on_search_geometry)
        c.bridge.comparatorPaneStateChanged.connect(c.on_comparator_pane_state)
        c.bridge.searchResultVisibilityToggled.connect(
            c.toggle_search_result_visibility
        )
        c.bridge.annotationsSynced.connect(c.on_annotations_sync)
        c.panel.uploaded_assets_list.itemSelectionChanged.connect(
            c.preview_selected_uploaded_asset
        )
        c.panel.measurement_result_clear_selected_requested.connect(
            c.clear_selected_measurement_result
        )
        c.panel.measurement_result_clear_all_requested.connect(
            c.clear_all_measurement_results
        )
        c.panel.uploaded_assets_refresh_requested.connect(c._clear_asset_caches)
        c.panel.search_layer_delete_requested.connect(c.remove_search_layer)
        if hasattr(c.panel, "aoi_visibility_changed"):
            c.panel.aoi_visibility_changed.connect(
                lambda visible: c._set_search_aoi_visible(visible)
            )

    def _connect_button(
        self, signal, label: str, callback: Callable[..., object]
    ) -> None:
        """Connect a button signal with error handling."""
        c = self._controller
        signal.connect(
            lambda *args, _label=label, _callback=callback: c._on_button_invoked(
                _label,
                _callback,
                *args,
            )
        )


__all__ = ["SignalCoordinator"]
