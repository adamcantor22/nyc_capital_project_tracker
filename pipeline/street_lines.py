"""Draw street projects as lines along the NYC street centerline.

Two shapes of project text are recognised (only street names that exist in the project's borough
count, which keeps prose from being read as a street):
  extent       'WM IN BAY ST BETWEEN SLOSSON TER & MINTHORNE ST'  -> the stretch of Bay St between
               the two cross streets, routed along Bay St's own segments          -> Tier A
  street_only  'SANITARY SEWERS & WM IN E 72ND ST, AVE L & ROYCE'  -> those streets' segments inside
               the project's community district(s)                                 -> Tier B
Cross streets are found through the street network (segments meeting at a shared node), not by
exact name, which tolerates 'RECTOR STR' or a bare 'THAMES'.

Writes `street_lines` (one row per project: GeoJSON MultiLineString, length, a representative point
on the line). Every candidate project is processed, including ones that already have Tier A
coordinates, so pipeline/profile.py can validate lines against them.
Run after pipeline/ingest.py and before pipeline/locations.py, which uses the results.
"""
import heapq
import json
import re
import sys
from collections import defaultdict

import duckdb

from db import DB_PATH, replace_table
from geo import contains, haversine_m
from locations import LINEAR, parse_districts
from streets import base, normalize

BOROUGH_CODES = {"Manhattan": 1, "Bronx": 2, "Brooklyn": 3, "Queens": 4, "Staten Island": 5}
STREET_AGENCIES = {"DOT", "DEP", "DDC"}
MAX_NAME_WORDS = 6
MAX_EXTENT_M = 3000         # longer routed extents are probably a misparse
MAX_STREET_ONLY_DISTRICT_M = 5000  # street-only, clipped to the project's district(s)
MAX_STREET_ONLY_BOROUGH_M = 2500   # street-only with just a borough: long streets are not a location

EXTENT = re.compile(r"\b(?:FROM|BETWEEN|BETW|BTWN|BTW|BWT|BET|B/T)\b")
NOT_ONE_STREET = re.compile(r"\bVARIOUS\b|\b(?:EAST|WEST|NORTH|SOUTH|E|W|N|S) OF\b")
NOT_A_STREET_NEXT = re.compile(r"^\s*(?:PARK|PLAYGROUND|PLGD|PG|HOUSES|LIBRARY|SCHOOL)\b")
EXTENT_JOIN = re.compile(r"\b(?:TO|AND|&)\b|&")
STREET_ONLY = re.compile(r"\b(?:IN|ON|ALONG|OF)\b")
LIST_SEP = re.compile(r"\s*(?:,|&|\bAND\b)\s*")


def words(text: str) -> list[str]:
    return normalize(text).split()


def longest_prefix(ws: list[str], known: set[str]) -> str | None:
    """Longest run of leading words that is a known street name."""
    for n in range(min(MAX_NAME_WORDS, len(ws)), 0, -1):
        cand = " ".join(ws[:n])
        if cand in known:
            return cand
    return None


def longest_suffix(ws: list[str], known: set[str]) -> str | None:
    for n in range(min(MAX_NAME_WORDS, len(ws)), 0, -1):
        cand = " ".join(ws[-n:])
        if cand in known:
            return cand
    return None


def loose_prefix(ws: list[str], known: set[str], known_base: set[str]) -> str | None:
    """Cross street: exact known name, or a known base name ('THAMES' for 'THAMES ST')."""
    exact = longest_prefix(ws, known)
    if exact:
        return exact
    for n in range(min(MAX_NAME_WORDS, len(ws)), 0, -1):
        cand = base(" ".join(ws[:n]))
        if cand in known_base:
            return cand
    return None


def parse(text: str, known: set[str], known_base: set[str]):
    """Return ('extent', X, A, B) or ('street_only', [X, ...]) or None."""
    t = text.upper()
    for m in EXTENT.finditer(t):
        x = longest_suffix(words(t[:m.start()]), known)
        if not x:
            continue
        rest = t[m.end():]
        j = EXTENT_JOIN.search(rest)
        if not j:
            continue
        a = loose_prefix(words(rest[:j.start()]), known, known_base)
        b = loose_prefix(words(rest[j.end():]), known, known_base)
        if a and b and a != x and b != x:
            return ("extent", x, a, b)
    streets = []
    if NOT_ONE_STREET.search(t):
        return None  # 'VARIOUS STREETS WEST OF BROADWAY' is an area, not Broadway
    for m in STREET_ONLY.finditer(t):
        for chunk in LIST_SEP.split(t[m.end():m.end() + 120])[:4]:
            ws = words(chunk)
            s = longest_prefix(ws, known)
            if not s:
                break
            if NOT_A_STREET_NEXT.match(" ".join(ws[len(s.split()):])):
                break  # 'GRANT AVE PARK' is a park, not Grant Ave
            if s not in streets:
                streets.append(s)
    return ("street_only", streets) if streets else None


