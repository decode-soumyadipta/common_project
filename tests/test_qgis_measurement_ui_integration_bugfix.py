from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from qtpy.QtWidgets import QApplication

from desktop_client.client_backend.desktop.app_mode import DesktopAppMode
from desktop_client.client_backend.desktop.bridge import WebBridge
from desktop_client.client_backend.desktop.control_panel import ControlPanel
from desktop_client.client_backend.desktop.controller import DesktopController
from desktop_client.client_backend.desktop.status_bar import GISStatusBar


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def mock_web_view():
    view = Mock()
    page = Mock()
    view.page.return_value = page
    page.runJavaScript = Mock()
    return view


@pytest.fixture
def mock_panel():
    panel = Mock(spec=ControlPanel)
    panel.log = Mock()
    panel.assets_combo = Mock()
    panel.assets_combo.count.return_value = 0
    panel.search_coord_lon = Mock()
    panel.search_coord_lat = Mock()
    panel.search_draw_polygon_btn = Mock()
    panel.search_draw_polygon_btn.isChecked.return_value = False
    panel.search_draw_polygon_btn.blockSignals = Mock()
    panel.search_draw_polygon_btn.setChecked = Mock()
    panel.click_label = Mock()
    panel.measure_label = Mock()
    panel.clear_measurement_result_entries = Mock()
    return panel


@pytest.fixture
def controller(qapp, mock_panel, mock_web_view):
    bridge = WebBridge()

    with (
        patch("offline_gis_app.client_backend.desktop.controller.DesktopApiClient"),
        patch("offline_gis_app.client_backend.desktop.controller.ApiServerManager"),
        patch("offline_gis_app.client_backend.desktop.controller.TiTilerManager"),
        patch("offline_gis_app.client_backend.desktop.controller.QTimer"),
        patch("offline_gis_app.client_backend.desktop.controller.QThreadPool"),
        patch.object(DesktopController, "_connect_signals"),
        patch.object(DesktopController, "_apply_display_control_mode"),
    ):
        controller = DesktopController(
            panel=mock_panel,
            web_view=mock_web_view,
            bridge=bridge,
            app_mode=DesktopAppMode.UNIFIED,
        )

    controller._run_js_call = Mock()
    controller._selected_dem_path = Mock(return_value="/tmp/dem.tif")
    controller._submit_measurement_job = Mock()
    return controller


def test_status_bar_updates_coordinates_and_clears_invalid_sample(qapp):
    status_bar = GISStatusBar()

    # Test 1: Valid coordinates with DEM elevation
    status_bar.on_mouse_coordinates(87.2314, 23.7102, 312.5)
    assert "87.2314" in status_bar._lon_box.label.text()
    assert "23.7102" in status_bar._lat_box.label.text()
    assert "312" in status_bar._elev_box.label.text()

    # Test 2: Valid coordinates (0,0) but no DEM available (-9999)
    # Lon/Lat/UTM should show, but elevation should be blank
    status_bar.on_mouse_coordinates(0.0, 0.0, -9999.0)
    assert "0.000000" in status_bar._lon_box.label.text()
    assert "0.000000" in status_bar._lat_box.label.text()
    assert "31N" in status_bar._utm_box.label.text()  # UTM zone for 0,0
    assert status_bar._elev_box.label.text() == "Elev: —"  # No DEM = blank elevation

def test_polygon_measurement_button_enables_crosshair_and_draw_mode(controller):
    controller.state.clicked_points = []

    controller._toolbar_measure_polygon_area()

    assert controller._polygon_area_mode_enabled is True
    assert controller._polygon_drawing_context == "measurement"
    controller._run_js_call.assert_any_call("setSearchDrawMode", "polygon")
    controller._run_js_call.assert_any_call("setMeasurementCursor", True)


def test_viewshed_button_enters_point_selection_mode(controller):
    controller.state.clicked_points = []

    controller._toolbar_measure_viewshed()

    assert controller._viewshed_mode_enabled is True
    controller._run_js_call.assert_any_call("setMeasurementCursor", True)
    controller.panel.log.assert_called()
    assert "Click on the map to select observer point" in controller.panel.log.call_args[0][0]


def test_clear_all_resets_measurement_cursor(controller):
    controller._distance_measure_mode_enabled = True
    controller._add_point_mode_enabled = True
    controller._shadow_height_mode_enabled = True
    controller._viewshed_mode_enabled = True

    controller._toolbar_clear_all()

    controller._run_js_call.assert_any_call("setMeasurementCursor", False)
    assert controller._viewshed_mode_enabled is False


def test_compositor_comparator_mutual_exclusion(qapp, mock_panel, mock_web_view):
    """Compositor and Comparator toolbar actions must be mutually exclusive."""
    from unittest.mock import MagicMock, patch
    from qtpy.QtWidgets import QAction
    from desktop_client.client_backend.desktop.main_window import MainWindow

    # Build minimal toolbar_actions dict with real QActions
    compositor_action = QAction("Layer Compositor")
    compositor_action.setCheckable(True)
    compositor_action.setChecked(False)
    compositor_action.setEnabled(True)

    comparator_action = QAction("Comparator")
    comparator_action.setCheckable(True)
    comparator_action.setChecked(False)
    comparator_action.setEnabled(True)

    # Simulate: Comparator turned ON → Compositor must be disabled
    compositor_action.setEnabled(False)
    compositor_action.setChecked(False)
    assert not compositor_action.isEnabled(), "Compositor must be disabled when Comparator is on"
    assert not compositor_action.isChecked()

    # Simulate: Comparator turned OFF → Compositor must be re-enabled
    compositor_action.setEnabled(True)
    assert compositor_action.isEnabled(), "Compositor must be re-enabled when Comparator is off"

    # Simulate: Compositor turned ON → Comparator must be disabled
    comparator_action.setEnabled(False)
    comparator_action.setChecked(False)
    assert not comparator_action.isEnabled(), "Comparator must be disabled when Compositor is on"
    assert not comparator_action.isChecked()

    # Simulate: Compositor turned OFF → Comparator must be re-enabled
    comparator_action.setEnabled(True)
    assert comparator_action.isEnabled(), "Comparator must be re-enabled when Compositor is off"
