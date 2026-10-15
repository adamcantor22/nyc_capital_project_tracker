"""Rail lines and new stations' walk zones for the story maps -> rail_lines, station_reach.

`rail_lines` holds lines as drawn from official sources, one row per line and part:
  - Penn Station Access's route. MTA's City Terminal Zone line (2vcb-zrh4, the LIRR's) carries it from Penn Station
    through the East River tunnels, which the city's planimetric railroad layer (anc7-97cy) does not draw. The city
    layer carries it from where its Hell Gate route leaves that corridor (Harold, in Sunnyside) over the Hell Gate
    Bridge to the city line: the shortest path along the segments named for the New York Connecting Railroad and the
    Hell Gate Line, so yards and branches drop out. Penn Station is MTA's point for it (wxmd-5cpm, code NYK). North of
    the city line, where neither draws it, the federal North American Rail Network (USDOT/BTS NTAD, from FRA; fetched
    by fetch_mta.py) carries it to the New Haven Line: its Hell Gate Line arcs, followed by their FRA node ids from
    the arc where the city layer stops to the first node a New Haven Line arc shares (near New Rochelle).
  - Metro-North's Hudson, Harlem and New Haven lines as MTA publishes them (2vcb-zrh4).

`rail_terminals` holds the Manhattan terminals the story map marks, from MTA's rail station list (wxmd-5cpm): Grand
Central Terminal (Metro-North, 0NY), where New Haven Line trains end today, and Penn Station (NYK), where Penn
Station Access will take them.

`station_reach` holds the residents within 800 m of each Penn Station Access station (psa_stations), by the same
method as subway catchments (ridership.catchment: 2020 census tract density on a 50 m grid). The counts are estimates.

Run after pipeline/project_areas.py (census, ridership and psa_stations in place).
"""
import ast
import heapq
import json
import math
import sys
from collections import defaultdict

import duckdb

from db import DB_PATH, RAW_DIR, replace_table
from project_areas import Geography, Transit
from ridership import CATCHMENT_M, GRID_M, catchment

SNAP_M = 25  # segment ends this close are joined (bridge ends, capture breaks); provisional
JOIN_M = 40  # the city layer's route is on the LIRR corridor within this distance of its line; provisional
PSA_NAMES = {"NEW YORK CONNECTING RR", "CONRAIL-AMTRAK", "CONRAIL AMTRAK", "AMTRAK RR"}
BRANCHES = {"HUD": "Hudson", "HAR": "Harlem", "NHV": "New Haven"}
RULE_CITY = (f"shortest path along anc7-97cy segments named {', '.join(sorted(PSA_NAMES))}, ends within {SNAP_M} m "
             "joined, from the city line to the first point on the LIRR corridor; drawn as one line from the City "
             "Terminal Zone part's end")
RULE_CTZ = (f"2vcb-zrh4 City Terminal Zone (CTZ), shortest path from Penn Station (wxmd-5cpm NYK) to the city layer's "
            f"route, joined within {JOIN_M} m")
TERMINALS = {"0NY": "where New Haven Line trains end today", "NYK": "where Penn Station Access will take them"}
NARN = "narn-hellgate"
RULE_NARN = ("USDOT/BTS NTAD North American Rail Network: SUBDIV 'HELLGATE LINE' arcs, from the vertex nearest the "
             "city layer's end, followed by FRFRANODE/TOFRANODE to the first node shared with a 'NEW HAVEN LINE' arc")
RESIDENTS_RULE = (f"residents within {CATCHMENT_M} m: 2020 census tract density (63ge-mke6, ref_tract_population "
                  f"P1_001N) on a {GRID_M} m grid (ridership.catchment); an estimate")


def m(a, b) -> float:
    """Metres between two lon/lat points (equirectangular; fine at city scale)."""
    k = math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot((a[0] - b[0]) * 111_320 * k, (a[1] - b[1]) * 110_574)