class Network:
    """Centerline segments of one borough, indexed by street name and by node (shared endpoint)."""

    def __init__(self, rows):
        self.by_street = defaultdict(list)   # street_norm -> [segment]
        self.by_node = defaultdict(list)     # (x, y) -> [segment]
        for physicalid, name, length, x0, y0, x1, y1, gj in rows:
            g = json.loads(gj)
            coords = [tuple(p[:2]) for line in g["coordinates"] for p in line]
            seg = {"id": physicalid, "street": name, "length": length,
                   "a": (x0, y0), "b": (x1, y1), "coords": coords}
            self.by_street[name].append(seg)
            self.by_node[seg["a"]].append(seg)
            self.by_node[seg["b"]].append(seg)

    def crossing_nodes(self, street: str, cross: str) -> set:
        """Nodes on `street` that a segment of `cross` also touches (exact or base-name match)."""
        out = set()
        for seg in self.by_street[street]:
            for n in (seg["a"], seg["b"]):
                if any(o["street"] == cross or base(o["street"]) == cross for o in self.by_node[n]):
                    out.add(n)
        return out

    def route(self, street: str, sources: set, targets: set):
        """Shortest path along `street`'s own segments from any source node to any target node."""
        adj = defaultdict(list)
        for seg in self.by_street[street]:
            adj[seg["a"]].append((seg["b"], seg))
            adj[seg["b"]].append((seg["a"], seg))
        dist = {n: 0.0 for n in sources}
        prev = {}
        heap = [(0.0, n) for n in sources]
        heapq.heapify(heap)
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist.get(u, float("inf")) or d > MAX_EXTENT_M:
                continue
            if u in targets and u not in sources:
                path, n = [], u
                while n in prev:
                    p, seg = prev[n]
                    path.append((p, seg))
                    n = p
                return d, path[::-1]
            for v, seg in adj[u]:
                nd = d + seg["length"]
                if nd < dist.get(v, float("inf")):
                    dist[v] = nd
                    prev[v] = (u, seg)
                    heapq.heappush(heap, (nd, v))
        return None


def oriented(seg, start):
    return seg["coords"] if seg["coords"][0] == start else seg["coords"][::-1]


def point_along(line: list, fraction: float) -> tuple:
    """Point at `fraction` of the way along a polyline of (lon, lat)."""
    steps = [haversine_m(a[1], a[0], b[1], b[0]) for a, b in zip(line, line[1:], strict=False)]
    target, walked = sum(steps) * fraction, 0.0
    for (a, b), step in zip(zip(line, line[1:], strict=False), steps, strict=True):
        if walked + step >= target and step > 0:
            f = (target - walked) / step
            return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        walked += step
    return line[-1]


def main() -> int:
    con = duckdb.connect(str(DB_PATH))
    networks = {bc: Network(con.execute(
        "select physicalid, street_norm, length_m, x0, y0, x1, y1, geojson from ref_centerline "
        "where borough_code = ?", [bc]).fetchall()) for bc in BOROUGH_CODES.values()}
    known = {bc: set(n.by_street) for bc, n in networks.items()}
    known_base = {bc: {base(n) for n in names} for bc, names in known.items()}
    cds = con.execute("select boro_cd, borough, geojson from ref_community_districts").fetchall()
    cd_geom = {c: json.loads(g) for c, _, g in cds}
    cd_codes = {b: c // 100 for c, b, _ in cds}

    projects = con.execute("""
        select fms_id,
               arg_max(managing_agency, reporting_period),
               arg_max(upper(coalesce(agency_project_name, '') || ' ' || coalesce(fms_project_name, '') || ' ' ||
                       coalesce(agency_project_description, '')), reporting_period),
               arg_max(borough, reporting_period),
               arg_max(community_board, reporting_period)
        from project_budget_schedule group by fms_id""").fetchall()

    out, stats = [], defaultdict(int)
    for fms, agency, text, boro, board in projects:
        if boro not in BOROUGH_CODES or not (LINEAR.search(text) or agency in STREET_AGENCIES):
            continue
        bc = BOROUGH_CODES[boro]
        net = networks[bc]
        p = parse(text, known[bc], known_base[bc])
        if not p:
            continue
        if p[0] == "extent":
            _, x, a, b = p
            found = net.route(x, net.crossing_nodes(x, a), net.crossing_nodes(x, b))
            if not found:
                stats["extent: no route"] += 1
                continue
            length, path = found
            line = []
            for start, seg in path:
                line.extend(oriented(seg, start)[1 if line else 0:])
            lines = [line]
            lon, lat = point_along(line, 0.5)
            label = f"{x} from {a} to {b}"
        else:
            districts = parse_districts(board, cd_codes, set(cd_geom))
            segs = [seg for s in p[1] for seg in net.by_street[s]]
            if districts:
                segs = [seg for seg in segs if any(
                    contains(cd_geom[d], *point_along(seg["coords"], 0.5)) for d in districts)]
                cap = MAX_STREET_ONLY_DISTRICT_M
            else:
                cap = MAX_STREET_ONLY_BOROUGH_M
            length = sum(seg["length"] for seg in segs)
            if not segs or length > cap:
                stats["street_only: none in district" if not segs else "street_only: over length cap"] += 1
                continue
            lines = [seg["coords"] for seg in segs]
            mids = [point_along(seg["coords"], 0.5) for seg in segs]
            cx, cy = sum(m[0] for m in mids) / len(mids), sum(m[1] for m in mids) / len(mids)
            lon, lat = min(mids, key=lambda m: haversine_m(cy, cx, m[1], m[0]))
            label = ", ".join(p[1]) + (f" in CD {','.join(map(str, districts))}" if districts else f" in {boro}")
        stats[p[0]] += 1
        out.append((fms, p[0], label, round(length), lon, lat,
                    json.dumps({"type": "MultiLineString", "coordinates": [[list(c) for c in ln] for ln in lines]})))

    replace_table(con, "street_lines",
                  "fms_id varchar, kind varchar, label varchar, length_m integer, lon double, lat double, "
                  "geojson varchar", out)
    print(dict(stats))
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
