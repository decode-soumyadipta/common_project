import sys
import os
import sqlite3
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path('/Users/soumyadiptadey/Developer/common_project')
sys.path.append(str(PROJECT_ROOT))

# Initialize configuration (needed for CogConverter)
from src_new.shared.config import settings
settings.apply_gdal_env()

from src_new.services.ingestion.gdal_pipelines.cog_converter import CogConverter

def run_migration():
    db_path = PROJECT_ROOT / 'offline_gis.db'
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Query JP2/J2K assets in the database
    cursor.execute("SELECT raster_id, file_path, file_name FROM raster_assets WHERE file_path LIKE '%.j2k' OR file_path LIKE '%.jp2';")
    rows = cursor.fetchall()
    
    print(f"Found {len(rows)} JP2/J2K entries to migrate:")
    for row in rows:
        print(f"- {row[0]}: {row[1]}")

    converter = CogConverter()
    migrated_count = 0

    for raster_id, file_path, file_name in rows:
        source_path = Path(file_path)
        if not source_path.exists():
            print(f"Warning: File {source_path} does not exist, skipping conversion but will check if a sibling COG exists.")
            # Let's check if the COG exists anyway (e.g. if we had run gdal_translate manually or it got converted but DB not updated)
            cog_path = source_path.with_name(f"{source_path.stem}.cog.tif")
            if cog_path.exists():
                print(f"Found existing COG at {cog_path}, updating DB path...")
                cursor.execute(
                    "UPDATE raster_assets SET file_path = ? WHERE raster_id = ?;",
                    (str(cog_path.resolve()), raster_id)
                )
                conn.commit()
                migrated_count += 1
            continue

        print(f"\nConverting {source_path} to COG...")
        result = converter.convert(source_path)
        if result.converted or result.working_path != source_path:
            target_path = result.working_path.resolve()
            print(f"Conversion successful! Target path: {target_path}")
            cursor.execute(
                "UPDATE raster_assets SET file_path = ? WHERE raster_id = ?;",
                (str(target_path), raster_id)
            )
            conn.commit()
            print(f"Updated database record for raster_id {raster_id}.")
            migrated_count += 1
        else:
            print(f"Error: Conversion failed for {source_path}.")

    conn.close()
    print(f"\nMigration complete. {migrated_count} of {len(rows)} entries updated.")

if __name__ == '__main__':
    run_migration()
