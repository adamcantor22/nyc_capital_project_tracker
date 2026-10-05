
import pytest

from geo import central_point, contains, haversine_m, in_nyc, label_point, mean_point, points, polygon_centroid

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


def test_label_point_keeps_an_inside_centroid():
    assert label_point({"type": "Polygon", "coordinates": [SQUARE]}) == pytest.approx((1, 1))


def test_label_point_of_a_u_shape_is_inside():
    u = [[0, 0], [3, 0], [3, 3], [2, 3], [2, 1], [1, 1], [1, 3], [0, 3], [0, 0]]  # centroid in the notch
    g = {"type": "Polygon", "coordinates": [u]}
    assert not contains(g, *polygon_centroid(g))
    assert contains(g, *label_point(g))


def test_label_point_of_scattered_parts_is_in_the_largest():
    big = [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]]
    far = [[20, 0], [21, 0], [21, 1], [20, 1], [20, 0]]
    lon, lat = label_point({"type": "MultiPolygon", "coordinates": [[far], [big]]})
    assert 0 < lon < 4 and 0 < lat < 4


def test_central_point_is_a_real_site():
    pts = [(-74.07, 40.60), (-74.06, 40.61), (-73.80, 40.58)]  # two close, one far: the mean is between
    assert central_point(pts) in pts[:2]
    assert central_point([(1.0, 2.0)]) == (1.0, 2.0)
