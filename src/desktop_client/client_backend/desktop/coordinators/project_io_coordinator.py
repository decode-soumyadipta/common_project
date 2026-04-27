from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

from qtpy.QtWidgets import QFileDialog


class ProjectIoCoordinator:
    """Handle toolbar export/save actions without bloating the desktop controller."""

    def __init__(self, controller):
        self._controller = controller

    def _panel(self):
        return self._controller.panel

    def export_profile_csv(self) -> None:
        controller = self._controller
        if not controller._last_profile_values:
            controller.panel.log("No profile values available. Run Elevation Profile first.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            controller.panel,
            "Export Profile CSV",
            "profile_export.csv",
            "CSV Files (*.csv)",
        )
        if not file_path:
            return
        output_path = Path(file_path)
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["index", "elevation_m"])
            for idx, value in enumerate(controller._last_profile_values):
                writer.writerow([idx, f"{value:.6f}"])
        controller.panel.log(f"Profile CSV exported: {output_path}")

    def export_annotations_geojson(self) -> None:
        controller = self._controller
        if (
            not controller._annotation_records
            and not controller._annotation_line_records
            and not controller._annotation_polygon_records
        ):
            controller.panel.log("No annotations captured yet.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            controller.panel,
            "Export Annotation GeoJSON",
            "annotations.geojson",
            "GeoJSON (*.geojson)",
        )
        if not file_path:
            return
        features = []
        for item in controller._annotation_records:
            lon = float(item.get("lon") or 0.0)
            lat = float(item.get("lat") or 0.0)
            properties = {
                "type": item.get("type", "point"),
                "text": item.get("text", ""),
                "created_at": item.get("created_at", ""),
            }
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": properties,
                }
            )
        for item in controller._annotation_line_records:
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": item.get("coords", []),
                    },
                    "properties": {
                        "feature_type": item.get("feature_type", "road"),
                        "length_m": item.get("length_m", 0.0),
                        "width_m": item.get("width_m", 0.0),
                        "condition": item.get("condition", "intact"),
                        "created_at": item.get("created_at", ""),
                    },
                }
            )
        for item in controller._annotation_polygon_records:
            ring = item.get("coords", [])
            if ring and ring[0] != ring[-1]:
                ring = list(ring) + [ring[0]]
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                    "properties": {
                        "feature_type": item.get("feature_type", "building"),
                        "condition": item.get("condition", "intact"),
                        "area_m2": item.get("area_m2", 0.0),
                        "perimeter_m": item.get("perimeter_m", 0.0),
                        "orientation_deg": item.get("orientation_deg", 0.0),
                        "notes": item.get("notes", ""),
                        "created_at": item.get("created_at", ""),
                    },
                }
            )
        payload = {"type": "FeatureCollection", "features": features}
        Path(file_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        controller.panel.log(f"Annotation export complete: {file_path}")

    def export_annotations_geopackage(self) -> None:
        controller = self._controller
        if (
            not controller._annotation_records
            and not controller._annotation_line_records
            and not controller._annotation_polygon_records
        ):
            controller.panel.log("No annotations captured yet.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            controller.panel,
            "Export Annotation GeoPackage",
            "annotations.gpkg",
            "GeoPackage (*.gpkg)",
        )
        if not file_path:
            return

        try:
            import fiona
            from fiona.crs import CRS as FionaCRS
        except Exception:
            controller.panel.log("Fiona is unavailable. Falling back to GeoJSON export.")
            self.export_annotations_geojson()
            return

        point_schema = {
            "geometry": "Point",
            "properties": {
                "category": "str",
                "confidence": "str",
                "height_m": "float",
                "created_at": "str",
                "notes": "str",
                "class_level": "str",
            },
        }
        with fiona.open(
            file_path,
            "w",
            driver="GPKG",
            layer="annotations_point",
            crs=FionaCRS.from_epsg(4326),
            schema=point_schema,
        ) as sink:
            for item in controller._annotation_records:
                lon = float(item.get("lon") or 0.0)
                lat = float(item.get("lat") or 0.0)
                sink.write(
                    {
                        "geometry": {"type": "Point", "coordinates": (lon, lat)},
                        "properties": {
                            "category": "other",
                            "confidence": "possible",
                            "height_m": -9999.0,
                            "created_at": str(item.get("created_at") or ""),
                            "notes": str(item.get("text") or ""),
                            "class_level": "UNCLASS",
                        },
                    }
                )

        line_schema = {
            "geometry": "LineString",
            "properties": {
                "feature_type": "str",
                "length_m": "float",
                "width_m": "float",
                "condition": "str",
            },
        }
        with fiona.open(
            file_path,
            "a",
            driver="GPKG",
            layer="annotations_line",
            crs=FionaCRS.from_epsg(4326),
            schema=line_schema,
        ) as sink:
            for item in controller._annotation_line_records:
                sink.write(
                    {
                        "geometry": {
                            "type": "LineString",
                            "coordinates": item.get("coords", []),
                        },
                        "properties": {
                            "feature_type": str(item.get("feature_type") or "road"),
                            "length_m": float(item.get("length_m") or 0.0),
                            "width_m": float(item.get("width_m") or 0.0),
                            "condition": str(item.get("condition") or "intact"),
                        },
                    }
                )

        polygon_schema = {
            "geometry": "Polygon",
            "properties": {
                "feature_type": "str",
                "condition": "str",
                "area_m2": "float",
                "perimeter_m": "float",
                "orientation_deg": "float",
                "notes": "str",
            },
        }
        with fiona.open(
            file_path,
            "a",
            driver="GPKG",
            layer="annotations_polygon",
            crs=FionaCRS.from_epsg(4326),
            schema=polygon_schema,
        ) as sink:
            for item in controller._annotation_polygon_records:
                ring = item.get("coords", [])
                if ring and ring[0] != ring[-1]:
                    ring = list(ring) + [ring[0]]
                sink.write(
                    {
                        "geometry": {"type": "Polygon", "coordinates": [ring]},
                        "properties": {
                            "feature_type": str(item.get("feature_type") or "building"),
                            "condition": str(item.get("condition") or "intact"),
                            "area_m2": float(item.get("area_m2") or 0.0),
                            "perimeter_m": float(item.get("perimeter_m") or 0.0),
                            "orientation_deg": float(item.get("orientation_deg") or 0.0),
                            "notes": str(item.get("notes") or ""),
                        },
                    }
                )

        controller.panel.log(f"GeoPackage export complete: {file_path}")

    def save_project(self) -> None:
        controller = self._controller
        file_path, _ = QFileDialog.getSaveFileName(
            controller.panel,
            "Save Project",
            "offline_gis_project.json",
            "JSON Files (*.json)",
        )
        if not file_path:
            return
        payload = {
            "selected_asset": controller.state.selected_asset,
            "clicked_points": controller.state.clicked_points,
            "search_geometry_type": controller.state.search_geometry_type,
            "search_geometry_payload": controller.state.search_geometry_payload,
            "search_visibility": controller._search_layer_visibility,
            "saved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        Path(file_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        controller.panel.log(f"Project saved: {file_path}")


__all__ = ["ProjectIoCoordinator"]