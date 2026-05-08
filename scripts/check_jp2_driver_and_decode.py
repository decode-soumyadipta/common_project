#!/usr/bin/env python3
"""
Check GDAL JPEG2000 driver availability and simulate JP2/J2K decode reads.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


JP2_EXTS = (".jp2", ".j2k")


def _find_sample_file() -> Path | None:
    data_root = Path("data_test")
    if data_root.exists():
        for ext in JP2_EXTS:
            hits = list(data_root.rglob(f"*{ext}"))
            if hits:
                return hits[0]
    return None


def _check_gdal_drivers() -> tuple[bool, str | None, list[str]]:
    try:
        from osgeo import gdal
    except Exception as exc:  # noqa: BLE001
        return False, f"GDAL import failed: {exc}", []

    gdal.UseExceptions()
    drivers: list[str] = []
    for i in range(gdal.GetDriverCount()):
        driver = gdal.GetDriver(i)
        if not driver:
            continue
        name = driver.ShortName or ""
        if "JP2" in name.upper() or "JPEG2000" in name.upper():
            drivers.append(name)

    return True, None, sorted(set(drivers))


def _open_dataset(path: Path):
    from osgeo import gdal

    gdal.UseExceptions()
    return gdal.Open(str(path), gdal.GA_ReadOnly)


def _simulate_stream_reads(ds, *, samples: int, window: int) -> list[tuple[int, int, str]]:
    width = int(ds.RasterXSize)
    height = int(ds.RasterYSize)
    if width <= 0 or height <= 0:
        return [(0, 0, "invalid raster dimensions")]

    win = max(1, min(int(window), width, height))

    points: list[tuple[int, int]] = [
        (0, 0),
        (max(0, width - win), 0),
        (0, max(0, height - win)),
        (max(0, width - win), max(0, height - win)),
        (max(0, (width - win) // 2), max(0, (height - win) // 2)),
    ]

    import random

    while len(points) < max(5, samples):
        x = random.randint(0, max(0, width - win))
        y = random.randint(0, max(0, height - win))
        points.append((x, y))

    failures: list[tuple[int, int, str]] = []
    for x, y in points[: max(5, samples)]:
        try:
            data = ds.ReadRaster(x, y, win, win, buf_xsize=1, buf_ysize=1)
            if data is None:
                failures.append((x, y, "ReadRaster returned None"))
        except Exception as exc:  # noqa: BLE001
            failures.append((x, y, str(exc)))

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check JPEG2000 driver availability and simulate decode reads",
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to a .jp2 or .j2k file (default: first under data_test)",
    )
    parser.add_argument("--samples", type=int, default=8, help="Number of read probes")
    parser.add_argument("--window", type=int, default=256, help="Probe window size")
    args = parser.parse_args()

    path = Path(args.path) if args.path else _find_sample_file()
    if path is None:
        print("ERROR: No input file provided and no JP2/J2K found under data_test")
        return 1

    path = path.expanduser().resolve()
    print(f"Input: {path}")

    if not path.exists():
        print("ERROR: File does not exist")
        return 1

    if path.suffix.lower() not in JP2_EXTS:
        print("ERROR: File must be .jp2 or .j2k")
        return 1

    gdal_on_path = shutil.which("gdal_translate") is not None
    print(f"gdal_translate on PATH: {gdal_on_path}")

    ok, err, drivers = _check_gdal_drivers()
    if not ok:
        print(f"ERROR: {err}")
        return 2

    if not drivers:
        print("ERROR: No JPEG2000 drivers found in GDAL")
        return 2

    print("JPEG2000 drivers:")
    for name in drivers:
        print(f"  - {name}")

    try:
        ds = _open_dataset(path)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: GDAL open failed: {exc}")
        return 3

    if ds is None:
        print("ERROR: GDAL returned no dataset")
        return 3

    print(f"Driver: {ds.GetDriver().ShortName}")
    print(f"Size: {ds.RasterXSize} x {ds.RasterYSize}")
    print(f"Bands: {ds.RasterCount}")
    print(f"CRS: {ds.GetProjection()[:60]}{'...' if len(ds.GetProjection()) > 60 else ''}")

    failures = _simulate_stream_reads(
        ds,
        samples=max(5, int(args.samples)),
        window=max(1, int(args.window)),
    )

    if failures:
        print("Decode probe failures:")
        for x, y, message in failures:
            print(f"  - at ({x},{y}): {message}")
        return 4

    print("Decode probes: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
