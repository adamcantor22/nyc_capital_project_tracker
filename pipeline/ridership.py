"""Where each subway station's riders live, from MTA's origin-destination estimate and the 2020 census.

Catchment: the residents within CATCHMENT_M of a station complex (800 m, the half mile planners treat as about a
10-minute walk), sampled on a GRID_M grid: each point inside the circle takes the 2020 population density of the
census tract it falls in (DCP's shoreline-clipped tracts, 63ge-mke6; ref_tract_population) and the community district
it falls in, so a tract or district counts only for its part inside the circle. `subway_station_catchment` gives
each station's share of catchment residents per district; a station with no residents in reach (a yard, an
airport) takes its own district whole.

Riders: morning trips (05:00-11:59; fetch_ridership.py, MTA Subway Origin-Destination Ridership Estimate 2025,
y2qv-fytt) mostly start where riders live. A station's morning users are the riders who board there, taken to live in
its catchment, and those who arrive there, taken to live in the catchment of the station they boarded at. The
station's own area is the districts (boroughs) holding at least AREA_MIN of its catchment; `share_district`
(`share_borough`) is the share of its users living there.

Transfers: a catchment can only produce so many boardings. Boardings per catchment resident at residential stations
(over RESIDENTIAL_MIN residents, arriving under half of boarding) set a cap, their RATE_Q quantile; boardings above
residents x cap are riders transferring from a bus, commuter rail, PATH or a ferry, whose homes are unknown. They are
left out of both sides of the shares, at the station and among the riders it sends to others, so the shares are
measured among riders whose homes can be placed. Riders are an average day's morning riders: MTA's
averages by month and day of week summed over hours, divided by the months times 7.
"""
import json
import math
import sys
from collections import defaultdict

import duckdb

from db import DB_PATH, RAW_DIR, replace_table
from geo import contains, distance_to_polygon_m

DATASET = "y2qv-fytt"
SOURCE = (f"MTA Subway Origin-Destination Ridership Estimate 2025 ({DATASET}), trips starting 05:00-11:59; "
          "2020 census tracts (63ge-mke6) and population")
CATCHMENT_M = 800
GRID_M = 50
AREA_MIN = 0.1
RESIDENTIAL_MIN = 1000
RATE_Q = 0.9
UNKNOWN = "unknown"
CELL = 0.01  # degrees, for the tract index
M_LAT = 110_950.0


def m_lon(lat: float) -> float:
    return M_LAT * math.cos(math.radians(lat))


def area_m2(geom: dict) -> float:
    """Planar area of a (Multi)Polygon in square metres (outer rings minus holes), fine at city scale."""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    total = 0.0
    for poly in polys:
        for k, ring in enumerate(poly):
            kx = m_lon(ring[0][1])
            a = sum((x1 * kx) * (y2 * M_LAT) - (x2 * kx) * (y1 * M_LAT)
                    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=True)) / 2
            total += abs(a) if k == 0 else -abs(a)
    return total


def district_of(cds: list[tuple], lon: float, lat: float) -> tuple[str, str]:
    for cd, boro, g in cds:
        if contains(g, lon, lat):
            return cd, boro
    cd, boro, _ = min(cds, key=lambda c: distance_to_polygon_m(c[2], lon, lat))
    return cd, boro


