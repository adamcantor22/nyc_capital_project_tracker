"""Checks on data/export (pipeline/export.py). Run after the pipeline; skipped when not exported.
The field lists are pinned here: a change to them is a format change for the site and should be
deliberate (bump SCHEMA_VERSION in export.py)."""
import json
from collections import defaultdict

import duckdb
import pytest

from db import DB_PATH, ROOT
from money import project_budgets

EXPORT = ROOT / "data" / "export"
pytestmark = [
    pytest.mark.data,
    pytest.mark.skipif(not (EXPORT / "manifest.json").exists(), reason="data/export not built; run export.py"),
]

PROJECT_FIELDS = [
    "program", "fms_id", "title", "agency_project_name", "description", "managing_agencies", "sponsor_agency", "pids",
    "borough", "community_board", "category", "budget_line", "theme", "subtheme",
    "phase", "phase_group", "has_schedule", "forecast_completion",
    "budget", "budget_city", "budget_non_city", "budget_federal", "budget_state", "budget_other",
    "split_release", "split_basis",
    "spend", "spend_pct", "budget_change", "spending_kind", "reserve_flag", "delivery",
    "original_budget", "original_period", "original_basis", "budget_vs_original", "price_index",
    "budget_vs_original_real", "omb_delay_reason", "omb_delay_as_of",
    "start_date",
    "design_start", "design_end", "construction_start", "construction_end", "phase_start",
    "first_reported", "last_reported", "status",
    "schedule_state", "expected_finish", "finish_kind", "finish_precision", "baseline_finish",
    "baseline_kind", "late_days", "late_precision", "late_phase", "slip_days", "official_finish",
    "official_precision", "official_source", "schedule_rule",
    "area_class", "area_local", "area_regional", "area_citywide", "area_outside", "area_rule", "area_via",
    "tier", "source", "lon", "lat", "matched_to", "source_flag", "spread_m", "n_points", "on_map",
    "approximate", "outside_nyc", "district", "districts", "neighborhood",
]


def load(name):
    return json.loads((EXPORT / name).read_text())


@pytest.fixture(scope="module")
def projects():
    return load("projects.json")


def test_manifest_lists_every_file_with_pinned_project_fields():
    m = load("manifest.json")
    assert m["schema_version"] == 12
    assert {f for prog in m["programs"] for f in prog["files"].values()} <= set(m["files"])
    assert m["files"]["projects.json"]["fields"] == PROJECT_FIELDS
    assert all((EXPORT / name).exists() for name in m["files"])


def test_every_project_once_with_every_field(projects):
    con = duckdb.connect(str(DB_PATH), read_only=True)
    n = con.execute("select count(distinct fms_id) from project_budget_schedule").fetchone()[0]
    assert len(projects) == n == len({p["fms_id"] for p in projects})
    assert all(list(p) == PROJECT_FIELDS for p in projects)


def test_current_budget_matches_money_totals(projects):
    con = duckdb.connect(str(DB_PATH), read_only=True)
    budgets = project_budgets(con)
    latest = max(p for *_, p in budgets.values())
    expected = sum(b for b, _, p in budgets.values() if p == latest)
    got = sum(p["budget"] for p in projects if p["status"] in ("current", "completed"))
    assert abs(got - expected) < 1.0


def test_completed_status_is_the_done_phase_group(projects, sca, mta):
    for p in projects + sca + mta:
        assert (p["status"] == "completed") == (p["status"] != "dropped" and p["phase_group"] == "Done")


def test_site_shares_sum_to_one():
    totals = defaultdict(float)
    for s in load("sites.json"):
        totals[s["fms_id"]] += s["share"]
    assert all(abs(t - 1) < 1e-4 for t in totals.values())


def test_schedule_variances_are_plausible_or_flagged():
    m = load("manifest.json")
    for s in load("schedules.json"):
        for snap in s["snapshots"]:
            v = snap["variance_days"]
            assert v is None or abs(v) <= m["max_variance_days"]


def test_only_placed_projects_have_coordinates(projects):
    assert all((p["lon"] is None) == (p["tier"] == "Unplaced") for p in projects)
    assert all(p["on_map"] == (p["tier"] in ("A", "B")) for p in projects)


def test_projects_name_a_registered_program(projects):
    ids = {prog["id"] for prog in load("manifest.json")["programs"]}
    assert {p["program"] for p in projects} <= ids


def test_city_and_non_city_add_up_to_the_budget(projects):
    # fiscal-year rows sum to each (FMS ID, agency) record's budget; 37 projects (when set, May 2026) have an
    # agency record with no funding rows, so their split covers only part of the budget
    funded = [p for p in projects if p["budget_city"] is not None]
    off = [p["fms_id"] for p in funded if abs(p["budget_city"] + p["budget_non_city"] - p["budget"]) > 1]
    assert len(funded) > 0.95 * len(projects)
    assert len(off) <= 0.01 * len(funded), off[:10]


