from unittest.mock import MagicMock

from src_new.clients.desktop_search.coordinators.search_results_coordinator import (
    SearchResultsCoordinator,
)


def test_search_results_coordinator_populates_tile_url():
    # Arrange
    mock_controller = MagicMock()
    mock_controller._asset_path_accessible_locally.return_value = True
    mock_controller._find_best_file_version.side_effect = lambda path: path
    mock_controller.api.titiler_base_url = "http://127.0.0.1:8002"
    mock_controller._search_result_assets_by_path = {}
    mock_controller._search_layer_visibility = {}
    mock_controller._user_added_assets = {}
    mock_controller._asset_cache = {}
    mock_controller._is_dem_asset.return_value = False

    coordinator = SearchResultsCoordinator(mock_controller)

    # Asset with NO tile_url
    assets = [
        {
            "file_name": "coal_13.tif",
            "file_path": "/Users/soumyadiptadey/Developer/common_project/uploads/coal_13.tif",
            "kind": "geotiff",
            "crs": "EPSG:4326",
        }
    ]

    # Act
    coordinator.apply_search_results_event_driven(assets, label="Test Search")

    # Assert Verify search result assets by path has been populated
    result_path = "/Users/soumyadiptadey/Developer/common_project/uploads/coal_13.tif"
    assert result_path in mock_controller._search_result_assets_by_path
    
    asset_result = mock_controller._search_result_assets_by_path[result_path]
    # Check that tile_url has been populated dynamically!
    assert "tile_url" in asset_result
    assert asset_result["tile_url"].startswith("http://127.0.0.1:8002/titiler/cog/tiles/WebMercatorQuad/")
    assert "url=file:///" in asset_result["tile_url"]


def test_search_results_coordinator_initializes_hidden_by_default():
    mock_controller = MagicMock()
    mock_controller._asset_path_accessible_locally.return_value = True
    mock_controller._find_best_file_version.side_effect = lambda path: path
    mock_controller.api.titiler_base_url = "http://127.0.0.1:8002"
    mock_controller._search_result_assets_by_path = {}
    mock_controller._search_layer_visibility = {}
    mock_controller._user_added_assets = {}
    mock_controller._asset_cache = {}
    mock_controller._is_dem_asset.return_value = False

    coordinator = SearchResultsCoordinator(mock_controller)

    assets = [
        {
            "file_name": "coal_13.tif",
            "file_path": "/Users/soumyadiptadey/Developer/common_project/uploads/coal_13.tif",
            "kind": "geotiff",
            "crs": "EPSG:4326",
        }
    ]

    coordinator.apply_search_results_event_driven(assets, label="Test Search")

    result_path = "/Users/soumyadiptadey/Developer/common_project/uploads/coal_13.tif"
    # Ensure they are initialized as visible = False
    assert mock_controller._search_layer_visibility[result_path] is False


def test_sync_focus_coordinator_fallback_focus_all_assets_when_none_visible():
    from src_new.clients.desktop_search.coordinators.sync_focus_coordinator import (
        SyncFocusCoordinator,
    )
    mock_controller = MagicMock()
    mock_controller._search_result_assets_by_path = {
        "/path/1": {"file_name": "asset1.tif", "file_path": "/path/1"},
        "/path/2": {"file_name": "asset2.tif", "file_path": "/path/2"}
    }
    mock_controller._search_layer_visibility = {
        "/path/1": False,
        "/path/2": False
    }
    
    # Return bounds for the assets
    mock_controller._asset_bounds.side_effect = lambda asset: {
        "west": 10.0, "south": 20.0, "east": 15.0, "north": 25.0
    } if asset["file_path"] == "/path/1" else {
        "west": 12.0, "south": 18.0, "east": 17.0, "north": 22.0
    }

    coordinator = SyncFocusCoordinator(mock_controller)

    coordinator.focus_visible_search_assets_with_enhanced_behavior(
        force=True, is_first_search=True, asset_count=2
    )

    # Verify fallback calculated the union bounds of all assets: union of bounds is west=10.0, south=18.0, east=17.0, north=25.0
    mock_controller._run_js_call.assert_any_call(
        "focusBoundsWithPadding",
        10.0,
        18.0,
        17.0,
        25.0,
        1.5
    )


