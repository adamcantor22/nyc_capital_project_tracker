"""Geocode street addresses found in project titles/descriptions with NYC Geoclient.

Writes `geocoded_addresses` (one row per accepted address point). Only exact matches whose
community district is in the project's own borough are accepted. Projects that already have
Tier A geometry are geocoded too, so `pipeline/profile.py` can measure agreement.
Responses are cached in data/raw/geoclient_cache.json; re-runs make no new requests.
Run after pipeline/ingest.py; pipeline/locations.py picks the results up.
"""
import re
import sys

import duckdb

from db import DB_PATH, replace_table
from geo import in_nyc
from geoclient import Geoclient

SUFFIX = (r"STREET|ST|AVENUE|AVE|ROAD|RD|BOULEVARD|BLVD|PLACE|PL|DRIVE|DR|PARKWAY|PKWY|LANE|LN|"
          r"CONCOURSE|TERRACE|TER|COURT|CT|WAY|PLAZA|EXPRESSWAY|TURNPIKE|HIGHWAY")
# House number (incl. Queens hyphenated, e.g. 120-55), then up to 4 street-name words, then a suffix.
# "BROADWAY" has no suffix, so it is listed as a name on its own.
ADDRESS = re.compile(
    rf"\b(\d{{1,5}}(?:-\d{{1,3}})?[A-Z]?)\s+((?:[A-Z0-9.']+\s+){{0,4}}?(?:{SUFFIX})\b\.?|BROADWAY\b)")
BOROUGH_CODES = {"Manhattan": 1, "Bronx": 2, "Brooklyn": 3, "Queens": 4, "Staten Island": 5}
MAX_PER_PROJECT = 3
CANONICAL_SUFFIX = {"ST": "STREET", "AVE": "AVENUE", "RD": "ROAD", "BLVD": "BOULEVARD", "PL": "PLACE",
                    "DR": "DRIVE", "PKWY": "PARKWAY", "LN": "LANE", "TER": "TERRACE", "CT": "COURT"}
# Words that mean the match ran through prose or a facility name rather than an address.
NOT_STREET_WORDS = set("""THIS THAT PROJECT WILL PLANT PLAYGROUND BASKETBALL HANDBALL FIELD FIELDS PARK
AND OF IN AT FOR TO WITH FROM BY ON FLOOR FLOORS PHASE PHASES LOCATIONS SITES SITE BUILDING BUILDINGS
UNITS UNIT TREES ROOF REPLACEMENT CB ACRE ACRES""".split())
DIRECTIONS = {"E": "EAST", "W": "WEST", "N": "NORTH", "S": "SOUTH"}


def extract_addresses(text: str) -> list[str]:
    """'Renovation at 100 Gold St.' -> ['100 GOLD STREET']. Street names without a house number
    ('E 79 STREET') and prose fragments are rejected."""
    text = re.sub(r"\b([EWNS])\.?(\d)", r"\1 \2", text.upper())  # E161 / E.161 -> E 161
    out = []
    for num, street in ADDRESS.findall(text):
        words = street.strip().rstrip(".").split()
        if words != ["BROADWAY"]:
            name, suffix = words[:-1], words[-1]
            if not name or any(w in NOT_STREET_WORDS or re.fullmatch(r"FY\d+", w) for w in name):
                continue  # '79 STREET' is a street, not an address; '8 THIS PROJECT ... STREET' is prose
            words = [DIRECTIONS.get(w, w) for w in name] + [CANONICAL_SUFFIX.get(suffix, suffix)]
        a = f"{num} {' '.join(words)}"
        if a not in out:
            out.append(a)
    return out[:MAX_PER_PROJECT]


def main() -> int:
    con = duckdb.connect(str(DB_PATH))
    projects = con.execute("""
        select fms_id,
               arg_max(upper(coalesce(agency_project_name, '') || ' ' || coalesce(fms_project_name, '') || ' ' ||
                       coalesce(agency_project_description, '')), reporting_period),
               arg_max(borough, reporting_period)
        from project_budget_schedule group by fms_id""").fetchall()

    gc = Geoclient()
    rows, tried = [], 0
    try:
        for fms, text, boro in projects:
            for addr in extract_addresses(text):
                tried += 1
                query = f"{addr}, {boro}" if boro in BOROUGH_CODES else addr
                res = gc.search(query)
                lat, lon = res.get("latitude"), res.get("longitude")
                cd = res.get("communityDistrict")
                ok = (res.get("status") == "EXACT_MATCH" and lat is not None and in_nyc(lat, lon)
                      and (boro not in BOROUGH_CODES or (cd and int(cd) // 100 == BOROUGH_CODES[boro])))
                if ok:
                    rows.append((fms, addr, query, lon, lat, res.get("bbl"),
                                 res.get("buildingIdentificationNumber"), int(cd) if cd else None))
            if gc.requests and gc.requests % 100 == 0:
                gc.save()
    finally:
        gc.close()

    replace_table(con, "geocoded_addresses",
                  "fms_id varchar, address varchar, query varchar, lon double, lat double, bbl varchar, "
                  "bin varchar, community_district integer", rows)
    n_fms = len({r[0] for r in rows})
    print(f"addresses tried: {tried}, accepted: {len(rows)} ({n_fms} projects), new Geoclient requests: {gc.requests}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
