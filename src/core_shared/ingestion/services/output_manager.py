"""
Output file organization manager for ingestion pipeline.

Organizes processed files (COG, MBTiles, metadata) into timestamped directories
to keep source directories clean and outputs easy to find.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

LOGGER = logging.getLogger("services.output_manager")


class OutputManager:
    """Manages organized output directories for processed geospatial files."""
    
    def __init__(self, base_dir: Path, enabled: bool = True):
        """
        Initialize output manager.
        
        Args:
            base_dir: Base directory for all processed outputs
            enabled: Whether to use organized outputs (False = write to source dir)
        """
        self.base_dir = base_dir
        self.enabled = enabled
        self._current_session_dir: Optional[Path] = None
        self._logger = LOGGER
    
    def create_session_directory(self, timestamp: Optional[datetime] = None) -> Path:
        """
        Create a new timestamped session directory for this ingestion batch.
        
        Args:
            timestamp: Optional timestamp (defaults to now)
            
        Returns:
            Path to session root directory
        """
        if not self.enabled:
            raise ValueError("Output organization is disabled")
        
        if timestamp is None:
            timestamp = datetime.now()
        
        # Format: YYYY-MM-DD_HH-MM-SS
        timestamp_str = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        session_dir = self.base_dir / timestamp_str
        
        # Create subdirectories
        subdirs = {
            'cog': session_dir / "cog",
            'mbtiles': session_dir / "mbtiles",
            'metadata': session_dir / "metadata",
            'logs': session_dir / "logs"
        }
        
        for subdir in subdirs.values():
            subdir.mkdir(parents=True, exist_ok=True)
        
        self._current_session_dir = session_dir
        self._logger.info(f"Created session directory: {session_dir}")
        
        # Create README
        readme_path = session_dir / "README.txt"
        readme_path.write_text(
            f"Processed Geospatial Data - {timestamp_str}\n"
            f"{'=' * 60}\n\n"
            f"This directory contains processed geospatial files:\n\n"
            f"  cog/       - Cloud-Optimized GeoTIFF files\n"
            f"  mbtiles/   - MBTiles pyramid files (Web Mercator)\n"
            f"  metadata/  - JSON metadata for each processed file\n"
            f"  logs/      - Processing logs\n\n"
            f"Generated: {timestamp.isoformat()}\n"
        )
        
        return session_dir
    
    def get_cog_output_path(self, source_path: Path, session_dir: Optional[Path] = None) -> Path:
        """
        Get output path for COG file.
        
        Args:
            source_path: Original source file path
            session_dir: Optional session directory (uses current if None)
            
        Returns:
            Path where COG should be written
        """
        if not self.enabled:
            # Fallback: write to same directory as source
            stem = source_path.stem
            if stem.endswith(".cog"):
                return source_path.with_suffix(".tif")
            return source_path.parent / f"{stem}.cog.tif"
        
        session = session_dir or self._current_session_dir
        if session is None:
            raise ValueError("No session directory created - call create_session_directory() first")
        
        stem = source_path.stem
        if stem.endswith(".cog"):
            cog_name = source_path.with_suffix(".tif").name
        else:
            cog_name = f"{stem}.cog.tif"
        
        return session / "cog" / cog_name
    
    def get_mbtiles_output_path(self, source_path: Path, session_dir: Optional[Path] = None) -> Path:
        """
        Get output path for MBTiles file.
        
        Args:
            source_path: Original source file path
            session_dir: Optional session directory (uses current if None)
            
        Returns:
            Path where MBTiles should be written
        """
        if not self.enabled:
            # Fallback: write to same directory as source
            return source_path.parent / f"{source_path.stem}_3857.mbtiles"
        
        session = session_dir or self._current_session_dir
        if session is None:
            raise ValueError("No session directory created - call create_session_directory() first")
        
        mbtiles_name = f"{source_path.stem}_3857.mbtiles"
        return session / "mbtiles" / mbtiles_name
    
    def get_metadata_output_path(self, source_path: Path, session_dir: Optional[Path] = None) -> Path:
        """
        Get output path for metadata JSON file.
        
        Args:
            source_path: Original source file path
            session_dir: Optional session directory (uses current if None)
            
        Returns:
            Path where metadata JSON should be written
        """
        if not self.enabled:
            # Fallback: write to same directory as source
            return source_path.parent / f"{source_path.stem}_metadata.json"
        
        session = session_dir or self._current_session_dir
        if session is None:
            raise ValueError("No session directory created - call create_session_directory() first")
        
        metadata_name = f"{source_path.stem}_metadata.json"
        return session / "metadata" / metadata_name
    
    def save_metadata(
        self, 
        source_path: Path, 
        metadata: Dict, 
        session_dir: Optional[Path] = None
    ) -> Path:
        """
        Save metadata JSON file.
        
        Args:
            source_path: Original source file path
            metadata: Metadata dictionary to save
            session_dir: Optional session directory (uses current if None)
            
        Returns:
            Path where metadata was saved
        """
        output_path = self.get_metadata_output_path(source_path, session_dir)
        
        # Add timestamp and source info
        metadata_with_info = {
            'source_file': str(source_path),
            'processed_at': datetime.now().isoformat(),
            'session_directory': str(session_dir or self._current_session_dir),
            **metadata
        }
        
        output_path.write_text(json.dumps(metadata_with_info, indent=2))
        self._logger.info(f"Saved metadata: {output_path}")
        
        return output_path
    
    def get_current_session_dir(self) -> Optional[Path]:
        """Get the current session directory."""
        return self._current_session_dir
    
    def list_sessions(self) -> list[Path]:
        """
        List all session directories.
        
        Returns:
            List of session directory paths, sorted by timestamp (newest first)
        """
        if not self.base_dir.exists():
            return []
        
        sessions = [
            d for d in self.base_dir.iterdir()
            if d.is_dir() and self._is_valid_session_dir(d)
        ]
        
        # Sort by directory name (timestamp) descending
        sessions.sort(reverse=True)
        
        return sessions
    
    def _is_valid_session_dir(self, dir_path: Path) -> bool:
        """Check if directory is a valid session directory."""
        # Check if name matches timestamp format: YYYY-MM-DD_HH-MM-SS
        name = dir_path.name
        try:
            datetime.strptime(name, "%Y-%m-%d_%H-%M-%S")
            return True
        except ValueError:
            return False
    
    def cleanup_old_sessions(self, keep_count: int = 10) -> int:
        """
        Clean up old session directories, keeping only the most recent ones.
        
        Args:
            keep_count: Number of recent sessions to keep
            
        Returns:
            Number of sessions deleted
        """
        sessions = self.list_sessions()
        
        if len(sessions) <= keep_count:
            return 0
        
        sessions_to_delete = sessions[keep_count:]
        deleted_count = 0
        
        for session_dir in sessions_to_delete:
            try:
                import shutil
                shutil.rmtree(session_dir)
                self._logger.info(f"Deleted old session: {session_dir}")
                deleted_count += 1
            except Exception as e:
                self._logger.warning(f"Failed to delete session {session_dir}: {e}")
        
        return deleted_count
