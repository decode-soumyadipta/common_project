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
