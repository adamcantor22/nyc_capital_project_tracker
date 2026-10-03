"""2020 Census population per tract (US Census Bureau, P.L. 94-171 redistricting data, P1_001N), for
per-resident area measures. One request for all NYC tracts (needs CENSUS_API_KEY in .env, free from
api.census.gov/data/key_signup.html), cached in data/raw; re-runs read the cache.
Tracts roll up to NTAs and CDTAs (DCP's community district approximations) through ref_tracts
(hm78-6dwm). Writes ref_tract_population."""
import json
import os
import sys

import duckdb
import httpx

from db import DB_PATH, RAW_DIR, replace_table
from socrata import load_env

URL = "https://api.census.gov/data/2020/dec/pl"
COUNTIES = "005,047,061,081,085"  # Bronx, Kings, New York, Queens, Richmond
CACHE = RAW_DIR / "census_2020_pl_tracts.json"


def fetch() -> list[list[str]]:
    if CACHE.exists():
        return json.loads(CACHE.read_text())
    load_env()
    params = [("get", "P1_001N"), ("for", "tract:*"), ("in", "state:36"), ("in", f"county:{COUNTIES}"),
              ("key", os.environ["CENSUS_API_KEY"])]
    r = httpx.get(URL, params=params, timeout=60)
    r.raise_for_status()
    rows = r.json()
    CACHE.write_text(json.dumps(rows))
    return rows


def parse(rows: list[list[str]]) -> list[tuple[str, int]]:
    head = rows[0]
    i = {k: head.index(k) for k in ("P1_001N", "state", "county", "tract")}
    return [(r[i["state"]] + r[i["county"]] + r[i["tract"]], int(r[i["P1_001N"]])) for r in rows[1:]]


def main() -> int:
    tracts = parse(fetch())
    con = duckdb.connect(str(DB_PATH))
    replace_table(con, "ref_tract_population", "geoid varchar, population integer", tracts)
    total = sum(p for _, p in tracts)
    unmatched = con.execute(
        "select count(*) from ref_tract_population anti join ref_tracts using (geoid)").fetchone()[0]
    print(f"ref_tract_population: {len(tracts)} tracts, {total:,} people; {unmatched} tracts not in ref_tracts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