def test_sync_search_visibility_layers_event_driven_does_not_call_js_for_unloaded_hidden_layers():
    from src_new.clients.desktop_search.coordinators.sync_focus_coordinator import (
        SyncFocusCoordinator,
    )
    mock_controller = MagicMock()
    mock_controller._search_result_assets_by_path = {
        "/path/1": {"file_name": "asset1.tif", "file_path": "/path/1"},
    }
    mock_controller._search_layer_visibility = {
        "/path/1": False,
    }
    mock_controller._loaded_search_layer_keys = set()
    mock_controller._is_dem_asset.return_value = False

    coordinator = SyncFocusCoordinator(mock_controller)
    coordinator.sync_search_visibility_layers_event_driven()

    # Verify setLayerVisibility was NOT called
    for call in mock_controller._run_js_call.mock_calls:
        assert call[1][0] != "setLayerVisibility"


def test_project_io_coordinator_roundtrip():
    from src_new.clients.desktop_search.coordinators.project_io_coordinator import (
        ProjectIoCoordinator,
    )
    
    mock_controller = MagicMock()
    mock_controller.panel = MagicMock()
    mock_controller.panel._layer_order_registry = {
        "/path/raster1.tif": {"order": 1, "is_visible": True}
    }
    mock_controller.panel.search_aoi_visible_check = MagicMock()
    mock_controller.panel.search_aoi_visible_check.isChecked.return_value = False
    
    # Setup state
    mock_controller._search_result_assets_by_path = {
        "/path/raster1.tif": {
            "file_name": "raster1.tif",
            "file_path": "/path/raster1.tif",
            "kind": "geotiff",
            "crs": "EPSG:4326"
        }
    }
    mock_controller._search_layer_visibility = {"/path/raster1.tif": True}
    mock_controller._user_added_assets = {}
    mock_controller._vector_layers = {
        "vector1": {
            "layer_key": "vector1",
            "label": "Vector Layer 1",
            "geojson": {"type": "FeatureCollection", "features": []},
            "is_visible": True
        }
    }
    mock_controller.state.selected_asset = {"file_path": "/path/raster1.tif"}
    mock_controller.state.clicked_points = [[10.0, 20.0]]
    mock_controller.state.search_geometry_type = "polygon"
    mock_controller.state.search_geometry_payload = {"points": [[10, 20], [15, 20], [15, 25], [10, 20]]}
    
    mock_controller._annotation_records = [{"lon": 10.0, "lat": 20.0, "text": "Hello"}]
    mock_controller._annotation_line_records = []
    mock_controller._annotation_polygon_records = []
    mock_controller._annotation_icon_records = []
    mock_controller._annotation_text_records = []
    mock_controller._raster_stretch_settings = {"/path/raster1.tif": {"brightness": 1.2}}
    mock_controller._active_dem_search_layer_key = None
    mock_controller._event_driven_enabled = True
    mock_controller._last_camera_state = {
        "lon": 77.2,
        "lat": 28.6,
        "height": 5000.0,
        "heading": 12.0,
        "pitch": -45.0,
        "roll": 0.0,
    }
    
    coordinator = ProjectIoCoordinator(mock_controller)
    
    # Build payload
    payload = coordinator.build_project_payload()
    
    # Assert payload structure
    assert payload["version"] == 1
    assert payload["selected_asset_path"] == "/path/raster1.tif"
    assert payload["clicked_points"] == [[10.0, 20.0]]
    assert payload["search"]["geometry_type"] == "polygon"
    assert payload["search"]["aoi_visible"] is False
    assert len(payload["layers"]["rasters"]) == 1
    assert payload["layers"]["rasters"][0]["file_path"] == "/path/raster1.tif"
    assert len(payload["layers"]["vectors"]) == 1
    assert payload["layers"]["vectors"][0]["layer_key"] == "vector1"
    assert payload["camera"]["lon"] == 77.2
    
    # Apply payload Let's reset controller state first to verify reconstruction
    mock_controller._search_result_assets_by_path = {}
    mock_controller._vector_layers = {}
    mock_controller._annotation_records = []
    mock_controller.state.clicked_points = []
    mock_controller._last_camera_state = None
    
    from unittest.mock import patch
    with patch("qtpy.QtCore.QTimer.singleShot", lambda ms, cb: cb()):
        coordinator.apply_project_payload(payload)
    
    # Assert reconstructed state
    assert "/path/raster1.tif" in mock_controller._search_result_assets_by_path
    assert "vector1" in mock_controller._vector_layers
    assert len(mock_controller._annotation_records) == 1
    assert mock_controller._annotation_records[0]["text"] == "Hello"
    assert mock_controller._last_camera_state["lon"] == 77.2
    assert mock_controller.state.clicked_points == [[10.0, 20.0]]
    mock_controller._set_search_aoi_visible.assert_called_with(False)


