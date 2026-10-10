"""New rail stations from MTA's own records, placed with the city's street and rail lines: the Interborough Express
(IBX) and Penn Station Access (PSA).

MTA publishes one point per IBX ACEP (wcsa-vkhf), though the work runs 14 miles from Bay Ridge to Jackson Heights.
`ibx_stations.csv` lists the stations of MTA's Draft Scoping Document (October 2025, Table 4), each citing its row
and the 2026 community board briefing that names it; Sutter Avenue is listed as dropped (the briefings count 18
stations, none of them Sutter). A station's point is computed, never entered: where its Table 4 street (`street`, a
centerline name) meets the IBX right of way (`rail_feature`, a line of the planimetric railroad layer anc7-97cy), the
point on the rail line nearest the street; or, for a station Table 4 places on a block (`between` two cross
streets), the middle of that block along the centerline. The link from a station's description to the rail line is
read by hand, so the points are Tier B. mta_locations.py makes the stations the sites of every ACEP whose title
names the IBX.

`psa_stations.csv` lists Penn Station Access's four Bronx stations from its Environmental Assessment (May 2021,
Executive Summary p. ES-6), each on the Hell Gate Line (`CONRAIL-AMTRAK` in anc7-97cy): where the access street meets
the line, or for a station given at a corner (`at`, the access street's cross street), the point on the line nearest
that intersection of the centerline. mta_locations.py makes them the sites of MTA's Penn Station Access ACEPs.
"""
import csv
import json
import math
import re
from pathlib import Path

from db import RAW_DIR
from geo import central_point
from street_lines import Network, oriented, point_along

STATIONS = Path(__file__).with_name("ibx_stations.csv")
PSA_STATIONS = Path(__file__).with_name("psa_stations.csv")
RAIL = "anc7-97cy"
TITLE = re.compile(r"\bIBX\b|\bINTERBOROUGH EXPRESS\b", re.IGNORECASE)
M_LON, M_LAT = 111320 * math.cos(math.radians(40.7)), 110574  # metres per degree near the city


def load(path: Path = STATIONS) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def _xy(p):
    return p[0] * M_LON, p[1] * M_LAT


def _nearest_on_segment(p, a, b):
    """(distance, point) from p to the segment a-b, in metres on a local plane."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
    q = (a[0] + t * dx, a[1] + t * dy)
    return math.dist(p, q), q


def _cross(a, b, c, d):
    """Where segments a-b and c-d cross, or None."""
    den = (b[0] - a[0]) * (d[1] - c[1]) - (b[1] - a[1]) * (d[0] - c[0])
    if den == 0:
        return None
    t = ((c[0] - a[0]) * (d[1] - c[1]) - (c[1] - a[1]) * (d[0] - c[0])) / den
    u = ((c[0] - a[0]) * (b[1] - a[1]) - (c[1] - a[1]) * (b[0] - a[0])) / den
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])) if 0 <= t <= 1 and 0 <= u <= 1 else None


def meeting_point(street_lines: list[list], rail_lines: list[list]) -> tuple[tuple[float, float], float]:
    """((lon, lat), gap in metres): the point on the rail lines nearest the street lines, 0 where they cross."""
    best = None
    for s in street_lines:
        for a, b in zip(map(_xy, s), map(_xy, s[1:]), strict=False):
            for r in rail_lines:
                for c, d in zip(map(_xy, r), map(_xy, r[1:]), strict=False):
                    if x := _cross(a, b, c, d):
                        cand = (0.0, x)
                    else:
                        cand = min(_nearest_on_segment(a, c, d), _nearest_on_segment(b, c, d),
                                   (_nearest_on_segment(c, a, b)[0], c), (_nearest_on_segment(d, a, b)[0], d),
                                   key=lambda v: v[0])
                    if best is None or cand[0] < best[0]:
                        best = cand
    gap, (x, y) = best
    return (round(x / M_LON, 6), round(y / M_LAT, 6)), round(gap, 1)


def block_middle(net: Network, street: str, a: str, b: str) -> tuple[float, float] | None:
    """The middle of `street` between cross streets a and b, along the centerline."""
    r = net.route(street, net.crossing_nodes(street, a), net.crossing_nodes(street, b))
    if r is None:
        return None
    line = []
    for start, seg in r[1]:
        line.extend(oriented(seg, start)[1 if line else 0:])
    lon, lat = point_along(line, 0.5)
    return round(lon, 6), round(lat, 6)


def corner(con, bc: int, a: str, b: str) -> list[float] | None:
    """The centerline node where streets a and b meet (the most central, where a divided road meets twice)."""
    ends = [{tuple(c) for (g,) in con.execute(
        "select geojson from ref_centerline where borough_code = ? and street_norm = ?", [bc, s]).fetchall()
        for line in json.loads(g)["coordinates"] for c in (line[0], line[-1])} for s in (a, b)]
    nodes = sorted(ends[0] & ends[1])
    return list(central_point(nodes)) if nodes else None


def stations(con, path: Path = STATIONS, line: str = "the IBX right of way") -> list[dict]:
    """Each proposed station with its point, how it was found and its evidence."""
    rows = [r for r in load(path) if r["status"] == "proposed"]
    rail = {r["source_id"]: r for r in json.loads((RAW_DIR / f"{RAIL}.json").read_text()) if r.get("the_geom")}
    out = []
    for r in rows:
        bc = int(r["borough_code"])
        if r["between"]:
            a, b = r["between"].split("|")
            seg_rows = con.execute(
                """select physicalid, street_norm, length_m, x0, y0, x1, y1, geojson from ref_centerline
                   where borough_code = ? and street_norm in (?, ?, ?)""", [bc, r["street"], a, b]).fetchall()
            point, gap = block_middle(Network(seg_rows), r["street"], a, b), None
            how = f"middle of {r['street']} between {a} and {b} (street centerline inkn-q76z)"
        elif r.get("at"):
            feature = rail[r["rail_feature"]]
            node = corner(con, bc, r["street"], r["at"])
            point, gap = meeting_point([[node, node]], feature["the_geom"]["coordinates"]) if node else (None, None)
            how = (f"the point of {line}, {RAIL} line {r['rail_feature']} ('{feature.get('name')}'), nearest the "
                   f"corner of {r['street']} and {r['at']} (street centerline inkn-q76z), {gap or 0:.0f} m away")
        else:
            feature = rail[r["rail_feature"]]
            street = [line for (g,) in con.execute(
                "select geojson from ref_centerline where borough_code = ? and street_norm = ?",
                [bc, r["street"]]).fetchall() for line in json.loads(g)["coordinates"]]
            point, gap = meeting_point(street, feature["the_geom"]["coordinates"])
            how = (f"where {r['street']} (street centerline inkn-q76z) meets {line}, {RAIL} line "
                   f"{r['rail_feature']} ('{feature.get('name')}'), {gap:.0f} m apart")
        out.append({"no": int(r["no"]), "station": r["station"], "borough_code": bc,
                    "lon": point[0] if point else None, "lat": point[1] if point else None, "gap_m": gap,
                    "rule": "between" if r["between"] else "corner" if r.get("at") else "rail_crossing",
                    "evidence": f"{r['evidence']} Point: {how}."})
    return out
