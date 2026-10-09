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
than 2 km outside the five boroughs are rejected too (MTA Bus is not on this list: it runs the Yonkers depot). A
rejected point can be replaced by a site in `mta_sites.csv`: the FacDB facility the ACEP's title names, with its
evidence (Tier B, inferred; coordinates from FacDB, never entered by hand).

An ACEP whose title names the Interborough Express takes its stations as sites (ibx.py: MTA's station list, each
point computed from the street centerline and the railroad line; Tier B), with equal shares: an assumption, as a
design-phase budget does not say where it will be spent. Its own point stays MTA's (Tier A) where MTA publishes one;
otherwise it is the most central station (Tier B, source `ibx_stations`). Writes mta_locations, mta_sites (`label`
names a station), ibx_stations and mta_point_errors. Run after pipeline/mta.py, with the street centerline
(ingest.py) and the railroad lines (fetch_locations.py, anc7-97cy) in place.
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import duckdb

import ibx
from db import DB_PATH, RAW_DIR, replace_table
from geo import central_point, contains, distance_to_polygon_m, haversine_m
from sites import MERGE_M, shares

DATASET = "wcsa-vkhf"
SITES = Path(__file__).with_name("mta_sites.csv")
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

    facilities = {u: (lon, lat) for u, lon, lat in con.execute("select uid, lon, lat from ref_facilities").fetchall()}
    with SITES.open() as f:
        cited = {}
        for r in csv.DictReader(f):
            cited.setdefault(r["acep"], []).append(r)
    stations = ibx.stations(con)
    station_note = (f"sites: the {len(stations)} Interborough Express stations (ibx_stations, Tier B), equal shares "
                    "assumed")
    locations, sites = [], []
    for acep, indicator, title in con.execute(
            "select acep, location_indicator, description from mta_projects order by 1").fetchall():
        pts = sorted(by_acep.get(acep, []))
        extra = [(int(r["sequence"]), facilities[r["facdb_uid"]], r["tier"]) for r in cited.get(acep, [])]
        if ibx.TITLE.search(title or ""):
            places = [(*p, "A", DATASET) for p in merge_points(pts)]
            if places:
                lon, lat = central_point([(p[0], p[1]) for p in places])
                tier, source = "A", "mta_point" if len(places) == 1 else "mta_multilocation"
                note = (f"{DATASET}, MTA Capital Dashboard project locations: {len(pts)} point(s) for {acep}; "
                        f"{station_note}")
            else:
                lon, lat = central_point([(st["lon"], st["lat"]) for st in stations])
                tier, source = "B", "ibx_stations"
                note = f"{DATASET} has no point for {acep}; its title names the Interborough Express; {station_note}"
            spread = max(haversine_m(lat, lon, st["lat"], st["lon"]) for st in stations)
            boro = next((b for b, g in boroughs if contains(g, lon, lat)), None)
            locations.append((acep, tier, source, lon, lat, len(stations), len(pts), round(spread), boro, None, note))
            sites.extend((acep, i, st["lon"], st["lat"], 1 / len(stations), "equal", None, "B", "ibx_station",
                          st["station"]) for i, st in enumerate(stations, 1))
            continue
        if not pts and not extra:
            locations.append((acep, "Unplaced", indicator or "none", None, None, 0, 0, None, None, None,
                              f"{DATASET} has no point for {acep}; Capital Dashboard location indicator "
                              f"'{indicator or ''}'"))
            continue
        places = [(*p, "A", DATASET) for p in merge_points(pts)] + [
            (lon, lat, [seq], tier, "facdb") for seq, (lon, lat), tier in extra]
        lon, lat = central_point([(p[0], p[1]) for p in places])
        spread = max(haversine_m(lat, lon, p[1], p[0]) for p in places)
        boro = next((b for b, g in boroughs if contains(g, lon, lat)), None)
        fixes = sorted({e[4] for e in errors if e[0] == acep})
        seqs = [s for s, _ in pts]
        locations.append((
            acep, "A" if pts else extra[0][2], "mta_point" if len(places) == 1 else "mta_multilocation", lon, lat,
            len(places), len(pts),
            round(spread), boro, ", ".join(fixes) or None,
            f"{DATASET}, MTA Capital Dashboard project locations: {len(pts)} point(s) for {acep} "
            f"(sequence {min(seqs)}-{max(seqs)})" + (f"; {', '.join(fixes)} point(s), see mta_point_errors"
                                                     if fixes else "")
            + (f"; {len(extra)} site(s) from FacDB, see mta_sites.csv" if extra else ""),
        ))
        for i, ((slon, slat, share, method), place) in enumerate(
                zip(shares([(p[0], p[1], None) for p in places]), places, strict=True), 1):
            sites.append((acep, i, slon, slat, share, method, ",".join(map(str, place[2])), place[3], place[4], None))

    replace_table(con, "mta_point_errors", "acep varchar, sequence integer, latitude varchar, longitude varchar, "
                  "problem varchar, action varchar", errors)
    replace_table(con, "mta_locations", "acep varchar, tier varchar, source varchar, lon double, lat double, "
                  "n_sites integer, n_points integer, spread_m integer, borough varchar, point_fixes varchar, "
                  "evidence varchar", locations)
    replace_table(con, "mta_sites", "acep varchar, site_no integer, lon double, lat double, share double, "
                  "share_method varchar, sequences varchar, tier varchar, source varchar, label varchar", sites)
    replace_table(con, "ibx_stations", "no integer, station varchar, borough_code integer, lon double, lat double, "
                  "gap_m double, rule varchar, evidence varchar",
                  [tuple(s[k] for k in ("no", "station", "borough_code", "lon", "lat", "gap_m", "rule", "evidence"))
                   for s in stations])
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
