from core_shared.utils.geometry import Bounds


def test_bounds_centroid():
    b = Bounds(min_x=0, min_y=0, max_x=10, max_y=20)
    assert b.centroid() == (5.0, 10.0)


def test_bounds_wkt_polygon():
    b = Bounds(min_x=1, min_y=2, max_x=3, max_y=4)
    assert b.to_wkt_polygon() == "POLYGON((1 2,3 2,3 4,1 4,1 2))"
