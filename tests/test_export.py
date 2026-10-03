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
    "spend", "spend_pct", "budget_change", "start_date", "first_reported", "last_reported", "status",
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
    assert m["schema_version"] == 3
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
    got = sum(p["budget"] for p in projects if p["status"] == "current")
    assert abs(got - expected) < 1.0


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


def test_sites_carry_district_and_nta():
    sites = load("sites.json")
    assert sum(s["district"] is not None for s in sites) > 0.9 * len(sites)


def test_present_drops_placeholders():
    from export import present
    assert present("<blank>") is None and present(" <BLANK> ") is None and present("") is None
    assert present("Rebuild the roof") == "Rebuild the roof"
