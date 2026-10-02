"""Load data/raw/* into data/capital.duckdb with friendly table names.

Core CSVs load as-is. Location sources (JSON with GeoJSON geometry) are normalised to one
row per point/feature with lon/lat, dropping coordinates outside NYC.
Rebuilds the tables on each run. Records load time and Socrata metadata in `_ingest_meta`.
"""
import json
import re
import sys
from datetime import datetime, timezone

import duckdb

from db import DB_PATH, RAW_DIR, replace_table
from geo import in_nyc, points, polygon_centroid

# dataset id -> (table name, {socrata auto-suffixed column -> meaningful name})
TABLES = {
    "fb86-vt7u": ("project_budget_schedule", {
        "spend_to_date_1": "spend_to_date_pct",
        "actual_construction": "actual_construction_procurement_start",
        "actual_construction_1": "actual_construction_procurement_end",
    }),
    "gyhf-rsr3": ("budget_spend_by_fy", {}),
    "qj5n-h5qp": ("budget_history", {
        "spend_to_date_1": "spend_to_date_pct",
        "budget_variance_1": "budget_variance_pct",
    }),
    "95tx-snak": ("schedule_history", {}),
}

BOROUGHS = {
    "M": "Manhattan", "MANHATTAN": "Manhattan", "1": "Manhattan",
    "X": "Bronx", "BRONX": "Bronx", "2": "Bronx",
    "B": "Brooklyn", "BROOKLYN": "Brooklyn", "3": "Brooklyn",  # Parks Properties uses B = Brooklyn
    "Q": "Queens", "QUEENS": "Queens", "4": "Queens",
    "R": "Staten Island", "STATEN ISLAND": "Staten Island", "5": "Staten Island",
}


def borough(v) -> str | None:
    return BOROUGHS.get(str(v).strip().upper()) if v not in (None, "") else None


def strip_agency_prefix(fms: str) -> str:
    """Parks tracker FMS IDs carry a 3-digit agency code prefix, e.g. '846 P-4BWIDEN'."""
    return re.sub(r"^\d{3}\s+", "", fms.strip())


def load_cpdb_points(rows):
    for r in rows:
        if r.get("projectid") and r.get("the_geom"):
            for lon, lat in points(r["the_geom"]):
                if in_nyc(lat, lon):
                    yield r["projectid"], r.get("description"), lon, lat


def load_cpdb_polygons(rows):
    for r in rows:
        if r.get("projectid") and r.get("the_geom"):
            lon, lat = polygon_centroid(r["the_geom"])
            if in_nyc(lat, lon):
                yield r["projectid"], r.get("description"), lon, lat, json.dumps(r["the_geom"])


