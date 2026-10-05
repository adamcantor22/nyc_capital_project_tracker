"""Locate SCA building codes ('K461', 'M015') from official sources, writing `sca_buildings`.

A school building code is DOE's identifier for a building. Sources, in precedence order (the first that
places a building wins):
  1. sca_active      SCA's active construction list (8586-3zfm): current, SCA's own coordinates
  2. doe_2019        DOE School Locations 2019-20 (wg9x-4ke6)
  3. doe_2018        DOE School Locations 2018-19 (9ck8-hj3u; its latitude and longitude fields are swapped)
  4. doe_2017        DOE School Locations 2017-18 (p6h4-mpyy)
  5. safety_2016     DOE School Safety Report 2010-16 (qybk-bjjc)
  6. covid_2021      DOE school testing list, Feb 2021 (7a57-qgkz): an address, located by Geoclient
  7. name_address    an address in SCA's school name ('P.S. @ 257 FRANKLIN STREET - BROOKLYN'), by Geoclient
All are official records keyed by the building code itself (1-6) or SCA's own text (7), so placements are
Tier A. A source's point more than BOROUGH_SLACK_M outside the borough its code letter names is skipped
(`sca_building_conflicts`). Buildings no source places are left to a later step and otherwise sit at their
borough (Tier E).

Run after pipeline/sca.py.
"""
import json
import re
import sys

import duckdb

from db import DB_PATH, RAW_DIR, replace_table
from geo import central_point, contains, distance_to_polygon_m, in_nyc
from geoclient import Geoclient

BOROUGH = {"K": "Brooklyn", "M": "Manhattan", "Q": "Queens", "X": "Bronx", "R": "Staten Island"}
BOROUGH_SLACK_M = 2000
ACCEPT = {"EXACT_MATCH", "POSSIBLE_MATCH"}
NAME_ADDRESS = re.compile(r"@\s*(\d[\w-]*\s+.+?)\s+-\s+(BROOKLYN|MANHATTAN|QUEENS|BRONX|STATEN ISLAND)\s*$")


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

    def outside_m(code, lon, lat):
        g = boroughs.get(code_borough(code))
        if g is None or contains(g, lon, lat):
            return 0.0
        return distance_to_polygon_m(g, lon, lat)

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
            if not placed:
                for name, text in [("covid_2021", covid.get(code.upper())), ("name_address", name_address(school))]:
                    if not text:
                        continue
                    res = gc.search(text)
                    lat, lon = res.get("latitude"), res.get("longitude")
                    if res.get("status") not in ACCEPT or lat is None or not in_nyc(lat, lon):
                        continue
                    off = outside_m(code, lon, lat)
                    if off > BOROUGH_SLACK_M:
                        conflicts.append((code, name, lon, lat, code_borough(code), round(off)))
                        continue
                    placed = (name, lon, lat, text)
                    break
            if placed:
                out.append((code, school, code_borough(code), "A", *placed))
            else:
                out.append((code, school, code_borough(code), "E" if code_borough(code) else "Unplaced",
                            "borough" if code_borough(code) else "none", None, None, None))
        print(f"geoclient requests: {gc.requests}")
    finally:
        gc.close()

    replace_table(con, "sca_buildings", "building varchar, school_name varchar, borough varchar, tier varchar, "
                  "source varchar, lon double, lat double, lookup varchar", out)
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
