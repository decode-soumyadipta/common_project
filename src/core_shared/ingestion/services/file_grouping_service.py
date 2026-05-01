"""
Intelligent file grouping service for multi-file geospatial ingestion.

This service automatically groups related geospatial files by:
1. Basename matching (e.g., scene1.jp2 + scene1.prj)
2. Geographic metadata analysis
3. Spatial proximity detection
4. File type associations

Supports various file combinations:
- Imagery + projection files (.jp2 + .prj, .tif + .tfw, etc.)
- DEM + world files (.tif + .tfw, .dem + .hdr, etc.)
- Multi-band imagery with auxiliary files (.tif + .aux.xml)
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

from core_shared.ingestion.services.metadata_extractor import (
    extract_metadata,
    MetadataExtractorError,
)
from core_shared.utils.geometry import Bounds

LOGGER = logging.getLogger("services.file_grouping")


@dataclass
class FileGroup:
    """Represents a group of related geospatial files."""

    primary_file: Path
    """The main raster file (e.g., .tif, .jp2)"""

    auxiliary_files: List[Path] = field(default_factory=list)
    """Related files (.prj, .tfw, .aux.xml, etc.)"""

    group_id: str = ""
    """Unique identifier for this group"""

    scene_name: str = ""
    """Extracted scene/area name"""

    bounds: Optional[Bounds] = None
    """Geographic bounds if extractable"""

    file_size_bytes: int = 0
    """Total size of all files in the group"""

    confidence_score: float = 0.0
    """Confidence that files belong together (0.0-1.0)"""

    grouping_method: str = ""
    """Method used to group files (basename, geographic, etc.)"""


class FileGroupingService:
    """Service for intelligently grouping related geospatial files."""

    # Supported raster file extensions (primary files)
    RASTER_EXTENSIONS = {
        ".tif",
        ".tiff",
        ".jp2",
        ".j2k",
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".gif",
        ".hdf",
        ".nc",
        ".grib",
        ".dem",
    }

    # Auxiliary file extensions and their associations
    AUXILIARY_EXTENSIONS = {
        ".prj": "projection",  # Projection file
        ".tfw": "world_file",  # TIFF world file
        ".jgw": "world_file",  # JPEG world file
        ".pgw": "world_file",  # PNG world file
        ".bpw": "world_file",  # BMP world file
        ".gfw": "world_file",  # GIF world file
        ".aux": "auxiliary",  # Auxiliary file
        ".aux.xml": "auxiliary",  # GDAL auxiliary file
        ".xml": "metadata",  # Metadata file
        ".hdr": "header",  # ENVI header file
        ".rrd": "pyramid",  # Pyramid file
        ".ovr": "overview",  # Overview file
        ".msk": "mask",  # Mask file
        ".clr": "color_table",  # Color table
        ".vat": "attribute_table",  # Value attribute table
        ".txt": "metadata",  # Text metadata
        ".met": "metadata",  # Metadata file
    }

    def __init__(self):
        self._logger = LOGGER

    def group_files_in_folder(
        self,
        folder_path: Path,
        recursive: bool = True,
        max_groups: Optional[int] = None,
    ) -> List[FileGroup]:
        """
        Group all related geospatial files in a folder.

        Args:
            folder_path: Path to folder to scan
            recursive: Whether to scan subdirectories
            max_groups: Maximum number of groups to return (None for all)

        Returns:
            List of FileGroup objects, sorted by confidence score
        """
        self._logger.info(f"Starting file grouping in folder: {folder_path}")

        if not folder_path.exists() or not folder_path.is_dir():
            raise ValueError(f"Invalid folder path: {folder_path}")

        # Scan for all relevant files
        all_files = self._scan_files(folder_path, recursive)
        self._logger.info(f"Found {len(all_files)} relevant files")

        # Separate primary raster files from auxiliary files
        raster_files, auxiliary_files = self._categorize_files(all_files)
        self._logger.info(
            f"Categorized: {len(raster_files)} raster files, {len(auxiliary_files)} auxiliary files"
        )

        # Group files using multiple strategies
        groups = self._create_file_groups(raster_files, auxiliary_files)

        # Sort by confidence score (highest first)
        groups.sort(key=lambda g: g.confidence_score, reverse=True)

        # Apply limit if specified
        if max_groups is not None:
            groups = groups[:max_groups]

        self._logger.info(f"Created {len(groups)} file groups")
        return groups

    def _scan_files(self, folder_path: Path, recursive: bool) -> List[Path]:
        """Scan folder for relevant geospatial files."""
        files = []

        try:
            if recursive:
                # Use rglob for recursive scanning
                pattern = "**/*"
                for file_path in folder_path.rglob("*"):
                    if file_path.is_file() and self._is_relevant_file(file_path):
                        files.append(file_path)
            else:
                # Scan only immediate directory
                for file_path in folder_path.iterdir():
                    if file_path.is_file() and self._is_relevant_file(file_path):
                        files.append(file_path)

        except Exception as e:
            self._logger.error(f"Error scanning folder {folder_path}: {e}")
            raise

        return files

    def _is_relevant_file(self, file_path: Path) -> bool:
        """Check if file is relevant for geospatial processing."""
        # Handle compound extensions like .aux.xml
        full_suffix = "".join(file_path.suffixes).lower()
        simple_suffix = file_path.suffix.lower()

        # Check for raster extensions
        if simple_suffix in self.RASTER_EXTENSIONS:
            return True

        # Check for auxiliary extensions (including compound ones)
        if full_suffix in self.AUXILIARY_EXTENSIONS:
            return True
        if simple_suffix in self.AUXILIARY_EXTENSIONS:
            return True

        # Skip common non-geospatial files
        skip_extensions = {".txt", ".log", ".tmp", ".bak", ".lock", ".db", ".ini"}
        if (
            simple_suffix in skip_extensions
            and full_suffix not in self.AUXILIARY_EXTENSIONS
        ):
            return False

        return False

    def _categorize_files(self, files: List[Path]) -> Tuple[List[Path], List[Path]]:
        """Separate raster files from auxiliary files."""
        raster_files = []
        auxiliary_files = []

        for file_path in files:
            if file_path.suffix.lower() in self.RASTER_EXTENSIONS:
                raster_files.append(file_path)
            else:
                auxiliary_files.append(file_path)

        return raster_files, auxiliary_files

    def _create_file_groups(
        self, raster_files: List[Path], auxiliary_files: List[Path]
    ) -> List[FileGroup]:
        """Create file groups using multiple grouping strategies."""
        groups = []

        # Strategy 1: Basename matching (highest confidence)
        basename_groups = self._group_by_basename(raster_files, auxiliary_files)
        groups.extend(basename_groups)

        # Strategy 2: Geographic proximity (medium confidence)
        # Only for raster files not already grouped
        ungrouped_rasters = self._get_ungrouped_rasters(raster_files, basename_groups)
        geographic_groups = []  # Initialize to empty list
        if ungrouped_rasters:
            geographic_groups = self._group_by_geography(
                ungrouped_rasters, auxiliary_files
            )
            groups.extend(geographic_groups)

        # Strategy 3: Directory-based grouping (lower confidence)
        # For remaining files
        remaining_rasters = self._get_ungrouped_rasters(
            ungrouped_rasters, geographic_groups
        )
        if remaining_rasters:
            directory_groups = self._group_by_directory(
                remaining_rasters, auxiliary_files
            )
            groups.extend(directory_groups)

        return groups

    def _group_by_basename(
        self, raster_files: List[Path], auxiliary_files: List[Path]
    ) -> List[FileGroup]:
        """Group files by matching basenames (highest confidence method)."""
        groups = []

        for raster_file in raster_files:
            # Extract basename (without extension)
            basename = self._extract_basename(raster_file)

            # Find matching auxiliary files
            matching_aux = []
            for aux_file in auxiliary_files:
                aux_basename = self._extract_basename(aux_file)
                if self._basenames_match(basename, aux_basename):
                    matching_aux.append(aux_file)

            # Create group
            group = FileGroup(
                primary_file=raster_file,
                auxiliary_files=matching_aux,
                group_id=f"basename_{basename}",
                scene_name=basename,
                confidence_score=0.9
                if matching_aux
                else 0.7,  # Higher if has aux files
                grouping_method="basename_matching",
            )

            # Try to extract geographic bounds (skip if fails for mock data)
            try:
                metadata = extract_metadata(raster_file)
                group.bounds = metadata.bounds
            except (MetadataExtractorError, Exception) as e:
                self._logger.debug(f"Could not extract metadata for {raster_file}: {e}")
                # For mock/test data, this is expected - just continue without bounds

            # Calculate total file size
            group.file_size_bytes = self._calculate_group_size(group)

            groups.append(group)

        self._logger.info(f"Basename grouping created {len(groups)} groups")
        return groups

    def _group_by_geography(
        self, raster_files: List[Path], auxiliary_files: List[Path]
    ) -> List[FileGroup]:
        """Group files by geographic proximity (medium confidence method)."""
        groups = []

        # Extract metadata for all raster files
        file_metadata = {}
        for raster_file in raster_files:
            try:
                metadata = extract_metadata(raster_file)
                file_metadata[raster_file] = metadata
            except (MetadataExtractorError, Exception) as e:
                self._logger.debug(f"Could not extract metadata for {raster_file}: {e}")

        # Group files with overlapping or adjacent bounds
        processed_files = set()

        for raster_file, metadata in file_metadata.items():
            if raster_file in processed_files:
                continue

            # Find spatially related files
            related_files = [raster_file]
            processed_files.add(raster_file)

            for other_file, other_metadata in file_metadata.items():
                if other_file in processed_files:
                    continue

                if self._bounds_are_related(metadata.bounds, other_metadata.bounds):
                    related_files.append(other_file)
                    processed_files.add(other_file)

            # Create group for spatially related files
            if len(related_files) > 1:
                # Multi-file geographic group
                primary_file = related_files[0]  # Use first as primary
                group = FileGroup(
                    primary_file=primary_file,
                    auxiliary_files=related_files[1:],  # Other rasters as auxiliary
                    group_id=f"geographic_{len(groups)}",
                    scene_name=f"geographic_scene_{len(groups)}",
                    bounds=self._merge_bounds(
                        [file_metadata[f].bounds for f in related_files]
                    ),
                    confidence_score=0.6,
                    grouping_method="geographic_proximity",
                )
            else:
                # Single file group
                group = FileGroup(
                    primary_file=raster_file,
                    auxiliary_files=[],
                    group_id=f"single_{raster_file.stem}",
                    scene_name=raster_file.stem,
                    bounds=metadata.bounds,
                    confidence_score=0.5,
                    grouping_method="single_file",
                )

            group.file_size_bytes = self._calculate_group_size(group)
            groups.append(group)

        self._logger.info(f"Geographic grouping created {len(groups)} groups")
        return groups

    def _group_by_directory(
        self, raster_files: List[Path], auxiliary_files: List[Path]
    ) -> List[FileGroup]:
        """Group remaining files by directory structure (lower confidence method)."""
        groups = []

        # Group by parent directory
        dir_groups = defaultdict(list)
        for raster_file in raster_files:
            dir_groups[raster_file.parent].append(raster_file)

        for directory, files in dir_groups.items():
            # Find auxiliary files in same directory
            dir_aux_files = [f for f in auxiliary_files if f.parent == directory]

            for raster_file in files:
                group = FileGroup(
                    primary_file=raster_file,
                    auxiliary_files=dir_aux_files,
                    group_id=f"directory_{directory.name}_{raster_file.stem}",
                    scene_name=raster_file.stem,
                    confidence_score=0.3,
                    grouping_method="directory_based",
                )

                group.file_size_bytes = self._calculate_group_size(group)
                groups.append(group)

        self._logger.info(f"Directory grouping created {len(groups)} groups")
        return groups

    def _extract_basename(self, file_path: Path) -> str:
        """Extract basename from file path, handling compound extensions."""
        # Handle compound extensions like .aux.xml, .cog.tif
        name = file_path.name

        # Remove known compound extensions
        compound_extensions = [".aux.xml", ".cog.tif", ".cog.tiff"]
        for ext in compound_extensions:
            if name.lower().endswith(ext.lower()):
                return name[: -len(ext)]

        # Remove simple extension
        return file_path.stem

    def _basenames_match(self, basename1: str, basename2: str) -> bool:
        """Check if two basenames match, handling common variations."""
        # Direct match
        if basename1.lower() == basename2.lower():
            return True

        # Handle common suffixes/prefixes that might be added
        # e.g., "scene1" matches "scene1_processed", "scene1_3857"
        patterns = [
            r"_processed$",
            r"_3857$",
            r"_4326$",
            r"_utm$",
            r"_wgs84$",
            r"_reprojected$",
            r"_clipped$",
            r"_masked$",
            r"_final$",
        ]

        base1_clean = basename1.lower()
        base2_clean = basename2.lower()

        for pattern in patterns:
            base1_clean = re.sub(pattern, "", base1_clean)
            base2_clean = re.sub(pattern, "", base2_clean)

        return base1_clean == base2_clean

    def _bounds_are_related(
        self, bounds1: Bounds, bounds2: Bounds, threshold: float = 0.1
    ) -> bool:
        """Check if two bounds are spatially related (overlapping or adjacent)."""
        # Calculate overlap
        overlap_x = max(
            0, min(bounds1.max_x, bounds2.max_x) - max(bounds1.min_x, bounds2.min_x)
        )
        overlap_y = max(
            0, min(bounds1.max_y, bounds2.max_y) - max(bounds1.min_y, bounds2.min_y)
        )

        area1 = (bounds1.max_x - bounds1.min_x) * (bounds1.max_y - bounds1.min_y)
        area2 = (bounds2.max_x - bounds2.min_x) * (bounds2.max_y - bounds2.min_y)
        overlap_area = overlap_x * overlap_y

        # Check for significant overlap
        if overlap_area > 0:
            overlap_ratio = overlap_area / min(area1, area2)
            return overlap_ratio > threshold

        # Check for adjacency (within small distance)
        distance_threshold = threshold * min(
            bounds1.max_x - bounds1.min_x,
            bounds1.max_y - bounds1.min_y,
            bounds2.max_x - bounds2.min_x,
            bounds2.max_y - bounds2.min_y,
        )

        # Check if bounds are adjacent
        x_adjacent = (
            abs(bounds1.max_x - bounds2.min_x) < distance_threshold
            or abs(bounds2.max_x - bounds1.min_x) < distance_threshold
        )
        y_adjacent = (
            abs(bounds1.max_y - bounds2.min_y) < distance_threshold
            or abs(bounds2.max_y - bounds1.min_y) < distance_threshold
        )

        return x_adjacent or y_adjacent

    def _merge_bounds(self, bounds_list: List[Bounds]) -> Bounds:
        """Merge multiple bounds into a single union bounds."""
        if not bounds_list:
            raise ValueError("Cannot merge empty bounds list")

        min_x = min(b.min_x for b in bounds_list)
        min_y = min(b.min_y for b in bounds_list)
        max_x = max(b.max_x for b in bounds_list)
        max_y = max(b.max_y for b in bounds_list)

        return Bounds(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y)

    def _get_ungrouped_rasters(
        self, all_rasters: List[Path], existing_groups: List[FileGroup]
    ) -> List[Path]:
        """Get raster files that haven't been grouped yet."""
        grouped_files = set()
        for group in existing_groups:
            grouped_files.add(group.primary_file)
            grouped_files.update(group.auxiliary_files)

        return [f for f in all_rasters if f not in grouped_files]

    def _calculate_group_size(self, group: FileGroup) -> int:
        """Calculate total size of all files in a group."""
        total_size = 0

        try:
            if group.primary_file.exists():
                total_size += group.primary_file.stat().st_size

            for aux_file in group.auxiliary_files:
                if aux_file.exists():
                    total_size += aux_file.stat().st_size
        except Exception as e:
            self._logger.debug(f"Error calculating group size: {e}")

        return total_size