def load_parks_tracker(rows):
    for r in rows:
        try:
            lat, lon = float(r["latitude"]), float(r["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if r.get("fmsid") and in_nyc(lat, lon):
            yield strip_agency_prefix(r["fmsid"]), r.get("trackerid"), r.get("title"), lon, lat


def load_dot_intersections(rows):
    for r in rows:
        if r.get("fmsid") and r.get("the_geom"):
            for lon, lat in points(r["the_geom"]):
                if in_nyc(lat, lon):
                    yield strip_agency_prefix(r["fmsid"]), r.get("projtitle"), r.get("leadagency"), lon, lat


def load_facilities(rows):
    for r in rows:
        try:
            lat, lon = float(r["latitude"]), float(r["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if r.get("facname") and in_nyc(lat, lon):
            yield (r["uid"], r["facname"], borough(r.get("boro")), r.get("facgroup"),
                   r.get("facsubgrp"), r.get("factype"), lon, lat)


def load_parks_properties(rows):
    for r in rows:
        if r.get("signname") and r.get("multipolygon"):
            lon, lat = polygon_centroid(r["multipolygon"])
            if in_nyc(lat, lon):
                yield (r.get("gispropnum"), r["signname"], borough(r.get("borough")),
                       r.get("typecategory"), lon, lat)


def load_community_districts(rows):
    for r in rows:
        code = int(float(r["boro_cd"]))
        if code % 100 > 18:  # joint interest areas (parks, airports), not community districts
            continue
        lon, lat = polygon_centroid(r["the_geom"])
        yield code, borough(str(code // 100)), code % 100, lon, lat, json.dumps(r["the_geom"])


# dataset id -> (table name, column DDL, row generator)
LOCATION_TABLES = {
    "h2ic-zdws": ("loc_cpdb_points",
                  "fms_id varchar, description varchar, lon double, lat double", load_cpdb_points),
    "9jkp-n57r": ("loc_cpdb_polygons",
                  "fms_id varchar, description varchar, lon double, lat double, geojson varchar",
                  load_cpdb_polygons),
    "4hcv-tc5r": ("loc_parks_tracker",
                  "fms_id varchar, tracker_id varchar, title varchar, lon double, lat double",
                  load_parks_tracker),
    "97nd-ff3i": ("loc_dot_intersections",
                  "fms_id varchar, title varchar, lead_agency varchar, lon double, lat double",
                  load_dot_intersections),
    "ji82-xba5": ("ref_facilities",
                  "uid varchar, name varchar, borough varchar, facgroup varchar, facsubgrp varchar, "
                  "factype varchar, lon double, lat double", load_facilities),
    "enfh-gkve": ("ref_parks_properties",
                  "gispropnum varchar, name varchar, borough varchar, typecategory varchar, "
                  "lon double, lat double", load_parks_properties),
    "5crt-au7u": ("ref_community_districts",
                  "boro_cd integer, borough varchar, district integer, lon double, lat double, "
                  "geojson varchar", load_community_districts),
}


def record_meta(con, ds: str, table: str, source_rows: int) -> dict:
    meta = json.loads((RAW_DIR / f"{ds}.meta.json").read_text())
    updated = datetime.fromtimestamp(meta["rowsUpdatedAt"], timezone.utc).replace(tzinfo=None)
    con.execute("insert into _ingest_meta values (?,?,?,?,?,?,now())",
                [ds, table, meta["name"], updated, meta["_remote_count"], source_rows])
    return meta


def main() -> int:
    if not RAW_DIR.exists() or not any(RAW_DIR.glob("*.csv")):
        print("No raw data; run pipeline/fetch.py first", file=sys.stderr)
        return 1
    con = duckdb.connect(str(DB_PATH))
    con.execute("create or replace table _ingest_meta (dataset_id varchar, table_name varchar, "
                "source_name varchar, source_rows_updated_at timestamp, remote_count bigint, "
                "loaded_rows bigint, loaded_at timestamp)")
    for ds, (table, renames) in TABLES.items():
        csv = RAW_DIR / f"{ds}.csv"
        con.execute(f"create or replace table {table} as "
                    f"select * from read_csv('{csv}', sample_size=-1)")
        for old, new in renames.items():
            con.execute(f'alter table {table} rename column {old} to {new}')
        n = con.execute(f"select count(*) from {table}").fetchone()[0]
        meta = record_meta(con, ds, table, n)
        flag = "" if n == meta["_remote_count"] else "  <-- COUNT MISMATCH"
        print(f"{table}: {n} rows (remote {meta['_remote_count']}){flag}")

    for ds, (table, ddl, loader) in LOCATION_TABLES.items():
        path = RAW_DIR / f"{ds}.json"
        if not path.exists():
            print(f"{table}: {path.name} missing; run pipeline/fetch_locations.py", file=sys.stderr)
            continue
        src = json.loads(path.read_text())
        out = list(loader(src))
        replace_table(con, table, ddl, out)
        meta = record_meta(con, ds, table, len(src))
        flag = "" if len(src) == meta["_remote_count"] else "  <-- COUNT MISMATCH"
        print(f"{table}: {len(out)} rows from {len(src)} source rows (remote {meta['_remote_count']}){flag}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
