"""Checks on the built database (data/capital.duckdb). Run after the pipeline; skipped when the
database is absent. Thresholds sit a few points below the values measured when they were set
(noted inline), so real regressions fail but ordinary data refreshes don't.

    .venv/bin/python -m pytest -m data      # only these
"""
import csv
from pathlib import Path

import duckdb
import pytest

from db import DB_PATH
from facility_codes import code_key, load_codes, resolve
from geo import in_nyc
from street_lines import MAX_EXTENT_M, MAX_STREET_ONLY_DISTRICT_M
from validation import (
    address_agreement,
    district_agreement,
    named_feature_agreement,
    share_within,
    street_line_agreement,
    tier_b_precision,
)

pytestmark = [
    pytest.mark.data,
    pytest.mark.skipif(not DB_PATH.exists(), reason="data/capital.duckdb not built; run the pipeline"),
]

DISTRICT_BOARD = "(Manhattan|Bronx|Brooklyn|Queens|Staten Island) (0[1-9]|1[0-8])"


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(DB_PATH), read_only=True)
    yield c
    c.close()


def latest(con) -> int:
    return con.execute("select max(reporting_period) from project_budget_schedule").fetchone()[0]


# --- loads ---------------------------------------------------------------------------------------

def test_every_source_loaded_all_remote_rows(con):
    bad = con.execute("select table_name, loaded_rows, remote_count from _ingest_meta "
                      "where loaded_rows <> remote_count").fetchall()
    assert bad == []


# --- project_locations structure -----------------------------------------------------------------

def test_one_location_per_project_with_valid_tier(con):
    n, distinct, bad_tier, null_coord = con.execute("""
        select count(*), count(distinct fms_id), count_if(tier not in ('A', 'B', 'C', 'D', 'E')),
               count_if(lon is null or lat is null) from project_locations""").fetchone()
    assert n == distinct
    assert bad_tier == 0 and null_coord == 0


def test_locations_refer_to_known_projects(con):
    orphans = con.execute("""select count(*) from project_locations
        where fms_id not in (select fms_id from project_budget_schedule)""").fetchone()[0]
    assert orphans == 0


def test_only_upstate_gazetteer_features_lie_outside_nyc(con):
    upstate = {n for (n,) in con.execute("select name from named_features where lookup like 'gnis:%'").fetchall()}
    outside = [(f, src, name) for f, src, name, lon, lat in con.execute(
        "select fms_id, source, matched_to, lon, lat from project_locations").fetchall() if not in_nyc(lat, lon)]
    assert [o for o in outside if o[2] not in upstate] == []


def test_projects_naming_a_district_are_always_placed(con):
    missing = con.execute(f"""
        select count(*) from (select fms_id, any_value(community_board) board from project_budget_schedule
                              where reporting_period = {latest(con)} group by 1) p
        left join project_locations l using (fms_id)
        where l.fms_id is null
          and regexp_matches(p.board, '{DISTRICT_BOARD}')""").fetchone()[0]
    assert missing == 0


def test_street_lines_respect_length_caps(con):
    over = con.execute(f"""select count(*) from street_lines
        where (kind = 'extent' and length_m > {MAX_EXTENT_M})
           or (kind = 'street_only' and length_m > {MAX_STREET_ONLY_DISTRICT_M})""").fetchone()[0]
    assert over == 0


# --- coverage floors (guard against a broken join silently dropping placements) -----------------

def test_tier_a_coverage_floor(con):
    share = con.execute(f"""
        select avg(case when l.tier = 'A' then 1.0 else 0 end)
        from (select distinct fms_id from project_budget_schedule where reporting_period = {latest(con)}) p
        left join project_locations l using (fms_id)""").fetchone()[0]
    assert share >= 0.45   # 0.498 when set


def test_tier_a_points_mostly_in_their_listed_borough(con):
    # Cheap proxy for the profile's point-in-polygon check: nearest district centroid's borough.
    rows = con.execute(f"""
        with p as (select fms_id, any_value(borough) borough from project_budget_schedule
                   where reporting_period = {latest(con)} group by 1),
             a as (select l.fms_id, l.lon, l.lat, p.borough from project_locations l join p using (fms_id)
                   where l.tier = 'A' and p.borough in ('Manhattan', 'Bronx', 'Brooklyn', 'Queens', 'Staten Island'))
        select a.borough = arg_min(d.borough, (a.lon - d.lon) ^ 2 + (a.lat - d.lat) ^ 2)
        from a cross join ref_community_districts d group by a.fms_id, a.borough""").fetchall()
    same = sum(r[0] for r in rows) / len(rows)
    assert same >= 0.93   # point-in-polygon: 98% in-borough, the rest mostly in parks outside districts


# --- precision floors ----------------------------------------------------------------------------

def test_tier_b_name_matching_precision(con):
    matched, near = tier_b_precision(con)
    assert matched >= 500
    assert near / matched >= 0.80   # 0.855 when set (in-sample)


def test_address_geocoding_agrees_with_agency_sources(con):
    dists = [d for ds in address_agreement(con).values() for d in ds]
    assert len(dists) >= 100
    assert share_within(dists, 500) >= 0.90   # 0.95 when set


def test_named_features_agree_with_agency_sources(con):
    dists = named_feature_agreement(con)
    assert len(dists) >= 40
    assert share_within(dists, 1000) >= 0.85   # 0.92 when set


