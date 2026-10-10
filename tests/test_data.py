"""Checks on the built database (data/capital.duckdb). Run after the pipeline; skipped when the
database is absent. Thresholds sit a few points below the values measured when they were set
(noted inline), so real regressions fail but ordinary data refreshes don't.

    .venv/bin/python -m pytest -m data      # only these
"""
import csv
import datetime
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


@pytest.mark.parametrize("rule, floor", [("bridge_id", 0.95), ("bridge_name", 0.90)])  # 25/25, 58/60 when set
def test_inferred_bridge_precision(con, rule, floor):
    """Bridges inferred from a DOT FMS ID or named in a title (pipeline/bridges.py), run on projects with Tier A
    points; the name misses when set were reference points (a park polygon, a CPDB polygon 3 km off)."""
    n, near = con.execute("""select count(*), count_if(distance_m <= 500) from location_validation
                             where rule = ?""", [rule]).fetchone()
    assert n >= 20
    assert near / n >= floor


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


def test_linked_project_districts(con):
    """Tier D from a cited FMS ID: where a project and the one its title cites are both Tier A, they lie in the same
    community district for at least 72% of pairs (59 of 74, 80%, when set); every linked_project row names what it
    cites."""
    from locations import cited_ids
    tier_a = {f: (lon, lat) for f, lon, lat in con.execute(
        "select fms_id, lon, lat from project_locations where tier = 'A'").fetchall()}
    titles = con.execute("""select fms_id, arg_max(coalesce(agency_project_name, '') || ' ' ||
        coalesce(fms_project_name, ''), reporting_period) from project_budget_schedule group by 1""").fetchall()
    cds = [(c, json.loads(g))
           for c, g in con.execute("select boro_cd, geojson from ref_community_districts").fetchall()]

    def cd(pt):
        return next((c for c, g in cds if contains(g, *pt)), None)

    pairs = [(f, t) for f, title in titles if f in tier_a for t in cited_ids(f, title, tier_a)]
    same = sum(cd(tier_a[f]) == cd(tier_a[t]) for f, t in pairs)
    assert len(pairs) >= 60 and same / len(pairs) >= 0.72
    rows = con.execute("select matched_to from project_locations where source = 'linked_project'").fetchall()
    assert rows and all(m and "(CD " in m for (m,) in rows)

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
    with evidence. A new one fails here until reviewed (stale rows are checked across every version, below)."""
    if not sca_built(con):
        pytest.skip("pipeline/sca.py not run")
    from sca import REPEAT_MIN, load_repeats
    found = {tuple(r) for r in con.execute("""
        select project_type, description, phase, estimate from sca_phases where estimate >= ?
        group by all having count(distinct building) >= 3""", [REPEAT_MIN]).fetchall()}
    listed = set(load_repeats())
    assert found - listed == set(), "new repeated amounts: review and add to pipeline/sca_repeats.csv"


def test_sca_city_links_review_every_school_record(con):
    """Every city FMS ID prefixed 'SCA' or 'ACEDOE', or managed or sponsored by DOE, is reviewed in
    pipeline/sca_city_links.csv with evidence; each link names exactly one SCA project at a building the city record
    names; every SCA project labelled DCAS is linked; a building marked no_sca_match still has no such work."""
    if not sca_built(con):
        pytest.skip("pipeline/sca.py not run")
    from sca import LINKS
    with LINKS.open() as f:
        rows = list(csv.DictReader(f))
    city = dict(con.execute("""select fms_id, string_agg(distinct coalesce(fms_project_name, '') || ' '
        || coalesce(agency_project_description, ''), ' ') from project_budget_schedule
        where fms_id like 'SCA%' or fms_id like 'ACEDOE%' or managing_agency = 'DOE' or sponsor_agency = 'DOE'
        group by 1""").fetchall())
    assert {r["fms_id"] for r in rows} == set(city), "review new or stale FMS IDs in pipeline/sca_city_links.csv"
    assert all(len(r["evidence"]) > 40 and "fb86-vt7u" in r["evidence"] for r in rows)
    for r in rows:
        if r["sca_dsf"]:
            assert r["building"] in r["fms_id"] + city[r["fms_id"]], r["fms_id"]
            assert con.execute("select count(*) from sca_projects where building = ? and dsf = ?",
                               [r["building"], r["sca_dsf"]]).fetchone()[0] == 1, r["fms_id"]
        if r["decision"] == "no_sca_match":
            assert con.execute("""select count(*) from sca_projects where building = ? and (description like '%DCAS%'
                or description like 'ACE %' or description ilike '%electrif%' or description ilike '%solar%')""",
                               [r["building"]]).fetchone()[0] == 0, r["fms_id"]
    assert sum(r["decision"] == "same_work" for r in rows) == con.execute(
        "select count(city_fms_id) from sca_projects").fetchone()[0]
    assert con.execute("select count(*) from sca_projects where description like '%DCAS%' "
                       "and city_fms_id is null").fetchone()[0] == 0


def history_built(con) -> bool:
    return bool(con.execute("select count(*) from duckdb_tables() where table_name = 'sca_history'").fetchone()[0])


def test_sca_versions_account_for_every_capture(con):
    """Every archived capture and dated copy is a version: usable and kept, the same as an earlier one, or unusable
    with a reason; no usable version has a date or money value that fails to parse."""
    if not history_built(con):
        pytest.skip("pipeline/sca_history.py not run")
    from sca_history import ARCHIVE, OWN
    files = {e["file"] for e in json.loads((ARCHIVE / "index.json").read_text())} | {
        p.name for p in OWN.glob("2xh6-psuq-*.json")}
    rows = con.execute("select file, usable, same_as, unparsed, note from sca_versions").fetchall()
    assert {r[0] for r in rows} == files
    assert all(r[1] or r[4] for r in rows)
    assert all(r[3] == 0 for r in rows if r[1])
    kept = {d for (d,) in con.execute("select distinct as_of from sca_history").fetchall()}
    usable = {d for (d,) in con.execute("select as_of from sca_versions where usable and same_as is null").fetchall()}
    assert kept == usable



def cpdb_history_built(con) -> bool:
    return bool(con.execute("select count(*) from duckdb_tables() where table_name = 'cpdb_versions'").fetchone()[0])


def test_cpdb_versions_account_for_every_file(con):
    """Every archived CPDB capture and our current copy is a file of some release, with its source; each release is
    read from one file, and archived ones carry the archive URL and digest."""
    if not cpdb_history_built(con):
        pytest.skip("pipeline/cpdb_history.py not run")
    from cpdb_history import ARCHIVE, DATASETS, DATED
    files = {e["file"] for e in json.loads((ARCHIVE / "index.json").read_text()) if e["dataset"] in DATASETS}
    files |= {f"cpdb/{p.name}" for p in DATED.glob("*-*.json")} | {f"{d}.json" for d in DATASETS}
    rows = con.execute("select file, origin, archive_url, digest, release, same_as from cpdb_versions").fetchall()
    assert {r[0] for r in rows} == files
    assert all(r[4] for r in rows)
    assert all(r[2] and r[3] for r in rows if r[1] == "archive")
    used = {(r[0]) for r in rows if r[5] is None}
    for table in ("cpdb_history_funding", "cpdb_history_geoms"):
        held = {f for (f,) in con.execute(f"select distinct file from {table}").fetchall()}
        assert held <= used, table
        assert con.execute(f"select count(*) from {table} where dataset is null or file is null or release is null"
                           ).fetchone()[0] == 0
    for table in ("loc_cpdb_points_archived", "loc_cpdb_polygons_archived"):
        assert con.execute(f"""select count(*) from {table} where release is null or listed is null
                               or dataset is null or file not in (select file from cpdb_versions)""").fetchone()[0] == 0
        # only projects the current release has no geometry for
        assert con.execute(f"""select count(*) from {table} where fms_id in (select projectid from cpdb_history_geoms
                               where release = (select max(release) from cpdb_history_geoms))""").fetchone()[0] == 0
    # one file per release and dataset
    assert con.execute("""select count(*) from (select dataset, release from cpdb_versions where same_as is null
                          group by all having count(*) > 1)""").fetchone()[0] == 0


def test_cpdb_history_funding_sources_add_up(con):
    """In every release that publishes a total, city + state + federal + other planned commitments equal it: the
    check that each era's column names are mapped right."""
    if not cpdb_history_built(con):
        pytest.skip("pipeline/cpdb_history.py not run")
    assert con.execute("""select count(*) from cpdb_history_funding where plan_total is not null
        and abs(coalesce(plan_city, 0) + coalesce(plan_state, 0) + coalesce(plan_federal, 0)
                + coalesce(plan_other, 0) - plan_total) > 1""").fetchone()[0] == 0
    assert con.execute("""select count(*) from (select release, kind, projectid, agency from cpdb_history_geoms
                          group by all having count(*) > 1)""").fetchone()[0] == 0