def grid_index(shapes: list[tuple]) -> dict[tuple, list]:
    """Grid cell -> [(bbox, geom, *values)] for shapes given as (geom, *values)."""
    index: dict[tuple, list] = defaultdict(list)
    for g, *values in shapes:
        pts = [p for poly in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]])
               for p in poly[0]]
        x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
        y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
        for i in range(int(x0 // CELL), int(x1 // CELL) + 1):
            for j in range(int(y0 // CELL), int(y1 // CELL) + 1):
                index[(i, j)].append(((x0, y0, x1, y1), g, *values))
    return index


def lookup(index: dict, x: float, y: float):
    for (x0, y0, x1, y1), g, *values in index.get((int(x // CELL), int(y // CELL)), ()):
        if x0 <= x <= x1 and y0 <= y <= y1 and contains(g, x, y):
            return values
    return None


def catchment(tracts: dict, districts: dict, lon: float, lat: float) -> dict[tuple[str, str], float]:
    """(district, borough) -> estimated residents within CATCHMENT_M: each grid point inside the circle counts its
    tract's density times the cell area, in the district it falls in."""
    out: dict[tuple[str, str], float] = defaultdict(float)
    dx, dy = GRID_M / m_lon(lat), GRID_M / M_LAT
    n = CATCHMENT_M // GRID_M
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            if (i * i + j * j) * GRID_M * GRID_M > CATCHMENT_M * CATCHMENT_M:
                continue
            x, y = lon + i * dx, lat + j * dy
            t, d = lookup(tracts, x, y), lookup(districts, x, y)
            if t and d and t[0] > 0:
                out[tuple(d)] += t[0] * GRID_M * GRID_M
    return out


def shares(c: dict[tuple[str, str], float]) -> tuple[dict[str, float], dict[str, float]]:
    total = sum(c.values())
    d, b = defaultdict(float), defaultdict(float)
    for (cd, boro), v in c.items():
        d[cd] += v / total
        b[boro] += v / total
    return d, b


def station_users(complexes: list[dict], pairs: list[list], days: int, tracts: dict, districts: dict,
                  cds: list[tuple]):
    info, reach = {}, {}
    catch_rows = []
    for c in complexes:
        i, lon, lat = int(c["id"]), float(c["lon"]), float(c["lat"])
        cd, boro = district_of(cds, lon, lat)
        r = catchment(tracts, districts, lon, lat)
        residents = sum(r.values())
        if residents < 1:
            r, residents = {(cd, boro): 1.0}, 0.0
        info[i] = (c["name"], lat, lon, cd, boro, residents)
        reach[i] = r
        catch_rows += [(i, d, b, round(v / sum(r.values()), 4), round(v * (residents > 0)))
                       for (d, b), v in sorted(r.items(), key=lambda kv: -kv[1])]
    boarding: dict[int, float] = defaultdict(float)
    arriving: dict[int, float] = defaultdict(float)
    for o, d, riders in pairs:
        boarding[o] += riders / days
        arriving[d] += riders / days
    rates = sorted(boarding[i] / v[5] for i, v in info.items()
                   if v[5] > RESIDENTIAL_MIN and arriving[i] < 0.5 * boarding[i])
    cap = rates[int(RATE_Q * (len(rates) - 1))]
    home = {}  # complex -> where its boarders live, by district and by borough
    resident = {}
    for i, (*_, residents) in info.items():
        resident[i] = min(boarding[i], residents * cap) if residents else boarding[i]
        frac = resident[i] / boarding[i] if boarding[i] else 1.0
        by_d, by_b = shares(reach[i])
        by_d = {k: v * frac for k, v in by_d.items()}
        by_b = {k: v * frac for k, v in by_b.items()}
        by_d[UNKNOWN] = by_b[UNKNOWN] = 1 - frac
        home[i] = (by_d, by_b)
    homes: dict[int, list[dict]] = defaultdict(lambda: [defaultdict(float), defaultdict(float)])
    for o, d, riders in pairs:
        for k in (0, 1):  # boarders at o live where o's boarders live, and so do the riders o sends to d
            for area, sh in home[o][k].items():
                homes[o][k][area] += riders / days * sh
                homes[d][k][area] += riders / days * sh
    rows = []
    for i, (name, lat, lon, cd, boro, residents) in sorted(info.items()):
        users = boarding[i] + arriving[i] - homes[i][0].get(UNKNOWN, 0.0)
        by_d, by_b = shares(reach[i])
        own = [{a for a, sh in by_d.items() if sh >= AREA_MIN}, {a for a, sh in by_b.items() if sh >= AREA_MIN}]
        share = [round(sum(v for a, v in homes[i][k].items() if a in own[k]) / users, 4) if users else None
                 for k in (0, 1)]
        rows.append((i, name, lat, lon, boro, cd, *(",".join(sorted(map(str, o))) for o in own), round(residents),
                     round(boarding[i], 1), round(resident[i], 1), round(arriving[i], 1),
                     round(homes[i][0].get(UNKNOWN, 0.0), 1), *share, SOURCE))
    return rows, catch_rows, cap


def main() -> int:
    raw = RAW_DIR / "mta"
    complexes = json.loads((raw / f"od-{DATASET}-complexes.json").read_text())
    pairs = json.loads((raw / f"od-{DATASET}-am.json").read_text())
    tracts = json.loads((RAW_DIR / "63ge-mke6.json").read_text())
    con = duckdb.connect(str(DB_PATH))
    cds = [(cd, boro, json.loads(g)) for cd, boro, g in
           con.execute("select boro_cd, borough, geojson from ref_community_districts").fetchall()]
    pop = dict(con.execute("select geoid, population from ref_tract_population").fetchall())
    tract_idx = grid_index([(t["the_geom"], pop.get(t["geoid"], 0) / (area_m2(t["the_geom"]) or 1)) for t in tracts])
    district_idx = grid_index([(g, cd, boro) for cd, boro, g in cds])
    days = 7 * len(json.loads((raw / f"od-{DATASET}.meta.json").read_text())["_queries"]["months"])
    rows, catch_rows, cap = station_users(complexes, pairs, days, tract_idx, district_idx, cds)
    replace_table(con, "subway_station_catchment", "complex_id integer, district varchar, borough varchar, "
                  "share double, residents integer", catch_rows)
    replace_table(con, "subway_station_users", "complex_id integer, name varchar, lat double, lon double, "
                  "borough varchar, district varchar, own_districts varchar, own_boroughs varchar, residents integer, "
                  "boarding double, boarding_residents double, arriving double, unknown_home double, "
                  "share_district double, share_borough double, source varchar",
                  rows)
    for q in (0.1, 0.25, 0.5, 0.75, 0.9):
        d, b = con.execute(f"""select quantile_cont(share_district, {q}), quantile_cont(share_borough, {q})
                               from subway_station_users""").fetchone()
        print(f"q{q:.2f}: district {d:.2f}, borough {b:.2f}")
    multi = con.execute("select count(*) from subway_station_users where own_districts like '%,%'").fetchone()[0]
    print(f"{len(rows)} station complexes; {multi} with a catchment in two or more districts; "
          f"boardings capped at {cap:.3f} per catchment resident a day")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
