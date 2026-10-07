"""Write the files the site reads to data/export/ (JSON and GeoJSON).

  manifest.json        schema version, snapshots, source freshness, files with counts and fields
  projects.json        one object per FMS ID ever reported: money, phase, theme, location, search fields
  schedules.json       one object per PID: its FMS IDs and its schedule in every snapshot
  history.json         per FMS ID and snapshot: budget, spend, phase, forecast completion, source (fb86-vt7u, or
                       qj5n-h5qp for a period the project is missing from in fb86-vt7u)
  sites.json           per-site points and budget shares (project_sites)
  funding.json         per FMS ID and fiscal year: city and non-city budget, spend (budget_spend_by_fy)
  schedule_phases.json per project id of every program (city FMS ID, 'sca:' or 'mta:' ids): phases with dates under
                       shared names (project_phases)

Non-city money is split into federal, state and other (budget_federal, budget_state, budget_other) by
each project's shares in CPDB (planned commitments plus commitments to date). It is an estimate, null
where CPDB has no non-city split for the project. start_date is the earliest actual phase start any
linked PID reports. design_start/end and construction_start/end are the actual milestone dates in the
latest snapshot (earliest start across linked PIDs; an end only when every PID reports one), and
phase_start is when the current phase began. original_budget is the sum over the project's managing agencies of
budget_original (pipeline/budget_history.py), original_period the earliest of their periods, original_basis
original_row, first_snapshot or mixed; budget_vs_original is the signed change in FMS commitments since, not cost
growth alone. Each site carries the community district and NTA it falls
in, for area totals. spending_kind (physical or overhead), reserve_flag and delivery come from project_spending
(pipeline/spending.py; reviewed rows in city_spending.csv and sca_spending.csv), null for dropped city projects.
Every program's projects carry the schedule summary of pipeline/schedules.py (SCHEDULE_FIELDS:
state, expected finish, baseline, signed late and slip days with their precision, schedule_rule); has_schedule
means a dated expected finish.
  lines.geojson        street lines used to place projects
  footprints.geojson   CPDB polygons used to place projects
  areas/districts.geojson, areas/neighborhoods.geojson, areas/boroughs.geojson

Money follows pipeline/money.py: budgets are per (FMS ID, managing agency), summed. Variances are
signed. A schedule variance is implausible, set to null and flagged, when the forecast date is after
LAST_PLAUSIBLE_YEAR (FDNY's 'Generator - EC16' once said 3026) or the variance is a correction of such a
date (over a century either way). Large real swings, such as Newtown Creek's 11 years, stay.
Coordinates are rounded to 5 decimals (about 1 m).
`status` is the same in every program: `current` for unfinished work in the latest report, `completed` for
finished work still listed there (phase group Done; out of the site's default totals, since MTA keeps
completed ACEPs for years and the city and SCA drop them unevenly), `dropped` for projects the latest
report no longer lists.
The manifest's `programs` registry lists each capital program the site can show; every project row names
its program. City capital projects are `nyc_capital`. School Construction Authority projects are `sca`
(pipeline/sca.py, sca_locations.py), in their own files:
  sca_projects.json    one object per SCA project (id 'sca:' + its DSF numbers and building code): cost is
                       the final estimate of actual costs; location from its building, with the evidence;
                       `city_fms_id` names a city FMS ID funding the same work, counted there in combined totals
  sca_sites.json       one site per placed project, keyed by `id`
  sca_phases.json      per project: its phase rows as SCA publishes them (2xh6-psuq)
MTA capital program projects are `mta` (pipeline/mta.py, mta_locations.py):
  mta_projects.json    one object per ACEP (id 'mta:' + ACEP): current budget and MTA's original, dates, % complete,
                       spending kind and reserve flag (pipeline/mta_spending.csv), location with its evidence;
                       `current` for live ACEPs in the latest Capital Dashboard load, `completed` for Complete ones,
                       `dropped` for Superseded ACEPs and those the latest load omits. MTA publishes no spending
                       to date here.
  mta_sites.json       per-site points and equal shares, keyed by `id`
Run after pipeline/sites.py (and pipeline/sca_locations.py for SCA, pipeline/mta_locations.py for MTA).
"""
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime

import duckdb

import phase_groups
import themes
from db import DB_PATH, RAW_DIR, ROOT
from geo import contains, distance_to_polygon_m
from money import project_budgets