def test_layer_coordinator_vector_layers():
    import json
    from unittest.mock import patch

    from src_new.clients.desktop_search.controller import DesktopController
    from src_new.clients.desktop_search.coordinators.layer_coordinator import (
        LayerCoordinator,
    )

    # Arrange
    mock_controller = MagicMock()
    mock_controller._vector_layers = {}
    mock_controller.panel = MagicMock()
    
    # Define dummy GeoJSON content
    dummy_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [77.0, 28.0]},
                "properties": {"name": "Test Point"}
            }
        ]
    }
    
    # 1. Test DesktopController._read_vector_geojson directly
    mock_path = MagicMock()
    mock_path.suffix = ".geojson"
    mock_path.name = "test.geojson"
    mock_path.read_text.return_value = json.dumps(dummy_geojson)
    
    parsed = DesktopController._read_vector_geojson(mock_controller, mock_path)
    assert parsed == dummy_geojson
    
    # 2. Test LayerCoordinator.add_vector_layers adding & caching vector layers
    coordinator = LayerCoordinator(mock_controller)
    mock_controller._read_vector_geojson.return_value = dummy_geojson
    mock_controller._make_unique_vector_key.return_value = "vector:test.geojson"
    
    with patch("qtpy.QtWidgets.QFileDialog.getOpenFileNames", return_value=(["/path/test.geojson"], "GeoJSON")):
        coordinator.add_vector_layers()
        
    # Verify vector layers registration
    assert "vector:test.geojson" in mock_controller._vector_layers
    assert mock_controller._vector_layers["vector:test.geojson"]["label"] == "test"
    assert mock_controller._vector_layers["vector:test.geojson"]["geojson"] == dummy_geojson
    
    # Verify JS bridge was called to render on the Cesium globe
    mock_controller._run_js_call.assert_any_call("addVectorLayer", "vector:test.geojson", "test", dummy_geojson, {})
    mock_controller._refresh_vector_layers_ui.assert_called()


