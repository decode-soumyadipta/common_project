import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, '/Users/soumyadiptadey/Developer/common_project')

# Configure logger to print to stdout
import logging

from src_new.services.ingestion.gdal_pipelines.cog_converter import CogConverter

logging.basicConfig(level=logging.DEBUG)

def main():
    source_path = Path('/Users/soumyadiptadey/Developer/common_project/data/uploads/4f002110-e33d-471e-82ee-2b552d2018e8/02_JAN_NEW_ORTHO-2x0.j2k')
    print(f"Source file exists: {source_path.exists()}")
    
    # Run conversion
    converter = CogConverter()
    result = converter.convert(source_path)
    print("Result:")
    print(f"  Source path: {result.source_path}")
    print(f"  Working path: {result.working_path}")
    print(f"  Converted: {result.converted}")

if __name__ == '__main__':
    main()
