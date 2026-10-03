"""Split each placed project into its known sites, with a share of the budget.

A project gets one row per site in `project_sites`:
  - Tier A with several points in the source it was placed from (CPDB multi-points, several Parks
    tracker entries, DOT/DEP intersections, several BINs or addresses): one site per distinct point;
  - Tier D listing several community districts, or Tier C naming several neighborhoods: one site per
    area centroid;
  - any other placed project: one site with the whole budget. Unplaced projects have none.
Shares are equal (`share_method = 'equal'`), except where the Parks tracker gives different amounts
for its entries: those are split in proportion (`source_proportion`). Shares sum to 1 per project.
The averaged point and `spread_m` in `project_locations` are unchanged.
Run after pipeline/locations.py.
"""
import sys
from collections import defaultdict

import duckdb

from db import DB_PATH, replace_table

POINT_TABLES = {"parks_tracker": "loc_parks_tracker", "cpdb_points": "loc_cpdb_points",
                "dot_intersections": "loc_dot_intersections", "bridge_bin": "bridge_matches",
                "geoclient_address": "geocoded_addresses"}


def merge(points):
    """Distinct points (5-decimal coordinates), summing any weights: [(lon, lat, weight or None)]."""
    out: dict[tuple, list] = {}
    for lon, lat, w in points:
        out.setdefault((round(lon, 5), round(lat, 5)), []).append(w)
    return [(lon, lat, None if None in ws else sum(ws)) for (lon, lat), ws in out.items()]


def shares(points):
    """(lon, lat, share, method): proportional when every point has a weight and they differ."""
    if len(points) == 1:
        return [(points[0][0], points[0][1], 1.0, "single")]
    weights = [w for _, _, w in points]
    if len(points) > 1 and all(w for w in weights) and len(set(weights)) > 1:
        total = sum(weights)
        return [(lon, lat, w / total, "source_proportion") for lon, lat, w in points]
    return [(lon, lat, 1 / len(points), "equal") for lon, lat, _ in points]


def main() -> int:
    con = duckdb.connect(str(DB_PATH))
    tables = {t for (t,) in con.execute("select table_name from duckdb_tables()").fetchall()}
    pts = defaultdict(list)  # (source, fms_id) -> [(lon, lat, weight)]
    for source, table in POINT_TABLES.items():
        if table not in tables:
            continue
        weight = "total_funding" if source == "parks_tracker" else "null"
        for fms, lon, lat, w in con.execute(f"select fms_id, lon, lat, {weight} from {table}").fetchall():
            pts[(source, fms)].append((lon, lat, w))
    cd = {str(c): (lon, lat) for c, lon, lat in
          con.execute("select boro_cd, lon, lat from ref_community_districts").fetchall()}
    nta = {n: (lon, lat) for n, lon, lat in con.execute("select name, lon, lat from ref_ntas").fetchall()}

    out = []
    for fms, tier, source, lon, lat, matched in con.execute(
            "select fms_id, tier, source, lon, lat, matched_to from project_locations where tier <> 'Unplaced'"
    ).fetchall():
        if tier == "A" and (source, fms) in pts:
            sites = shares(merge(pts[(source, fms)]))
        elif tier == "D" and matched and "," in matched:
            sites = shares([(*cd[c], None) for c in matched.split(",") if c in cd])
        elif tier == "C" and matched and " / " in matched:
            sites = shares([(*nta[n], None) for n in matched.split(" / ") if n in nta])
        else:
            sites = [(lon, lat, 1.0, "single")]
        for i, (slon, slat, share, method) in enumerate(sites, 1):
            out.append((fms, i, tier, source, slon, slat, share, method))
    replace_table(con, "project_sites", "fms_id varchar, site_no integer, tier varchar, source varchar, "
                  "lon double, lat double, share double, share_method varchar", out)
    multi = len({o[0] for o in out if o[1] > 1})
    print(f"project_sites: {len(out):,} sites for {len({o[0] for o in out}):,} projects; {multi:,} with several")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
