from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

MigrationFn = Callable[[Connection], None]
LOGGER = logging.getLogger("db.migrations")


def apply_migrations(engine: Engine) -> None:
    """Apply ordered schema migrations once per database."""
    with engine.begin() as conn:
        _ensure_migration_table(conn)
        applied = _applied_versions(conn)
        for version, fn in _ordered_migrations():
            if version in applied:
                continue
            try:
                fn(conn)
                conn.execute(
                    text(
                        "INSERT INTO schema_migrations(version, description) VALUES (:version, :description)"
                    ),
                    {"version": version, "description": _migration_description(version)},
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Migration %s failed: %s", version, exc)


def _ensure_migration_table(conn: Connection) -> None:
    """Create the migration ledger table if it does not exist."""
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(64) PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


def _applied_versions(conn: Connection) -> set[str]:
    """Return migration versions already recorded in the ledger."""
    rows = conn.execute(text("SELECT version FROM schema_migrations"))
    return {str(row[0]) for row in rows}


def _ordered_migrations() -> list[tuple[str, MigrationFn]]:
    return [
        ("20260417_002_ingest_queue_indexes", _migration_ingest_queue_indexes),
        ("20260418_001_legacy_schema_backfill", _migration_legacy_schema_backfill),
        ("20260419_001_raster_bounds_spatial_index", _migration_raster_bounds_spatial_index),
    ]


def _migration_description(version: str) -> str:
    descriptions = {
        "20260417_002_ingest_queue_indexes": "Add ingest queue state indexes",
        "20260418_001_legacy_schema_backfill": "Backfill missing legacy table columns for existing databases",
        "20260419_001_raster_bounds_spatial_index": "Add PostGIS-backed spatial index for raster bounds search",
    }
    return descriptions.get(version, "migration")


def _migration_ingest_queue_indexes(conn: Connection) -> None:
    """Create indexes that speed up ingest queue polling and ordering."""
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_ingest_jobs_status
            ON ingest_jobs (status)
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_ingest_job_items_job_status
            ON ingest_job_items (job_id, status)
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_ingest_job_items_job_order
            ON ingest_job_items (job_id, item_index)
            """
        )
    )


def _migration_legacy_schema_backfill(conn: Connection) -> None:
    """Backfill nullable timestamp columns for older database installs."""
    _ensure_column(conn, "raster_assets", "updated_at", "TIMESTAMP")
    _ensure_column(conn, "ingest_jobs", "updated_at", "TIMESTAMP")
    _ensure_column(conn, "ingest_job_items", "updated_at", "TIMESTAMP")


def _migration_raster_bounds_spatial_index(conn: Connection) -> None:
    """Create a PostGIS expression index to accelerate bounds intersection search."""
    if conn.dialect.name != "postgresql":
        return
    if not _table_exists(conn, "raster_assets"):
        return

    has_postgis = conn.execute(text("SELECT to_regproc('st_geomfromtext') IS NOT NULL")).scalar()
    if not has_postgis:
        return

    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_raster_assets_bounds_geom_gist
            ON raster_assets
            USING GIST (ST_GeomFromText(bounds_wkt, 4326))
            """
        )
    )


def _ensure_column(conn: Connection, table_name: str, column_name: str, column_type: str) -> None:
    if not _table_exists(conn, table_name):
        return
    columns = _table_columns(conn, table_name)
    if column_name in columns:
        return
    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))


def _table_exists(conn: Connection, table_name: str) -> bool:
    if conn.dialect.name == "sqlite":
        row = conn.execute(
            text(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table' AND name=:table_name
                """
            ),
            {"table_name": table_name},
        ).first()
        return row is not None

    row = conn.execute(
        text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    ).first()
    return row is not None


def _table_columns(conn: Connection, table_name: str) -> set[str]:
    if conn.dialect.name == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table_name})"))
        return {str(row[1]) for row in rows}

    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    )
    return {str(row[0]) for row in rows}