def test_sca_history_money_reconciles_per_version(con):
    """In each version, projects sum to their phase rows, and counted = estimates - program figures + those rows'
    spending; the latest version equals sca_projects."""
    if not history_built(con):
        pytest.skip("pipeline/sca_history.py not run")
    for as_of, phases, projects, est, figures, their_spend in con.execute("""
            select as_of, sum(counted), (select sum(cost) from sca_history h where h.as_of = p.as_of),
                   sum(coalesce(estimate, 0)), sum(coalesce(program_figure, 0)),
                   coalesce(sum(spent) filter (where program_figure is not null), 0)
            from sca_history_phases p group by as_of""").fetchall():
        assert abs(phases - projects) < 1, as_of
        assert abs(phases - (est - figures + their_spend)) < 1, as_of
    n, cost = con.execute("select count(*), sum(cost) from sca_history "
                          "where as_of = (select max(as_of) from sca_history)").fetchone()
    assert (n, round(cost)) == tuple(con.execute("select count(*), round(sum(cost)) from sca_projects").fetchone())


def test_sca_repeats_reviewed_in_every_version(con):
    """A $10M+ amount on 3+ buildings (same type, description and phase) in any version is in sca_repeats.csv, and
    every listed row occurs in some version."""
    if not history_built(con):
        pytest.skip("pipeline/sca_history.py not run")
    from sca import REPEAT_MIN, load_repeats
    found = {tuple(r) for r in con.execute("""
        select project_type, description, phase, estimate from sca_history_phases where estimate >= ?
        group by as_of, project_type, description, phase, estimate having count(distinct building) >= 3""",
                                            [REPEAT_MIN]).fetchall()}
    listed = set(load_repeats())
    assert found - listed == set(), "new repeated amounts in an SCA version: review in pipeline/sca_repeats.csv"
    assert listed - found == set(), "stale rows in pipeline/sca_repeats.csv"


def test_sca_repeat_assumptions_rechecked_after_an_update(con):
    """sca_repeats.csv rows marked ASSUMPTION were reasoned from versions up to 2026-08-04; once a newer SCA version
    exists, check them against it and replace the assumption with what it shows."""
    if not history_built(con):
        pytest.skip("pipeline/sca_history.py not run")
    from sca import REPEATS
    latest = con.execute("select max(as_of) from sca_versions where usable").fetchone()[0]
    with REPEATS.open() as f:
        pending = [r["amount"] for r in csv.DictReader(f) if "ASSUMPTION" in r["evidence"]]
    assert not pending or str(latest) <= "2026-08-04", f"recheck sca_repeats.csv assumptions for {pending}"


def test_sca_trends_one_row_per_current_project(con):
    """sca_trends covers every current SCA project once; a first sighting names a kept version, and a cost change is
    measured from it; days late is measured only against a published planned end."""
    if not history_built(con):
        pytest.skip("pipeline/sca_history.py not run")
    n, keys, orphans = con.execute("""select count(*), count(distinct project_key),
        count(*) filter (where project_key not in (select project_key from sca_projects)) from sca_trends""").fetchone()
    assert n == keys == con.execute("select count(*) from sca_projects").fetchone()[0] and orphans == 0
    assert con.execute("""select count(*) from sca_trends where first_seen is not null
        and first_seen not in (select distinct as_of from sca_history)""").fetchone()[0] == 0
    assert con.execute("select count(*) from sca_trends where (cost_change is null) <> (first_seen is null)"
                       ).fetchone()[0] == 0
    assert con.execute("select count(*) from sca_trends where days_late is not null and planned_end is null"
                       ).fetchone()[0] == 0


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


# --- MTA capital program (pipeline/mta.py) -------------------------------------------------------

def mta_built(con) -> bool:
    return bool(con.execute("select count(*) from duckdb_tables() where table_name = 'mta_projects'").fetchone()[0])


@pytest.fixture(scope="module")
def mta_raw():
    from mta import DATASET
    return json.loads((DB_PATH.parent / "raw" / f"{DATASET}.json").read_text())


def test_mta_every_published_row_once(con, mta_raw):
    if not mta_built(con):
        pytest.skip("pipeline/mta.py not run")
    n, keys = con.execute("select count(*), count(distinct (loaddate, acep)) from mta_history").fetchone()
    assert n == keys == len(mta_raw)
    assert con.execute("select count(*) from mta_projects").fetchone()[0] == len({r["proj_num"] for r in mta_raw})
    assert con.execute("select count(*) from mta_projects where dataset is null").fetchone()[0] == 0


def test_mta_live_money_matches_the_latest_load(con, mta_raw):
    """Live = in the latest load and not Complete or Superseded; its money recomputed from the raw rows."""
    if not mta_built(con):
        pytest.skip("pipeline/mta.py not run")
    latest = max(r["loaddate"] for r in mta_raw)
    rows = [r for r in mta_raw if r["loaddate"] == latest and r["phase"] not in ("Complete", "Superseded")]
    n, total = con.execute("select count(*), sum(current_budget) from mta_projects where status = 'live'").fetchone()
    assert n == len(rows) and abs(total - sum(float(r["current_budget"]) for r in rows)) < 1