def geometry(v) -> dict:
    return ast.literal_eval(v) if isinstance(v, str) else v


def key(p) -> tuple[float, float]:
    return round(p[0], 6), round(p[1], 6)


def network(lines: list[list]) -> dict:
    """Node -> [(neighbour, metres, line index or None)]: each line joins its two ends; ends of different lines within
    SNAP_M are joined too."""
    adj = defaultdict(list)
    for i, ln in enumerate(lines):
        a, b = key(ln[0]), key(ln[-1])
        d = sum(m(ln[j], ln[j + 1]) for j in range(len(ln) - 1))
        adj[a].append((b, d, i))
        adj[b].append((a, d, i))
    cell = SNAP_M / 111_000 * 2
    grid = defaultdict(list)
    for n in list(adj):
        grid[(int(n[0] / cell), int(n[1] / cell))].append(n)
    for n in list(adj):
        gx, gy = int(n[0] / cell), int(n[1] / cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for o in grid[(gx + dx, gy + dy)]:
                    if o != n and m(n, o) <= SNAP_M:
                        adj[n].append((o, m(n, o), None))
    return adj


def shortest(adj: dict, s, e) -> list[tuple]:
    """[(node, line index or None)] from s to e, each node with the line that reached it."""
    dist, prev, q = {s: 0.0}, {}, [(0.0, s)]
    while q:
        d, n = heapq.heappop(q)
        if n == e:
            break
        if d > dist.get(n, math.inf):
            continue
        for nb, w, i in adj[n]:
            if d + w < dist.get(nb, math.inf):
                dist[nb], prev[nb] = d + w, (n, i)
                heapq.heappush(q, (d + w, nb))
    if e not in dist:
        raise ValueError(f"no path from {s} to {e}")
    path, n = [], e
    while n != s:
        p, i = prev[n]
        path.append((n, i))
        n = p
    return [(s, None), *reversed(path)]


def component(adj: dict, start) -> set:
    seen, stack = {start}, [start]
    while stack:
        for nb, _, _ in adj[stack.pop()]:
            if nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return seen


def chain(lines: list[list], path: list[tuple]) -> list[list]:
    """The path's lines in path order, each oriented to run along it."""
    out = []
    for (a, _), (_b, i) in zip(path, path[1:], strict=False):
        if i is None:
            continue
        ln = lines[i]
        out.append(ln if key(ln[0]) == a else list(reversed(ln)))
    return out


def joined(lines: list[list], start=None) -> list:
    """Lines already in order and orientation as one line: shared ends once, ends up to SNAP_M apart bridged, and
    `start` (where the previous part ends) ahead of them, so the route draws without breaks."""
    out = [start] if start is not None else []
    for ln in lines:
        for p in ln:
            if not out or key(out[-1]) != key(p):
                out.append(p)
    return out


def until_corridor(lines: list[list], corridor: list) -> tuple[list[list], tuple | None]:
    """Lines (in order from the far end) up to the first point within JOIN_M of the corridor, and the corridor point
    there; the rest of the lines run along the corridor."""
    cell = JOIN_M / 111_000 * 2
    grid = defaultdict(list)
    for c in corridor:
        grid[(int(c[0] / cell), int(c[1] / cell))].append(c)

    def near(p):
        gx, gy = int(p[0] / cell), int(p[1] / cell)
        cands = [c for dx in (-1, 0, 1) for dy in (-1, 0, 1) for c in grid[(gx + dx, gy + dy)]]
        best = min(cands, key=lambda c: m(c, p), default=None)
        return best if best is not None and m(best, p) <= JOIN_M else None

    kept = []
    for ln in lines:
        for j, p in enumerate(ln):
            hit = near(p)
            if hit is not None:
                if j:
                    kept.append(ln[: j + 1])
                return kept, key(hit)
        kept.append(ln)
    return kept, None


def segments(rows: list[dict], names: set[str]) -> tuple[list[list], list[str]]:
    lines, ids = [], []
    for r in rows:
        if r.get("name") in names:
            for ln in geometry(r["the_geom"])["coordinates"]:
                lines.append([tuple(p) for p in ln])
                ids.append(r["source_id"])
    return lines, ids


def parts(g: dict) -> list[list]:
    return g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]