def create_mock_test_data(output_dir: Path, num_scenes: int = 5) -> List[Path]:
    """
    Create mock geospatial test data for testing the file grouping system.

    Args:
        output_dir: Directory to create test files in
        num_scenes: Number of mock scenes to create

    Returns:
        List of created file paths
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    created_files = []

    # Create mock scenes with various file combinations
    for i in range(num_scenes):
        scene_name = f"scene_{i + 1:03d}"

        # Create primary raster file (mock - just text for testing)
        raster_file = output_dir / f"{scene_name}.jp2"
        raster_file.write_text(f"Mock JP2 data for {scene_name}")
        created_files.append(raster_file)

        # Create projection file
        prj_file = output_dir / f"{scene_name}.prj"
        prj_file.write_text('GEOGCS["WGS 84",DATUM["WGS_1984"]]')
        created_files.append(prj_file)

        # Create world file (every other scene)
        if i % 2 == 0:
            world_file = output_dir / f"{scene_name}.j2w"
            world_file.write_text("1.0\n0.0\n0.0\n-1.0\n100.0\n200.0")
            created_files.append(world_file)

        # Create auxiliary XML (every third scene)
        if i % 3 == 0:
            aux_file = output_dir / f"{scene_name}.aux.xml"
            aux_file.write_text("<PAMDataset><Metadata></Metadata></PAMDataset>")
            created_files.append(aux_file)

    # Create some DEM files with different extensions
    for i in range(2):
        dem_name = f"dem_{i + 1:02d}"

        # Create DEM file
        dem_file = output_dir / f"{dem_name}.tif"
        dem_file.write_text(f"Mock DEM data for {dem_name}")
        created_files.append(dem_file)

        # Create world file
        tfw_file = output_dir / f"{dem_name}.tfw"
        tfw_file.write_text("30.0\n0.0\n0.0\n-30.0\n500000.0\n4000000.0")
        created_files.append(tfw_file)

        # Create projection file
        prj_file = output_dir / f"{dem_name}.prj"
        prj_file.write_text('PROJCS["UTM Zone 33N",GEOGCS["WGS 84"]]')
        created_files.append(prj_file)

    LOGGER.info(f"Created {len(created_files)} mock test files in {output_dir}")
    return created_files
