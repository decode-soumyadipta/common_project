#!/usr/bin/env python3
"""Test script to verify database connectivity and data."""

import sys
from pathlib import Path

# Add src_new to path
sys.path.insert(0, str(Path(__file__).parent))

from src_new.services.query.api.dependencies import get_db
from src_new.services.query.repositories.raster_repository import RasterRepository

# Get a database session
db_gen = get_db()
db = next(db_gen)

try:
    # Create repository
    repo = RasterRepository(db)
    
    # Try to find all rasters
    print("Calling repo.find_all()...")
    rasters = repo.find_all()
    
    print(f"\nFound {len(rasters)} rasters")
    
    if rasters:
        print("\nFirst 5 rasters:")
        for i, raster in enumerate(rasters[:5], 1):
            print(f"  {i}. {raster.file_name} ({raster.kind.value})")
    else:
        print("\nNo rasters found!")
        
        # Check if table exists
        from sqlalchemy import text
        result = db.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = [row[0] for row in result]
        print(f"\nTables in database: {tables}")
        
        # Check raster_assets table
        if "raster_assets" in tables:
            result = db.execute(text("SELECT COUNT(*) FROM raster_assets"))
            count = result.scalar()
            print(f"\nDirect SQL query: {count} rows in raster_assets table")
            
finally:
    db.close()
