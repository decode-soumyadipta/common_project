from dataclasses import dataclass


@dataclass(frozen=True)
class Bounds:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def centroid(self) -> tuple[float, float]:
        return ((self.min_x + self.max_x) / 2.0, (self.min_y + self.max_y) / 2.0)

    def to_wkt_polygon(self) -> str:
        return (
            "POLYGON(("
            f"{self.min_x} {self.min_y},"
            f"{self.max_x} {self.min_y},"
            f"{self.max_x} {self.max_y},"
            f"{self.min_x} {self.max_y},"
            f"{self.min_x} {self.min_y}"
            "))"
        )


def parse_bounds_wkt_polygon(wkt: str) -> Bounds:
    """Parse WKT polygon string into Bounds, robustly handling spaces and formatting."""
    # Remove POLYGON, Z, M and all parenthesis robustly
    raw = wkt.upper().replace("POLYGON", "").replace("Z", "").replace("M", "")
    raw = raw.replace("(", "").replace(")", "").strip()

    points = []
    for token in raw.split(","):
        parts = token.strip().split()
        if len(parts) >= 2:
            points.append((float(parts[0]), float(parts[1])))

    if not points:
        return Bounds(0.0, 0.0, 0.0, 0.0)

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return Bounds(min(xs), min(ys), max(xs), max(ys))