def test_mta_only_reviewed_loads_withhold_fields(con):
    """A money field that is 0 for every ACEP in a load is read as unpublished there; the one known case is the
    current budget in 2023-03-31. A new one needs a look before its zeros are trusted or dropped."""
    if not mta_built(con):
        pytest.skip("pipeline/mta.py not run")
    bad = dict((str(d), f) for d, f in con.execute(
        "select loaddate, withheld_fields from mta_loads where withheld_fields is not null").fetchall())
    assert bad == {"2023-03-31": "current_budget"}
    assert con.execute("""select count(*) filter (where original_budget is null), count(*) filter (where
        current_budget is not null) from mta_history where loaddate = '2023-03-31'""").fetchone() == (0, 0)


def test_mta_no_date_part_silently_dropped(con, mta_raw):
    """Every load-ACEP row with a date part present has the date parsed or the raw value in date_issues."""
    if not mta_built(con):
        pytest.skip("pipeline/mta.py not run")
    from mta import DATES
    issues = dict(((str(d), a), i) for d, a, i in con.execute(
        "select loaddate, acep, date_issues from mta_history").fetchall())
    parsed = {(str(r[0]), r[1]): r[2:] for r in con.execute(
        f"select loaddate, acep, {', '.join(DATES)} from mta_history").fetchall()}
    for r in mta_raw:
        key = (f"{r['loaddate'][:4]}-{r['loaddate'][4:6]}-{r['loaddate'][6:]}", r["proj_num"])
        for f, v in zip(DATES, parsed[key], strict=True):
            if (r.get(f"{f}_mm") or r.get(f"{f}_yyyy")) and v is None:
                assert issues[key] and f in issues[key], (key, f)


def mta_located(con) -> bool:
    return bool(con.execute("select count(*) from duckdb_tables() where table_name = 'mta_locations'").fetchone()[0])


def test_mta_every_acep_has_one_location_row_with_evidence(con):
    if not mta_located(con):
        pytest.skip("pipeline/mta_locations.py not run")
    n, keys, missing = con.execute("""select count(*), count(distinct acep),
        count(*) filter (where coalesce(length(evidence), 0) < 20) from mta_locations""").fetchone()
    assert n == keys == con.execute("select count(*) from mta_projects").fetchone()[0] and missing == 0
    assert con.execute("select count(*) from mta_locations where (lon is null) <> (tier = 'Unplaced')"
                       ).fetchone()[0] == 0


def test_mta_every_published_point_used_or_recorded(con):
    """Each wcsa-vkhf point is behind a placed ACEP's sites, or listed in mta_point_errors as rejected; points for an
    ACEP the dashboard does not list are counted apart."""
    if not mta_located(con):
        pytest.skip("pipeline/mta_locations.py not run")
    from mta_locations import DATASET
    raw = json.loads((DB_PATH.parent / "raw" / f"{DATASET}.json").read_text())
    known = {a for (a,) in con.execute("select acep from mta_projects").fetchall()}
    used = con.execute("select sum(n_points) from mta_locations").fetchone()[0]
    rejected = con.execute("select count(*) from mta_point_errors where problem <> 'swapped'").fetchone()[0]
    orphan = sum(r["project_number"] not in known for r in raw)
    assert used + rejected + orphan == len(raw)
    assert orphan <= 5, "points for ACEPs the dashboard does not list"


def test_mta_sites_shares_and_region(con):
    if not mta_located(con):
        pytest.skip("pipeline/mta_locations.py not run")
    from mta_locations import in_region
    bad = con.execute("""select acep from mta_sites group by acep having abs(sum(share) - 1) > 1e-6
        or count(*) <> (select n_sites from mta_locations l where l.acep = mta_sites.acep)""").fetchall()
    assert bad == []
    assert all(in_region(lat, lon) for lon, lat in con.execute("select lon, lat from mta_sites").fetchall())


def test_mta_sites_name_their_published_points(con):
    """Each site lists the wcsa-vkhf sequence numbers behind it, and an ACEP's sites together list every published
    point it has except rejected ones."""
    if not mta_located(con):
        pytest.skip("pipeline/mta_locations.py not run")
    from mta_locations import DATASET
    raw = json.loads((DB_PATH.parent / "raw" / f"{DATASET}.json").read_text())
    rejected = {(a, s) for a, s in con.execute(
        "select acep, sequence from mta_point_errors where problem <> 'swapped'").fetchall()}
    expected = {}
    for r in raw:
        key = (r["project_number"], int(r["project_number_sequence"]))
        if key not in rejected:
            expected.setdefault(key[0], set()).add(key[1])
    got = {}
    for acep, seqs in con.execute("select acep, sequences from mta_sites where source = 'wcsa-vkhf'").fetchall():
        assert seqs
        got.setdefault(acep, set()).update(int(x) for x in seqs.split(","))
    assert all(got[a] == expected[a] for a in got)


def test_mta_spending_rows_cover_every_screened_live_acep(con):
    """Every live ACEP with the 'dollar' indicator or a screening word has a row in pipeline/mta_spending.csv, with a
    valid kind and evidence quoting its record; every live ACEP has a kind."""
    if not mta_built(con):
        pytest.skip("pipeline/mta.py not run")
    from mta_spending import KINDS, load, screened
    rows = load()
    missing = [a for a, *_ in screened(con) if a not in rows]
    assert missing == [], "run pipeline/mta_spending.py --draft and review the new rows"
    known = {a for (a,) in con.execute("select acep from mta_projects").fetchall()}
    assert set(rows) <= known
    assert all(r["kind"] in KINDS and r["status"] in ("draft", "reviewed") and "ehz8-ag3n" in r["evidence"]
               for r in rows.values())
    from mta_spending import CONTINGENCY
    pending = [a for a, r in rows.items() if r["basis"].startswith(CONTINGENCY) and r["status"] == "draft"]
    assert pending == [], "agency-wide contingency drafted: review whether it is tied to a program"
    assert con.execute("select count(*) from mta_projects where status = 'live' and spending_kind is null"
                       ).fetchone()[0] == 0


def test_mta_city_agency_points_inside_the_city(con):
    """NYC Transit, SIR and B&T sites lie in the five boroughs or within 2 km of them; one rejected point is known
    (T6120323, Brooklyn depots, placed in New Jersey)."""
    if not mta_located(con):
        pytest.skip("pipeline/mta_locations.py not run")
    from geo import contains, distance_to_polygon_m
    from mta_locations import CITY_ONLY, CITY_SLACK_M
    bor = [json.loads(g) for (g,) in con.execute("select geojson from ref_boroughs").fetchall()]
    rows = con.execute("""select s.acep, s.lon, s.lat, p.agency_code from mta_sites s
                          join mta_projects p using (acep)""").fetchall()
    far = [a for a, lon, lat, code in rows if code in CITY_ONLY and not any(contains(g, lon, lat) for g in bor)
           and min(distance_to_polygon_m(g, lon, lat) for g in bor) > CITY_SLACK_M]
    assert far == []
    assert {a for (a,) in con.execute("select acep from mta_point_errors where problem = 'outside_service_area'"
                                      ).fetchall()} == {"T6120323"}