def psa_route(anc7: list[dict], branches: list[dict], penn: tuple[float, float]) -> list[tuple]:
    """rail_lines rows for Penn Station Access: the CTZ part from Penn Station, then the city layer's part."""
    lines, ids = segments(anc7, PSA_NAMES)
    adj = network(lines)
    north = max(adj, key=lambda n: n[1])  # the line's end at the city line
    reach = component(adj, north)
    start = min(reach, key=lambda n: m(n, penn))  # where the layer's track begins east of the river
    path = shortest(adj, north, start)
    city = chain(lines, path)  # from the city line southwards
    ctz = next(b for b in branches if b["route_code"] == "CTZ")
    corridor = [tuple(p) for ln in parts(geometry(ctz["geometry"])) for p in ln]
    kept, junction = until_corridor(city, corridor)
    if junction is None:
        raise ValueError("the city layer's route never meets the City Terminal Zone")
    cadj = network([[tuple(p) for p in ln] for ln in parts(geometry(ctz["geometry"]))])
    # CTZ is published as short lines: join every consecutive vertex so the path can leave a line midway.
    for ln in parts(geometry(ctz["geometry"])):
        for a, b in zip(ln, ln[1:], strict=False):
            cadj[key(a)].append((key(b), m(a, b), None))
            cadj[key(b)].append((key(a), m(a, b), None))
    cnodes = list(cadj)
    near_junction = min(cnodes, key=lambda n: m(n, junction))
    tunnel = [n for n, _ in shortest(cadj, min(cnodes, key=lambda n: m(n, penn)), near_junction)]
    city_part = joined([list(reversed(ln)) for ln in reversed(kept)], tunnel[-1])  # junction northwards
    used = sorted({ids[i] for _, i in path if i is not None})
    return [
        ("Penn Station Access", 1, "ctz", "2vcb-zrh4", RULE_CTZ,
         f"2vcb-zrh4 route_code CTZ; Penn Station: wxmd-5cpm NYK {penn[0]}, {penn[1]}",
         json.dumps({"type": "LineString", "coordinates": [list(p) for p in tunnel]})),
        ("Penn Station Access", 2, "city_layer", "anc7-97cy", RULE_CITY,
         f"anc7-97cy source_id {', '.join(used)}",
         json.dumps({"type": "LineString", "coordinates": [list(p) for p in city_part]})),
    ]


def to_new_haven(narn: list[dict], start: tuple) -> tuple[list, list[str], int]:
    """The Hell Gate Line in NARN from the point nearest `start` to its junction with the New Haven Line: the line
    (beginning at `start`), the arcs used (FRAARCID) and the junction's FRA node."""
    hg = [f for f in narn if f["properties"]["SUBDIV"] == "HELLGATE LINE"]
    nh = {f["properties"][k] for f in narn if f["properties"]["SUBDIV"] == "NEW HAVEN LINE"
          for k in ("FRFRANODE", "TOFRANODE")}
    first, at = min(((f, i) for f in hg for i in range(len(f["geometry"]["coordinates"]))),
                    key=lambda fi: m(fi[0]["geometry"]["coordinates"][fi[1]], start))
    if m(first["geometry"]["coordinates"][at], start) > JOIN_M:
        raise ValueError("NARN's Hell Gate Line does not pass the city layer's end")
    for ahead in (True, False):  # walk each way from the arc; the way that reaches the New Haven Line is the route
        f, coords, arcs = first, [start], []
        pts = f["geometry"]["coordinates"]
        node = f["properties"]["TOFRANODE" if ahead else "FRFRANODE"]
        coords += pts[at + 1:] if ahead else pts[:at][::-1]
        arcs.append(str(f["properties"]["FRAARCID"]))
        while node not in nh:
            ends = ("FRFRANODE", "TOFRANODE")
            nxt = next((g for g in hg if g is not f and node in (g["properties"][k] for k in ends)), None)
            if nxt is None:
                break
            f = nxt
            pts = f["geometry"]["coordinates"]
            forward = f["properties"]["FRFRANODE"] == node
            coords += (pts if forward else pts[::-1])[1:]
            node = f["properties"]["TOFRANODE" if forward else "FRFRANODE"]
            arcs.append(str(f["properties"]["FRAARCID"]))
        if node in nh:
            return [tuple(p) for p in coords], arcs, node
    raise ValueError("NARN's Hell Gate Line never meets the New Haven Line")


