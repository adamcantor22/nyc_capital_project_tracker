"""Write the files the site reads to data/export/ (JSON and GeoJSON).

  manifest.json        schema version, snapshots, source freshness, files with counts and fields
  projects.json        one object per FMS ID ever reported: money, phase, theme, location, search fields
  schedules.json       one object per PID: its FMS IDs and its schedule in every snapshot
  history.json         per FMS ID and snapshot: budget, spend, phase, forecast completion
  sites.json           per-site points and budget shares (project_sites)
  funding.json         per FMS ID and fiscal year: city and non-city budget, spend (budget_spend_by_fy)

Non-city money is split into federal, state and other (budget_federal, budget_state, budget_other) by
each project's shares in CPDB (planned commitments plus commitments to date). It is an estimate, null
where CPDB has no non-city split for the project. start_date is the earliest actual phase start any
linked PID reports. Each site carries the community district and NTA it falls in, for area totals.
  lines.geojson        street lines used to place projects
  footprints.geojson   CPDB polygons used to place projects
  areas/districts.geojson, areas/neighborhoods.geojson, areas/boroughs.geojson

Money follows pipeline/money.py: budgets are per (FMS ID, managing agency), summed. Variances are
signed. A schedule variance is implausible, set to null and flagged, when the forecast date is after
LAST_PLAUSIBLE_YEAR (FDNY's 'Generator - EC16' once said 3026) or the variance is a correction of such a
date (over a century either way). Large real swings, such as Newtown Creek's 11 years, stay.
Coordinates are rounded to 5 decimals (about 1 m).
The manifest's `programs` registry lists each capital program the site can show; every project row names
its program. City capital projects are `nyc_capital`; other programs (MTA, SCA, state) would add an entry
and their own files.
Run after pipeline/sites.py.
"""
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime

import duckdb

import phase_groups
import themes
from db import DB_PATH, ROOT
from geo import contains, distance_to_polygon_m
from money import project_budgets

OUT = ROOT / "data" / "export"
SCHEMA_VERSION = 3
LAST_PLAUSIBLE_YEAR = 2100
MAX_VARIANCE_DAYS = 36500
NEAR_KM = 30  # sites this close to the city's edge extend the map; farther ones get edge markers
NYC_BOUNDS = (40.47, 40.93, -74.27, -73.68)  # lat0, lat1, lon0, lon1: points inside count as in the city

PROGRAMS = [{
    "id": "nyc_capital", "label": "NYC capital projects", "publisher": "NYC Office of Management and Budget",
    "datasets": ["fb86-vt7u", "gyhf-rsr3", "qj5n-h5qp", "95tx-snak", "fi59-268w"], "key": "fms_id", "currency": "USD",
    "files": {"projects": "projects.json", "schedules": "schedules.json", "history": "history.json",
              "sites": "sites.json", "funding": "funding.json", "lines": "lines.geojson",
              "footprints": "footprints.geojson"},
}]

PROJECT_FIELDS = [
    "program", "fms_id", "title", "agency_project_name", "description", "managing_agencies", "sponsor_agency", "pids",
    "borough", "community_board", "category", "budget_line", "theme", "subtheme",
    "phase", "phase_group", "has_schedule", "forecast_completion",
    "budget", "budget_city", "budget_non_city", "budget_federal", "budget_state", "budget_other",
    "spend", "spend_pct", "budget_change", "start_date",
    "first_reported", "last_reported", "status",
    "tier", "source", "lon", "lat", "matched_to", "source_flag", "spread_m", "n_points", "on_map",
    "approximate", "outside_nyc", "district", "districts", "neighborhood",
]


def r5(x):
    return None if x is None else round(x, 5)


def round_geom(g):
    if isinstance(g, list):
        return [round_geom(c) for c in g] if g and isinstance(g[0], list) else [round(c, 5) for c in g[:2]]
    return g


def feature(geom: dict, props: dict) -> dict:
    return {"type": "Feature", "properties": props,
            "geometry": {"type": geom["type"], "coordinates": round_geom(geom["coordinates"])}}


def write(name: str, data) -> int:
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(",", ":"), default=str))
    return path.stat().st_size


def present(text):
    """None for empty text and the source's '<blank>' placeholder (182 descriptions in May 2026)."""
    return None if text is None or text.strip().lower() in ("", "<blank>") else text