def test_mta_cited_sites_replace_rejected_points(con):
    """Each mta_sites.csv row replaces a rejected point with a FacDB facility, cites it, and is used (Tier B)."""
    if not mta_located(con):
        pytest.skip("pipeline/mta_locations.py not run")
    from mta_locations import SITES
    with SITES.open() as f:
        rows = list(csv.DictReader(f))
    rejected = {(a, s) for a, s in con.execute(
        "select acep, sequence from mta_point_errors where problem <> 'swapped'").fetchall()}
    uids = {u for (u,) in con.execute("select uid from ref_facilities").fetchall()}
    for r in rows:
        assert (r["acep"], int(r["sequence"])) in rejected, "stale row: the point is no longer rejected"
        assert r["facdb_uid"] in uids and r["facdb_uid"] in r["evidence"] and r["tier"] == "B"
    used = con.execute("select count(*) from mta_sites where source = 'facdb' and tier = 'B'").fetchone()[0]
    assert used == len(rows)


def test_mta_points_far_from_their_titles_station_are_reviewed(con):
    """Every NYC Transit point more than TITLE_STATION_M from each station its title names has a verdict in
    mta_point_reviews.csv citing the published point, and no review is stale; a wrong point is rejected and its
    replacement, if any, is a station in MTA's list."""
    if not mta_located(con):
        pytest.skip("pipeline/mta_locations.py not run")
    from mta_locations import REVIEWS
    with REVIEWS.open() as f:
        rows = list(csv.DictReader(f))
    flagged = {(a, s): v for a, s, v in con.execute("select acep, sequence, verdict from mta_title_checks").fetchall()}
    assert all(v for v in flagged.values()), "review the new points in pipeline/mta_point_reviews.csv"
    assert {(r["acep"], int(r["sequence"])) for r in rows} == set(flagged), "stale review rows"
    assert all(r["verdict"] in ("wrong", "right", "unclear") and "wcsa-vkhf" in r["evidence"] for r in rows)
    wrong = {(r["acep"], int(r["sequence"])) for r in rows if r["verdict"] == "wrong"}
    assert wrong == {(a, s) for a, s in con.execute(
        "select acep, sequence from mta_point_errors where problem = 'contradicts_title'").fetchall()}
    stations = {s["station_id"] for s in json.loads((DB_PATH.parent / "raw" / "39hk-dx4f.json").read_text())}
    assert all(r["station_id"] in stations for r in rows if r["station_id"])
    assert con.execute("select count(*) from mta_sites where source = 'mta_station'").fetchone()[0] == sum(
        bool(r["station_id"]) for r in rows)

def test_ibx_stations_placed_in_order_along_the_line(con):
    """The 18 Interborough Express stations MTA's 2026 briefings count are each placed on the rail line within 50 m
    of their street, run in order (each 600-2,500 m from the last), and mostly stand by subway stops (when set: 11 of
    18 within 300 m); every ACEP whose title names the IBX takes them as its sites."""
    if not mta_located(con):
        pytest.skip("pipeline/mta_locations.py not run")
    from geo import haversine_m
    from ibx import TITLE
    rows = con.execute("select station, lon, lat, gap_m, rule, evidence from ibx_stations order by no").fetchall()
    assert len(rows) == 18
    assert all(lon is not None and in_nyc(lat, lon) and "Point:" in ev for _, lon, lat, _, _, ev in rows)
    assert all(gap <= 50 for *_, gap, rule, _ in rows if rule == "rail_crossing")
    steps = [haversine_m(a[2], a[1], b[2], b[1]) for a, b in zip(rows, rows[1:], strict=False)]
    assert all(600 <= s <= 2500 for s in steps)
    stops = json.loads((DB_PATH.parent / "raw" / "39hk-dx4f.json").read_text())
    near = sum(min(haversine_m(lat, lon, float(s["gtfs_latitude"]), float(s["gtfs_longitude"])) for s in stops) <= 300
               for _, lon, lat, *_ in rows)
    assert near >= 10
    ibx = [a for a, t in con.execute("select acep, description from mta_projects").fetchall() if TITLE.search(t or "")]
    sites = dict(con.execute("""select acep, count(*) from mta_sites where source = 'ibx_station'
                                group by 1""").fetchall())
    assert ibx and sites == dict.fromkeys(ibx, 18)


def test_psa_stations_on_the_hell_gate_line_in_order(con):
    """Penn Station Access's four Bronx stations are each placed on the Hell Gate Line within 40 m of their access
    street or corner, west to east from Hunts Point to Co-op City, in the districts they serve; every ACEP of MTA's
    PSA category except vehicle purchases takes them as its sites, so no one district holds most of the program."""
    if not mta_located(con):
        pytest.skip("pipeline/mta_locations.py not run")
    from mta_locations import PSA_CATEGORY, ROLLING_STOCK
    rows = con.execute("select station, lon, lat, gap_m from psa_stations order by no").fetchall()
    assert [r[0] for r in rows] == ["Hunts Point", "Parkchester-Van Nest", "Morris Park", "Co-op City"]
    assert all(gap <= 40 for *_, gap in rows) and [r[1] for r in rows] == sorted(r[1] for r in rows)
    psa = [a for a, ind in con.execute("select acep, location_indicator from mta_projects where agency = ? and "
                                       "category = ?", list(PSA_CATEGORY)).fetchall() if ind not in ROLLING_STOCK]
    sites = dict(con.execute("select acep, count(*) from mta_sites where source = 'psa_station' group by 1").fetchall())
    assert psa and sites == dict.fromkeys(psa, 4)
    if con.execute("select count(*) from duckdb_tables() where table_name = 'project_areas'").fetchone()[0]:
        top = con.execute("""select max(s) from (select area, sum(share) s from project_areas
                             where program = 'mta' and id = 'G8110114' and level = 'district' group by 1)""").fetchone()
        assert top[0] < 0.5   # the design-build contract was 74% in CD 209 at MTA's one point

def mta_growth_built(con) -> bool:
    return bool(con.execute(
        "select count(*) from duckdb_tables() where table_name = 'mta_plan_amendments'").fetchone()[0])


def test_mta_allocations_every_row_once_with_its_plan(con):
    """Each 6kvv-fcph row once; its plan_id names the same plan as the dashboard for every shared ACEP."""
    if not mta_growth_built(con):
        pytest.skip("pipeline/mta_growth.py not run")
    from mta_growth import DATASET
    raw = json.loads((DB_PATH.parent / "raw" / f"{DATASET}.json").read_text())
    n, keys = con.execute("select count(*), count(distinct (acep, approved)) from mta_allocations").fetchone()
    assert n == keys == len(raw)
    assert con.execute("""select count(*) from mta_allocations a join mta_projects p using (acep)
                          where a.capital_plan <> p.capital_plan""").fetchone()[0] == 0
    assert con.execute("select count(*) from mta_allocations where dataset is null").fetchone()[0] == 0


