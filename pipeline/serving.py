"""Which area each project serves: local, regional or citywide -> project_serving.

The classes are those of DCP's Citywide Statement of Needs (pipeline/son.py): local serves an area no larger than a
community district, regional two or more districts or a borough, citywide the city as a whole. The Statement lists
facilities, so rules for facility types it covers cite a proposal of that type (`son`: edition|page|proposal text,
checked against son_proposals); rules for work it does not cover (streets, sewers, transit) extend the definition by
service area and start 'review:'.

serving_rules.csv is read in order and the first matching rule decides. A rule applies to one program and, when
`scope` is set, only to projects of that theme or theme/subtheme. Kinds:
  id              the project id (city FMS ID, SCA project key, MTA ACEP): a reviewed exception
  title           a regular expression on the title (city: agency name and FMS title; SCA: school name, types and
                  description; MTA: description)
  category        the city's ten-year plan category
  subtheme, theme the project's theme (themes.py; SCA is Education, MTA Transportation/Transit (MTA))
  location_source project_locations.source (fdny_unit, nypd_unit, dsny_unit)
  parks_type      NYC Parks Properties' typecategory of the property containing the project's Tier A or B point
  sca_school      DOE School Locations' category or administrative district of any school in the building (the
                  latest list holding the building code; rules run widest first, so a shared building takes the
                  widest class)
  mta_location    MTA's location indicator (car, bus, systemwide, dollar, cbdt)
  mta_category    'agency|category' (an empty category matches every category of the agency)
  program         every project of the program (the default)
`|` separates alternatives in parks_type, sca_school and mta_location keys. Every project of every program is
classified, current or not.
"""
import csv
import json
import re
import sys
from pathlib import Path

import duckdb

import themes
from db import DB_PATH, RAW_DIR, replace_table
from geo import contains

RULES = Path(__file__).with_name("serving_rules.csv")
CLASSES = ("local", "regional", "citywide")
DOE_LISTS = ["wg9x-4ke6", "9ck8-hj3u", "p6h4-mpyy"]  # 2019-20, 2018-19, 2017-18: the first holding a code wins


def load_rules(path: Path = RULES) -> list[dict]:
    with path.open() as f:
        rows = list(csv.DictReader(f))
    for n, r in enumerate(rows, 1):
        r["rule_no"] = n
        if r["kind"] == "title":
            r["regex"] = re.compile(r["key"], re.I)
    return rows


def in_scope(rule: dict, theme: str | None, subtheme: str | None) -> bool:
    s = rule["scope"]
    return not s or s == theme or s == f"{theme}/{subtheme}"


def match(rule: dict, p: dict) -> str | None:
    """What in the project's record matched the rule (quoted as evidence), or None."""
    if rule["program"] != p["program"] or not in_scope(rule, p.get("theme"), p.get("subtheme")):
        return None
    kind, key = rule["kind"], rule["key"]
    if kind == "id":
        return f"id: {p['id']}" if p["id"] == key else None
    if kind == "title":
        m = rule["regex"].search(p.get("title") or "")
        return f"title: '{m.group(0)}' in '{p['title']}'" if m else None
    if kind == "category":
        c = p.get("category") or ""
        return f"category: {c}" if c.upper() == key.upper() else None
    if kind in ("subtheme", "theme"):
        return f"{kind}: {key}" if p.get(kind) == key else None
    if kind == "location_source":
        return f"location source: {key}" if p.get("location_source") == key else None
    if kind == "parks_type":
        t = p.get("parks_type")
        return f"Parks property: {p.get('parks_name')} ({t})" if t and t in key.split("|") else None
    if kind == "sca_school":
        hits = sorted(set(key.split("|")) & set(p.get("school_kinds") or ()))
        return f"building {p.get('building')}: {', '.join(hits)} ({p.get('doe_list')})" if hits else None
    if kind == "mta_location":
        li = p.get("location_indicator")
        return f"location indicator: {li}" if li and li in key.split("|") else None
    if kind == "mta_category":
        agency, _, cat = key.partition("|")
        if p.get("agency") == agency and (not cat or p.get("category") == cat):
            return f"agency: {agency}; category: {p.get('category')}"
        return None
    if kind == "program":
        return f"program: {p['program']}"
    raise ValueError(f"unknown rule kind {kind!r}")


def classify(p: dict, rules: list[dict]) -> tuple[dict, str]:
    for r in rules:
        if (hit := match(r, p)) is not None:
            return r, hit
    raise LookupError(f"no rule for {p['program']} {p['id']}")


