"""Locate SCA building codes ('K461', 'M015') from official sources, writing `sca_buildings`.

A school building code is DOE's identifier for a building. Sources, in precedence order (the first that
places a building wins):
  1. sca_active      SCA's active construction list (8586-3zfm): current, SCA's own coordinates
  2. doe_2019        DOE School Locations 2019-20 (wg9x-4ke6)
  3. doe_2018        DOE School Locations 2018-19 (9ck8-hj3u; its latitude and longitude fields are swapped)
  4. doe_2017        DOE School Locations 2017-18 (p6h4-mpyy)
  5. safety_2016     DOE School Safety Report 2010-16 (qybk-bjjc)
  6. cited_site      `sca_sites.csv`: a site found in official records (Mayor's Office, DOB filings), with the
                     evidence; Tier A, or Tier B where the link is inferred
  7. dob_filing      DOB NOW job filings by SCA or DOE (w9ak-ipjd) whose description names the code ('Q517- ...'),
                     in the code's borough: the most-filed tax lot, located by Geoclient
  8. covid_2021      DOE school testing list, Feb 2021 (7a57-qgkz): an address, located by Geoclient
  9. name_address    an address in SCA's school name ('P.S. @ 257 FRANKLIN STREET - BROOKLYN'), by Geoclient
All are official records keyed by the building code itself or SCA's own text, so placements are Tier A unless
`sca_sites.csv` says otherwise. A source's point more than BOROUGH_SLACK_M outside the borough its code letter
names is skipped (`sca_building_conflicts`).

Buildings none of these place are matched by SCA's school name to a DOE or charter school in FacDB, in the
same borough (Tier B, inferred): by school number ('P.S. 65' -> 'P.S. 065 ...'), else when every word of the
name appears in the FacDB name ('MIDWOOD HS' -> 'MIDWOOD HIGH SCHOOL'). Candidates more than 200 m apart are
rejected as ambiguous. Many of these buildings are annexes or second buildings of a school, so the match can
land on the main building. `sca_name_validation` measures each rule against Tier A buildings, including the
annex-like ones whose code number differs from the school's. The rest sit at their borough (Tier E).

Run after pipeline/sca.py.
"""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

import duckdb

from db import DB_PATH, RAW_DIR, replace_table
from geo import central_point, contains, distance_to_polygon_m, haversine_m, in_nyc
from geoclient import Geoclient

BOROUGH = {"K": "Brooklyn", "M": "Manhattan", "Q": "Queens", "X": "Bronx", "R": "Staten Island"}
BOROUGH_DIGIT = {"Manhattan": "1", "Bronx": "2", "Brooklyn": "3", "Queens": "4", "Staten Island": "5"}
SITES = Path(__file__).with_name("sca_sites.csv")
CODE = re.compile(r"(?<![A-Z0-9])([KMQXR][A-Z0-9]{3})(?![A-Z0-9])")
BOROUGH_SLACK_M = 2000
ACCEPT = {"EXACT_MATCH", "POSSIBLE_MATCH"}
NAME_ADDRESS = re.compile(r"@\s*(\d[\w-]*\s+.+?)\s+-\s+(BROOKLYN|MANHATTAN|QUEENS|BRONX|STATEN ISLAND)\s*$")


ABBREVIATIONS = {"HS": "HIGH SCHOOL", "SCL": "SCHOOL", "ACAD": "ACADEMY", "CTR": "CENTER", "CEN": "CENTER"}
BOROUGH_SUFFIX = re.compile(r"\s+-\s+(BROOKLYN|MANHATTAN|QUEENS|BRONX|STATEN ISLAND|K|M|Q|X|R)\s*$")
NUMBER_PREFIXES = {"PS", "IS", "MS", "JHS", "HS"}
AMBIGUOUS_M = 200


def tokens(name: str | None) -> list[str]:
    """'P.S./I.S. 045 HORACE E. GREENE' -> ['PS', 'IS', '045', 'HORACE', 'E', 'GREENE']: dots dropped first, so
    'H.S.' stays one word."""
    s = BOROUGH_SUFFIX.sub("", (name or "").upper()).replace(".", "")
    return re.sub(r"[^\w\s]", " ", s).split()


def school_words(name: str | None) -> str:
    """'BOYS & GIRLS HS - BROOKLYN' -> 'BOYS GIRLS HIGH SCHOOL'."""
    return " ".join(ABBREVIATIONS.get(w, w) for w in tokens(name))


def school_number(name: str | None) -> tuple[frozenset, str] | None:
    """'P.S. 45 - BROOKLYN' -> ({'PS'}, '45'); 'P.S./I.S. 045 HORACE E. GREENE' -> ({'PS', 'IS'}, '45'). Not for
    new schools named by their address ('P.S. @ 257 FRANKLIN STREET'), whose number is a house number."""
    if "@" in (name or ""):
        return None
    ws = tokens(name)
    prefixes = set()
    while ws and ws[0] in NUMBER_PREFIXES:
        prefixes.add(ws.pop(0))
    return (frozenset(prefixes), ws[0].lstrip("0") or "0") if prefixes and ws and ws[0].isdigit() else None