def test_desktop_controller_undo_redo_stack():
    from unittest.mock import patch

    from src_new.clients.desktop_search.controller import DesktopController

    # Create a subclass or instance with mocked dependencies
    mock_panel = MagicMock()
    mock_view = MagicMock()
    mock_bridge = MagicMock()
    
    # Avoid QComboBox findData TypeError with MagicMocks
    mock_panel.dem_color_mode_combo.findData.return_value = -1
    mock_panel.dem_stretch_mode_combo.findData.return_value = -1
    mock_panel.stretch_mode_combo.findData.return_value = -1
    
    with patch("src_new.clients.desktop_search.controller.QTimer"), \
         patch("src_new.clients.desktop_search.controller.QThreadPool"):
        # Instantiate DesktopController with basic mocks
        controller = DesktopController(
            panel=mock_panel,
            web_view=mock_view,
            bridge=mock_bridge,
            api_client=MagicMock(),
            titiler_manager=MagicMock(),
            api_server_manager=MagicMock(),
        )
    
    # Mock project IO and serialization with a larger state sequence
    state_seq = [{"version": 1, "state_id": i, "annotations": {"points": []}} for i in range(100)]
    
    current_state_idx = 0
    
    def mock_build_payload():
        return state_seq[current_state_idx]
        
    def mock_apply_payload(payload, source_path=None):
        nonlocal current_state_idx
        current_state_idx = payload["state_id"]

    controller.build_project_payload = mock_build_payload
    controller.apply_project_payload = mock_apply_payload
    controller._last_state_snapshot = state_seq[0]
    
    # Initially stack is empty
    assert len(controller._undo_stack) == 0
    
    # 1. State changes to 1 (Action 1)
    current_state_idx = 1
    controller._set_project_modified(True)
    # The baseline State 0 should be on the undo stack
    assert len(controller._undo_stack) == 1
    assert controller._undo_stack[0]["state_id"] == 0
    
    # 2. State changes to 2 (Action 2)
    current_state_idx = 2
    controller._set_project_modified(True)
    # Both State 0 and State 1 should be on the undo stack
    assert len(controller._undo_stack) == 2
    assert controller._undo_stack[0]["state_id"] == 0
    assert controller._undo_stack[1]["state_id"] == 1
    
    # 3. Undo Action
    controller.undo_last_action()
    # Should revert current state to 1
    assert current_state_idx == 1
    assert len(controller._undo_stack) == 1
    assert controller._undo_stack[0]["state_id"] == 0
    
    # 4. Test Stack limit capping (capped at 50) Restore state_idx back to 1 for consistency
    current_state_idx = 1
    # Advance project modification 58 more times (state_idx from 2 to 59)
    for i in range(2, 60):
        current_state_idx = i
        controller._set_project_modified(True)
        
    # Stack size should be capped at 50, with the earliest states (0 to 8) discarded
    assert len(controller._undo_stack) == 50
    assert controller._undo_stack[0]["state_id"] == 9
    assert controller._undo_stack[-1]["state_id"] == 58
    assert controller._last_state_snapshot["state_id"] == 59


def test_export_dialog_thread_retention(monkeypatch):
    from src_new.clients.desktop_search.coordinators.export_coordinator import (
        ExportAssetDialog,
    )
    
    # Mock QDialog methods
    monkeypatch.setattr("qtpy.QtWidgets.QDialog.__init__", lambda self, parent=None: None)
    monkeypatch.setattr("qtpy.QtWidgets.QDialog.style", lambda self: MagicMock())
    
    # Instantiate without calling init_ui
    dialog = ExportAssetDialog.__new__(ExportAssetDialog)
    dialog.assets = []
    dialog._resolve_source_path = None
    dialog.threads = {}
    dialog.finished_threads = []
    
    # Create mock components
    mock_btn = MagicMock()
    mock_progress_bar = MagicMock()
    mock_status_label = MagicMock()
    
    # Mock QFileDialog
    monkeypatch.setattr("qtpy.QtWidgets.QFileDialog.getSaveFileName", lambda *args, **kwargs: ("/path/to/dest.tif", "Filter"))
    
    # Mock AssetExportThread
    mock_thread = MagicMock()
    mock_thread_class = MagicMock(return_value=mock_thread)
    monkeypatch.setattr("src_new.clients.desktop_search.coordinators.export_coordinator.AssetExportThread", mock_thread_class)
    
    # Mock Path exists
    monkeypatch.setattr("pathlib.Path.exists", lambda self: True)
    
    # Trigger start_download
    dialog.start_download("/path/to/src.tif", "src.tif", mock_btn, mock_progress_bar, mock_status_label)
    
    # Verify thread was added to threads dictionary
    assert "/path/to/src.tif" in dialog.threads
    assert dialog.threads["/path/to/src.tif"] == mock_thread
    
    # Capture handle_finished connected to finished signal
    finished_connection = mock_thread.finished.connect.call_args[0][0]
    
    # Call handle_finished(success=True, err_msg="")
    finished_connection(True, "")
    
    # Verify that the thread is removed from active threads
    assert "/path/to/src.tif" not in dialog.threads
    # Verify that it is appended to finished_threads to protect its lifecycle
    assert mock_thread in dialog.finished_threads