def test_mta_plan_amendments_reconcile(con):
    """Each date's change is new plus changed money; each plan's latest total is its dashboard current budget."""
    if not mta_growth_built(con):
        pytest.skip("pipeline/mta_growth.py not run")
    rows = con.execute("""select capital_plan, approved, change, new_allocation, changed_allocation, rule, dataset
                          from mta_plan_amendments""").fetchall()
    for plan, day, change, new, changed, rule, ds in rows:
        assert rule and ds
        if change is not None:
            assert abs(change - new - changed) < 1, (plan, day)
    mismatched = con.execute("""
        with a as (select capital_plan, arg_max(total, approved) as total from mta_plan_amendments group by 1),
        d as (select capital_plan, sum(current_budget) as total from mta_history
              where loaddate = (select max(loaddate) from mta_history) group by 1)
        select a.capital_plan, a.total, d.total from a join d using (capital_plan)
        where abs(a.total - d.total) > 1e6""").fetchall()
    assert mismatched == []  # when set: all four plans in the 2026-03 load agree within $1M
    noted = con.execute("select count(*) from mta_plan_amendments where note is not null").fetchone()[0]
    assert noted == con.execute("select count(*) from mta_plan_amendments where approved = "
                                "(select max(approved) from mta_plan_amendments)").fetchone()[0]


def test_mta_mega_series_carries_absent_members(con):
    """The latest total is every member's last current budget held; nothing counted twice."""
    if not mta_growth_built(con):
        pytest.skip("pipeline/mta_growth.py not run")
    got = dict(con.execute("select mega_project, arg_max(total, loaddate) from mta_mega_series group by 1").fetchall())
    want = dict(con.execute("""
        with m as (select distinct mega_project, acep from mta_history where coalesce(mega_project, '') <> ''),
        h as (select acep, arg_max(current_budget, loaddate) as cur from mta_history
              where loaddate not in (select loaddate from mta_loads where withheld_fields like '%current_budget%')
              group by 1)
        select mega_project, sum(coalesce(cur, 0)) from m join h using (acep) group by 1""").fetchall())
    assert got.keys() == want.keys() and all(abs(got[k] - want[k]) < 1 for k in got)
    assert con.execute("select count(*) from mta_mega_series where rule is null or dataset is null").fetchone()[0] == 0


def budget_history_built(con):
    return bool(con.execute("select count(*) from duckdb_tables() where table_name = 'budget_original'").fetchone()[0])


def test_budget_history_every_row_used_or_recorded(con):
    """Each qj5n-h5qp row is in the series, is a project's original, or is recorded as an issue, exactly once."""
    if not budget_history_built(con):
        pytest.skip("pipeline/budget_history.py not run")
    raw = con.execute("select count(*) from budget_history").fetchone()[0]
    used = con.execute("""select (select count(*) from budget_series) + (select count(*) from budget_history_issues)
        + (select count(*) from budget_original where basis = 'original_row')""").fetchone()[0]
    assert used == raw
    assert con.execute("select count(*) - count(distinct (fms_id, managing_agency, period)) from budget_series"
                       ).fetchone()[0] == 0
    assert con.execute("""select (select count(*) from budget_series where source is null)
        + (select count(*) from budget_history_issues where source is null or issue is null or action is null)"""
                       ).fetchone()[0] == 0


def test_budget_series_agrees_with_the_snapshot_tables(con):
    """Where project_budget_schedule has the same record and period, the budget is the same (every row when set)."""
    if not budget_history_built(con):
        pytest.skip("pipeline/budget_history.py not run")
    n, bad = con.execute("""select count(*), count(*) filter (where abs(s.budget - p.budget) >= 1) from budget_series s
        join (select fms_id, managing_agency, reporting_period, any_value(total_budget) budget
              from project_budget_schedule group by all) p
        on p.fms_id = s.fms_id and p.managing_agency = s.managing_agency and p.reporting_period = s.period"""
                         ).fetchone()
    assert n > 45_000 and bad == 0  # 46,575 when set


def test_budget_change_matches_the_publisher_except_through_recorded_rows(con):
    """Our signed change equals the publisher's budget_variance, except in projects whose odd row it chains through."""
    if not budget_history_built(con):
        pytest.skip("pipeline/budget_history.py not run")
    assert con.execute("""select count(*) from budget_series s
        where abs(coalesce(change, 0) - coalesce(publisher_change, 0)) >= 1
          and not exists (select 1 from budget_history_issues i
                          where i.fms_id = s.fms_id and i.managing_agency = s.managing_agency)""").fetchone()[0] == 0


def test_budget_original_once_per_record_with_provenance(con):
    if not budget_history_built(con):
        pytest.skip("pipeline/budget_history.py not run")
    records = con.execute("""select count(*) from (select fms_id, managing_agency from budget_history
        union select fms_id, managing_agency from project_budget_schedule)""").fetchone()[0]
    n, keys, bad = con.execute("""select count(*), count(distinct (fms_id, managing_agency)), count(*) filter (where
        source is null or evidence is null or basis not in ('original_row', 'first_snapshot')
        or original_budget is null or original_period is null) from budget_original""").fetchone()
    assert n == keys == records and bad == 0


def schedules_built(con):
    return bool(con.execute("select count(*) from duckdb_tables() where table_name = 'project_schedule'").fetchone()[0])


def test_schedule_one_row_per_project_with_provenance(con):
    if not schedules_built(con):
        pytest.skip("pipeline/schedules.py not run")
    counts = dict(con.execute("select program, count(*) from project_schedule group by 1").fetchall())
    assert counts["nyc_capital"] == con.execute("select count(distinct fms_id) from project_budget_schedule"
                                                ).fetchone()[0]
    assert counts["sca"] == con.execute("select count(*) from sca_projects").fetchone()[0]
    assert counts["mta"] == con.execute("select count(*) from mta_projects").fetchone()[0]
    assert con.execute("select count(*) - count(distinct (program, project_id)) from project_schedule"
                       ).fetchone()[0] == 0
    assert con.execute("""select count(*) from project_schedule where schedule_rule is null
        or (expected_finish is not null and (finish_source is null or finish_precision is null or finish_kind is null))
        or (baseline_finish is not null
            and (baseline_source is null or baseline_kind is null or baseline_as_of is null))
        or (late_days is not null and (late_precision is null or late_phase is null))
        or (slip_days is not null and (slip_precision is null or slip_since is null))""").fetchone()[0] == 0


