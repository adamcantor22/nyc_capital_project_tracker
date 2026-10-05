"""Locate MTA ACEPs from the Capital Dashboard's project locations (wcsa-vkhf).

The MTA publishes points for ACEPs whose location indicator is `base` (one point) or `multilocation` (one point per
work site: stations, pump rooms, substations). Each is an official point keyed by the ACEP, so placements are Tier A.
Multi-location sites closer than 100 m are one place (sites.merge), and each site gets an equal share of the budget
(the sites are taken to cost about the same); the project's own point is its most central site
(geo.central_point). ACEPs with any other indicator (`systemwide`, rolling stock `car` and `bus`, `dollar`, `cbdt`)
have no location and are Unplaced, with the indicator as their source.

Point problems are fixed only by rule and recorded in `mta_point_errors`: a point whose latitude and longitude are
exchanged (latitude near -74, longitude near 41) is read the right way round; any other point outside the region is
rejected. Writes mta_locations, mta_sites and mta_point_errors. Run after pipeline/mta.py.
"""
import json
import sys
from collections import defaultdict

import duckdb

from db import DB_PATH, RAW_DIR, replace_table
from geo import central_point, contains, haversine_m
from sites import merge, shares

DATASET = "wcsa-vkhf"
LAT, LON = (40.0, 42.5), (-75.5, -71.0)  # the MTA region: New York City, Long Island, the Hudson Valley, Connecticut


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


def main() -> int:
    raw = json.loads((RAW_DIR / f"{DATASET}.json").read_text())
    con = duckdb.connect(str(DB_PATH))
    boroughs = [(b, json.loads(g)) for b, g in con.execute("select borough, geojson from ref_boroughs").fetchall()]
    by_acep = defaultdict(list)
    errors = []
    for r in raw:
        point, problem = read_point(r)
        seq = int(r.get("project_number_sequence") or 0)
        if problem:
            errors.append((r["project_number"], seq, r.get("latitude"), r.get("longitude"), problem,
                           "read with latitude and longitude exchanged" if problem == "swapped" else "point rejected"))
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
        places = merge([(lon, lat, None) for _, (lon, lat) in pts])
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
        for i, (slon, slat, share, method) in enumerate(shares(places), 1):
            sites.append((acep, i, slon, slat, share, method))

    replace_table(con, "mta_point_errors", "acep varchar, sequence integer, latitude varchar, longitude varchar, "
                  "problem varchar, action varchar", errors)
    replace_table(con, "mta_locations", "acep varchar, tier varchar, source varchar, lon double, lat double, "
                  "n_sites integer, n_points integer, spread_m integer, borough varchar, point_fixes varchar, "
                  "evidence varchar", locations)
    replace_table(con, "mta_sites", "acep varchar, site_no integer, lon double, lat double, share double, "
                  "share_method varchar", sites)
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