def outside_nyc(lat, lon, boroughs: list[dict]):
    """None within the city's bounding box (or unplaced); beyond it, 'near' within NEAR_KM of the
    city's edge (Kensico), else 'far' (Catskill and Delaware reservoirs)."""
    lat0, lat1, lon0, lon1 = NYC_BOUNDS
    if lat is None or (lat0 <= lat <= lat1 and lon0 <= lon <= lon1):
        return None
    return "near" if min(distance_to_polygon_m(g, lon, lat) for g in boroughs) <= NEAR_KM * 1000 else "far"


def main() -> int:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    periods = [p for (p,) in con.execute(
        "select distinct reporting_period from project_budget_schedule order by 1").fetchall()]
    latest = periods[-1]
    budgets = project_budgets(con)
    groups = phase_groups.load()
    rules = themes.load()

    # Latest descriptive record per FMS ID: the agency record with the largest budget in its last snapshot.
    attrs = {}
    for row in con.execute("""
        select fms_id, fms_project_name, agency_project_name, agency_project_description, sponsor_agency,
               borough, community_board, ten_year_plan_category, budget_line, current_phase,
               forecast_completion, managing_agency, reporting_period
        from project_budget_schedule
        qualify reporting_period = max(reporting_period) over (partition by fms_id)
        order by fms_id, total_budget desc nulls last""").fetchall():
        attrs.setdefault(row[0], row)
    agencies = defaultdict(set)
    pids = defaultdict(set)
    first = {}
    for f, ag, pid, p in con.execute(
            "select fms_id, managing_agency, pid, reporting_period from project_budget_schedule").fetchall():
        agencies[f].add(ag)
        if pid is not None:
            pids[f].add(int(pid))
        first[f] = min(first.get(f, p), p)
    by_period = defaultdict(dict)  # fms -> period -> budget (deduplicated per agency)
    for f, p, b in con.execute("""select fms_id, reporting_period, sum(budget) from (
            select fms_id, managing_agency, reporting_period, any_value(total_budget) budget
            from project_budget_schedule group by all) group by all""").fetchall():
        by_period[f][p] = b
    scheduled = defaultdict(set)  # period -> PIDs with a schedule row
    for p, pid in con.execute("select distinct reporting_period, pid from schedule_history").fetchall():
        scheduled[p].add(pid)

    cds = [(c, b, json.loads(g)) for c, b, g in
           con.execute("select boro_cd, borough, geojson from ref_community_districts").fetchall()]
    ntas = [(n, json.loads(g)) for n, g in con.execute("select name, geojson from ref_ntas").fetchall()]

    def cd_of(lon, lat):
        return next((c for c, _, g in cds if contains(g, lon, lat)), None)

    boro_geoms = []
    for b in sorted({b for _, b, _ in cds}):
        polys = [p for _, bb, g in cds if bb == b for p in (g["coordinates"] if g["type"] == "MultiPolygon"
                                                              else [g["coordinates"]])]
        boro_geoms.append({"type": "MultiPolygon", "coordinates": polys})
    def nta_of(lon, lat):
        return next((n for n, g in ntas if contains(g, lon, lat)), None)

    site_cds = defaultdict(set)
    sites_out = []
    for f, i, lon, lat, share, method in con.execute(
            "select fms_id, site_no, lon, lat, share, share_method from project_sites order by 1, 2").fetchall():
        cd = cd_of(lon, lat)
        site_cds[f].add(cd)
        sites_out.append({"fms_id": f, "site_no": i, "lon": r5(lon), "lat": r5(lat),
                          "share": round(share, 6), "share_method": method, "district": cd,
                          "nta": nta_of(lon, lat)})
    funding = defaultdict(list)  # fms -> per fiscal year, summed over managing agencies, at its last snapshot
    for f, fy, c, n, sp in con.execute("""
            with last as (select fms_id, max(reporting_period) p from project_budget_schedule group by 1)
            select b.fms_id, fiscal_year, sum(city), sum(non_city), sum(spend) from budget_spend_by_fy b
            join last l on b.fms_id = l.fms_id and b.reporting_period = l.p
            group by 1, 2 order by 1, 2""").fetchall():
        funding[f].append({"fy": fy, "city": round(c or 0, 2), "non_city": round(n or 0, 2),
                           "spend": None if sp is None else round(sp, 2)})
    # Shares of non-city money by source, from CPDB (planned plus committed), per FMS ID.
    split = {}
    for f, st, fe, ot in con.execute("""
            select fms_id, sum(plan_state + commit_state), sum(plan_federal + commit_federal),
                   sum(plan_other + commit_other) from cpdb_funding group by 1""").fetchall():
        tot = (st or 0) + (fe or 0) + (ot or 0)
        if tot > 0:
            split[f] = (st / tot, fe / tot, ot / tot)
    starts = dict(con.execute("""
        with last as (select fms_id, max(reporting_period) as p from project_budget_schedule group by 1)
        select b.fms_id, min(least(coalesce(actual_design_start, '9999-01-01'),
                                   coalesce(actual_construction_procurement_start, '9999-01-01'),
                                   coalesce(actual_construction_start, '9999-01-01')))
        from project_budget_schedule b join last l on b.fms_id = l.fms_id and b.reporting_period = l.p
        group by 1""").fetchall())
    locs = {r[0]: r for r in con.execute("""select fms_id, tier, source, lon, lat, matched_to, source_flag,
                                            spread_m, n_points from project_locations""").fetchall()}

    projects = []
    for f, (budget, spend, last) in sorted(budgets.items()):
        a = attrs[f]
        _, title, aname, desc, sponsor, boro, board, cat, bline, phase, forecast, managing, _ = a
        theme, subtheme = themes.theme(cat, sponsor, managing, f"{aname or ''} {title or ''}", bline, rules)
        hist = sorted(by_period[f].items())
        prev = [b for p, b in hist if p < last]
        _, tier, source, lon, lat, matched, flag, spread, npts = locs[f]
        districts = sorted(d for d in site_cds.get(f, ()) if d is not None)
        neighborhood = (next((n for n, g in ntas if contains(g, lon, lat)), None)
                        if tier in ("A", "B") and lon is not None else matched if tier == "C" else None)
        fund = funding.get(f)
        noncity = round(sum(y["non_city"] for y in fund), 2) if fund else None
        sh = split.get(f) if noncity else None
        start = starts.get(f)
        start = None if start is None or start.year >= 9999 else start.date().isoformat()
        projects.append({
            "program": "nyc_capital", "fms_id": f, "title": title,
            "agency_project_name": present(aname), "description": present(desc),
            "managing_agencies": sorted(agencies[f]), "sponsor_agency": sponsor, "pids": sorted(pids[f]),
            "borough": boro, "community_board": board, "category": cat, "budget_line": bline,
            "theme": theme, "subtheme": subtheme,
            "phase": phase, "phase_group": phase_groups.group(phase, groups),
            "has_schedule": any(p in scheduled[last] for p in pids[f]), "forecast_completion": forecast,
            "budget": round(budget, 2),
            "budget_city": round(sum(y["city"] for y in fund), 2) if fund else None,
            "budget_non_city": noncity,
            "budget_federal": round(noncity * sh[1], 2) if sh else None,
            "budget_state": round(noncity * sh[0], 2) if sh else None,
            "budget_other": round(noncity * sh[2], 2) if sh else None,
            "spend": round(spend, 2),
            "spend_pct": round(100 * spend / budget, 1) if budget else None,
            "budget_change": round(budget - prev[-1], 2) if prev else None,
            "start_date": start,
            "first_reported": first[f], "last_reported": last,
            "status": "current" if last == latest else "dropped",
            "tier": tier, "source": source, "lon": r5(lon), "lat": r5(lat), "matched_to": matched,
            "source_flag": flag, "spread_m": spread, "n_points": npts,
            "on_map": tier in ("A", "B"), "approximate": tier == "B",
            "outside_nyc": outside_nyc(lat, lon, boro_geoms),
            "district": districts[0] if len(districts) == 1 and tier in ("A", "B", "C", "D") else None,
            "districts": districts, "neighborhood": neighborhood,
        })

    schedules = defaultdict(lambda: {"fms_ids": set(), "snapshots": []})
    for f, pid in con.execute("select distinct fms_id, pid from project_budget_schedule "
                              "where pid is not null").fetchall():
        schedules[int(pid)]["fms_ids"].add(f)
    clamped = 0
    for p, ag, pid, name, phase, date, kind, var, reason in con.execute("""
            select reporting_period, managing_agency, pid, agency_project_name, current_phase, completion_date,
                   completion_date_type, variance_day, reason_for_forecast_completion_change
            from schedule_history order by pid, reporting_period""").fetchall():
        bad = ((date is not None and date.year > LAST_PLAUSIBLE_YEAR)
               or (var is not None and abs(var) > MAX_VARIANCE_DAYS))
        clamped += bad
        s = schedules[int(pid)]
        s.update(managing_agency=ag, name=name)
        s["snapshots"].append({"period": p, "phase": phase, "completion_date": date, "completion_type": kind,
                               "variance_days": None if bad else var, "variance_implausible": bad,
                               "reason": reason})
    schedules_out = [{"pid": pid, "fms_ids": sorted(s["fms_ids"]), "managing_agency": s.get("managing_agency"),
                      "name": s.get("name"), "snapshots": s["snapshots"]} for pid, s in sorted(schedules.items())]

    history = defaultdict(list)
    for f, p, phase, forecast, spend in con.execute("""
            select fms_id, reporting_period, arg_max(current_phase, total_budget), any_value(forecast_completion),
                   sum(spend) from (select fms_id, managing_agency, reporting_period, any_value(current_phase)
                   current_phase, any_value(forecast_completion) forecast_completion, any_value(total_budget)
                   total_budget, any_value(spend_to_date) spend from project_budget_schedule group by all)
            group by 1, 2 order by 1, 2""").fetchall():
        history[f].append({"period": p, "budget": by_period[f][p], "spend": spend, "phase": phase,
                           "forecast_completion": forecast})

    used = {r[0]: r[2] for r in locs.values()}
    lines = [feature(json.loads(g), {"fms_id": f, "kind": k, "label": lb})
             for f, k, lb, g in con.execute("select fms_id, kind, label, geojson from street_lines").fetchall()
             if used.get(f, "").startswith("street_")]
    footprints = [feature(json.loads(g), {"fms_id": f, "description": d})
                  for f, d, g in con.execute("select fms_id, description, geojson from loc_cpdb_polygons").fetchall()
                  if used.get(f) == "cpdb_polygons"]
    districts_fc = [feature(g, {"district": c, "borough": b}) for c, b, g in cds]
    ntas_fc = [feature(json.loads(g), {"nta": n, "name": nm, "borough": b, "type": t}) for n, nm, b, t, g in
               con.execute("select nta, name, borough, nta_type, geojson from ref_ntas").fetchall()]
    # DCP's shoreline-clipped borough outlines; a union of districts would show every district edge
    # and leave holes at parks and airports, which belong to no district.
    boroughs_fc = [feature(json.loads(g), {"borough": b}) for b, g in
                   con.execute("select borough, geojson from ref_boroughs order by borough").fetchall()]

    files = {
        "projects.json": (projects, len(projects), PROJECT_FIELDS),
        "schedules.json": (schedules_out, len(schedules_out), list(schedules_out[0]) if schedules_out else []),
        "history.json": (history, sum(len(v) for v in history.values()), ["period", "budget", "spend", "phase",
                                                                            "forecast_completion"]),
        "sites.json": (sites_out, len(sites_out), list(sites_out[0]) if sites_out else []),
        "funding.json": (funding, sum(len(v) for v in funding.values()), ["fy", "city", "non_city", "spend"]),
        "lines.geojson": ({"type": "FeatureCollection", "features": lines}, len(lines), ["fms_id", "kind", "label"]),
        "footprints.geojson": ({"type": "FeatureCollection", "features": footprints}, len(footprints),
                               ["fms_id", "description"]),
        "areas/districts.geojson": ({"type": "FeatureCollection", "features": districts_fc}, len(districts_fc),
                                    ["district", "borough"]),
        "areas/neighborhoods.geojson": ({"type": "FeatureCollection", "features": ntas_fc}, len(ntas_fc),
                                        ["nta", "name", "borough", "type"]),
        "areas/boroughs.geojson": ({"type": "FeatureCollection", "features": boroughs_fc}, len(boroughs_fc),
                                   ["borough"]),
    }
    sizes = {name: write(name, data) for name, (data, _, _) in files.items()}
    sources = [dict(zip(["dataset_id", "table", "name", "source_updated", "remote_rows", "loaded_rows", "loaded_at"],
                        r, strict=True)) for r in con.execute("select * from _ingest_meta order by 1").fetchall()]
    manifest = {
        "schema_version": SCHEMA_VERSION, "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "latest_snapshot": latest, "snapshots": periods, "last_plausible_year": LAST_PLAUSIBLE_YEAR,
        "max_variance_days": MAX_VARIANCE_DAYS,
        "implausible_variances": clamped, "programs": PROGRAMS, "sources": sources,
        "files": {name: {"rows": n, "bytes": sizes[name], "fields": fields}
                  for name, (_, n, fields) in files.items()},
    }
    write("manifest.json", manifest)
    for name, (_, n, _) in files.items():
        print(f"{name:30s} {n:7,d} rows {sizes[name] / 1e6:7.2f} MB")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