def test_schedule_reviews_cited_and_applied(con):
    """Each reviewed PID exists in every report it lists, cites official evidence, and its project carries the
    official finish with no reviewed forecast left in it."""
    if not schedules_built(con):
        pytest.skip("pipeline/schedules.py not run")
    from schedules import load_reviews, partial
    for pid, r in load_reviews().items():
        assert len(r["evidence"]) >= 40 and partial(r["official_finish"])[1] == r["official_precision"]
        held = {p for (p,) in con.execute("select distinct reporting_period from project_budget_schedule "
                                          "where pid = ?", [pid]).fetchall()}
        assert r["reports"] <= held, f"PID {pid}: reports not held"
        rows = con.execute("""select official_finish, official_source, finish_source from project_schedule
            where program = 'nyc_capital' and project_id in
            (select fms_id from project_budget_schedule where pid = ?)""", [pid]).fetchall()
        assert rows and all(o is not None and src for o, src, _ in rows)
        assert all(fs is None or f"PID {pid}, report " not in fs or int(fs.rsplit(" ", 1)[1]) not in r["reports"]
                   for *_, fs in rows)


def test_schedule_phases_belong_to_projects_with_provenance(con):
    if not schedules_built(con):
        pytest.skip("pipeline/schedules.py not run")
    assert con.execute("""select count(*) from project_phases anti join project_schedule using (program, project_id)
        """).fetchone()[0] == 0
    assert con.execute("""select count(*) from project_phases where source is null or rule is null or as_of is null
        or precision is null or phase not in ('planning', 'design', 'procurement', 'construction', 'close_out')
        or (end_date is null) <> (end_kind is null) or coalesce(start, end_date) is null""").fetchone()[0] == 0
    assert con.execute("""select count(*) - count(distinct (program, project_id, phase)) from project_phases
        where program <> 'sca'""").fetchone()[0] == 0
    assert con.execute("select count(*) from project_phases where program = 'sca'").fetchone()[0] == con.execute(
        "select count(*) from sca_phases where coalesce(start_date, planned_end, actual_end) is not null").fetchone()[0]


def test_schedule_city_slip_matches_the_publisher(con):
    """For single-PID projects dated by schedule_history, our slip equals the publisher's variance_day wherever the
    publisher gives one (it leaves none when a forecast becomes an actual finish; 1,794 of 1,794 when set)."""
    if not schedules_built(con):
        pytest.skip("pipeline/schedules.py not run")
    n, eq = con.execute("""with one as (select fms_id, any_value(pid) pid, max(reporting_period) p
            from project_budget_schedule where pid is not null group by 1 having count(distinct pid) = 1)
        select count(*), count(*) filter (where s.slip_days = h.variance_day) from project_schedule s
        join one on one.fms_id = s.project_id and s.as_of = one.p::varchar
        join schedule_history h on h.pid = one.pid and h.reporting_period = one.p
        where s.program = 'nyc_capital' and s.slip_days is not null and s.finish_source like '95tx-snak%'
          and h.variance_day is not null""").fetchone()
    assert n > 1_500 and eq == n


def test_schedule_sca_and_mta_follow_their_sources(con):
    if not schedules_built(con):
        pytest.skip("pipeline/schedules.py not run")
    assert con.execute("""select count(*) from project_schedule s join sca_trends t on t.project_key = s.project_id
        where s.program = 'sca' and s.late_days is distinct from t.days_late""").fetchone()[0] == 0
    assert con.execute("""select count(*) from project_schedule s join mta_projects m on m.acep = s.project_id
        where s.program = 'mta' and m.original_completion is not null and m.current_completion is not null
        and (s.baseline_kind <> 'published' or s.baseline_source not like '%original_completion')""").fetchone()[0] == 0


def test_spending_rows_cover_every_screened_project(con):
    """Every screened city and SCA project has a row in city_spending.csv or sca_spending.csv, with a valid kind and
    evidence quoting its record; every current city project, SCA project and classified ACEP has one kind."""
    if not bool(con.execute("select count(*) from duckdb_tables() where table_name = 'project_spending'"
                            ).fetchone()[0]):
        pytest.skip("pipeline/spending.py not run")
    from spending import CITY_CSV, KINDS, SCA_CSV, city_screened, load, sca_screened
    city, sca = load(CITY_CSV, "fms_id"), load(SCA_CSV, "project_key")
    assert [r[0] for r in city_screened(con) if r[0] not in city] == [], "run pipeline/spending.py --draft"
    assert [r[0] for r in sca_screened(con) if r[0] not in sca] == [], "run pipeline/spending.py --draft"
    for rows, dataset in ((city, "fb86-vt7u"), (sca, "2xh6-psuq")):
        assert [k for k, r in rows.items() if r["basis"].startswith("review:") and r["status"] == "draft"] == [], \
            "a judgement call is still a draft: review it"
        assert all(r["kind"] in KINDS and r["status"] in ("draft", "reviewed") and dataset in r["evidence"]
                   and r["reserve_flag"] in ("", "yes") for r in rows.values())
    counts = dict(con.execute("select program, count(*) from project_spending group by 1").fetchall())
    assert counts["nyc_capital"] == con.execute("""select count(distinct fms_id) from project_budget_schedule
        where reporting_period = (select max(reporting_period) from project_budget_schedule)""").fetchone()[0]
    assert counts["sca"] == con.execute("select count(*) from sca_projects").fetchone()[0]
    assert con.execute("select count(*) - count(distinct (program, project_id)) from project_spending"
                       ).fetchone()[0] == 0
    assert con.execute("select count(*) from project_spending where kind is null or basis is null").fetchone()[0] == 0


def test_data_issues_collects_every_record(con):
    """data_issues holds every recorded problem once per record, each with a dataset, an action and evidence."""
    if not bool(con.execute("select count(*) from duckdb_tables() where table_name = 'data_issues'").fetchone()[0]):
        pytest.skip("pipeline/data_issues.py not run")
    from data_issues import rows_of
    counts = dict(con.execute("select recorded_in, count(*) from data_issues group by 1").fetchall())
    folded = con.execute("select count(*) from data_issues where recorded_in like '%, pipeline/source_errors.csv'"
                         ).fetchone()[0]
    assert counts.get("pipeline/source_errors.csv", 0) + folded == len(rows_of("source_errors.csv"))
    assert counts.get("pipeline/sca_repeats.csv") == len(rows_of("sca_repeats.csv"))
    assert counts.get("pipeline/mta_point_reviews.csv", 0) == sum(
        r["verdict"] == "unclear" for r in rows_of("mta_point_reviews.csv"))
    assert counts.get("pipeline/sca_city_links.csv") == sum(
        r["decision"] in ("same_work", "possible") for r in rows_of("sca_city_links.csv"))
    for table, where, key in [("mta_point_errors", "true", "mta_point_errors"),
                              ("mta_loads", "withheld_fields is not null", "mta_loads"),
                              ("mta_history", "date_issues is not null", "mta_history.date_issues"),
                              ("sca_versions", "not usable or same_as is not null", "sca_versions"),
                              ("sca_building_conflicts", "true", "sca_building_conflicts"),
                              ("budget_history_issues", "true", "budget_history_issues")]:
        n = con.execute(f"select count(*) from {table} where {where}").fetchone()[0]
        assert counts.get(key, 0) == n, key
    assert con.execute("""select count(*) from data_issues where dataset is null or action is null
                          or coalesce(length(evidence), 0) < 10""").fetchone()[0] == 0


