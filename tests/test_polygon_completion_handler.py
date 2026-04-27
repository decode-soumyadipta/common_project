"""Test for Task 3.7: Polygon completion handler for measurement context."""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from qtpy.QtWidgets import QApplication

from desktop_client.client_backend.desktop.app_mode import DesktopAppMode
from desktop_client.client_backend.desktop.bridge import WebBridge
from desktop_client.client_backend.desktop.control_panel import ControlPanel
from desktop_client.client_backend.desktop.controller import DesktopController


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
    # QComboBox used by _toolbar_measure_slope_aspect to read/set DEM colour mode
    panel.dem_color_mode_combo = Mock()
    panel.dem_color_mode_combo.currentData.return_value = "gray"
    panel.dem_color_mode_combo.findData.return_value = -1
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


def test_finish_polygon_triggers_polygon_area_measurement(controller):
    """Test that finishing polygon in measurement context triggers polygon area calculation."""
    # Setup: Enable polygon area mode
    controller._polygon_drawing_context = "measurement"
    controller._polygon_area_mode_enabled = True
    controller._volume_mode_enabled = False
    controller._slope_aspect_mode_enabled = False
    
    # Mock the measurement method
    controller._toolbar_measure_polygon_area = Mock()
    
    # Act: Finish the polygon
    controller.finish_search_polygon()
    
    # Assert: Polygon area measurement was triggered
    controller._toolbar_measure_polygon_area.assert_called_once()
    assert controller._polygon_drawing_context == "none"


def test_finish_polygon_triggers_volume_measurement(controller):
    """Test that finishing polygon in measurement context triggers volume calculation."""
    # Setup: Enable volume mode
    controller._polygon_drawing_context = "measurement"
    controller._polygon_area_mode_enabled = False
    controller._volume_mode_enabled = True
    controller._slope_aspect_mode_enabled = False
    
    # Mock the measurement method
    controller._toolbar_measure_volume = Mock()
    
    # Act: Finish the polygon
    controller.finish_search_polygon()
    
    # Assert: Volume measurement was triggered
    controller._toolbar_measure_volume.assert_called_once()
    assert controller._polygon_drawing_context == "none"


def test_finish_polygon_triggers_slope_aspect_measurement(controller):
    """Test that finishing polygon in measurement context triggers slope/aspect calculation."""
    # Setup: Enable slope/aspect mode
    controller._polygon_drawing_context = "measurement"
    controller._polygon_area_mode_enabled = False
    controller._volume_mode_enabled = False
    controller._slope_aspect_mode_enabled = True
    
    # Mock the measurement method
    controller._toolbar_measure_slope_aspect = Mock()
    
    # Act: Finish the polygon
    controller.finish_search_polygon()
    
    # Assert: Slope/aspect measurement was triggered
    controller._toolbar_measure_slope_aspect.assert_called_once()
    assert controller._polygon_drawing_context == "none"


def test_finish_polygon_does_not_trigger_measurement_for_search_context(controller):
    """Test that finishing polygon in search context does NOT trigger measurement."""
    # Setup: Set search context (not measurement)
    controller._polygon_drawing_context = "search"
    controller._polygon_area_mode_enabled = True
    
    # Mock the measurement method
    controller._toolbar_measure_polygon_area = Mock()
    
    # Act: Finish the polygon
    controller.finish_search_polygon()
    
    # Assert: Measurement was NOT triggered
    controller._toolbar_measure_polygon_area.assert_not_called()
    # Context should remain "search" (not reset to "none")
    assert controller._polygon_drawing_context == "search"


def test_handle_toolbar_action_routes_slope_aspect_toggle_state(controller):
    """Ensure toolbar checked state is forwarded to slope/aspect handler."""
    controller._toolbar_measure_slope_aspect = Mock(return_value=True)

    result = controller.handle_toolbar_action("Slope & Aspect", checked=True)

    controller._toolbar_measure_slope_aspect.assert_called_once_with(enabled=True)
    assert result is True


def test_toolbar_measure_slope_aspect_disable_clears_active_state(controller):
    """Disabling slope/aspect should clear interaction state and return unchecked."""
    controller._slope_aspect_mode_enabled = True
    controller._slope_aspect_computing = True
    controller._polygon_drawing_context = "measurement"

    result = controller._toolbar_measure_slope_aspect(enabled=False)

    assert result is False
    assert controller._slope_aspect_mode_enabled is False
    assert controller._slope_aspect_computing is False
    assert controller._polygon_drawing_context == "none"
    controller._run_js_call.assert_called_with("setSearchDrawMode", "none")


def test_toolbar_measure_slope_aspect_false_checked_activates_when_idle(controller):
    """A false checked signal should still activate slope/aspect when currently idle."""
    controller._slope_aspect_mode_enabled = False
    controller._slope_aspect_computing = False
    controller._current_polygon_lonlat = Mock(return_value=None)

    result = controller._toolbar_measure_slope_aspect(enabled=False)

    assert result is True
    assert controller._slope_aspect_mode_enabled is True
