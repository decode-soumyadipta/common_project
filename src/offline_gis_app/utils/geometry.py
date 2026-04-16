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
    # Expects "POLYGON((x1 y1,x2 y2,...))" with axis-aligned envelope points.
    raw = wkt.strip().removeprefix("POLYGON((").removesuffix("))")
    points = []
    for token in raw.split(","):
        x_str, y_str = token.strip().split()
        points.append((float(x_str), float(y_str)))
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return Bounds(min(xs), min(ys), max(xs), max(ys))
