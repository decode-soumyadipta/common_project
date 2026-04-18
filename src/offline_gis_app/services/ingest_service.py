from pathlib import Path
import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from offline_gis_app.db.catalog import CatalogRepository
from offline_gis_app.services.metadata_extractor import ensure_overviews, extract_metadata
from offline_gis_app.services.tile_url_builder import build_xyz_url


LOGGER = logging.getLogger("services.ingest")


def register_raster(path: Path, session: Session, progress_callback: Callable[[str], None] | None = None) -> dict:
    """Register a raster in the catalog and return its API-facing payload."""
    if progress_callback:
        progress_callback("Validating source path")

    if path.suffix.lower() in {".tif", ".tiff"}:
        if progress_callback:
            progress_callback("Building overview pyramid / indexing raster")
        if ensure_overviews(path):
            LOGGER.info("Built raster overviews for %s", path)

    if progress_callback:
        progress_callback("Extracting metadata from raster")

    metadata = extract_metadata(path)

    if progress_callback:
        progress_callback("Writing metadata to PostgreSQL catalog")

    repo = CatalogRepository(session)
    asset = repo.upsert_asset(metadata)

    if progress_callback:
        progress_callback("Metadata committed (source file remains on secure storage)")

    centroid_x, centroid_y = metadata.bounds.centroid()
    return {
        "id": asset.id,
        "file_name": asset.file_name,
        "file_path": asset.file_path,
        "kind": asset.raster_kind.value,
        "crs": asset.crs,
        "centroid": {"lon": centroid_x, "lat": centroid_y},
        "bounds_wkt": asset.bounds_wkt,
        "tile_url": build_xyz_url(asset.file_path),
    }