def branch_rows(branches: list[dict]) -> list[tuple]:
    return [(f"Metro-North {BRANCHES[b['route_code']]}", 1, "branch", "2vcb-zrh4", "MTA's branch as published",
             f"2vcb-zrh4 object_id {b['object_id']} ({b['route_name']})", json.dumps(geometry(b["geometry"])))
            for b in branches if b["route_code"] in BRANCHES]


def main() -> int:
    anc7 = json.loads((RAW_DIR / "anc7-97cy.json").read_text())
    branches = json.loads((RAW_DIR / "2vcb-zrh4.json").read_text())
    nyk = next(r for r in json.loads((RAW_DIR / "wxmd-5cpm.json").read_text()) if r["code"] == "NYK")
    penn = (float(nyk["longitude"]), float(nyk["latitude"]))
    rows = psa_route(anc7, branches, penn)
    narn = json.loads((RAW_DIR / f"{NARN}.json").read_text())["features"]
    north, arcs, junction = to_new_haven(narn, tuple(json.loads(rows[-1][6])["coordinates"][-1]))
    rows.append(("Penn Station Access", 3, "narn", NARN, RULE_NARN,
                 f"NTAD North American Rail Network Lines FRAARCID {', '.join(arcs)}; New Haven Line junction FRA node "
                 f"{junction}", json.dumps({"type": "LineString", "coordinates": [list(p) for p in north]})))
    rows += branch_rows(branches)
    stations = json.loads((RAW_DIR / "wxmd-5cpm.json").read_text())
    terminals = [(r["station_name"], r["railroad"], r["code"], float(r["longitude"]), float(r["latitude"]), role,
                  "wxmd-5cpm", f"wxmd-5cpm {r['railroad']} code {r['code']} ({r['station_name']})")
                 for code, role in TERMINALS.items() for r in stations if r["code"] == code]
    con = duckdb.connect(str(DB_PATH))
    replace_table(con, "rail_terminals", "name varchar, railroad varchar, code varchar, lon double, lat double, "
                  "role varchar, dataset varchar, evidence varchar", terminals)
    replace_table(con, "rail_lines", "line varchar, seq integer, part varchar, dataset varchar, rule varchar, "
                  "evidence varchar, geojson varchar", rows)
    geo = Geography(con)
    tracts = Transit(con, geo).tracts
    reach = []
    for no, name, lon, lat, evidence in con.execute(
            "select no, station, lon, lat, evidence from psa_stations order by no").fetchall():
        residents = sum(catchment(tracts, geo.districts, lon, lat).values())
        reach.append(("Penn Station Access", no, name, lon, lat, CATCHMENT_M, round(residents), "psa_stations",
                      RESIDENTS_RULE, evidence))
    replace_table(con, "station_reach", "mega_project varchar, no integer, station varchar, lon double, lat double, "
                  "radius_m integer, residents integer, source varchar, rule varchar, evidence varchar", reach)
    for line, _, part, ds, _, _, g in rows:
        n = sum(len(ln) for ln in parts(json.loads(g)))
        print(f"{line:22} {part:10} {ds}  {n} points")
    for r in reach:
        print(f"{r[2]:22} {r[6]:>7,} residents within {r[5]} m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