def test_non_city_split_adds_up(projects):
    # federal/state/other are CPDB shares applied to the non-city amount, so they sum back to it
    split = [p for p in projects if p["budget_federal"] is not None]
    assert split
    assert all(abs(p["budget_federal"] + p["budget_state"] + p["budget_other"] - p["budget_non_city"]) < 1
               for p in split)
    # every split names the CPDB release it came from and its basis
    assert all((p["split_release"] is not None) == (p in split) for p in projects)
    assert {p["split_basis"] for p in split} <= {"planned_and_committed", "planned"}


def test_every_project_has_an_original_budget(projects):
    bad = [p["fms_id"] for p in projects if p["original_budget"] is None or p["original_period"] is None
           or p["original_basis"] not in ("original_row", "first_snapshot", "mixed")
           or abs(p["budget"] - p["original_budget"] - p["budget_vs_original"]) > 0.02]
    assert bad == []


def test_history_periods_once_each_with_a_source():
    history = load("history.json")
    for f, rows in history.items():
        periods = [r["period"] for r in rows]
        assert periods == sorted(set(periods)), f
        assert {r["source"] for r in rows} <= {"fb86-vt7u", "qj5n-h5qp"}, f


def test_sites_carry_district_and_nta():
    sites = load("sites.json")
    # 86.8% when set: borough-level sites have none, nor do footprint parts in large parks and airports
    # (outside every district) or on piers and the shoreline
    assert sum(s["district"] is not None for s in sites) > 0.84 * len(sites)


def test_present_drops_placeholders():
    from export import present
    assert present("<blank>") is None and present(" <BLANK> ") is None and present("") is None
    assert present("Rebuild the roof") == "Rebuild the roof"


# --- SCA (School Construction Authority) ---------------------------------------------------------

SCA_FIELDS = [
    "program", "id", "dsf", "building", "school_name", "school_district", "project_types", "description",
    "n_phases", "status", "sca_status", "current_phase", "phase_group", "theme", "start_date", "forecast_end",
    "finished", "budget", "spend", "spend_pct", "spending_kind", "reserve_flag", "program_figure", "city_fms_id",
    "city_link", "has_schedule",
    "schedule_state", "expected_finish", "finish_kind", "finish_precision", "baseline_finish",
    "baseline_kind", "late_days", "late_precision", "late_phase", "slip_days", "official_finish",
    "official_precision", "official_source", "schedule_rule",
    "area_class", "area_local", "area_regional", "area_citywide", "area_outside", "area_rule", "area_via",
    "borough", "tier", "source", "lon", "lat", "matched_to", "location_evidence", "on_map", "approximate",
    "district", "districts", "neighborhood",
]


@pytest.fixture(scope="module")
def sca():
    if "sca_projects.json" not in load("manifest.json")["files"]:
        pytest.skip("SCA not exported (pipeline/sca.py not run)")
    return load("sca_projects.json")


def test_sca_program_and_pinned_fields(sca):
    m = load("manifest.json")
    prog = next(p for p in m["programs"] if p["id"] == "sca")
    assert prog["key"] == "id" and "2xh6-psuq" in prog["datasets"] and prog["updated"]
    assert m["files"]["sca_projects.json"]["fields"] == SCA_FIELDS
    assert all(list(p) == SCA_FIELDS for p in sca)


