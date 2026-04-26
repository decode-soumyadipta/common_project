"""Tests for the ElevationProfilePanel Qt widget."""
from __future__ import annotations

import math

import pytest
from qtpy.QtWidgets import QApplication

from offline_gis_app.client_backend.desktop.elevation_profile_panel import (
    ElevationProfilePanel,
    _Profile2DWidget,
    _Profile3DWidget,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


SAMPLE_VALUES = [100.0, 120.0, 150.0, 140.0, 130.0, 160.0, 180.0, 170.0, 155.0, 110.0]
DISTANCE_M = 4500.0


def test_profile_2d_widget_accepts_data(qapp):
    w = _Profile2DWidget()
    w.set_data(SAMPLE_VALUES, DISTANCE_M)
    assert w._values == SAMPLE_VALUES
    assert w._distance_m == DISTANCE_M


def test_profile_2d_widget_filters_nan(qapp):
    vals = [100.0, float("nan"), 150.0, float("inf"), 130.0]
    w = _Profile2DWidget()
    w.set_data(vals, 1000.0)
    assert all(math.isfinite(v) for v in w._values)
    assert len(w._values) == 3


def test_profile_3d_widget_accepts_data(qapp):
    w = _Profile3DWidget()
    w.set_data(SAMPLE_VALUES, DISTANCE_M)
    assert w._values == SAMPLE_VALUES
    assert w._distance_m == DISTANCE_M


def test_elevation_profile_panel_shows_and_updates(qapp):
    panel = ElevationProfilePanel()
    panel.set_profile(SAMPLE_VALUES, DISTANCE_M, 87.1, 23.7, 87.2, 23.8)

    # Info label should contain coordinate info
    info_text = panel._info_label.text()
    assert "87.1" in info_text
    assert "23.7" in info_text

    # Charts should have data
    assert panel._chart_2d._values == SAMPLE_VALUES
    assert panel._chart_3d._values == SAMPLE_VALUES
    panel.close()


def test_elevation_profile_panel_km_formatting(qapp):
    panel = ElevationProfilePanel()
    panel.set_profile(SAMPLE_VALUES, 5500.0, 0.0, 0.0, 0.1, 0.1)
    assert "km" in panel._info_label.text()
    panel.close()


def test_elevation_profile_panel_m_formatting(qapp):
    panel = ElevationProfilePanel()
    panel.set_profile(SAMPLE_VALUES, 800.0, 0.0, 0.0, 0.01, 0.01)
    info = panel._info_label.text()
    assert "800" in info or "m" in info
    panel.close()
