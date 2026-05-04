from osgeo import gdal
import os

def convert_jp2_to_j2k(input_path, output_path):
    """
    Convert a JP2 (JPEG 2000) satellite image to J2K format using GDAL.

    Args:
        input_path  : Path to the input .jp2 file
        output_path : Path to the output .j2k file
    """

    # Register all GDAL drivers
    gdal.AllRegister()

    # Open the input JP2 file
    print(f"Opening input file: {input_path}")
    src_ds = gdal.Open(input_path, gdal.GA_ReadOnly)

    if src_ds is None:
        raise FileNotFoundError(f"Could not open input file: {input_path}")

    # Print source image info
    print(f"  Driver     : {src_ds.GetDriver().ShortName}")
    print(f"  Size       : {src_ds.RasterXSize} x {src_ds.RasterYSize} pixels")
    print(f"  Bands      : {src_ds.RasterCount}")
    print(f"  Projection : {src_ds.GetProjection()[:60]}..." if src_ds.GetProjection() else "  Projection : None")

    # Get the JPEG2000 driver for writing .j2k
    driver = gdal.GetDriverByName("JPEG2000")

    if driver is None:
        # Fallback: try JP2OpenJPEG or JP2ECW drivers
        for drv_name in ["JP2OpenJPEG", "JP2ECW", "JP2KAK"]:
            driver = gdal.GetDriverByName(drv_name)
            if driver:
                print(f"  Using driver: {drv_name}")
                break

    if driver is None:
        raise RuntimeError(
            "No JPEG2000-compatible write driver found. "
            "Ensure GDAL is built with OpenJPEG, ECW, or Kakadu support."
        )

    # Creation options for J2K output
    creation_options = [
        "CODEC=J2K",          # Use raw J2K codec (no JP2 container/metadata box)
        "QUALITY=100",        # Lossless-like quality (adjust as needed: 1–100)
        "REVERSIBLE=YES",     # Reversible (lossless) wavelet transform
        "RESOLUTIONS=6",      # Number of DWT resolution levels
    ]

    print(f"\nConverting to J2K: {output_path}")

    # Perform the conversion using CreateCopy
    out_ds = driver.CreateCopy(
        output_path,
        src_ds,
        strict=0,                        # 0 = non-strict (allow minor issues)
        options=creation_options,
        callback=gdal.TermProgress_nocb  # Show progress in terminal
    )

    if out_ds is None:
        raise RuntimeError(
            f"Conversion failed. GDAL Error: {gdal.GetLastErrorMsg()}"
        )

    # Flush and close datasets
    out_ds.FlushCache()
    out_ds = None
    src_ds = None

    # Verify output
    file_size = os.path.getsize(output_path) / (1024 * 1024)
    print(f"\nConversion successful!")
    print(f"  Output file : {output_path}")
    print(f"  File size   : {file_size:.2f} MB")


# ── Entry Point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":

    input_jp2  = r"C:\Users\Jitaditya Ray\common_project\data_test\T44SND_20250706T052241_AOT_10m.jp2"
    output_j2k = r"C:\Users\Jitaditya Ray\common_project\data_test\T44SND_20250706T052241_AOT_10m.j2k"

    convert_jp2_to_j2k(input_jp2, output_j2k)