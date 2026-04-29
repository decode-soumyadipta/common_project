#!/usr/bin/env python3
"""
Filter duplicate files from the data_test/images directory.
This script identifies and optionally removes duplicate processed files.
"""

from pathlib import Path
import shutil

def analyze_files():
    """Analyze files in data_test/images and identify duplicates."""
    
    images_dir = Path("data_test/images")
    if not images_dir.exists():
        print("❌ data_test/images directory not found")
        return
    
    files = list(images_dir.glob("*.tif"))
    print(f"📁 Found {len(files)} .tif files")
    
    # Group files by base name
    file_groups = {}
    for file_path in files:
        # Extract base name (remove processing suffixes)
        name = file_path.stem
        
        # Remove common suffixes
        base_name = name
        for suffix in ["_3857", ".cog", "_cog"]:
            base_name = base_name.replace(suffix, "")
        
        if base_name not in file_groups:
            file_groups[base_name] = []
        file_groups[base_name].append(file_path)
    
    print(f"\n📊 Analysis Results:")
    print(f"   Unique base files: {len(file_groups)}")
    
    original_files = []
    processed_files = []
    
    for base_name, group in file_groups.items():
        print(f"\n🔍 {base_name}:")
        
        # Sort by processing stage (original first)
        group.sort(key=lambda p: (
            "_3857" in p.stem,  # Reprojected files last
            ".cog" in p.stem,   # COG files after original
            p.stem              # Alphabetical
        ))
        
        for i, file_path in enumerate(group):
            is_original = not any(suffix in file_path.stem for suffix in ["_3857", ".cog"])
            marker = "📄" if is_original else "🔄"
            print(f"   {marker} {file_path.name}")
            
            if is_original:
                original_files.append(file_path)
            else:
                processed_files.append(file_path)
    
    print(f"\n📈 Summary:")
    print(f"   Original files: {len(original_files)}")
    print(f"   Processed files: {len(processed_files)}")
    print(f"   Total files: {len(files)}")
    
    return original_files, processed_files

def create_filtered_directory():
    """Create a filtered directory with only original files."""
    
    original_files, processed_files = analyze_files()
    
    # Create filtered directory
    filtered_dir = Path("data_test/images_filtered")
    if filtered_dir.exists():
        shutil.rmtree(filtered_dir)
    filtered_dir.mkdir(parents=True)
    
    print(f"\n📁 Creating filtered directory: {filtered_dir}")
    
    for file_path in original_files:
        dest_path = filtered_dir / file_path.name
        shutil.copy2(file_path, dest_path)
        print(f"   ✅ Copied: {file_path.name}")
    
    print(f"\n🎉 Filtered directory created with {len(original_files)} original files")
    print(f"   Use this directory for ingestion to avoid duplicates")
    
    return filtered_dir

if __name__ == "__main__":
    print("🔍 File Duplicate Analysis")
    print("=" * 50)
    
    # Analyze files
    analyze_files()
    
    # Ask user if they want to create filtered directory
    response = input("\n❓ Create filtered directory with only original files? (y/n): ")
    if response.lower() in ['y', 'yes']:
        create_filtered_directory()
    else:
        print("ℹ️ Skipping filtered directory creation")