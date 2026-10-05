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


def parts(geom: dict) -> list:
    """The polygons (lists of rings) of a Polygon/MultiPolygon."""
    return geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]


def label_point(geom: dict) -> tuple[float, float]:
    """A point inside a Polygon/MultiPolygon: the centroid when it falls inside, else a point in the
    largest part (its centroid, or the middle of the widest horizontal run across it). Centroids of
    long, curved or scattered shapes can land in the water or another block."""
    lon, lat = polygon_centroid(geom)
    if contains(geom, lon, lat):
        return lon, lat
    part = max(parts(geom), key=lambda p: abs(_ring_area_centroid(p[0])[0]))
    one = {"type": "Polygon", "coordinates": part}
    lon, lat = polygon_centroid(one)
    if contains(one, lon, lat):
        return lon, lat
    ys = [y for _, y in part[0]]
    best = None
    for y in [lat] + [min(ys) + (max(ys) - min(ys)) * k / 6 for k in range(1, 6)]:
        xs = sorted(x0 + (y - y0) * (x1 - x0) / (y1 - y0)
                    for ring in part for (x0, y0), (x1, y1) in zip(ring, ring[1:], strict=False)
                    if (y0 > y) != (y1 > y))
        for a, b in zip(xs[::2], xs[1::2], strict=False):
            if best is None or b - a > best[0]:
                best = (b - a, (a + b) / 2, y)
    return (best[1], best[2]) if best else tuple(part[0][0][:2])


def central_point(pts: list[tuple[float, float]]) -> tuple[float, float]:
    """The point with the least total distance to the others (lon, lat): a real site, unlike the mean,
    which for scattered sites can fall in the water between them."""
    return min(pts, key=lambda p: sum(haversine_m(p[1], p[0], q[1], q[0]) for q in pts))


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


def distance_to_polygon_m(geom: dict, lon: float, lat: float) -> float:
    """0 inside a Polygon/MultiPolygon, else metres to its nearest edge (local flat approximation)."""
    if contains(geom, lon, lat):
        return 0.0
    kx, ky = 111_320 * math.cos(math.radians(lat)), 110_574
    best = math.inf
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        for ring in poly:
            for (x0, y0), (x1, y1) in zip(ring, ring[1:], strict=False):
                ax, ay = (x0 - lon) * kx, (y0 - lat) * ky
                bx, by = (x1 - lon) * kx, (y1 - lat) * ky
                dx, dy = bx - ax, by - ay
                t = max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy))) if dx or dy else 0.0
                best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best
