"""Agreement checks between location methods, shared by pipeline/profile.py (which reports them)
and tests/test_data.py (which asserts thresholds so regressions fail).

Each function compares one method's output with independent Tier A sources for projects that
have both, and returns distances in metres.
"""
import json

from geo import haversine_m

# Tier A sources that come straight from agencies/DCP (not derived from project text).
AGENCY_SOURCES = """
    select 'cpdb_points' s, fms_id, lon, lat from loc_cpdb_points
    union all select 'cpdb_polygons', fms_id, lon, lat from loc_cpdb_polygons
    union all select 'parks_tracker', fms_id, lon, lat from loc_parks_tracker
    union all select 'dot_intersections', fms_id, lon, lat from loc_dot_intersections"""


def address_agreement(con) -> dict[str, list[float]]:
    """Geoclient-geocoded addresses vs agency sources, per source."""
    rows = con.execute(f"""
        with g as (select fms_id, avg(lon) lon, avg(lat) lat from geocoded_addresses group by 1),
             o as (select s, fms_id, avg(lon) lon, avg(lat) lat from ({AGENCY_SOURCES}) group by 1, 2)
        select o.s, g.lat, g.lon, o.lat, o.lon from g join o using (fms_id)
        where o.s <> 'dot_intersections'""").fetchall()
    out: dict[str, list[float]] = {}
    for s, la1, lo1, la2, lo2 in rows:
        out.setdefault(s, []).append(haversine_m(la1, lo1, la2, lo2))
    return {s: sorted(d) for s, d in out.items()}


def named_feature_agreement(con) -> list[float]:
    """Gazetteer feature points vs agency sources (one averaged reference point per project)."""
    rows = con.execute(f"""
        with o as (select fms_id, avg(lon) lon, avg(lat) lat from ({AGENCY_SOURCES})
                   where s <> 'dot_intersections' group by 1)
        select n.lat, n.lon, o.lat, o.lon from named_feature_matches n join o using (fms_id)""").fetchall()
    return sorted(haversine_m(a, b, c, d) for a, b, c, d in rows)


def street_line_agreement(con) -> tuple[dict[str, int], dict[str, list[float]]]:
    """Lines drawn per kind, and per kind the distance from a Tier A reference point (agency
    sources or a geocoded address) to the nearest vertex of the line."""
    ref = {f: (lo, la) for f, lo, la in con.execute(f"""
        select fms_id, avg(lon), avg(lat) from (
            select fms_id, lon, lat from ({AGENCY_SOURCES})
            union all select fms_id, lon, lat from geocoded_addresses) group by 1""").fetchall()}
    counts: dict[str, int] = {}
    dists: dict[str, list[float]] = {}
    for f, kind, gj in con.execute("select fms_id, kind, geojson from street_lines").fetchall():
        counts[kind] = counts.get(kind, 0) + 1
        if f in ref:
            lo, la = ref[f]
            dists.setdefault(kind, []).append(min(haversine_m(la, lo, p[1], p[0])
                                                  for line in json.loads(gj)["coordinates"] for p in line))
    return counts, {k: sorted(v) for k, v in dists.items()}


def tier_b_precision(con, within_m: int = 500) -> tuple[int, int]:
    """Tier B name matcher run on projects with Tier A coordinates: (matched, matched within_m).
    In-sample: the matcher's rules were tuned on this set, so treat as an upper bound."""
    return con.execute(f"select count_if(matched), count_if(distance_m <= {within_m}) "
                       "from location_validation").fetchone()


def share_within(dists: list[float], m: float) -> float:
    return sum(d <= m for d in dists) / len(dists) if dists else float("nan")