def parks_index() -> list[tuple]:
    rows = json.loads((RAW_DIR / "enfh-gkve.json").read_text())
    out = []
    for r in rows:
        g = r.get("multipolygon")
        if not g:
            continue
        xs = [x for poly in g["coordinates"] for ring in poly for x, _ in ring]
        ys = [y for poly in g["coordinates"] for ring in poly for _, y in ring]
        out.append((min(xs), min(ys), max(xs), max(ys), g, r.get("signname"), r.get("typecategory")))
    return out


def park_at(index: list[tuple], lon: float, lat: float) -> tuple[str, str] | None:
    hits = [(name, t) for x0, y0, x1, y1, g, name, t in index
            if x0 <= lon <= x1 and y0 <= lat <= y1 and contains(g, lon, lat)]
    return hits[0] if hits else None


def doe_buildings() -> dict[str, tuple[set, str]]:
    """building code -> (categories and administrative districts of its schools, the list they come from)."""
    out: dict[str, tuple[set, str]] = {}
    for ds in DOE_LISTS:
        found: dict[str, set] = {}
        for r in json.loads((RAW_DIR / f"{ds}.json").read_text()):
            code = (r.get("primary_building_code") or "").strip()
            if code:
                found.setdefault(code, set()).update(
                    v for v in (r.get("location_category_description"), r.get("administrative_district_name")) if v)
        for code, kinds in found.items():
            out.setdefault(code, (kinds, ds))
    return out


def city_projects(con) -> list[dict]:
    th = themes.city_themes(con)
    locs = {f: (s, t, x, y) for f, s, t, x, y in con.execute(
        "select fms_id, source, tier, lon, lat from project_locations").fetchall()}
    parks = parks_index()
    out = []
    for f, title, aname, cat in con.execute("""
            select fms_id, fms_project_name, agency_project_name, ten_year_plan_category
            from project_budget_schedule
            qualify reporting_period = max(reporting_period) over (partition by fms_id)
            order by fms_id, total_budget desc nulls last""").fetchall():
        if out and out[-1]["id"] == f:
            continue
        theme, sub = th[f]
        src, tier, lon, lat = locs.get(f, (None, None, None, None))
        p = {"program": "nyc_capital", "id": f, "theme": theme, "subtheme": sub, "category": cat,
             "title": " ".join(x for x in (aname, title) if x), "location_source": src}
        if theme == "Parks" and tier in ("A", "B") and lon is not None and (hit := park_at(parks, lon, lat)):
            p["parks_name"], p["parks_type"] = hit
        out.append(p)
    return out


def sca_projects(con) -> list[dict]:
    doe = doe_buildings()
    out = []
    for key, building, name, types, desc in con.execute(
            "select project_key, building, school_name, project_types, description from sca_projects").fetchall():
        kinds, ds = doe.get(building or "", (set(), None))
        out.append({"program": "sca", "id": key, "theme": "Education", "subtheme": None, "building": building,
                    "title": " ".join(str(x) for x in (name, types, desc) if x), "school_kinds": kinds,
                    "doe_list": ds})
    return out


def mta_projects(con) -> list[dict]:
    return [{"program": "mta", "id": a, "theme": "Transportation", "subtheme": "Transit (MTA)", "agency": ag,
             "category": cat, "title": desc, "location_indicator": li}
            for a, ag, cat, desc, li in con.execute(
                "select acep, agency, category, description, location_indicator from mta_projects").fetchall()]


def main() -> int:
    rules = load_rules()
    bad = [r["rule_no"] for r in rules if r["area_class"] not in CLASSES or not r["basis"]]
    if bad:
        print(f"rules without a class or basis: {bad}", file=sys.stderr)
        return 1
    con = duckdb.connect(str(DB_PATH))
    rows = []
    for p in city_projects(con) + sca_projects(con) + mta_projects(con):
        r, hit = classify(p, rules)
        rows.append((p["program"], p["id"], r["area_class"], r["rule_no"], r["kind"], r["basis"], hit,
                     r["evidence"] or None, r["son"] or None, r["status"]))
    replace_table(con, "project_serving", "program varchar, id varchar, area_class varchar, rule_no integer, "
                  "kind varchar, basis varchar, matched varchar, evidence varchar, son varchar, status varchar", rows)
    for prog, cls, n in con.execute("""select program, area_class, count(*) from project_serving
                                       group by all order by 1, 2""").fetchall():
        print(f"{prog:12} {cls:9} {n:6}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
