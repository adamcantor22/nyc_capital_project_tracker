"""Every problem found in the source data, in one table: `data_issues`.

Each pipeline step records the problems it finds where it finds them (a reviewed CSV or a table). This step collects
them, one row per issue: the program, the Open Data dataset and the record's key, the issue, what the pipeline does
about it, whether a rule or a review found it, the evidence, and where it is recorded. The records themselves stay
where they are; this is the index.

Sources: source_errors.csv (city points and listings, reviewed; it includes every Tier A point the borough check
flags), implausible schedule dates in schedule_history (by export.py's rule), DOE School Locations 2018-19 (its
latitude and longitude fields are exchanged, read so by sca_locations.py), sca_building_conflicts, sca_repeats.csv,
sca_city_links.csv, unusable or repeated SCA versions (sca_versions), mta_point_errors (with any replacement site from
mta_sites.csv), money fields MTA withheld in a load (mta_loads) and implausible MTA dates (mta_history).

Run last, after every other step.
"""
import csv
import sys
from pathlib import Path

import duckdb

from db import DB_PATH, replace_table
from export import LAST_PLAUSIBLE_YEAR, MAX_VARIANCE_DAYS

HERE = Path(__file__).parent
POINT_SOURCES = {"cpdb_points": "h2ic-zdws", "cpdb_polygons": "9jkp-n57r", "parks_tracker": "4hcv-tc5r",
                 "dot_intersections": "97nd-ff3i", "bridge_bin": "4yue-vjfc", "schedule_history": "95tx-snak"}
SOURCE_ERROR_ACTION = {
    "point_wrong": "the source's point is not used for the project",
    "generic_point": "the source's point is not used for the project (a generic or default location)",
    "listing_wrong": "the point is kept; the borough the city lists is treated as wrong",
    "unclear": "recorded for review; the official records do not settle it",
    "value_wrong": "the value is not used (set to null and flagged)",
}


def rows_of(name: str) -> list[dict]:
    with (HERE / name).open() as f:
        return list(csv.DictReader(f))


def table_exists(con, name: str) -> bool:
    return bool(con.execute("select count(*) from duckdb_tables() where table_name = ?", [name]).fetchone()[0])


def collect(con) -> list[tuple]:
    out = []

    def add(program, dataset, key, issue, action, found_by, evidence, recorded_in):
        out.append((program, dataset, key, issue, action, found_by, evidence, recorded_in))

    for r in rows_of("source_errors.csv"):
        dataset = "fb86-vt7u" if r["problem"] == "listing_wrong" else POINT_SOURCES.get(r["source"], r["source"])
        add("nyc_capital", dataset, r["fms_id"], f"{r['problem']}: {r['detail']}", SOURCE_ERROR_ACTION[r["problem"]],
            "review", r["evidence"], "pipeline/source_errors.csv")
    for pid, period, date, var in con.execute("""select pid, reporting_period, completion_date, variance_day
            from schedule_history where year(completion_date) > ? or abs(variance_day) > ?
            order by 1, 2""", [LAST_PLAUSIBLE_YEAR, MAX_VARIANCE_DAYS]).fetchall():
        add("nyc_capital", "95tx-snak", f"PID {pid}, report {period}",
            f"implausible forecast: completion {date}, variance {var} days", "variance set to null and flagged",
            "rule", f"completion after {LAST_PLAUSIBLE_YEAR} or a variance over {MAX_VARIANCE_DAYS} days",
            "export.py (schedules.json variance_implausible)")
    add("sca", "9ck8-hj3u", "every row", "latitude and longitude fields exchanged",
        "read with the fields exchanged", "rule", "every row's 'latitude' holds a longitude near -74",
        "pipeline/sca_locations.py")
    if table_exists(con, "sca_building_conflicts"):
        for b, src, dist in con.execute("select building, source, distance_m from sca_building_conflicts").fetchall():
            add("sca", src, b, f"point {dist} m outside the borough its code names", "point skipped", "rule",
                "building code's first letter names the borough", "sca_building_conflicts")
    for r in rows_of("sca_repeats.csv"):
        action = ("figure kept apart in program_figure; each school's own spending counted"
                  if r["decision"] == "program_figure" else "counted as separate projects")
        add("sca", "2xh6-psuq", f"{r['project_type']} | {r['description']} | {r['phase']} | {r['amount']}",
            f"amount repeated on many schools: {r['decision']}", action, "review", r["evidence"],
            "pipeline/sca_repeats.csv")
    for r in rows_of("sca_city_links.csv"):
        if r["decision"] not in ("same_work", "possible"):
            continue
        add("sca", "fb86-vt7u, 2xh6-psuq", f"{r['fms_id']} | {r['building']} {r['sca_dsf']}".strip(),
            "same work in the city's and SCA's data" if r["decision"] == "same_work" else
            "possibly the same work in the city's and SCA's data",
            "counted once, under the city record" if r["decision"] == "same_work" else "both counted (ambiguous)",
            "review", r["evidence"], "pipeline/sca_city_links.csv")
    if table_exists(con, "sca_versions"):
        for file, usable, same, note, url in con.execute("""select file, usable, same_as, note, archive_url
                from sca_versions where not usable or same_as is not null""").fetchall():
            add("sca", "2xh6-psuq", file, note if not usable else f"the same rows as the version of {same}",
                "version not used", "rule", url or file, "sca_versions")
    if table_exists(con, "mta_point_errors"):
        replaced = {(r["acep"], int(r["sequence"])): r["facdb_uid"] for r in rows_of("mta_sites.csv")}
        for acep, seq, lat, lon, problem, action in con.execute(
                "select acep, sequence, latitude, longitude, problem, action from mta_point_errors").fetchall():
            uid = replaced.get((acep, seq))
            add("mta", "wcsa-vkhf", f"{acep} point {seq}", f"{problem}: latitude {lat}, longitude {lon}",
                action + (f"; replaced by FacDB {uid} (pipeline/mta_sites.csv)" if uid else ""), "rule",
                f"point as published: {lat}, {lon}", "mta_point_errors")
    if table_exists(con, "mta_loads"):
        for day, fields, note in con.execute(
                "select loaddate, withheld_fields, note from mta_loads where withheld_fields is not null").fetchall():
            add("mta", "ehz8-ag3n", f"load {day}", f"{fields}: {note}", "read as not published in that load",
                "rule", "every ACEP in the load has the value 0", "mta_loads")
        for acep, day, issues in con.execute("""select acep, loaddate, date_issues from mta_history
                where date_issues is not null order by 1, 2""").fetchall():
            add("mta", "ehz8-ag3n", f"{acep}, load {day}", f"implausible date: {issues}", "date left empty", "rule",
                "month outside 1-12 or year outside 1990-2060", "mta_history.date_issues")
    return out


def main() -> int:
    con = duckdb.connect(str(DB_PATH))
    rows = collect(con)
    replace_table(con, "data_issues", "program varchar, dataset varchar, record_key varchar, issue varchar, "
                  "action varchar, found_by varchar, evidence varchar, recorded_in varchar", rows)
    print(con.execute("""select program, recorded_in, count(*) from data_issues group by all order by 1, 3 desc"""
                      ).fetchall())
    return 0


if __name__ == "__main__":
    sys.exit(main())