def test_sca_every_project_once_and_money_reconciles(sca):
    """Every SCA project exported once, and its cost is the sum of its counted phase rows: no double counting
    and no dropping against pipeline/sca.py."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    n, counted = con.execute("select (select count(*) from sca_projects), (select sum(counted) from sca_phases)"
                             ).fetchone()
    assert len(sca) == n == len({p["id"] for p in sca})
    assert abs(sum(p["budget"] for p in sca) - counted) < 1
    phases = load("sca_phases.json")
    assert set(phases) == {p["id"] for p in sca}
    assert all(abs(sum(r["counted"] for r in phases[p["id"]]) - p["budget"]) < 1 for p in sca)


def test_sca_every_project_has_location_provenance(sca):
    assert all(p["tier"] and p["source"] and len(p["location_evidence"] or "") >= 20 for p in sca)
    assert all((p["lon"] is None) == (p["tier"] == "Unplaced") for p in sca)
    assert all(p["on_map"] == (p["tier"] in ("A", "B")) for p in sca)


def test_sca_sites_one_per_placed_project(sca):
    sites = load("sca_sites.json")
    placed = {p["id"] for p in sca if p["lon"] is not None}
    assert sorted(s["id"] for s in sites) == sorted(placed)
    assert all(s["share"] == 1 for s in sites)


def test_sca_city_links_name_exported_city_projects(sca, projects):
    """A same-work link names a city FMS ID in projects.json; combined totals count that record instead."""
    fms = {p["fms_id"] for p in projects}
    linked = [p for p in sca if p["city_fms_id"]]
    assert linked and all(p["city_fms_id"] in fms and p["city_link"].startswith("same_work:") for p in linked)


# --- MTA capital program ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mta():
    if "mta_projects.json" not in load("manifest.json")["files"]:
        pytest.skip("MTA not exported (pipeline/mta_locations.py not run)")
    return load("mta_projects.json")


def test_mta_program_and_pinned_fields(mta):
    from export import MTA_FIELDS
    m = load("manifest.json")
    prog = next(p for p in m["programs"] if p["id"] == "mta")
    assert prog["key"] == "id" and "ehz8-ag3n" in prog["datasets"]
    assert m["files"]["mta_projects.json"]["fields"] == MTA_FIELDS
    assert all(list(p) == MTA_FIELDS for p in mta)


def test_mta_every_acep_once_and_live_money_reconciles(mta):
    con = duckdb.connect(str(DB_PATH), read_only=True)
    n, live = con.execute("""select count(*), sum(current_budget) filter (where status = 'live')
                             from mta_projects""").fetchone()
    assert len(mta) == n == len({p["id"] for p in mta})
    assert abs(sum(p["budget"] for p in mta if p["mta_status"] == "live") - live) < 1
    assert all(p["budget"] is not None for p in mta if p["status"] == "current")
    assert all((p["status"] == "current") == (p["mta_status"] == "live") for p in mta)
    assert all((p["status"] == "completed") == (p["mta_status"] == "complete") for p in mta)


def test_mta_history_and_growth_files(mta):
    from export import MTA_HISTORY_FIELDS, MTA_MEGA_FIELDS, MTA_PLAN_FIELDS
    con = duckdb.connect(str(DB_PATH), read_only=True)
    history = load("mta_history.json")
    assert sum(len(v) for v in history.values()) == con.execute("select count(*) from mta_history").fetchone()[0]
    assert all(list(h) == MTA_HISTORY_FIELDS for v in history.values() for h in v)
    latest = {p["id"]: p for p in mta}
    for pid, rows in history.items():
        assert [h["load"] for h in rows] == sorted(h["load"] for h in rows)
        assert rows[-1]["load"] == latest[pid]["last_load"] and rows[-1]["budget"] == latest[pid]["budget"]
    plans, megas = load("mta_plan_amendments.json"), load("mta_mega_series.json")
    assert len(plans) == con.execute("select count(*) from mta_plan_amendments").fetchone()[0]
    assert len(megas) == con.execute("select count(*) from mta_mega_series").fetchone()[0]
    assert all(list(r) == MTA_PLAN_FIELDS and r["rule"] and r["dataset"] for r in plans)
    assert all(list(r) == MTA_MEGA_FIELDS and r["rule"] and r["dataset"] for r in megas)
    m = load("manifest.json")
    files = next(p for p in m["programs"] if p["id"] == "mta")["files"]
    assert {"history", "plan_amendments", "mega_series"} <= set(files)


def test_mta_location_provenance_and_sites(mta):
    assert all(len(p["location_evidence"] or "") >= 20 for p in mta)
    assert all((p["lon"] is None) == (p["tier"] == "Unplaced") for p in mta)
    totals = defaultdict(float)
    for s in load("mta_sites.json"):
        totals[s["id"]] += s["share"]
    assert totals and all(abs(t - 1) < 1e-4 for t in totals.values())
    assert set(totals) == {p["id"] for p in mta if p["lon"] is not None}


def test_schedule_fields_follow_project_schedule(projects):
    con = duckdb.connect(str(DB_PATH), read_only=True)
    n = con.execute("""select count(*) from project_schedule where program = 'nyc_capital'
                       and expected_finish is not null""").fetchone()[0]
    assert sum(p["has_schedule"] for p in projects) == n
    assert all(p["has_schedule"] == (p["expected_finish"] is not None) for p in projects)
    assert all(p["late_precision"] for p in projects if p["late_days"] is not None)


def test_schedule_phases_keyed_by_exported_ids(projects):
    phases = load("schedule_phases.json")
    ids = {p["fms_id"] for p in projects}
    for name, key in (("sca_projects.json", "id"), ("mta_projects.json", "id")):
        if (EXPORT / name).exists():
            ids |= {p[key] for p in load(name)}
    assert set(phases) <= ids


def test_area_served_fields_and_rules(projects):
    """Every project of every program carries its area-served class and shares (summing to one), from a reviewed
    rule listed in serving_rules.json; the manifest marks the classes as estimates."""
    m = load("manifest.json")
    assert m["area_served"]["estimate"] is True and "not official" in m["area_served"]["note"]
    rules = {r["rule_id"]: r for r in load("serving_rules.json")}
    rows = list(projects)
    for name in ("sca_projects.json", "mta_projects.json"):
        if name in m["files"]:
            rows += load(name)
    keys = ("area_local", "area_regional", "area_citywide", "area_outside")
    for p in rows:
        assert p["area_class"] in ("local", "regional", "citywide", "outside")
        assert abs(sum(p[k] for k in keys) - 1) < 1e-3
        assert p[f"area_{p['area_class']}"] == max(p[k] for k in keys)
        assert rules[p["area_rule"]]["status"] == "reviewed"
