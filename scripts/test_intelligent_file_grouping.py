#!/usr/bin/env python3
"""
Test script for the intelligent file grouping system.

This script creates mock test data and validates the file grouping functionality
to ensure it works correctly on Windows and handles various file combinations.
"""

import logging
import sys
import tempfile
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from core_shared.ingestion.services.file_grouping_service import (
    FileGroupingService, 
    create_mock_test_data
)
from core_shared.ingestion.services.folder_ingestion_service import (
    FolderIngestionService,
    FolderIngestionOptions,
    create_test_folder_structure
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_basic_file_grouping():
    """Test basic file grouping functionality."""
    logger.info("=== Testing Basic File Grouping ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create mock test data
        logger.info(f"Creating mock test data in {temp_path}")
        created_files = create_mock_test_data(temp_path, num_scenes=5)
        logger.info(f"Created {len(created_files)} test files")
        
        # Test file grouping
        grouping_service = FileGroupingService()
        file_groups = grouping_service.group_files_in_folder(temp_path, recursive=False)
        
        logger.info(f"Found {len(file_groups)} file groups")
        
        # Validate results
        assert len(file_groups) > 0, "Should find at least one file group"
        
        for i, group in enumerate(file_groups):
            logger.info(f"Group {i+1}: {group.scene_name}")
            logger.info(f"  - Primary: {group.primary_file.name}")
            logger.info(f"  - Auxiliary: {[f.name for f in group.auxiliary_files]}")
            logger.info(f"  - Confidence: {group.confidence_score:.2f}")
            logger.info(f"  - Method: {group.grouping_method}")
            logger.info(f"  - Size: {group.file_size_bytes} bytes")
            
            # Validate group structure
            assert group.primary_file.exists(), f"Primary file should exist: {group.primary_file}"
            assert group.confidence_score >= 0.0, "Confidence score should be non-negative"
            assert group.grouping_method, "Grouping method should be specified"
            
            for aux_file in group.auxiliary_files:
                assert aux_file.exists(), f"Auxiliary file should exist: {aux_file}"
        
        logger.info("✓ Basic file grouping test passed")


def test_comprehensive_folder_structure():
    """Test with comprehensive folder structure including subdirectories."""
    logger.info("=== Testing Comprehensive Folder Structure ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create comprehensive test structure
        logger.info(f"Creating comprehensive test structure in {temp_path}")
        test_folder = create_test_folder_structure(temp_path)
        
        # Test recursive grouping
        grouping_service = FileGroupingService()
        file_groups = grouping_service.group_files_in_folder(test_folder, recursive=True)
        
        logger.info(f"Found {len(file_groups)} file groups in comprehensive structure")
        
        # Analyze grouping methods
        method_counts = {}
        confidence_distribution = {"high": 0, "medium": 0, "low": 0}
        
        for group in file_groups:
            method_counts[group.grouping_method] = method_counts.get(group.grouping_method, 0) + 1
            
            if group.confidence_score >= 0.8:
                confidence_distribution["high"] += 1
            elif group.confidence_score >= 0.5:
                confidence_distribution["medium"] += 1
            else:
                confidence_distribution["low"] += 1
        
        logger.info(f"Grouping methods: {method_counts}")
        logger.info(f"Confidence distribution: {confidence_distribution}")
        
        # Validate that we found groups with different methods
        assert len(method_counts) > 0, "Should use at least one grouping method"
        assert confidence_distribution["high"] + confidence_distribution["medium"] > 0, "Should have some high/medium confidence groups"
        
        # Show sample groups
        high_confidence_groups = [g for g in file_groups if g.confidence_score >= 0.5]
        logger.info(f"High-confidence groups ({len(high_confidence_groups)}):")
        for group in high_confidence_groups[:5]:  # Show first 5
            aux_count = len(group.auxiliary_files)
            logger.info(f"  - {group.scene_name} (conf: {group.confidence_score:.2f}, aux: {aux_count})")
        
        logger.info("✓ Comprehensive folder structure test passed")


def test_windows_path_handling():
    """Test Windows-specific path handling."""
    logger.info("=== Testing Windows Path Handling ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create files with Windows-problematic names
        problematic_files = [
            "file with spaces.tif",
            "file-with-dashes.jp2", 
            "file_with_underscores.tiff",
            "file.with.dots.tif",
            "file(with)parentheses.jp2",
            "file[with]brackets.tif"
        ]
        
        created_files = []
        for filename in problematic_files:
            # Create primary file
            file_path = temp_path / filename
            file_path.write_text(f"Mock data for {filename}")
            created_files.append(file_path)
            
            # Create corresponding auxiliary files
            stem = file_path.stem
            
            # Projection file
            prj_file = temp_path / f"{stem}.prj"
            prj_file.write_text('GEOGCS["WGS 84"]')
            created_files.append(prj_file)
            
            # World file
            if file_path.suffix.lower() == '.tif':
                world_file = temp_path / f"{stem}.tfw"
            elif file_path.suffix.lower() == '.jp2':
                world_file = temp_path / f"{stem}.j2w"
            else:
                world_file = temp_path / f"{stem}.tfw"
            
            world_file.write_text("1.0\n0.0\n0.0\n-1.0\n100.0\n200.0")
            created_files.append(world_file)
        
        logger.info(f"Created {len(created_files)} files with problematic names")
        
        # Test grouping with problematic filenames
        grouping_service = FileGroupingService()
        file_groups = grouping_service.group_files_in_folder(temp_path, recursive=False)
        
        logger.info(f"Successfully grouped {len(file_groups)} groups with problematic filenames")
        
        # Validate that all primary files were found and grouped
        primary_files = {group.primary_file.name for group in file_groups}
        expected_primary_files = set(problematic_files)
        
        assert primary_files == expected_primary_files, f"Expected {expected_primary_files}, got {primary_files}"
        
        # Validate that auxiliary files were properly associated
        for group in file_groups:
            logger.info(f"Group: {group.scene_name}")
            logger.info(f"  - Primary: {group.primary_file.name}")
            logger.info(f"  - Auxiliary: {[f.name for f in group.auxiliary_files]}")
            
            # Should have at least projection file
            aux_names = [f.name for f in group.auxiliary_files]
            expected_prj = f"{group.primary_file.stem}.prj"
            assert expected_prj in aux_names, f"Should have projection file {expected_prj}"
        
        logger.info("✓ Windows path handling test passed")


def test_folder_ingestion_service():
    """Test the complete folder ingestion service."""
    logger.info("=== Testing Folder Ingestion Service ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test data
        test_folder = create_test_folder_structure(temp_path)
        
        # Test folder statistics (without actual ingestion)
        ingestion_service = FolderIngestionService()
        stats = ingestion_service.get_folder_statistics(test_folder, recursive=True)
        
        logger.info("Folder statistics:")
        logger.info(f"  - Total groups: {stats['total_groups']}")
        logger.info(f"  - Total files: {stats['total_files']}")
        logger.info(f"  - Total size: {stats['total_size_mb']} MB")
        logger.info(f"  - Confidence distribution: {stats['confidence_distribution']}")
        logger.info(f"  - Method distribution: {stats['method_distribution']}")
        
        # Validate statistics
        assert stats['total_groups'] > 0, "Should find file groups"
        assert stats['total_files'] > 0, "Should find files"
        assert 'confidence_distribution' in stats, "Should have confidence distribution"
        assert 'method_distribution' in stats, "Should have method distribution"
        
        # Show sample groups
        if 'sample_groups' in stats:
            logger.info("Sample groups:")
            for group in stats['sample_groups']:
                logger.info(f"  - {group['scene_name']} (conf: {group['confidence_score']:.2f}, size: {group['size_mb']} MB)")
        
        logger.info("✓ Folder ingestion service test passed")


def test_error_handling():
    """Test error handling with invalid inputs."""
    logger.info("=== Testing Error Handling ===")
    
    grouping_service = FileGroupingService()
    
    # Test with non-existent folder
    try:
        non_existent = Path("/non/existent/folder")
        file_groups = grouping_service.group_files_in_folder(non_existent)
        assert False, "Should raise exception for non-existent folder"
    except ValueError as e:
        logger.info(f"✓ Correctly handled non-existent folder: {e}")
    
    # Test with empty folder
    with tempfile.TemporaryDirectory() as temp_dir:
        empty_folder = Path(temp_dir)
        file_groups = grouping_service.group_files_in_folder(empty_folder)
        assert len(file_groups) == 0, "Empty folder should return no groups"
        logger.info("✓ Correctly handled empty folder")
    
    # Test folder ingestion service error handling
    ingestion_service = FolderIngestionService()
    
    # Test statistics for non-existent folder
    stats = ingestion_service.get_folder_statistics(Path("/non/existent"))
    assert 'error' in stats, "Should return error for non-existent folder"
    logger.info(f"✓ Correctly handled statistics error: {stats['error']}")
    
    logger.info("✓ Error handling test passed")


def main():
    """Run all tests."""
    logger.info("Starting intelligent file grouping tests...")
    
    try:
        test_basic_file_grouping()
        test_comprehensive_folder_structure()
        test_windows_path_handling()
        test_folder_ingestion_service()
        test_error_handling()
        
        logger.info("🎉 All tests passed successfully!")
        return 0
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())