def same_school_number(a: tuple | None, b: tuple | None) -> bool:
    """Same number and a shared prefix: P.S. 45 is P.S./I.S. 045, but not I.S. 45."""
    return bool(a and b and a[1] == b[1] and a[0] & b[0])


def match_school(name: str | None, borough: str | None, schools: list[tuple]) -> tuple | None:
    """(rule, FacDB name, lon, lat) for the DOE or charter school SCA's name refers to, in its borough;
    ('ambiguous', ...) when candidates lie more than AMBIGUOUS_M apart; None without a candidate."""
    key = school_number(name)
    if key:
        rule, hits = "number", [f for f in schools if f[1] == borough and same_school_number(school_number(f[0]), key)]
    else:
        words = school_words(name)
        if len(words.split()) < 2:
            return None
        rule = "name"
        # The same name exactly, else every word of it ('FLUSHING HS' is not 'FLUSHING INTERNATIONAL HIGH SCHOOL')
        hits = [f for f in schools if f[1] == borough and school_words(f[0]) == words] or [
            f for f in schools if f[1] == borough and set(words.split()) <= set(school_words(f[0]).split())]
    if not hits:
        return None
    if max(haversine_m(a[3], a[2], b[3], b[2]) for a in hits for b in hits) > AMBIGUOUS_M:
        return ("ambiguous", None, None, None)
    return (rule, hits[0][0], hits[0][2], hits[0][3])


def annex_like(code: str, name: str | None) -> bool:
    """A building whose code number differs from its school's number ('K347' for P.S. 321)."""
    key = school_number(name)
    return bool(key and code[1:].isdigit() and int(code[1:]) != int(key[1]))


def load_sites(path: Path = SITES) -> dict[str, dict]:
    with path.open() as f:
        return {r["building"]: r for r in csv.DictReader(f)}


def filing_lots(rows: list[dict], codes: set[str]) -> dict[str, str]:
    """building code -> the tax lot (BBL) most often filed under it, counting filings in the code's own borough
    only (a code-like word in another borough's filing is noise)."""
    lots: dict[str, Counter] = {}
    for r in rows:
        boro = (r.get("borough") or "").title()
        try:
            bbl = f"{BOROUGH_DIGIT[boro]}{int(r['block']):05d}{int(r['lot']):04d}"
        except (KeyError, TypeError, ValueError):
            continue
        for code in set(CODE.findall((r.get("job_description") or "").upper())):
            if code in codes and code_borough(code) == boro:
                lots.setdefault(code, Counter())[bbl] += 1
    return {code: c.most_common(1)[0][0] for code, c in lots.items()}


def geoclient_point(gc, lookup: str) -> tuple[float, float] | None:
    """(lon, lat) for an address, or a tax lot as 'bbl:<10 digits>' (its label point)."""
    if lookup.startswith("bbl:"):
        res = gc.search(lookup[4:])
        lat, lon = res.get("latitudeInternalLabel"), res.get("longitudeInternalLabel")
    else:
        res = gc.search(lookup)
        lat, lon = res.get("latitude"), res.get("longitude")
    if res.get("status") not in ACCEPT or lat is None or not in_nyc(lat, lon):
        return None
    return lon, lat


def code_borough(code: str) -> str | None:
    return BOROUGH.get((code or " ")[0].upper())


def name_address(school_name: str | None) -> str | None:
    """'P.S. @ 257 FRANKLIN STREET - BROOKLYN' -> '257 FRANKLIN STREET, BROOKLYN'; None without a house number."""
    m = NAME_ADDRESS.search((school_name or "").upper())
    return f"{m.group(1)}, {m.group(2)}" if m else None


def field(row: dict, key: str):
    """A field, with nested keys as 'a.b'."""
    for part in key.split("."):
        row = (row or {}).get(part)
    return row


def coordinate_rows(ds: str, code: str, lat: str, lon: str) -> dict[str, list[tuple[float, float]]]:
    """building code -> [(lon, lat)] from a dataset's coordinate fields."""
    out: dict[str, list] = {}
    for r in json.loads((RAW_DIR / f"{ds}.json").read_text()):
        try:
            la, lo = float(field(r, lat)), float(field(r, lon))
        except (TypeError, ValueError):
            continue
        if r.get(code) and in_nyc(la, lo):
            out.setdefault(r[code].strip().upper(), []).append((lo, la))
    return out