# --- Price indexes (pipeline/inflation.py) ------------------------------------------------------------

def test_price_indexes_are_complete_and_recent(con):
    """Every index is loaded with its publisher series and fetch URL, and reaches within a year of the latest
    city snapshot; constant-dollar fields need an index observation at each original budget's date."""
    if not con.execute("select count(*) from duckdb_tables() where table_name = 'price_index'").fetchone()[0]:
        pytest.skip("pipeline/inflation.py not run")
    from inflation import INDEXES
    rows = dict(con.execute("""select index_id, max(period) from price_index
                               where publisher is not null and series is not null and fetched_from is not null
                               group by 1""").fetchall())
    assert set(rows) == set(INDEXES)
    latest = con.execute("select max(reporting_period) from project_budget_schedule").fetchone()[0]
    latest = datetime.date(latest // 100, latest % 100, 1)
    assert all((latest - d).days < 366 for d in rows.values()), rows
    first = dict(con.execute("select index_id, min(period) from price_index group by 1").fetchall())
    oldest = con.execute("select min(original_period) from budget_original").fetchone()[0]
    oldest = datetime.date(oldest // 100, oldest % 100, 1)
    assert all(first[k] <= oldest for k in ("bea_sl_structures", "ppi_school", "nhcci"))


# --- OMB Capital Project Detail Data (pipeline/cpdd.py) ------------------------------------------------

def test_cpdd_dates_decode_to_the_clean_edition(con):
    """Milestone dates in the mangled editions, once decoded, match the clean October 2023 edition for the same
    project and task (99.76% when set; the rest are originals OMB restated); every row names its dataset."""
    if not con.execute("select count(*) from duckdb_tables() where table_name = 'cpdd_milestones'").fetchone()[0]:
        pytest.skip("pipeline/cpdd.py not run")
    n, same = con.execute("""select count(*), count_if(a.orig_end = b.orig_end) from cpdd_milestones a
        join cpdd_milestones b using (fms_id, seq) where a.date_rule like '%2022-MM-YY%' and b.pub = '20231026'
        """).fetchone()
    assert n > 100_000 and same / n > 0.995
    assert con.execute("select count(*) from cpdd_milestones where dataset is null or pub is null").fetchone()[0] == 0
    assert con.execute("select count(*) from cpdd_projects where dataset is null or pub is null").fetchone()[0] == 0
    assert con.execute("select count(distinct pub) from cpdd_projects").fetchone()[0] == 14


def test_statement_of_needs_proposals_are_classed_and_traceable(con):
    """Every Statement of Needs proposal has an area class, its agency and page, and an edition with its URL and
    SHA-1 (858 proposals in 12 editions, FY2015-16 to FY2026-27, when set)."""
    if not con.execute("select count(*) from duckdb_tables() where table_name = 'son_proposals'").fetchone()[0]:
        pytest.skip("pipeline/son.py not run")
    assert con.execute("""select count(*) from son_proposals p left join son_editions e using (edition)
        where p.area_class is null or p.agency is null or p.proposal is null or p.page is null
           or e.url is null or e.sha1 is null""").fetchone()[0] == 0
    assert con.execute("select count(*) from son_proposals").fetchone()[0] > 800
    assert con.execute("select count(*) from son_editions where n_proposals = 0").fetchone()[0] == 0


def test_every_project_serves_an_area_by_a_cited_rule(con):
    """Every city, SCA and MTA project has an area class from serving_rules.csv; a rule citing the Statement of
    Needs names a proposal with the same class, at the page its evidence gives, and a cited (rule:) rule's facility
    type has at least two-thirds of its distinct proposals in that class."""
    if not con.execute("select count(*) from duckdb_tables() where table_name = 'project_serving'").fetchone()[0]:
        pytest.skip("pipeline/serving.py not run")
    from serving import load_rules
    n = con.execute("""select (select count(distinct fms_id) from project_budget_schedule)
                            + (select count(*) from sca_projects)
                            + (select count(*) from mta_projects)""").fetchone()[0]
    assert con.execute("select count(*) from project_serving where area_class is not null").fetchone()[0] == n
    # class shares sum to one per project and match its units; a place is outside only by the outside_nyc rule
    assert con.execute("""select count(*) from project_serving
        where abs(share_local + share_regional + share_citywide + share_outside - 1) > 1e-4""").fetchone()[0] == 0
    assert con.execute("""select count(*) from (select program, id, sum(share) s from project_serving_units
        group by all) where abs(s - 1) > 1e-4""").fetchone()[0] == 0
    assert con.execute("""select count(*) from project_serving_units u join (select rule_id, kind from
        (values {}) t(rule_id, kind)) r using (rule_id) where u.area_class = 'outside' and r.kind != 'outside_nyc'
        """.format(", ".join(f"('{r['rule_id']}', '{r['kind']}')" for r in load_rules()))).fetchone()[0] == 0
    for r in load_rules():
        if not r["son"]:
            continue
        edition, page, text = r["son"].split("|")
        classes = {c for (c,) in con.execute("""select area_class from son_proposals
            where edition = ? and page = ? and proposal ilike ?""", [edition, int(page), f"%{text}%"]).fetchall()}
        assert r["area_class"] in classes and f"PDF p.{page} " in r["evidence"], (r["rule_id"], classes)
    tally = {r[0]: r[1:] for r in con.execute(
        "select rule_id, proposals, local, regional, citywide from serving_rule_son").fetchall()}
    for r in load_rules():  # a cited rule's facility type is mostly in its class (2/3 of distinct proposals)
        if r["basis"].startswith("rule:") and r["son"]:
            n, *by_class = tally[r["rule_id"]]
            assert 3 * by_class[("local", "regional", "citywide").index(r["area_class"])] >= 2 * n, r["rule_id"]


def test_serving_rules_in_use_are_reviewed(con):
    """Every rule that classes a project, and every line name, has been reviewed (status 'reviewed', set from the
    area-served review's marks); a draft rule that starts matching projects fails until it is reviewed."""
    if not con.execute("select count(*) from duckdb_tables() where table_name = 'project_serving'").fetchone()[0]:
        pytest.skip("pipeline/serving.py not run")
    from serving import load_lines, load_rules
    used = {r for (r,) in con.execute("select distinct rule_id from project_serving").fetchall()}
    rules = load_rules()
    assert all(r["status"] in ("draft", "reviewed") for r in rules)
    assert [r["rule_id"] for r in rules if r["rule_id"] in used and r["status"] != "reviewed"] == [], \
        "review these rules (serving_rules.csv)"
    assert [ln["line_id"] for ln in load_lines() if ln["status"] != "reviewed"] == [], "review mta_lines.csv"


def test_project_areas_count_each_project_once_at_a_level_its_class_allows(con):
    """project_areas: every classed project's shares sum to 1, each row at a level its class and location allow,
    with its method; district rows name one of DCP's community districts."""
    if not con.execute("select count(*) from duckdb_tables() where table_name = 'project_areas'").fetchone()[0]:
        pytest.skip("pipeline/project_areas.py not run")
    assert con.execute("""select count(*) from (select program, id from project_serving
                          except select program, id from project_areas)""").fetchone()[0] == 0
    assert con.execute("""select count(*) from (select program, id, sum(share) s from project_areas
                          group by 1, 2 having abs(s - 1) > 1e-4)""").fetchone()[0] == 0
    allowed = {"outside": {"outside"}, "citywide": {"citywide"},
               "local": {"district", "borough", "citywide", "outside"}, "regional": {"borough", "citywide", "outside"}}
    transit = {"riders_homes", "station_catchment"}  # regional transit at stations counts by district
    bad = [r for r in con.execute("select distinct area_class, level, method from project_areas").fetchall()
           if not r[2] or (r[1] not in allowed[r[0]] and not (r[0] == "regional" and r[2] in transit))]
    assert bad == []
    assert con.execute("""select count(*) from project_areas where (level = 'district' and area not in (
                          select cast(boro_cd as varchar) from ref_community_districts))
                          or (level = 'borough' and area is null)""").fetchone()[0] == 0


def test_area_population_adds_up_to_the_census(con):
    """area_population: every district has people, districts sum to their boroughs and the city, and the city
    equals the 2020 census tracts' total."""
    if not con.execute("select count(*) from duckdb_tables() where table_name = 'area_population'").fetchone()[0]:
        pytest.skip("pipeline/project_areas.py not run")
    assert con.execute("""select count(*) from ref_community_districts
                          anti join (select area from area_population where level = 'district' and population > 0)
                          on area = cast(boro_cd as varchar)""").fetchone()[0] == 0
    city = con.execute("select sum(population) from ref_tract_population").fetchone()[0]
    sums = dict(con.execute("select level, sum(population) from area_population group by 1").fetchall())
    assert abs(sums["district"] - city) <= 59 and abs(sums["borough"] - city) <= 5 and sums["citywide"] == city


def test_regional_transit_counts_where_its_stations_riders_or_neighbours_live(con):
    """Regional station work counts in districts by riders' homes, or for stations not yet built (and lines without
    origin-destination data) by residents within 800 m, kept to the stations' boroughs (Brooklyn and Queens as one)."""
    if not con.execute("select count(*) from duckdb_tables() where table_name = 'project_areas'").fetchone()[0]:
        pytest.skip("pipeline/project_areas.py not run")
    from project_areas import CATCHMENT_RULES
    assert con.execute("""select count(*) from project_areas a join project_serving_units u using (program, id, unit_no)
                          where a.method = 'riders_homes' and u.rule_id in ?""",
                       [sorted(CATCHMENT_RULES)]).fetchone()[0] == 0, "an unbuilt station has no riders"

    def shares(acep):
        return dict(con.execute("""select area, sum(share) from project_areas where program = 'mta' and id = ?
                                   and level = 'district' group by 1""", [acep]).fetchall())
    burnside = shares("T8041376")   # ADA at Burnside Av (Jerome): 10% of riders live in Manhattan, clipped
    assert {d[0] for d in burnside} == {"2"} and burnside["205"] > 0.6
    rawson = shares("T8041349")     # ADA at 33 St-Rawson St (Flushing): Queens and Brooklyn riders
    assert {d[0] for d in rawson} == {"3", "4"} and max(rawson, key=rawson.get) == "402"
    sas2 = shares("G8100106")       # Second Avenue Subway phase 2 fit-out: East and Central Harlem
    assert set(sas2) <= {"110", "111"} and sas2["111"] > 0.5

@pytest.mark.parametrize("fms_id, area_class, parcel", [
    ("PW77501DB", "regional", "STATEN ISLAND BOROUGH HALL"),   # its address point is nearest the ferry terminal's lot
    ("PW325EV", "regional", "RUTH BADER GINSBURG BROOKLYN MUNICIPAL BUILDING"),   # condominium: billing lot 7501
    ("CO283FIRE", "regional", "CRIM COURTHOUSE/DETENTION CPLX"),   # 100 Centre St, not Collect Pond Park
])
def test_government_buildings_take_the_lot_of_their_address(con, fms_id, area_class, parcel):
    """A government project naming an address takes that address's city lot (Geoclient BBL, then COLP)."""
    if not con.execute("select count(*) from duckdb_tables() where table_name = 'project_serving'").fetchone()[0]:
        pytest.skip("pipeline/serving.py not run")
    cls, matched = con.execute("select area_class, matched from project_serving where id = ?", [fms_id]).fetchone()
    assert cls == area_class
    if matched.startswith("city property"):
        assert f"city property: {parcel} (lot" in matched and "found by: address lot" in matched


def test_mta_line_labels_exist_in_station_lists(con):
    """Every label in mta_lines.csv names a line in MTA Subway Stations (39hk-dx4f) or a branch in MTA Rail Stations
    (wxmd-5cpm), with a borough the line has, so a renamed label cannot silently drop stations."""
    import json

    from db import RAW_DIR
    from serving import RAIL_STATIONS, SUBWAY_STATIONS, load_lines
    if not (RAW_DIR / f"{SUBWAY_STATIONS}.json").exists():
        pytest.skip("pipeline/fetch_mta.py not run")
    subway = {(s["line"], s["borough"]) for s in json.loads((RAW_DIR / f"{SUBWAY_STATIONS}.json").read_text())}
    rail = {(s["railroad"], s["branch"]) for s in json.loads((RAW_DIR / f"{RAIL_STATIONS}.json").read_text())}
    for ln in load_lines():
        for label, boro in ln["label_list"]:
            if ln["network"] in ("subway", "sir"):
                assert any(lab == label and (boro is None or b == boro) for lab, b in subway), (ln["line_id"], label)
            else:
                assert (ln["network"], label) in rail, (ln["line_id"], label)


def test_subway_station_users_are_placed_and_sourced(con):
    """Every station complex in MTA's origin-destination estimate has a district, a borough, shares between 0 and 1
    (the borough share at least the district share) and its source."""
    if not con.execute("select count(*) from duckdb_tables() where table_name = 'subway_station_users'").fetchone()[0]:
        pytest.skip("pipeline/ridership.py not run")
    n, bad = con.execute("""select count(*), count(*) filter (where district is null or borough is null
        or source is null or not share_district between 0 and 1 or share_borough < share_district - 1e-9
        or share_borough > 1) from subway_station_users""").fetchone()
    assert n >= 400 and bad == 0  # 424 complexes when set (2025)
