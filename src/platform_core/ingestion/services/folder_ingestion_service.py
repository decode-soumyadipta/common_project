"""
Enhanced folder ingestion service with intelligent file grouping and robust error handling.

This service provides:
1. Recursive folder scanning with intelligent file grouping
2. Geographic scene detection and grouping
3. Robust Windows path handling
4. Progress tracking and detailed logging
5. Error recovery and partial success handling
6. Support for various geospatial file combinations
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Callable, Tuple, Any

from sqlalchemy.orm import Session

from platform_core.ingestion.services.file_grouping_service import (
    FileGroupingService,
    FileGroup,
)
from platform_core.ingestion.services.ingest_service import register_raster
from platform_core.ingestion.services.metadata_extractor import MetadataExtractorError

LOGGER = logging.getLogger("services.folder_ingestion")


@dataclass
class FolderIngestionResult:
    """Result of folder ingestion operation."""

    total_groups: int = 0
    """Total number of file groups found"""

    processed_groups: int = 0
    """Number of groups successfully processed"""

    failed_groups: int = 0
    """Number of groups that failed processing"""

    skipped_groups: int = 0
    """Number of groups skipped (e.g., already processed)"""

    total_files: int = 0
    """Total number of files in all groups"""

    processed_files: int = 0
    """Number of files successfully processed"""

    failed_files: int = 0
    """Number of files that failed processing"""

    elapsed_seconds: float = 0.0
    """Total processing time"""

    success_rate: float = 0.0
    """Success rate (processed_groups / total_groups)"""

    errors: List[str] = field(default_factory=list)
    """List of error messages encountered"""

    processed_assets: List[Dict[str, Any]] = field(default_factory=list)
    """List of successfully processed asset metadata"""

    group_results: List[Dict[str, Any]] = field(default_factory=list)
    """Detailed results for each group"""


@dataclass
class FolderIngestionOptions:
    """Options for folder ingestion."""

    recursive: bool = True
    """Whether to scan subdirectories recursively"""

    max_groups: Optional[int] = None
    """Maximum number of groups to process (None for all)"""

    skip_existing: bool = True
    """Whether to skip files already in the catalog"""

    continue_on_error: bool = True
    """Whether to continue processing after individual failures"""

    group_by_geography: bool = True
    """Whether to enable geographic grouping"""

    min_confidence_score: float = 0.3
    """Minimum confidence score for file groups"""

    progress_callback: Optional[Callable[[str], None]] = None
    """Callback for progress updates"""

    stage_callback: Optional[Callable[[str], None]] = None
    """Callback for stage completion updates"""


class FolderIngestionService:
    """Service for robust folder ingestion with intelligent file grouping."""

    def __init__(self):
        self._logger = LOGGER
        self._grouping_service = FileGroupingService()

    def ingest_folder(
        self,
        folder_path: Path,
        session: Session,
        options: Optional[FolderIngestionOptions] = None,
    ) -> FolderIngestionResult:
        """
        Ingest all geospatial files in a folder with intelligent grouping.

        Args:
            folder_path: Path to folder to ingest
            session: Database session for catalog operations
            options: Ingestion options (uses defaults if None)

        Returns:
            FolderIngestionResult with detailed processing information
        """
        if options is None:
            options = FolderIngestionOptions()

        start_time = time.time()
        result = FolderIngestionResult()

        try:
            self._logger.info(f"Starting folder ingestion: {folder_path}")
            self._report_progress(options, f"Scanning folder: {folder_path}")

            # Validate folder path
            if not folder_path.exists():
                raise ValueError(f"Folder does not exist: {folder_path}")
            if not folder_path.is_dir():
                raise ValueError(f"Path is not a directory: {folder_path}")

            # Group files intelligently
            self._report_progress(options, "Analyzing and grouping files...")
            file_groups = self._grouping_service.group_files_in_folder(
                folder_path=folder_path,
                recursive=options.recursive,
                max_groups=options.max_groups,
            )

            # Filter by confidence score
            file_groups = [
                group
                for group in file_groups
                if group.confidence_score >= options.min_confidence_score
            ]

            result.total_groups = len(file_groups)
            result.total_files = sum(
                1 + len(group.auxiliary_files) for group in file_groups
            )

            self._logger.info(
                f"Found {result.total_groups} file groups with {result.total_files} total files"
            )
            self._report_progress(
                options,
                f"Found {result.total_groups} file groups ({result.total_files} files)",
            )

            # Process each group
            for i, group in enumerate(file_groups):
                try:
                    self._report_progress(
                        options,
                        f"Processing group {i + 1}/{result.total_groups}: {group.scene_name}",
                    )

                    group_result = self._process_file_group(group, session, options)
                    result.group_results.append(group_result)

                    if group_result["success"]:
                        result.processed_groups += 1
                        result.processed_files += group_result["files_processed"]
                        if group_result.get("asset"):
                            result.processed_assets.append(group_result["asset"])
                    else:
                        result.failed_groups += 1
                        result.failed_files += group_result["files_failed"]
                        result.errors.extend(group_result["errors"])

                        if not options.continue_on_error:
                            self._logger.error(
                                f"Stopping ingestion due to error in group: {group.scene_name}"
                            )
                            break

                except Exception as e:
                    error_msg = (
                        f"Unexpected error processing group {group.scene_name}: {e}"
                    )
                    self._logger.error(error_msg, exc_info=True)
                    result.errors.append(error_msg)
                    result.failed_groups += 1

                    if not options.continue_on_error:
                        break

            # Calculate final statistics
            result.elapsed_seconds = time.time() - start_time
            if result.total_groups > 0:
                result.success_rate = result.processed_groups / result.total_groups

            self._logger.info(
                f"Folder ingestion completed: {result.processed_groups}/{result.total_groups} groups processed "
                f"({result.success_rate:.1%} success rate) in {result.elapsed_seconds:.1f}s"
            )

            self._report_progress(
                options,
                f"Completed: {result.processed_groups}/{result.total_groups} groups processed "
                f"({result.success_rate:.1%} success)",
            )

        except Exception as e:
            error_msg = f"Folder ingestion failed: {e}"
            self._logger.error(error_msg, exc_info=True)
            result.errors.append(error_msg)
            result.elapsed_seconds = time.time() - start_time

        return result

    def _process_file_group(
        self, group: FileGroup, session: Session, options: FolderIngestionOptions
    ) -> Dict[str, Any]:
        """Process a single file group."""
        group_result = {
            "group_id": group.group_id,
            "scene_name": group.scene_name,
            "primary_file": str(group.primary_file),
            "auxiliary_files": [str(f) for f in group.auxiliary_files],
            "confidence_score": group.confidence_score,
            "grouping_method": group.grouping_method,
            "success": False,
            "files_processed": 0,
            "files_failed": 0,
            "errors": [],
            "asset": None,
            "processing_time": 0.0,
        }

        start_time = time.time()

        try:
            self._logger.info(
                f"Processing file group: {group.scene_name} (method: {group.grouping_method})"
            )

            # Check if primary file already exists in catalog
            if options.skip_existing and self._file_exists_in_catalog(
                group.primary_file, session
            ):
                self._logger.info(f"Skipping existing file: {group.primary_file}")
                group_result["success"] = True
                group_result["files_processed"] = 1 + len(group.auxiliary_files)
                return group_result

            # Validate primary file exists and is readable
            if not group.primary_file.exists():
                error_msg = f"Primary file not found: {group.primary_file}"
                group_result["errors"].append(error_msg)
                group_result["files_failed"] = 1 + len(group.auxiliary_files)
                return group_result

            # Process the primary raster file through the ingestion pipeline
            self._logger.info(f"Ingesting primary file: {group.primary_file}")

            # Use the existing register_raster function with progress callback
            def progress_callback(message: str) -> None:
                self._logger.debug(f"[{group.scene_name}] {message}")
                if options.progress_callback:
                    options.progress_callback(f"[{group.scene_name}] {message}")

            def stage_callback(stage: str) -> None:
                self._logger.info(f"[{group.scene_name}] Completed stage: {stage}")
                if options.stage_callback:
                    options.stage_callback(f"[{group.scene_name}] {stage}")

            # Register the raster in the catalog
            asset = register_raster(
                path=group.primary_file,
                session=session,
                progress_callback=progress_callback,
                stage_checkpoint_callback=stage_callback,
            )

            group_result["success"] = True
            group_result["files_processed"] = 1 + len(group.auxiliary_files)
            group_result["asset"] = asset

            self._logger.info(f"Successfully processed group: {group.scene_name}")

        except MetadataExtractorError as e:
            error_msg = f"Metadata extraction failed for {group.primary_file}: {e}"
            self._logger.error(error_msg)
            group_result["errors"].append(error_msg)
            group_result["files_failed"] = 1 + len(group.auxiliary_files)

        except Exception as e:
            error_msg = f"Processing failed for {group.primary_file}: {e}"
            self._logger.error(error_msg, exc_info=True)
            group_result["errors"].append(error_msg)
            group_result["files_failed"] = 1 + len(group.auxiliary_files)

        finally:
            group_result["processing_time"] = time.time() - start_time

        return group_result

    def _file_exists_in_catalog(self, file_path: Path, session: Session) -> bool:
        """Check if a file already exists in the catalog."""
        try:
            from platform_core.db.models import RasterAsset

            # Normalize path for comparison
            normalized_path = str(file_path.resolve())

            existing = (
                session.query(RasterAsset)
                .filter(RasterAsset.file_path == normalized_path)
                .first()
            )

            return existing is not None

        except Exception as e:
            self._logger.debug(f"Error checking catalog for {file_path}: {e}")
            return False

    def _report_progress(self, options: FolderIngestionOptions, message: str) -> None:
        """Report progress through callback if available."""
        if options.progress_callback:
            options.progress_callback(message)

    def get_folder_statistics(
        self, folder_path: Path, recursive: bool = True
    ) -> Dict[str, Any]:
        """
        Get statistics about files in a folder without processing them.

        Args:
            folder_path: Path to analyze
            recursive: Whether to scan recursively

        Returns:
            Dictionary with folder statistics
        """
        try:
            self._logger.info(f"Analyzing folder statistics: {folder_path}")

            # Group files to get statistics
            file_groups = self._grouping_service.group_files_in_folder(
                folder_path=folder_path, recursive=recursive
            )

            # Calculate statistics
            total_files = sum(1 + len(group.auxiliary_files) for group in file_groups)
            total_size = sum(group.file_size_bytes for group in file_groups)

            # Group by confidence and method
            confidence_distribution = {}
            method_distribution = {}

            for group in file_groups:
                # Confidence buckets
                if group.confidence_score >= 0.8:
                    bucket = "high (≥0.8)"
                elif group.confidence_score >= 0.5:
                    bucket = "medium (0.5-0.8)"
                else:
                    bucket = "low (<0.5)"

                confidence_distribution[bucket] = (
                    confidence_distribution.get(bucket, 0) + 1
                )
                method_distribution[group.grouping_method] = (
                    method_distribution.get(group.grouping_method, 0) + 1
                )

            return {
                "folder_path": str(folder_path),
                "total_groups": len(file_groups),
                "total_files": total_files,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "confidence_distribution": confidence_distribution,
                "method_distribution": method_distribution,
                "sample_groups": [
                    {
                        "scene_name": group.scene_name,
                        "primary_file": group.primary_file.name,
                        "auxiliary_count": len(group.auxiliary_files),
                        "confidence_score": group.confidence_score,
                        "grouping_method": group.grouping_method,
                        "size_mb": round(group.file_size_bytes / (1024 * 1024), 2),
                    }
                    for group in file_groups[:5]  # First 5 groups as samples
                ],
            }

        except Exception as e:
            self._logger.error(f"Error analyzing folder statistics: {e}", exc_info=True)
            return {"error": str(e), "folder_path": str(folder_path)}


def create_test_folder_structure(base_dir: Path) -> Path:
    """
    Create a comprehensive test folder structure for testing the folder ingestion system.

    Args:
        base_dir: Base directory to create test structure in

    Returns:
        Path to the created test folder
    """
    test_dir = base_dir / "test_geospatial_folder"
    test_dir.mkdir(parents=True, exist_ok=True)

    # Create various subdirectories
    subdirs = [
        test_dir / "imagery" / "landsat",
        test_dir / "imagery" / "sentinel",
        test_dir / "dem" / "srtm",
        test_dir / "dem" / "aster",
        test_dir / "mixed_data",
        test_dir / "problematic_files",
    ]

    for subdir in subdirs:
        subdir.mkdir(parents=True, exist_ok=True)

    # Create mock files with various combinations
    test_files = []

    # Landsat imagery with proper auxiliary files
    for i in range(3):
        scene_name = f"LC08_L1TP_123045_20230{i + 1:02d}15_20230{i + 1:02d}25_02_T1"
        base_path = subdirs[0] / scene_name

        # Main imagery file
        img_file = base_path.with_suffix(".tif")
        img_file.write_text(f"Mock Landsat imagery data for {scene_name}")
        test_files.append(img_file)

        # Projection file
        prj_file = base_path.with_suffix(".prj")
        prj_file.write_text('PROJCS["UTM Zone 33N",GEOGCS["WGS 84"]]')
        test_files.append(prj_file)

        # World file
        tfw_file = base_path.with_suffix(".tfw")
        tfw_file.write_text("30.0\n0.0\n0.0\n-30.0\n500000.0\n4000000.0")
        test_files.append(tfw_file)

        # Auxiliary XML
        aux_file = Path(str(base_path) + ".aux.xml")
        aux_file.write_text(
            '<PAMDataset><Metadata><MDI key="AREA_OR_POINT">Area</MDI></Metadata></PAMDataset>'
        )
        test_files.append(aux_file)

    # Sentinel imagery with JP2 format
    for i in range(2):
        scene_name = f"S2A_MSIL1C_20230{i + 1:02d}15T123456_N0509_R007_T33UUP_20230{i + 1:02d}15T123456"
        base_path = subdirs[1] / scene_name

        # JP2 file
        jp2_file = base_path.with_suffix(".jp2")
        jp2_file.write_text(f"Mock Sentinel-2 JP2 data for {scene_name}")
        test_files.append(jp2_file)

        # Projection file
        prj_file = base_path.with_suffix(".prj")
        prj_file.write_text('PROJCS["UTM Zone 33N",GEOGCS["WGS 84"]]')
        test_files.append(prj_file)

        # World file for JP2
        j2w_file = base_path.with_suffix(".j2w")
        j2w_file.write_text("10.0\n0.0\n0.0\n-10.0\n600000.0\n5000000.0")
        test_files.append(j2w_file)

    # DEM files with various formats
    dem_files = [
        ("srtm_30m_dem", subdirs[2]),
        ("aster_gdem_v3", subdirs[3]),
        ("local_lidar_dem", subdirs[4]),
    ]

    for dem_name, dem_dir in dem_files:
        base_path = dem_dir / dem_name

        # DEM file
        dem_file = base_path.with_suffix(".tif")
        dem_file.write_text(f"Mock DEM data for {dem_name}")
        test_files.append(dem_file)

        # World file
        tfw_file = base_path.with_suffix(".tfw")
        tfw_file.write_text("30.0\n0.0\n0.0\n-30.0\n500000.0\n4000000.0")
        test_files.append(tfw_file)

        # Projection file
        prj_file = base_path.with_suffix(".prj")
        prj_file.write_text('PROJCS["UTM Zone 33N",GEOGCS["WGS 84"]]')
        test_files.append(prj_file)

    # Files with problematic names (spaces, special characters)
    problematic_dir = subdirs[5]
    problematic_files = [
        "file with spaces.tif",
        "file-with-dashes.jp2",
        "file_with_underscores.tiff",
        "file.with.dots.tif",
        "file(with)parentheses.jp2",
    ]

    for filename in problematic_files:
        file_path = problematic_dir / filename
        file_path.write_text(f"Mock data for problematic filename: {filename}")
        test_files.append(file_path)

        # Add corresponding projection file
        prj_name = Path(filename).stem + ".prj"
        prj_path = problematic_dir / prj_name
        prj_path.write_text('GEOGCS["WGS 84",DATUM["WGS_1984"]]')
        test_files.append(prj_path)

    LOGGER.info(
        f"Created test folder structure with {len(test_files)} files in {test_dir}"
    )
    return test_dir