def test_layer_coordinator_toggle_search_results_visibility_batch():
    from src_new.clients.desktop_search.coordinators.layer_coordinator import (
        LayerCoordinator,
    )

    mock_controller = MagicMock()
    mock_controller._search_result_assets_by_path = {
        "/path/1": {"file_name": "asset1.tif", "file_path": "/path/1"},
        "/path/2": {"file_name": "asset2.tif", "file_path": "/path/2"}
    }
    mock_controller._search_layer_visibility = {
        "/path/1": False,
        "/path/2": False
    }
    mock_controller._loaded_search_layer_keys = set()
    mock_controller._visibility_sync_in_progress = False
    mock_controller._event_driven_enabled = True
    mock_controller._is_dem_asset.return_value = False

    coordinator = LayerCoordinator(mock_controller)

    # Call batch visibility toggle to make all visible
    coordinator.toggle_search_results_visibility_batch(["/path/1", "/path/2"], True)

    # Assert visibility state updated
    assert mock_controller._search_layer_visibility["/path/1"] is True
    assert mock_controller._search_layer_visibility["/path/2"] is True
    # Verify single-pass visibility sync was called
    mock_controller._sync_search_visibility_layers_event_driven.assert_called_once()


def test_control_panel_search_calculate_all_visible_state():
    from src_new.clients.desktop_search.control_panel_search import (
        ControlPanelSearchMixin,
    )
    
    class DummySearchPanel(ControlPanelSearchMixin):
        def __init__(self):
            pass
            
    panel = DummySearchPanel()
    
    # Case 1: No assets
    assert panel._calculate_all_visible_state([], {}) is False
    
    # Case 2: Only imagery, all visible
    assets = [
        {"file_path": "/path/1", "kind": "image"},
        {"file_path": "/path/2", "kind": "image"}
    ]
    vis_map = {"/path/1": True, "/path/2": True}
    assert panel._calculate_all_visible_state(assets, vis_map) is True
    
    # Case 3: Only imagery, some hidden
    vis_map = {"/path/1": True, "/path/2": False}
    assert panel._calculate_all_visible_state(assets, vis_map) is False
    
    # Case 4: Multiple DEMs, one visible (due to DEM exclusivity)
    dem_assets = [
        {"file_path": "/path/dem1", "kind": "dem"},
        {"file_path": "/path/dem2", "kind": "dem"}
    ]
    vis_map = {"/path/dem1": True, "/path/dem2": False}
    assert panel._calculate_all_visible_state(dem_assets, vis_map) is True
    
    # Case 5: Multiple DEMs, all hidden
    vis_map = {"/path/dem1": False, "/path/dem2": False}
    assert panel._calculate_all_visible_state(dem_assets, vis_map) is False
    
    # Case 6: Mixed imagery and DEMs, imagery all visible and one DEM visible
    mixed_assets = assets + dem_assets
    vis_map = {"/path/1": True, "/path/2": True, "/path/dem1": True, "/path/dem2": False}
    assert panel._calculate_all_visible_state(mixed_assets, vis_map) is True
    
    # Case 7: Mixed imagery and DEMs, imagery not all visible
    vis_map = {"/path/1": True, "/path/2": False, "/path/dem1": True, "/path/dem2": False}
    assert panel._calculate_all_visible_state(mixed_assets, vis_map) is False


def test_rendering_coordinator_add_point_cloud_layer():
    from src_new.clients.desktop_search.coordinators.rendering_coordinator import (
        RenderingCoordinator,
    )
    mock_controller = MagicMock()
    mock_window = MagicMock()
    mock_controller.panel.window.return_value = mock_window
    
    coordinator = RenderingCoordinator(mock_controller)
    
    asset = {
        "file_name": "NEONDSSampleLiDARPointCloud.las",
        "file_path": "/path/to/NEONDSSampleLiDARPointCloud.las",
        "kind": "point_cloud",
    }
    options = {
        "bounds": [-120.0, 37.0, -119.0, 38.0],
        "replace_existing": True,
    }
    
    success = coordinator.add_layer(asset, options)
    
    assert success is True
    # Verify the canvas index is set to 0 (Cesium Map)
    mock_window.set_canvas_index.assert_called_once_with(0)
    # Verify javascript call was run to add point cloud layer to Cesium globe
    mock_controller._run_js_call.assert_called_once()
    call_args = mock_controller._run_js_call.call_args[0]
    assert call_args[0] == "addPointCloudLayer"
    assert call_args[1] == "NEONDSSampleLiDARPointCloud.las"
    assert "tileset.json" in call_args[2]