def main() -> int:
    con = duckdb.connect(str(DB_PATH))
    buildings = con.execute("""select building, any_value(school_name order by row_no desc) from sca_phases
                               group by 1 order by 1""").fetchall()
    coord_sources = [
        ("sca_active", coordinate_rows("8586-3zfm", "buildingid", "latitude", "longitude")),
        ("doe_2019", coordinate_rows("wg9x-4ke6", "primary_building_code", "latitude", "longitude")),
        # 2018-19 has its coordinates swapped on every row: `latitude` holds the longitude
        ("doe_2018", coordinate_rows("9ck8-hj3u", "primary_building_code", "longitude", "latitude")),
        ("doe_2017", coordinate_rows("p6h4-mpyy", "primary_building_code", "location_1.latitude",
                                     "location_1.longitude")),
        ("safety_2016", coordinate_rows("qybk-bjjc", "building_code", "latitude", "longitude")),
    ]
    covid = {}
    for r in json.loads((RAW_DIR / "7a57-qgkz.json").read_text()):
        if r.get("building_code") and r.get("building_primary_address"):
            where = f"{r.get('building_borough') or ''} {r.get('building_zip') or ''}".strip()
            covid.setdefault(r["building_code"].strip().upper(), f"{r['building_primary_address']}, {where}")
    boroughs = {b: json.loads(g) for b, g in con.execute("select borough, geojson from ref_boroughs").fetchall()}
    sites = load_sites()
    filings = RAW_DIR / "w9ak-ipjd-sca.json"
    filed = filing_lots(json.loads(filings.read_text()), {b for b, _ in buildings}) if filings.exists() else {}

    def outside_m(code, lon, lat):
        g = boroughs.get(code_borough(code))
        if g is None or contains(g, lon, lat):
            return 0.0
        return distance_to_polygon_m(g, lon, lat)

    schools = con.execute("""select name, borough, lon, lat from ref_facilities
                             where facsubgrp in ('PUBLIC K-12 SCHOOLS', 'CHARTER K-12 SCHOOLS')""").fetchall()
    gc = Geoclient()
    out, conflicts = [], []
    try:
        for code, school in buildings:
            placed = None
            candidates = [(name, pts.get(code.upper())) for name, pts in coord_sources]
            for name, pts in candidates:
                if not pts:
                    continue
                lon, lat = central_point(pts)
                off = outside_m(code, lon, lat)
                if off > BOROUGH_SLACK_M:
                    conflicts.append((code, name, lon, lat, code_borough(code), round(off)))
                    continue
                placed = (name, lon, lat, None)
                break
            tier = "A"
            if not placed:
                site = sites.get(code)
                lot = filed.get(code)
                for name, text in [("cited_site", site["lookup"] if site else None),
                                   ("dob_filing", f"bbl:{lot}" if lot else None),
                                   ("covid_2021", covid.get(code.upper())), ("name_address", name_address(school))]:
                    if not text:
                        continue
                    point = geoclient_point(gc, text)
                    if not point:
                        continue
                    lon, lat = point
                    off = outside_m(code, lon, lat)
                    if off > BOROUGH_SLACK_M:
                        conflicts.append((code, name, lon, lat, code_borough(code), round(off)))
                        continue
                    placed = (name, lon, lat, text)
                    tier = site["tier"] if name == "cited_site" else "A"
                    break
            if placed:
                out.append((code, school, code_borough(code), tier, *placed, None))
                continue
            hit = match_school(school, code_borough(code), schools)
            if hit and hit[0] != "ambiguous":
                out.append((code, school, code_borough(code), "B", f"facdb_{hit[0]}", hit[2], hit[3], None, hit[1]))
            else:
                out.append((code, school, code_borough(code), "E" if code_borough(code) else "Unplaced",
                            "borough" if code_borough(code) else "none", None, None, None, None))
        print(f"geoclient requests: {gc.requests}")
    finally:
        gc.close()

    replace_table(con, "sca_buildings", "building varchar, school_name varchar, borough varchar, tier varchar, "
                  "source varchar, lon double, lat double, lookup varchar, matched_to varchar", out)
    # The name rules run on every Tier A building too, measuring how far they land from the official point.
    validation = []
    for code, school, boro, tier, _src, lon, lat, *_ in out:
        hit = match_school(school, boro, schools) if tier == "A" else None
        if hit and hit[0] != "ambiguous":
            validation.append((code, hit[0], annex_like(code, school), round(haversine_m(lat, lon, hit[3], hit[2]))))
    replace_table(con, "sca_name_validation", "building varchar, rule varchar, annex_like boolean, distance_m integer",
                  validation)
    print(con.execute("""select rule, annex_like, count(*), median(distance_m),
                                round(100 * avg((distance_m <= 100)::int), 1),
                                round(100 * avg((distance_m <= 500)::int), 1)
                         from sca_name_validation group by 1, 2 order by 1, 2""").fetchall())
    replace_table(con, "sca_building_conflicts", "building varchar, source varchar, lon double, lat double, "
                  "code_borough varchar, distance_m integer", conflicts)
    print(con.execute("""select b.tier, b.source, count(*), count(*) filter (where p.active > 0),
                                round(sum(p.total_cost) / 1e9, 2)
                         from sca_buildings b join (select building, sum(cost) as total_cost,
                              count(*) filter (where status <> 'complete') active from sca_projects group by 1) p
                         using (building) group by 1, 2 order by 1, 3 desc""").fetchall())
    print(f"conflicts: {len(conflicts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