def test_facility_code_precision(con):
    n, near = con.execute("""select count(*), count_if(distance_m <= 500) from location_validation
                             where rule = 'facility_code'""").fetchone()
    assert n >= 100
    assert near / n >= 0.82   # 0.877 when set (in-sample; misses are mostly off-campus sites)


def test_fdny_units_fall_in_their_listed_district(con):
    n_in, n_other, n_out = district_agreement(con)["fdny_unit"]
    assert n_in + n_other + n_out >= 60
    assert n_in / (n_in + n_other + n_out) >= 0.85   # 0.899 when set; misses are mostly placeholder boards


def test_nypd_precinct_precision(con):
    n, near = con.execute("""select count(*), count_if(distance_m <= 500) from location_validation
                             where rule = 'nypd_unit'""").fetchone()
    assert n >= 6
    assert near / n >= 0.75   # 0.875 when set; the miss is a CPDB point 6 km from the 77th Precinct


def test_dsny_garage_precision(con):
    n, near = con.execute("""select count(*), count_if(distance_m <= 500) from location_validation
                             where rule = 'dsny_unit'""").fetchone()
    assert n >= 12
    assert near / n >= 0.75   # 0.875 when set; one miss is a CPDB point on the Brooklyn 9 garage


def test_doc_placements_stay_on_the_island(con):
    """Few DOC projects have a usable Tier A point: CPDB's generic Rikers point is excluded via
    source_errors.csv. Named jails agree within 2 m; island-wide work (fencing, the powerhouse) is
    judged against the island, about 1.5 km across."""
    n, far = con.execute("""select count(*), count_if(distance_m > 1500) from location_validation
                            where rule = 'doc_unit'""").fetchone()
    assert n >= 4 and far == 0


def source_errors():
    with (Path(__file__).parents[1] / "pipeline" / "source_errors.csv").open() as f:
        return list(csv.DictReader(f))


def test_every_borough_conflict_is_in_the_source_errors_list(con):
    """pipeline/source_errors.csv is the record of suspected source errors: each Tier A point the borough
    check flags must be listed, with evidence and a verdict."""
    listed = {(r["fms_id"], r["source"]) for r in source_errors()}
    flagged = set(con.execute("select fms_id, source from borough_conflicts").fetchall())
    assert flagged - listed == set()


def test_listing_wrong_points_are_kept(con):
    ids = [r["fms_id"] for r in source_errors() if r["problem"] == "listing_wrong"]
    tiers = dict(con.execute("select fms_id, tier from project_locations where list_contains(?, fms_id)",
                             [ids]).fetchall())
    assert ids and all(tiers.get(i) == "A" for i in ids)


def test_neighborhood_tier_contains_tier_a_points(con):
    """Tier C on projects with Tier A points: distance from the point to the named neighborhood."""
    n, near = con.execute("""select count(*), count_if(distance_m <= 500) from neighborhood_validation""").fetchone()
    assert n >= 300
    assert near / n >= 0.88   # 0.93 when set


@pytest.mark.parametrize("kind, floor", [("extent", 0.82), ("street_only", 0.82)])  # both ~0.89 when set
def test_street_lines_agree_with_tier_a(con, kind, floor):
    _, dists = street_line_agreement(con)
    assert len(dists.get(kind, [])) >= 40
    assert share_within(dists[kind], 500) >= floor


def test_facility_codes_resolve_to_exactly_one_facdb_row(con):
    _, unresolved = resolve(con, load_codes())
    assert unresolved == []   # a FacDB refresh renamed or duplicated a facility


def test_every_facility_code_is_supported_by_titles_or_tier_a(con):
    """The inclusion rule for pipeline/facility_codes.csv: some title under the code names the facility,
    or a project under the code has a Tier A location within 500 m of it."""
    codes = load_codes()
    titles = con.execute("""select fms_id, any_value(managing_agency),
        upper(string_agg(coalesce(agency_project_name, '') || ' ' || coalesce(fms_project_name, ''), ' '))
        from project_budget_schedule group by 1""").fetchall()
    keyed = [(code_key(a, f), t) for f, a, t in titles]
    named = {k for k, t in keyed if k in codes and codes[k]["regex"].search(t)}
    near = {code_key(a, f) for f, a in con.execute(
        "select fms_id, managing_agency from location_validation where rule = 'facility_code' and distance_m <= 500"
    ).fetchall()}
    assert set(codes) - named - near == set()


# --- golden set: hand-verified placements and known past mistakes --------------------------------

def load_golden():
    with (Path(__file__).parent / "golden_locations.csv").open() as f:
        return list(csv.DictReader(f))


@pytest.mark.parametrize("row", load_golden(), ids=lambda r: r["fms_id"])
def test_golden_locations(con, row):
    """tests/golden_locations.csv: add a row whenever a placement is verified or a mistake is found."""
    got = con.execute("select tier, matched_to from project_locations where fms_id = ?", [row["fms_id"]]).fetchone()
    tier, matched_to = got if got else (None, None)
    if row["expected_tier"]:
        assert tier == row["expected_tier"], row["evidence"]
    if row["expected_matched_to"]:
        assert matched_to == row["expected_matched_to"], row["evidence"]
    if row["forbidden_matched_to"]:
        assert matched_to != row["forbidden_matched_to"], row["evidence"]
