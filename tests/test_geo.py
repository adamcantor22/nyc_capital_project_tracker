
import pytest

from geo import contains, haversine_m, in_nyc, mean_point, points, polygon_centroid

SQUARE = [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]
HOLE = [[0.5, 0.5], [1, 0.5], [1, 1], [0.5, 1], [0.5, 0.5]]


def test_polygon_centroid_of_square():
    assert polygon_centroid({"type": "Polygon", "coordinates": [SQUARE]}) == pytest.approx((1, 1))


def test_polygon_centroid_is_area_weighted_across_multipolygon():
    big = [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]]            # area 16, centroid (2, 2)
    small = [[10, 0], [11, 0], [11, 1], [10, 1], [10, 0]]     # area 1, centroid (10.5, 0.5)
    lon, lat = polygon_centroid({"type": "MultiPolygon", "coordinates": [[big], [small]]})
    assert lon == pytest.approx((2 * 16 + 10.5) / 17)
    assert lat == pytest.approx((2 * 16 + 0.5) / 17)


def test_polygon_centroid_ignores_ring_orientation():
    clockwise = SQUARE[::-1]
    assert polygon_centroid({"type": "Polygon", "coordinates": [clockwise]}) == pytest.approx((1, 1))


def test_polygon_centroid_subtracts_holes():
    lon, lat = polygon_centroid({"type": "Polygon", "coordinates": [SQUARE, HOLE]})
    # removing area near the origin pushes the centroid away from it
    assert lon > 1 and lat > 1


def test_contains_handles_holes_and_outside():
    g = {"type": "Polygon", "coordinates": [SQUARE, HOLE]}
    assert contains(g, 1.5, 1.5)
    assert not contains(g, 0.75, 0.75)   # inside the hole
    assert not contains(g, 3, 3)


def test_contains_multipolygon():
    g = {"type": "MultiPolygon", "coordinates": [[SQUARE], [[[5, 5], [6, 5], [6, 6], [5, 6], [5, 5]]]]}
    assert contains(g, 5.5, 5.5) and contains(g, 1, 1) and not contains(g, 4, 4)


def test_haversine_one_degree_of_latitude():
    assert haversine_m(40, -74, 41, -74) == pytest.approx(111_195, rel=1e-3)
    assert haversine_m(40.7, -74, 40.7, -74) == 0


def test_in_nyc():
    assert in_nyc(40.7128, -74.0060)        # City Hall
    assert not in_nyc(41.97, -74.19)        # Ashokan Reservoir
    assert not in_nyc(0, 0)


def test_points_and_mean_point():
    assert points({"type": "Point", "coordinates": [1, 2]}) == [(1, 2)]
    pts = points({"type": "MultiPoint", "coordinates": [[0, 0], [2, 4]]})
    assert mean_point(pts) == (1, 2)
