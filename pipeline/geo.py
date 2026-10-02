"""Minimal GeoJSON helpers (no spatial dependencies)."""
import math

# Rough NYC bounding box, used to reject bad coordinates.
NYC_BOUNDS = (40.47, 40.93, -74.27, -73.68)  # lat_min, lat_max, lon_min, lon_max


def in_nyc(lat: float, lon: float) -> bool:
    return NYC_BOUNDS[0] <= lat <= NYC_BOUNDS[1] and NYC_BOUNDS[2] <= lon <= NYC_BOUNDS[3]


def _ring_area_centroid(ring: list) -> tuple[float, float, float]:
    """Signed shoelace area and centroid of one ring, in degree units (fine at city scale)."""
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:], strict=False):
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a /= 2
    if a == 0:
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        return 0.0, sum(xs) / len(xs), sum(ys) / len(ys)
    return a, cx / (6 * a), cy / (6 * a)


def polygon_centroid(geom: dict) -> tuple[float, float]:
    """Area-weighted centroid (lon, lat) of a Polygon/MultiPolygon; holes are subtracted."""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    total = sx = sy = 0.0
    for poly in polys:
        for i, ring in enumerate(poly):
            a, cx, cy = _ring_area_centroid(ring)
            w = abs(a) if i == 0 else -abs(a)
            total += w
            sx += cx * w
            sy += cy * w
    if total == 0:
        a, cx, cy = _ring_area_centroid(polys[0][0])
        return cx, cy
    return sx / total, sy / total


def points(geom: dict) -> list[tuple[float, float]]:
    """(lon, lat) pairs from a Point/MultiPoint."""
    if geom["type"] == "Point":
        return [tuple(geom["coordinates"][:2])]
    return [tuple(p[:2]) for p in geom["coordinates"]]


def mean_point(pts: list[tuple[float, float]]) -> tuple[float, float]:
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def contains(geom: dict, lon: float, lat: float) -> bool:
    """Even-odd ray casting over every ring of a Polygon/MultiPolygon (holes handled)."""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    inside = False
    for poly in polys:
        for ring in poly:
            for (x0, y0), (x1, y1) in zip(ring, ring[1:], strict=False):
                if (y0 > lat) != (y1 > lat) and lon < x0 + (lat - y0) * (x1 - x0) / (y1 - y0):
                    inside = not inside
    return inside


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (lat1, lon1, lat2, lon2))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))
