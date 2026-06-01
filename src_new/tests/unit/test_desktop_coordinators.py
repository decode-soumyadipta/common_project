from unittest.mock import MagicMock
from src_new.clients.desktop_search.coordinators.search_results_coordinator import SearchResultsCoordinator


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

    # Assert
    # Verify search result assets by path has been populated
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
    from src_new.clients.desktop_search.coordinators.sync_focus_coordinator import SyncFocusCoordinator
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

    # Verify fallback calculated the union bounds of all assets:
    # union of bounds is west=10.0, south=18.0, east=17.0, north=25.0
    mock_controller._run_js_call.assert_any_call(
        "focusBoundsWithPadding",
        10.0,
        18.0,
        17.0,
        25.0,
        1.5
    )


def test_sync_search_visibility_layers_event_driven_does_not_call_js_for_unloaded_hidden_layers():
    from src_new.clients.desktop_search.coordinators.sync_focus_coordinator import SyncFocusCoordinator
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
    from src_new.clients.desktop_search.coordinators.project_io_coordinator import ProjectIoCoordinator
    
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
    
    # Apply payload
    # Let's reset controller state first to verify reconstruction
    mock_controller._search_result_assets_by_path = {}
    mock_controller._vector_layers = {}
    mock_controller._annotation_records = []
    mock_controller.state.clicked_points = []
    mock_controller._last_camera_state = None
    
    coordinator.apply_project_payload(payload)
    
    # Assert reconstructed state
    assert "/path/raster1.tif" in mock_controller._search_result_assets_by_path
    assert "vector1" in mock_controller._vector_layers
    assert len(mock_controller._annotation_records) == 1
    assert mock_controller._annotation_records[0]["text"] == "Hello"
    assert mock_controller._last_camera_state["lon"] == 77.2
    assert mock_controller.state.clicked_points == [[10.0, 20.0]]
    mock_controller._set_search_aoi_visible.assert_called_with(False)