OUT = ROOT / "data" / "export"
SCHEMA_VERSION = 8
LAST_PLAUSIBLE_YEAR = 2100
MAX_VARIANCE_DAYS = 36500
NEAR_KM = 30  # sites this close to the city's edge extend the map; farther ones get edge markers
NYC_BOUNDS = (40.47, 40.93, -74.27, -73.68)  # lat0, lat1, lon0, lon1: points inside count as in the city

SCHEDULE_FIELDS = ["schedule_state", "expected_finish", "finish_kind", "finish_precision", "baseline_finish",
                   "baseline_kind", "late_days", "late_precision", "late_phase", "slip_days", "schedule_rule"]
PHASE_FIELDS = ["phase", "source_phase", "start", "end", "end_kind", "planned_end", "precision"]

PROGRAMS = [{
    "id": "nyc_capital", "label": "NYC capital projects", "publisher": "NYC Office of Management and Budget",
    "datasets": ["fb86-vt7u", "gyhf-rsr3", "qj5n-h5qp", "95tx-snak", "fi59-268w"], "key": "fms_id", "currency": "USD",
    "files": {"projects": "projects.json", "schedules": "schedules.json", "history": "history.json",
              "sites": "sites.json", "funding": "funding.json", "lines": "lines.geojson",
              "footprints": "footprints.geojson", "schedule_phases": "schedule_phases.json"},
}]

SCA_PROGRAM = {
    "id": "sca", "label": "School construction (SCA)", "publisher": "NYC School Construction Authority",
    "datasets": ["2xh6-psuq", "8586-3zfm", "wg9x-4ke6", "9ck8-hj3u", "p6h4-mpyy", "qybk-bjjc", "7a57-qgkz",
                 "w9ak-ipjd", "ji82-xba5"], "key": "id", "currency": "USD",
    "files": {"projects": "sca_projects.json", "sites": "sca_sites.json", "phases": "sca_phases.json",
              "schedule_phases": "schedule_phases.json"},
}
SCA_FIELDS = [
    "program", "id", "dsf", "building", "school_name", "school_district", "project_types", "description",
    "n_phases", "status", "sca_status", "current_phase", "phase_group", "theme", "start_date", "forecast_end",
    "finished", "budget", "spend", "spend_pct", "spending_kind", "reserve_flag", "program_figure", "city_fms_id",
    "city_link", "has_schedule",
    *SCHEDULE_FIELDS,
    "borough", "tier", "source", "lon", "lat", "matched_to", "location_evidence", "on_map", "approximate",
    "district", "districts", "neighborhood",
]
MTA_PROGRAM = {
    "id": "mta", "label": "MTA capital program", "publisher": "Metropolitan Transportation Authority",
    "datasets": ["ehz8-ag3n", "wcsa-vkhf", "ji82-xba5"], "key": "id", "currency": "USD",
    "files": {"projects": "mta_projects.json", "sites": "mta_sites.json", "schedule_phases": "schedule_phases.json"},
}
MTA_FIELDS = [
    "program", "id", "acep", "capital_plan", "agency", "category", "element", "description", "scope", "mega_project",
    "phase", "phase_group", "status", "mta_status", "theme", "subtheme", "spending_kind", "mta_calls_reserve",
    "budget", "original_budget", "budget_vs_original", "pct_complete", "current_start", "forecast_completion",
    "original_completion", "first_load", "last_load", "has_schedule", *SCHEDULE_FIELDS,
    "borough", "tier", "source", "lon", "lat", "n_sites",
    "location_evidence", "on_map", "approximate", "outside_nyc", "district", "districts", "neighborhood",
]
MTA_PHASE_GROUP = {"Planning": "Active", "Design": "Active", "Construction": "Active", "Support": "Active",
                   "Complete": "Done", "Superseded": "Moved or renamed"}
MTA_STATUS = {"live": "current", "complete": "completed"}
SCA_PHASE_GROUP = {"complete": "Done", "active": "Active", "not_started": "Not started"}

