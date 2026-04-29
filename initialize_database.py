#!/usr/bin/env python3
"""
Initialize the database schema for the ingestion pipeline.
This script creates all necessary tables if they don't exist.
"""

import sys
import logging
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from core_shared.db.session import init_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Initialize the database schema."""
    try:
        logger.info("🗄️ Initializing database schema...")
        init_db()
        logger.info("✅ Database schema initialized successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)