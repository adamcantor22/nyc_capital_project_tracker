"""Locate MTA ACEPs from the Capital Dashboard's project locations (wcsa-vkhf).

The MTA publishes points for ACEPs whose location indicator is `base` (one point) or `multilocation` (one point per
work site: stations, pump rooms, substations). Each is an official point keyed by the ACEP, so placements are Tier A.
Multi-location sites closer than 100 m are one place (as sites.merge joins them; `mta_sites.sequences` lists the
published points behind each), and each site gets an equal share of the budget
(the sites are taken to cost about the same); the project's own point is its most central site
(geo.central_point). ACEPs with any other indicator (`systemwide`, rolling stock `car` and `bus`, `dollar`, `cbdt`)
have no location and are Unplaced, with the indicator as their source.

Point problems are fixed only by rule and recorded in `mta_point_errors`: a point whose latitude and longitude are
exchanged (latitude near -74, longitude near 41) is read the right way round; any other point outside the region is
rejected. NYC Transit, Staten Island Railway and Bridges and Tunnels work only within the city, so their points more
than 2 km outside the five boroughs are rejected too (MTA Bus is not on this list: it runs the Yonkers depot). Writes
mta_locations, mta_sites and mta_point_errors. Run after pipeline/mta.py.
"""
import json
import sys
from collections import defaultdict

import duckdb

from db import DB_PATH, RAW_DIR, replace_table
from geo import central_point, contains, distance_to_polygon_m, haversine_m
from sites import MERGE_M, shares

DATASET = "wcsa-vkhf"
LAT, LON = (40.0, 42.5), (-75.5, -71.0)  # the MTA region: New York City, Long Island, the Hudson Valley, Connecticut
CITY_ONLY = {"T": "New York City Transit", "S": "Staten Island Railway", "D": "Bridges and Tunnels"}
CITY_SLACK_M = 2000  # a city-only agency's point farther than this outside the five boroughs is rejected


def in_region(lat: float, lon: float) -> bool:
    return LAT[0] <= lat <= LAT[1] and LON[0] <= lon <= LON[1]


def read_point(r: dict) -> tuple[tuple[float, float] | None, str | None]:
    """((lon, lat), problem): problem is 'swapped' (fixed) or 'outside_region' (rejected, no point)."""
    try:
        lat, lon = float(r["latitude"]), float(r["longitude"])
    except (KeyError, TypeError, ValueError):
        return None, "missing"
    if in_region(lat, lon):
        return (lon, lat), None
    if in_region(lon, lat):
        return (lat, lon), "swapped"
    return None, "outside_region"


def merge_points(pts: list[tuple[int, tuple[float, float]]]) -> list[tuple[float, float, list[int]]]:
    """(sequence, (lon, lat)) -> places (lon, lat, sequences), joining a point to the first place within MERGE_M, as
    sites.merge does, and keeping which published points each place stands for."""
    out: list[list] = []
    for seq, (lon, lat) in pts:
        near = next((o for o in out if haversine_m(lat, lon, o[1], o[0]) < MERGE_M), None)
        if near:
            near[2].append(seq)
        else:
            out.append([round(lon, 5), round(lat, 5), [seq]])
    return [(lon, lat, seqs) for lon, lat, seqs in out]


def main() -> int:
    raw = json.loads((RAW_DIR / f"{DATASET}.json").read_text())
    con = duckdb.connect(str(DB_PATH))
    boroughs = [(b, json.loads(g)) for b, g in con.execute("select borough, geojson from ref_boroughs").fetchall()]
    agency = dict(con.execute("select acep, agency_code from mta_projects").fetchall())
    by_acep = defaultdict(list)
    errors = []
    for r in raw:
        point, problem = read_point(r)
        seq = int(r.get("project_number_sequence") or 0)
        if problem:
            errors.append((r["project_number"], seq, r.get("latitude"), r.get("longitude"), problem,
                           "read with latitude and longitude exchanged" if problem == "swapped" else "point rejected"))
        if point and agency.get(r["project_number"]) in CITY_ONLY and not any(
                contains(g, *point) for _, g in boroughs):
            off = min(distance_to_polygon_m(g, *point) for _, g in boroughs)
            if off > CITY_SLACK_M:
                errors.append((r["project_number"], seq, r.get("latitude"), r.get("longitude"), "outside_service_area",
                               f"point rejected: {off / 1000:.1f} km outside the city, where "
                               f"{CITY_ONLY[agency[r['project_number']]]} works"))
                point = None
        if point:
            by_acep[r["project_number"]].append((seq, point))

    locations, sites = [], []
    for acep, indicator in con.execute("select acep, location_indicator from mta_projects order by 1").fetchall():
        pts = sorted(by_acep.get(acep, []))
        if not pts:
            locations.append((acep, "Unplaced", indicator or "none", None, None, 0, 0, None, None, None,
                              f"{DATASET} has no point for {acep}; Capital Dashboard location indicator "
                              f"'{indicator or ''}'"))
            continue
        places = merge_points(pts)
        lon, lat = central_point([(p[0], p[1]) for p in places])
        spread = max(haversine_m(lat, lon, p[1], p[0]) for p in places)
        boro = next((b for b, g in boroughs if contains(g, lon, lat)), None)
        fixes = sorted({e[4] for e in errors if e[0] == acep})
        seqs = [s for s, _ in pts]
        locations.append((
            acep, "A", "mta_point" if len(places) == 1 else "mta_multilocation", lon, lat, len(places), len(pts),
            round(spread), boro, ", ".join(fixes) or None,
            f"{DATASET}, MTA Capital Dashboard project locations: {len(pts)} point(s) for {acep} "
            f"(sequence {min(seqs)}-{max(seqs)})" + (f"; {', '.join(fixes)} point(s), see mta_point_errors"
                                                     if fixes else ""),
        ))
        for i, ((slon, slat, share, method), place) in enumerate(
                zip(shares([(p[0], p[1], None) for p in places]), places, strict=True), 1):
            sites.append((acep, i, slon, slat, share, method, ",".join(map(str, place[2]))))

    replace_table(con, "mta_point_errors", "acep varchar, sequence integer, latitude varchar, longitude varchar, "
                  "problem varchar, action varchar", errors)
    replace_table(con, "mta_locations", "acep varchar, tier varchar, source varchar, lon double, lat double, "
                  "n_sites integer, n_points integer, spread_m integer, borough varchar, point_fixes varchar, "
                  "evidence varchar", locations)
    replace_table(con, "mta_sites", "acep varchar, site_no integer, lon double, lat double, share double, "
                  "share_method varchar, sequences varchar", sites)
    print(con.execute("select problem, count(*) from mta_point_errors group by 1").fetchall())
    print(con.execute("""select l.tier, l.source, count(*), round(sum(p.current_budget) / 1e9, 1)
                         from mta_locations l join mta_projects p using (acep) where p.status = 'live'
                         group by all order by 1, 4 desc""").fetchall())
    print(con.execute("""select coalesce(l.borough, '(outside NYC)'), count(*) from mta_locations l
                         join mta_projects p using (acep) where p.status = 'live' and l.tier = 'A'
                         group by 1 order by 2 desc""").fetchall())
    return 0


if __name__ == "__main__":
    sys.exit(main())