PROJECT_FIELDS = [
    "program", "fms_id", "title", "agency_project_name", "description", "managing_agencies", "sponsor_agency", "pids",
    "borough", "community_board", "category", "budget_line", "theme", "subtheme",
    "phase", "phase_group", "has_schedule", "forecast_completion",
    "budget", "budget_city", "budget_non_city", "budget_federal", "budget_state", "budget_other",
    "spend", "spend_pct", "budget_change", "spending_kind", "reserve_flag", "delivery",
    "original_budget", "original_period", "original_basis", "budget_vs_original",
    "start_date",
    "design_start", "design_end", "construction_start", "construction_end", "phase_start",
    "first_reported", "last_reported", "status", *SCHEDULE_FIELDS,
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


def schedule_fields(con) -> dict[tuple[str, str], dict]:
    """(program, project id) -> the project's fields from project_schedule (pipeline/schedules.py)."""
    cols = ["state", *SCHEDULE_FIELDS[1:]]
    return {(prog, pid): {"has_schedule": r[1] is not None, **dict(zip(SCHEDULE_FIELDS, r, strict=True))}
            for prog, pid, *r in con.execute(f"""select program, project_id, {", ".join(cols)}
                from project_schedule""").fetchall()}


def spending(con) -> dict[tuple[str, str], tuple]:
    """(program, project id) -> (kind, reserve flag, delivery) from project_spending (pipeline/spending.py)."""
    return {(prog, pid): (k, r, d) for prog, pid, k, r, d in con.execute(
        "select program, project_id, kind, reserve_flag, delivery from project_spending").fetchall()}


def schedule_phases(con) -> dict[str, list[dict]]:
    """Export id -> phases with dates (project_phases), for every program."""
    out = defaultdict(list)
    for prog, pid, *r in con.execute("""select program, project_id, phase, source_phase, start, end_date, end_kind,
            planned_end, precision from project_phases order by program, project_id, coalesce(start, end_date)
            """).fetchall():
        out[pid if prog == "nyc_capital" else f"{prog}:{pid}"].append(dict(zip(PHASE_FIELDS, r, strict=True)))
    return out


def sca_export(con, cd_of, nta_of):
    """SCA projects, sites and phases (see the module docstring), or None when pipeline/sca.py has not run."""
    if not con.execute("select count(*) from duckdb_tables() where table_name = 'sca_buildings'").fetchone()[0]:
        return None
    projects, sites = [], []
    sched = schedule_fields(con)
    kinds = spending(con)
    for row in con.execute("""
            select p.project_key, p.dsf, p.building, p.school_name, p.school_district, p.project_types, p.description,
                   p.n_phases, p.status, p.current_phase, p.start_date, p.forecast_end, p.finished, p.cost, p.spent,
                   p.program_figure, p.city_fms_id, p.city_link, b.borough, b.tier, b.source, b.lon, b.lat,
                   b.matched_to, b.evidence
            from sca_projects p join sca_buildings b using (building) order by 1""").fetchall():
        (key, dsf, bldg, school, sd, types, desc, nph, status, phase, start, fend, done, cost, spent, figure, fms, link,
         boro, tier, source, lon, lat, matched, evidence) = row
        pid = f"sca:{key}"
        cd = cd_of(lon, lat) if lon is not None else None
        nta = nta_of(lon, lat) if lon is not None else None
        if lon is not None:
            sites.append({"id": pid, "site_no": 0, "lon": r5(lon), "lat": r5(lat), "share": 1.0,
                          "share_method": "single", "district": cd, "nta": nta})
        point = tier in ("A", "B")
        projects.append({
            "program": "sca", "id": pid, "dsf": dsf or None, "building": bldg, "school_name": school,
            "school_district": sd, "project_types": types, "description": present(desc), "n_phases": nph,
            "status": "completed" if status == "complete" else "current", "sca_status": status, "current_phase": phase,
            "phase_group": SCA_PHASE_GROUP[status], "theme": "Education",
            "start_date": start, "forecast_end": fend, "finished": done,
            "budget": round(cost, 2), "spend": round(spent, 2),
            "spend_pct": round(100 * spent / cost, 1) if cost else None,
            "spending_kind": kinds[("sca", key)][0], "reserve_flag": kinds[("sca", key)][1],
            "program_figure": figure, "city_fms_id": fms, "city_link": link, **sched[("sca", key)],
            "borough": boro, "tier": tier, "source": source, "lon": r5(lon), "lat": r5(lat), "matched_to": matched,
            "location_evidence": evidence, "on_map": point, "approximate": tier == "B",
            "district": cd if point else None, "districts": [cd] if point and cd is not None else [],
            "neighborhood": nta if point else None,
        })
    phases = defaultdict(list)
    for key, *rest in con.execute("""
            select project_key, phase, status, start_date, planned_end, actual_end, estimate, spent, counted,
                   program_figure
            from sca_phases order by project_key, row_no""").fetchall():
        phases[f"sca:{key}"].append(dict(zip(
            ["phase", "status", "start_date", "planned_end", "actual_end", "estimate", "spent", "counted",
             "program_figure"], rest, strict=True)))
    meta = json.loads((RAW_DIR / "2xh6-psuq.meta.json").read_text())
    program = {**SCA_PROGRAM, "updated": datetime.fromtimestamp(meta["rowsUpdatedAt"], UTC).date().isoformat()}
    return program, {
        "sca_projects.json": (projects, len(projects), SCA_FIELDS),
        "sca_sites.json": (sites, len(sites), list(sites[0]) if sites else []),
        "sca_phases.json": (phases, sum(len(v) for v in phases.values()),
                            ["phase", "status", "start_date", "planned_end", "actual_end", "estimate", "spent",
                             "counted", "program_figure"]),
    }


def mta_export(con, cd_of, nta_of, boro_geoms):
    """MTA projects and sites (see the module docstring), or None when pipeline/mta_locations.py has not run."""
    if not con.execute("select count(*) from duckdb_tables() where table_name = 'mta_locations'").fetchone()[0]:
        return None
    site_rows = defaultdict(list)
    sites = []
    for acep, n, lon, lat, share, method, seqs, tier, source in con.execute("""select acep, site_no, lon, lat, share,
            share_method, sequences, tier, source from mta_sites order by 1, 2""").fetchall():
        cd, nta = cd_of(lon, lat), nta_of(lon, lat)
        site_rows[acep].append(cd)
        sites.append({"id": f"mta:{acep}", "site_no": n, "lon": r5(lon), "lat": r5(lat), "share": round(share, 6),
                      "share_method": method, "district": cd, "nta": nta, "tier": tier, "source": source,
                      "sequences": seqs})
    projects = []
    sched = schedule_fields(con)
    for row in con.execute("""
            select p.acep, p.capital_plan, p.agency, p.category, p.element, p.description, p.scope, p.mega_project,
                   p.phase, p.status, p.spending_kind, p.mta_calls_reserve, p.current_budget, p.original_budget,
                   p.budget_vs_original, p.pct_complete, p.current_start, p.current_completion, p.original_completion,
                   p.first_load, p.last_load, l.borough, l.tier, l.source, l.lon, l.lat, l.n_sites, l.evidence
            from mta_projects p join mta_locations l using (acep) order by 1""").fetchall():
        (acep, plan, agency, cat, elem, desc, scope, mega, phase, status, kind, reserve, budget, orig, vs_orig, pct,
         start, completion, orig_completion, first, last, boro, tier, source, lon, lat, n_sites, evidence) = row
        point = tier in ("A", "B")
        districts = sorted({d for d in site_rows.get(acep, []) if d is not None})
        projects.append({
            "program": "mta", "id": f"mta:{acep}", "acep": acep, "capital_plan": plan, "agency": agency,
            "category": cat, "element": elem, "description": desc, "scope": present(scope), "mega_project": mega,
            "phase": phase, "phase_group": MTA_PHASE_GROUP.get(phase, "Unknown"),
            "status": MTA_STATUS.get(status, "dropped"), "mta_status": status,
            "theme": "Transportation", "subtheme": "Transit (MTA)", "spending_kind": kind, "mta_calls_reserve": reserve,
            "budget": None if budget is None else round(budget, 2), "original_budget": orig,
            "budget_vs_original": vs_orig, "pct_complete": pct, "current_start": start,
            "forecast_completion": completion, "original_completion": orig_completion,
            "first_load": first, "last_load": last, **sched[("mta", acep)],
            "borough": boro, "tier": tier, "source": source,
            "lon": r5(lon), "lat": r5(lat), "n_sites": n_sites, "location_evidence": evidence,
            "on_map": point, "approximate": tier == "B", "outside_nyc": outside_nyc(lat, lon, boro_geoms),
            "district": districts[0] if point and len(districts) == 1 else None,
            "districts": districts if point else [],
            "neighborhood": nta_of(lon, lat) if point else None,
        })
    return MTA_PROGRAM, {
        "mta_projects.json": (projects, len(projects), MTA_FIELDS),
        "mta_sites.json": (sites, len(sites), list(sites[0]) if sites else []),
    }


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
    originals = {f: (b, p, basis) for f, b, p, basis in con.execute("""select fms_id, sum(original_budget),
            min(original_period), case when count(distinct basis) = 1 then any_value(basis) else 'mixed' end
            from budget_original group by 1""").fetchall()}
    sched = schedule_fields(con)
    phases = schedule_phases(con)
    kinds = spending(con)

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
    def day(d):
        return None if d is None or d.year >= 9999 else d.date().isoformat()
    milestones = {r[0]: tuple(day(d) for d in r[1:]) for r in con.execute("""
        with last as (select fms_id, max(reporting_period) as p from project_budget_schedule group by 1)
        select b.fms_id, min(actual_design_start),
               case when bool_and(actual_design_end is not null) then max(actual_design_end) end,
               min(actual_construction_start),
               case when bool_and(actual_construction_end is not null) then max(actual_construction_end) end,
               min(current_phase_start)
        from project_budget_schedule b join last l on b.fms_id = l.fms_id and b.reporting_period = l.p
        group by 1""").fetchall()}
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
        orig_budget, orig_period, orig_basis = originals.get(f, (None, None, None))
        group = phase_groups.group(phase, groups)
        projects.append({
            "program": "nyc_capital", "fms_id": f, "title": title,
            "agency_project_name": present(aname), "description": present(desc),
            "managing_agencies": sorted(agencies[f]), "sponsor_agency": sponsor, "pids": sorted(pids[f]),
            "borough": boro, "community_board": board, "category": cat, "budget_line": bline,
            "theme": theme, "subtheme": subtheme,
            "phase": phase, "phase_group": group,
            "has_schedule": sched[("nyc_capital", f)]["has_schedule"], "forecast_completion": forecast,
            "budget": round(budget, 2),
            "budget_city": round(sum(y["city"] for y in fund), 2) if fund else None,
            "budget_non_city": noncity,
            "budget_federal": round(noncity * sh[1], 2) if sh else None,
            "budget_state": round(noncity * sh[0], 2) if sh else None,
            "budget_other": round(noncity * sh[2], 2) if sh else None,
            "spend": round(spend, 2),
            "spend_pct": round(100 * spend / budget, 1) if budget else None,
            "budget_change": round(budget - prev[-1], 2) if prev else None,
            **dict(zip(["spending_kind", "reserve_flag", "delivery"], kinds.get(("nyc_capital", f), (None,) * 3),
                       strict=True)),
            "original_budget": None if orig_budget is None else round(orig_budget, 2),
            "original_period": orig_period, "original_basis": orig_basis,
            "budget_vs_original": None if orig_budget is None else round(budget - orig_budget, 2),
            "start_date": start,
            **dict(zip(["design_start", "design_end", "construction_start", "construction_end", "phase_start"],
                       milestones.get(f, (None,) * 5), strict=True)),
            "first_reported": first[f], "last_reported": last,
            "status": "dropped" if last != latest else "completed" if group == "Done" else "current",
            **{k: sched[("nyc_capital", f)][k] for k in SCHEDULE_FIELDS},
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
                           "forecast_completion": forecast, "source": "fb86-vt7u"})
    # qj5n-h5qp also reports periods a project is missing from in the snapshots (before its first, or a gap).
    for f, p, b, spend in con.execute("""select fms_id, period, sum(budget), sum(spend) from budget_series
            group by all order by all""").fetchall():
        if f in history and p not in by_period[f]:
            history[f].append({"period": p, "budget": round(b, 2), "spend": spend, "phase": None,
                               "forecast_completion": None, "source": "qj5n-h5qp"})
    for rows in history.values():
        rows.sort(key=lambda r: r["period"])

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
        "schedule_phases.json": (phases, sum(len(v) for v in phases.values()), PHASE_FIELDS),
        "history.json": (history, sum(len(v) for v in history.values()), ["period", "budget", "spend", "phase",
                                                                            "forecast_completion", "source"]),
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
    programs = list(PROGRAMS)
    mta = mta_export(con, cd_of, nta_of, boro_geoms)
    if mta:
        programs.append(mta[0])
        files.update(mta[1])
    sca = sca_export(con, cd_of, nta_of)
    if sca:
        programs.append(sca[0])
        files.update(sca[1])
    sizes = {name: write(name, data) for name, (data, _, _) in files.items()}
    sources = [dict(zip(["dataset_id", "table", "name", "source_updated", "remote_rows", "loaded_rows", "loaded_at"],
                        r, strict=True)) for r in con.execute("select * from _ingest_meta order by 1").fetchall()]
    manifest = {
        "schema_version": SCHEMA_VERSION, "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "latest_snapshot": latest, "snapshots": periods, "last_plausible_year": LAST_PLAUSIBLE_YEAR,
        "max_variance_days": MAX_VARIANCE_DAYS,
        "implausible_variances": clamped, "programs": programs, "sources": sources,
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
