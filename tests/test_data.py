"""Checks on the built database (data/capital.duckdb). Run after the pipeline; skipped when the
database is absent. Thresholds sit a few points below the values measured when they were set
(noted inline), so real regressions fail but ordinary data refreshes don't.

    .venv/bin/python -m pytest -m data      # only these
"""
import csv
import json
from pathlib import Path

import duckdb
import pytest

import phase_groups
from db import DB_PATH
from facility_codes import code_key, load_codes, resolve
from geo import contains, in_nyc
from street_lines import MAX_EXTENT_M, MAX_STREET_ONLY_DISTRICT_M
from validation import (
    address_agreement,
    bridge_agreement,
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

def test_site_shares_sum_to_one_and_cover_every_placed_project(con):
    bad = con.execute("""select count(*) from (select fms_id, sum(share) s from project_sites group by 1)
                         where abs(s - 1) > 1e-9""").fetchone()[0]
    missing = con.execute("""select count(*) from project_locations where tier <> 'Unplaced'
                             and fms_id not in (select fms_id from project_sites)""").fetchone()[0]
    assert bad == 0 and missing == 0


def test_every_raw_phase_maps_to_a_group(con):
    groups = phase_groups.load()
    raw = [p for (p,) in con.execute("select distinct current_phase from project_budget_schedule").fetchall()]
    assert [p for p in raw if p and phase_groups.key(p) not in groups] == []


def test_one_location_per_project_with_valid_tier(con):
    n, distinct, bad_tier, null_coord = con.execute("""
        select count(*), count(distinct fms_id), count_if(tier not in ('A', 'B', 'C', 'D', 'E', 'Unplaced')),
               count_if((lon is null or lat is null) <> (tier = 'Unplaced')) from project_locations""").fetchone()
    assert n == distinct
    assert bad_tier == 0 and null_coord == 0   # coordinates exactly when placed


def test_multi_site_points_are_one_of_their_sites(con):
    """A multi-point Tier A project sits at its most central site, never at the mean, which for scattered
    sites fell in the water (Citywide Seawall Reconstruction, in the harbour off Bayonne). Sites within
    sites.MERGE_M are merged, so the point is within that of one."""
    bad = con.execute("""select l.fms_id from project_locations l where l.tier = 'A' and l.n_points > 1
                         and not exists (select 1 from project_sites s where s.fms_id = l.fms_id
                                         and abs(s.lon - l.lon) < 0.0012 and abs(s.lat - l.lat) < 0.0009)
                      """).fetchall()
    assert bad == []


def test_polygon_points_lie_on_their_polygon(con):
    """CPDB footprints are placed at a point inside the shape, not the centroid, which for long or scattered
    shapes fell offshore (Shorefront Parkway) or blocks away from the street work."""
    rows = con.execute("select fms_id, lon, lat, geojson from loc_cpdb_polygons").fetchall()
    def on_shape(g, lon, lat):
        parts = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        return any(contains({"type": "Polygon", "coordinates": p}, lon, lat) for p in parts)
    bad = [f for f, lon, lat, g in rows if not on_shape(json.loads(g), lon, lat)]
    assert bad == []


def test_every_project_has_a_location_row(con):
    missing = con.execute("""select count(distinct fms_id) from project_budget_schedule
        where fms_id not in (select fms_id from project_locations)""").fetchone()[0]
    assert missing == 0


def test_locations_refer_to_known_projects(con):
    orphans = con.execute("""select count(*) from project_locations
        where fms_id not in (select fms_id from project_budget_schedule)""").fetchone()[0]
    assert orphans == 0


def test_only_upstate_gazetteer_features_lie_outside_nyc(con):
    upstate = {n for (n,) in con.execute("select name from named_features where lookup like 'gnis:%'").fetchall()}
    outside = [(f, src, name) for f, src, name, lon, lat in con.execute(
        "select fms_id, source, matched_to, lon, lat from project_locations where lon is not null").fetchall()
        if not in_nyc(lat, lon)]
    assert [o for o in outside if o[2] not in upstate] == []


def test_projects_naming_a_district_are_always_placed(con):
    missing = con.execute(f"""
        select count(*) from (select fms_id, any_value(community_board) board from project_budget_schedule
                              where reporting_period = {latest(con)} group by 1) p
        left join project_locations l using (fms_id)
        where (l.fms_id is null or l.tier = 'Unplaced')
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


def test_every_listed_source_error_is_flagged_on_its_project(con):
    ids = {r["fms_id"] for r in source_errors() if r["source"] != "schedule_history"}
    flagged = dict(con.execute("select fms_id, source_flag from project_locations "
                               "where source_flag is not null").fetchall())
    placed = {f for (f,) in con.execute("select fms_id from project_locations").fetchall()}
    assert {i for i in ids & placed if i not in flagged} == set()
    assert not {r["fms_id"] for r in source_errors() if r["source"] == "schedule_history"} & set(flagged)
    assert {flagged[r["fms_id"]] for r in source_errors() if r["problem"] == "unclear"
            and r["fms_id"] in flagged} <= {"point_disputed", "official_point_rejected"}


def test_listing_wrong_points_are_kept(con):
    ids = [r["fms_id"] for r in source_errors() if r["problem"] == "listing_wrong"]
    tiers = dict(con.execute("select fms_id, tier from project_locations where list_contains(?, fms_id)",
                             [ids]).fetchall())
    assert ids and all(tiers.get(i) == "A" for i in ids)


def test_bridge_bins_agree_with_agency_points(con):
    ds = bridge_agreement(con)
    assert len(ds) >= 80
    assert sum(d <= 500 for d in ds) / len(ds) >= 0.9   # 0.94 when set; misses are CPDB errors


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


# --- SCA (pipeline/sca.py) --------------------------------------------------------------------------

def sca_built(con) -> bool:
    return bool(con.execute("select count(*) from duckdb_tables() where table_name = 'sca_phases'").fetchone()[0])


def test_sca_every_published_row_is_counted_once(con):
    if not sca_built(con):
        pytest.skip("pipeline/sca.py not run")
    raw = json.loads((DB_PATH.parent / "raw" / "2xh6-psuq.json").read_text())
    n, keys = con.execute("select count(*), count(distinct row_no) from sca_phases").fetchone()
    assert n == keys == len(raw)
    orphans = con.execute("select count(*) from sca_phases where project_key not in "
                          "(select project_key from sca_projects)").fetchone()[0]
    assert orphans == 0
    phases, projects = con.execute("select (select sum(counted) from sca_phases), "
                                   "(select sum(cost) from sca_projects)").fetchone()
    assert abs(phases - projects) < 1


def test_sca_counted_money_reconciles_with_published_estimates(con):
    """Counted = published estimates, minus the reviewed program figures, plus those schools' own spending."""
    if not sca_built(con):
        pytest.skip("pipeline/sca.py not run")
    est, counted, figures, their_spend = con.execute("""
        select sum(coalesce(estimate, 0)), sum(counted), sum(coalesce(program_figure, 0)),
               sum(coalesce(spent, 0)) filter (where program_figure is not null) from sca_phases""").fetchone()
    assert abs(counted - (est - figures + their_spend)) < 1


def test_sca_repeated_amounts_are_reviewed(con):
    """An amount of $10M+ on 3+ buildings with the same type, description and phase is either a program figure
    copied onto each school or separate projects that happen to match; pipeline/sca_repeats.csv records which,
    with evidence. A new one fails here until reviewed; a listed one that no longer occurs is stale."""
    if not sca_built(con):
        pytest.skip("pipeline/sca.py not run")
    from sca import REPEAT_MIN, load_repeats
    found = {tuple(r) for r in con.execute("""
        select project_type, description, phase, estimate from sca_phases where estimate >= ?
        group by all having count(distinct building) >= 3""", [REPEAT_MIN]).fetchall()}
    listed = set(load_repeats())
    assert found - listed == set(), "new repeated amounts: review and add to pipeline/sca_repeats.csv"
    assert listed - found == set(), "stale rows in pipeline/sca_repeats.csv"


def test_sca_every_building_has_a_location_row(con):
    if not sca_built(con):
        pytest.skip("pipeline/sca.py not run")
    missing = con.execute("select count(distinct building) from sca_projects "
                          "where building not in (select building from sca_buildings)").fetchone()[0]
    assert missing == 0


def test_sca_tier_a_coverage_floor(con):
    """Share of SCA buildings and of SCA money placed from official building-code sources (pipeline/sca_locations.py).
    When set: 92.1% of buildings, 98.7% of money."""
    if not sca_built(con):
        pytest.skip("pipeline/sca.py not run")
    buildings, money = con.execute("""
        select count(*) filter (where b.tier = 'A')::double / count(*), sum(p.c) filter (where b.tier = 'A') / sum(p.c)
        from sca_buildings b join (select building, sum(cost) as c from sca_projects group by 1) p using (building)
    """).fetchone()
    assert buildings > 0.89 and money > 0.96


def test_sca_and_doe_points_agree(con):
    """Where SCA's active list and DOE's 2019-20 locations both place a building code, they mostly agree; SCA's
    points match Geoclient's address point exactly, DOE's may sit on the building. When set: 86% within 100 m."""
    if not sca_built(con):
        pytest.skip("pipeline/sca.py not run")
    from geo import central_point, haversine_m
    from sca_locations import coordinate_rows
    sca = coordinate_rows("8586-3zfm", "buildingid", "latitude", "longitude")
    doe = coordinate_rows("wg9x-4ke6", "primary_building_code", "latitude", "longitude")
    d = [haversine_m(a[1], a[0], b[1], b[0]) for a, b in
         ((central_point(sca[k]), central_point(doe[k])) for k in sca.keys() & doe.keys())]
    assert len(d) > 500 and sum(x <= 100 for x in d) / len(d) > 0.82


@pytest.mark.parametrize("rule, annex, floor_100, floor_500", [
    ("number", False, 0.95, 0.97),  # 97.9% / 100% when set (534 buildings)
    ("number", True, 0.80, 0.88),   # 85.0% / 93.3% when set (60 annex-like buildings)
    ("name", False, 0.76, 0.90),    # 80.2% / 93.7% when set (207 buildings)
])
def test_sca_name_matching_precision(con, rule, annex, floor_100, floor_500):
    """School-name matches (Tier B) measured on buildings with an official point (pipeline/sca_locations.py).
    The buildings they place are often annexes, so the annex-like row is the fairer guide."""
    if not sca_built(con):
        pytest.skip("pipeline/sca.py not run")
    n, near, mid = con.execute("""select count(*), avg((distance_m <= 100)::int), avg((distance_m <= 500)::int)
                                  from sca_name_validation where rule = ? and annex_like = ?""",
                               [rule, annex]).fetchone()
    assert n >= 40 and near > floor_100 and mid > floor_500


def test_sca_cited_sites_resolve_and_are_used(con):
    """Every row of pipeline/sca_sites.csv places its building; a row an official list now covers is stale."""
    if not sca_built(con):
        pytest.skip("pipeline/sca.py not run")
    from sca_locations import load_sites
    used = {b for (b,) in con.execute("select building from sca_buildings where source = 'cited_site'").fetchall()}
    assert set(load_sites()) == used


def test_sca_dob_filing_lots_agree_with_doe(con):
    """The tax lot most often filed under a building code (DOB NOW filings by SCA or DOE) is DOE's own lot for it.
    When set: 96.2% of 237 codes."""
    if not sca_built(con):
        pytest.skip("pipeline/sca.py not run")
    from sca_locations import filing_lots
    path = DB_PATH.parent / "raw" / "w9ak-ipjd-sca.json"
    if not path.exists():
        pytest.skip("DOB filings not fetched")
    codes = {b for (b,) in con.execute("select building from sca_buildings").fetchall()}
    lots = filing_lots(json.loads(path.read_text()), codes)
    doe = {}
    for r in json.loads((DB_PATH.parent / "raw" / "wg9x-4ke6.json").read_text()):
        if r.get("borough_block_lot"):
            doe.setdefault(r["primary_building_code"], set()).add(r["borough_block_lot"])
    both = [k for k in lots if k in doe]
    assert len(both) > 200 and sum(lots[k][0] in doe[k] for k in both) / len(both) > 0.93


def test_sca_every_building_has_provenance(con):
    """Each placement names its dataset (and filing numbers, list row or matched name) in `evidence`."""
    if not sca_built(con):
        pytest.skip("pipeline/sca.py not run")
    assert con.execute("select count(*) from sca_buildings where coalesce(length(evidence), 0) < 20").fetchone()[0] == 0


def test_sca_no_borough_conflicts(con):
    """A source point more than 2 km outside the borough its building code names is skipped; none occur. If one
    appears, check it against the address before trusting either."""
    if not sca_built(con):
        pytest.skip("pipeline/sca.py not run")
    assert con.execute("select count(*) from sca_building_conflicts").fetchone()[0] == 0


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
