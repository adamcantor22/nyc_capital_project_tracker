"""Place large named features (bridges, plants, terminals, corridors) from a hand-written gazetteer.

`pipeline/named_features.csv` lists each feature with a regex matched against project titles and a
Geoclient lookup string; no coordinates are hand-entered. Writes:
  named_features         one row per gazetteer feature with its resolved location (or why not)
  named_feature_matches  fms_id -> feature (first matching row in CSV order wins)
pipeline/locations.py uses point/area features as Tier A and linear ones (tunnels, corridors) as
Tier B, since one point stands in for a long structure.
Run after pipeline/ingest.py.
"""
import csv
import re
import sys
from pathlib import Path

import duckdb

from db import DB_PATH, replace_table
from geo import in_nyc
from geoclient import Geoclient

GAZETTEER = Path(__file__).with_name("named_features.csv")
ACCEPT = {"EXACT_MATCH", "POSSIBLE_MATCH"}  # place names usually come back as POSSIBLE_MATCH


def load_gazetteer() -> list[dict]:
    with GAZETTEER.open() as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["regex"] = re.compile(rf"\b(?:{r['pattern']})")
    return rows


def main() -> int:
    features = load_gazetteer()
    gc = Geoclient()
    resolved = {}
    out_features = []
    try:
        for f in features:
            res = gc.search(f["lookup"])
            lat, lon = res.get("latitude"), res.get("longitude")
            ok = res.get("status") in ACCEPT and lat is not None and in_nyc(lat, lon)
            if ok:
                resolved[f["feature_id"]] = (lon, lat)
            out_features.append((f["feature_id"], f["name"], f["kind"], f["extent"], f["lookup"],
                                 lon if ok else None, lat if ok else None,
                                 "resolved" if ok else f"unresolved: {res.get('status')}"))
    finally:
        gc.close()

    con = duckdb.connect(str(DB_PATH))
    replace_table(con, "named_features",
                  "feature_id varchar, name varchar, kind varchar, extent varchar, lookup varchar, "
                  "lon double, lat double, status varchar", out_features)

    projects = con.execute("""
        select fms_id, arg_max(upper(coalesce(agency_project_name, '') || ' ' || coalesce(fms_project_name, '')),
                               reporting_period)
        from project_budget_schedule group by fms_id""").fetchall()
    matches = []
    for fms, title in projects:
        f = next((f for f in features if f["regex"].search(title)), None)
        if f and f["feature_id"] in resolved:
            lon, lat = resolved[f["feature_id"]]
            matches.append((fms, f["feature_id"], f["name"], f["extent"], lon, lat))
    replace_table(con, "named_feature_matches",
                  "fms_id varchar, feature_id varchar, name varchar, extent varchar, lon double, lat double",
                  matches)

    print(con.sql("select status, count(*) n from named_features group by 1"))
    print(con.sql("select feature_id, lookup, status from named_features where status <> 'resolved'"))
    print(f"projects matched: {len(matches)}; new Geoclient requests: {gc.requests}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
