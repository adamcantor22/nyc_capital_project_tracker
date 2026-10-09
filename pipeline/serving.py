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
                  widest class; a District 75 program contributes only its district, so a building it shares with a
                  zoned school takes that school's class)
  city_property   a regular expression on the city lot of a government project in DCP's City Owned and Leased
                  Property (fn4k-qyk2): the lot of the address its record names (Geoclient's BBL), else the lot nearest
                  its Tier A or B point within PROPERTY_RADIUS_M ('<parcel name> (lot <BBL>) | borough: <borough> |
                  agencies: <tenant agency codes> | uses: <their use types> | found by: <address lot or nearest>')
  mta_location    MTA's location indicator (car, bus, systemwide, dollar, cbdt)
  ridership_district, ridership_borough, ridership
                  NYC Transit station and line work (RIDERSHIP_AGENCIES, RIDERSHIP_CATEGORIES) whose sites are at
                  subway stations (the nearest station complex within STATION_RADIUS_M; at least half the budget
                  share): the share of the stations' morning riders living in the station's district or borough
                  (ridership.py; site shares weight the stations) is at least the key; `ridership` matches any
  mta_category    'agency|category' (an empty category matches every category of the agency)
  outside_nyc     at least the key's share of the project's budget share (its sites: project_sites, mta_sites) lies
                  outside the city (DCP's Borough Boundaries with water areas included, wh2p-dxnf, so bridges and
                  piers are inside): class `outside`, counted in program totals only, in no per-resident measure
  program         every project of the program (the default)
`|` separates alternatives in parks_type, sca_school and mta_location keys. Every project of every program is
classified, current or not. `rule_id` is a rule's stable name (review marks refer to it).

`son_type` is a regular expression on '<agency> :: <proposal>' naming the rule's facility type in the Statement;
serving_rule_son tallies its distinct proposals (titles compared without case or punctuation, across editions) by
class. A `rule:` basis needs at least two-thirds of them in the rule's class (a data check); a split type is a
`review:` rule that still shows its tally.
"""
import csv
import json
import re
import sys
from pathlib import Path

import duckdb

import themes
from db import DB_PATH, RAW_DIR, replace_table
from geo import contains, haversine_m

RULES = Path(__file__).with_name("serving_rules.csv")
CLASSES = ("local", "regional", "citywide")  # the Statement of Needs' classes
OUTSIDE = "outside"
AREA_CLASSES = (*CLASSES, OUTSIDE)
CITY_OUTLINE = "wh2p-dxnf"  # Borough Boundaries (water areas included)
DOE_LISTS = ["wg9x-4ke6", "9ck8-hj3u", "p6h4-mpyy"]  # 2019-20, 2018-19, 2017-18: the first holding a code wins
D75 = "CITYWIDE SPECIAL EDUCATION"
RIDERSHIP_AGENCIES = {"New York City Transit", "Super Storm Sandy"}
RIDERSHIP_CATEGORIES = {"Passenger Stations", "Line Structures", "Signals & Communications", "Signals & Communication",
                        "Communications And Signals", "Traction Power", "Line Equipment", "Track"}
STATION_RADIUS_M = 300
CITY_PROPERTY = "fn4k-qyk2"  # DCP City Owned and Leased Property (COLP)
PROPERTY_RADIUS_M = 50
BBL_BOROUGH = {"1": "Manhattan", "2": "Bronx", "3": "Brooklyn", "4": "Queens", "5": "Staten Island"}
LINE_CATEGORIES = RIDERSHIP_CATEGORIES - {"Passenger Stations"}  # work along lines, not at one station
LINES = Path(__file__).with_name("mta_lines.csv")
SUBWAY_STATIONS = "39hk-dx4f"  # MTA Subway Stations
RAIL_STATIONS = "wxmd-5cpm"  # MTA Rail Stations (LIRR and Metro-North)
NE_CATEGORY_MEGA = {"Esa Liability Reserve": "East Side Access", "Esa Rs / Liability Reserve": "East Side Access",
                    "Interborough Express": "Interborough Express"}


def load_rules(path: Path = RULES) -> list[dict]:
    with path.open() as f:
        rows = list(csv.DictReader(f))
    for n, r in enumerate(rows, 1):
        r["rule_no"] = n
        if r["kind"] == "title":
            r["regex"] = re.compile(r["key"], re.I)
    return rows


def proposal_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", re.sub(r"(?i)\s*DCAS PROJECT ID.*", "", text or "").lower())


def son_tally(con, rules: list[dict]) -> list[tuple]:
    """(rule_id, proposals, local, regional, citywide) for each rule naming a Statement of Needs facility type."""
    props = con.execute("select agency, proposal, area_class from son_proposals").fetchall()
    out = []
    for r in rules:
        if not r["son_type"]:
            continue
        pat = re.compile(r["son_type"], re.I)
        classes: dict[str, set] = {}
        for agency, proposal, cls in props:
            if pat.search(f"{agency} :: {proposal}"):
                classes.setdefault(proposal_key(proposal), set()).add(cls)
        # a proposal listed under two classes in different editions counts once under each
        out.append((r["rule_id"], len(classes), *(sum(c in s for s in classes.values()) for c in CLASSES)))
    return out


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
    if kind == "city_property":
        d = p.get("city_property")
        return f"city property: {d}" if d and re.search(key, d, re.I) else None
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
    if kind in ("ridership_district", "ridership_borough", "ridership"):
        r = p.get("ridership")
        if not r or (kind != "ridership" and r[kind.removeprefix("ridership_")] < float(key)):
            return None
        return (f"{r['station']}: morning riders living in its district {r['district']:.0%}, "
                f"borough {r['borough']:.0%}")
    if kind == "outside_nyc":
        o = p.get("outside")
        if o is None or o < float(key):
            return None
        return (f"{o:.0%} of the budget share at sites outside the city "
                f"(Borough Boundaries, water areas included, {CITY_OUTLINE})")
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


def city_outline() -> list[dict]:
    return [r["the_geom"] for r in json.loads((RAW_DIR / f"{CITY_OUTLINE}.json").read_text())]


def in_city(outline: list[dict], lon: float, lat: float) -> bool:
    return any(contains(g, lon, lat) for g in outline)


def outside_shares(con, query: str) -> dict[str, float]:
    """project -> the share of its site budget share lying outside the city's outline, water included."""
    outline = city_outline()
    acc: dict[str, list[float]] = {}
    for key, lon, lat, share in con.execute(query).fetchall():
        a = acc.setdefault(key, [0.0, 0.0])
        a[0] += share
        if not in_city(outline, lon, lat):
            a[1] += share
    return {k: out / total for k, (total, out) in acc.items() if total}


def doe_buildings() -> dict[str, tuple[set, str]]:
    """building code -> (categories and administrative districts of its schools, the list they come from)."""
    out: dict[str, tuple[set, str]] = {}
    for ds in DOE_LISTS:
        found: dict[str, set] = {}
        for r in json.loads((RAW_DIR / f"{ds}.json").read_text()):
            code = (r.get("primary_building_code") or "").strip()
            district = r.get("administrative_district_name")
            # a District 75 program adds only its district, so a building it shares takes the zoned school's class
            kinds = (district,) if district == D75 else (r.get("location_category_description"), district)
            if code:
                found.setdefault(code, set()).update(v for v in kinds if v)
        for code, kinds in found.items():
            out.setdefault(code, (kinds, ds))
    return out


def property_index(records: list[dict] | None = None) -> tuple[dict, dict]:
    """City Owned and Leased Property (COLP): grid cell -> lots, and lot -> its description (parcel name, borough,
    tenant agencies, their uses), one row per agency use of a property. Lots with the same parcel name at the same
    point are one building (a condominium's billing and unit lots: 210 Joralemon St is 3002667501 and 3002661001)
    and share one description."""
    lots: dict[str, list[dict]] = {}
    if records is None:
        records = json.loads((RAW_DIR / f"{CITY_PROPERTY}.json").read_text())
    for r in records:
        if r.get("latitude") and r.get("bbl"):
            lots.setdefault(r["bbl"], []).append(r)
    buildings: dict[tuple, list[str]] = {}
    for bbl, rows in lots.items():
        name = next((r["parcel_name"] for r in rows if r.get("parcel_name")), rows[0].get("address") or "")
        buildings.setdefault((name, rows[0]["latitude"], rows[0]["longitude"]), []).append(bbl)
    cells: dict[tuple, list] = {}
    desc = {}
    for (name, lat, lon), bbls in buildings.items():
        rows = [r for bbl in bbls for r in lots[bbl]]
        lat, lon = float(lat), float(lon)
        text = (f"{name} (lot {', '.join(sorted(b.split('.')[0] for b in bbls))}) | borough: {BBL_BOROUGH[bbls[0][0]]}"
                " | agencies: " + " ".join(sorted({r.get("agency") or "" for r in rows})) + " | uses: "
                + "; ".join(sorted({r.get("use_type") or "" for r in rows})))
        for bbl in bbls:
            cells.setdefault((round(lat, 2), round(lon, 2)), []).append((lat, lon, bbl))
            desc[bbl] = text
    return cells, desc


def property_at(index: tuple[dict, dict], lon: float, lat: float) -> str | None:
    """The description of the city lot nearest the point, within PROPERTY_RADIUS_M. COLP gives one point per lot,
    so near a large lot this can be a neighbour (10 Richmond Terrace's address point is nearest the ferry terminal)."""
    cells, desc = index
    near = [(haversine_m(lat, lon, la, lo), bbl) for i in (-1, 0, 1) for j in (-1, 0, 1)
            for la, lo, bbl in cells.get((round(lat + i / 100, 2), round(lon + j / 100, 2)), ())]
    d, bbl = min(near, default=(None, None))
    return f"{desc[bbl]} | found by: nearest lot point" if bbl and d <= PROPERTY_RADIUS_M else None


def address_lots(con, index: tuple[dict, dict]) -> dict[str, str]:
    """Per project, the city lot of the address its record names (geocode.py: Geoclient's BBL), where that lot is in
    COLP and the record's addresses name only one such lot."""
    desc = {bbl.split(".")[0]: d for bbl, d in index[1].items()}
    lots: dict[str, dict] = {}
    for f, address, bbl in con.execute("select fms_id, address, bbl from geocoded_addresses order by all").fetchall():
        if bbl in desc:
            lots.setdefault(f, {}).setdefault(bbl, address)
    return {f: f"{desc[bbl]} | found by: address lot ({address}, Geoclient)"
            for f, ls in lots.items() if len(ls) == 1 for bbl, address in ls.items()}


def city_projects(con) -> list[dict]:
    th = themes.city_themes(con)
    locs = {f: (s, t, x, y) for f, s, t, x, y in con.execute(
        "select fms_id, source, tier, lon, lat from project_locations").fetchall()}
    parks = parks_index()
    props = property_index()
    lots = address_lots(con, props)
    outside = outside_shares(con, "select fms_id, lon, lat, share from project_sites")
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
             "title": " ".join(x for x in (aname, title) if x), "location_source": src, "outside": outside.get(f)}
        if theme == "Parks" and tier in ("A", "B") and lon is not None and (hit := park_at(parks, lon, lat)):
            p["parks_name"], p["parks_type"] = hit
        if theme == "Government buildings and operations":
            p["city_property"] = lots.get(f) or (
                property_at(props, lon, lat) if tier in ("A", "B") and lon is not None else None)
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


def load_lines(path: Path = LINES) -> list[dict]:
    with path.open() as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        name = r["title"]
        # a subway line name counts only used as a line: '/ Brighton', 'Myrtle Line', 'Lexington And Jerome Lines'
        if r["network"] == "subway":
            name = rf"(?:/\s*(?:{name})|(?:{name})(?=(?:\s*(?:AND|&|,)\s*[A-Z0-9 .\-]+?)?\s+LINES?\b))"
        r["regex"] = re.compile(name, re.I)
        r["label_list"] = [tuple(x.split("@")) if "@" in x else (x, None) for x in r["labels"].split("|") if x]
    return rows


def norm_place(text: str) -> str:
    t = re.sub(r"[^A-Z0-9 ]", " ", text.upper())
    t = re.sub(r"\b(\d+)(ST|ND|RD|TH)\b", r"\1", t)
    for long, short in (("AVENUE", "AV"), ("AVE", "AV"), ("STREET", "ST"), ("PARKWAY", "PKWY"), ("PKY", "PKWY"),
                        ("BOULEVARD", "BLVD"), ("ROAD", "RD"), ("PLACE", "PL"), ("CENTER", "CTR")):
        t = re.sub(rf"\b{long}\b", short, t)
    return " ".join(t.split())


def stretch(stops: list[dict], title: str) -> list[dict]:
    """The stations of a line a title names: one or more stations ('At Nevins Street Station'), the stations
    between two named stations ('Queensboro Plaza To 33 Street'), or between two street numbers ('63 Street To 91
    Street', stations whose names start with a number in that range). Empty when it names none."""
    t = f" {norm_place(title)} "
    # one distinctive word names a station only where titles place work: '(Ditmas)', 'At N/O Dekalb', '(Crescent To
    # Cypress)'; elsewhere a first word is often a street or structure ('Westchester Avenue Bridges', 'Steinway Loop')
    near = [f" {norm_place(x)} " for x in re.findall(r"\(([^)]*)\)", title)
            + re.findall(r"\b(?:AT|[NSEW]/O)\b(.*?)(?=\bON THE\b|$)", title, re.I)]
    hits = []  # (start, end, stop)
    for s in stops:
        for part in s["stop_name"].split("-"):
            p = norm_place(part)
            words = p.split()
            keys = [p] + ([words[0]] if len(words) > 1 and words[0].isalpha() and len(words[0]) >= 5 else [])
            for n, k in enumerate(keys):
                pat = rf"(?<= ){re.escape(k)}(?= )"
                if n and not any(re.search(pat, w) for w in near):
                    continue
                for m in re.finditer(pat, t):
                    hits.append((m.start(), m.end(), s))
    hits = [h for h in hits if not any(o[0] <= h[0] and h[1] <= o[1] and (o[1] - o[0]) > (h[1] - h[0]) for o in hits)]
    rng = re.search(r" (\d+) ST TO (\d+) ST ", t)
    by_id = lambda s: int(s["station_id"])  # noqa: E731  station ids run along each line
    if m := re.search(r" TO ", t):
        before = [h for h in hits if h[1] <= m.start() + 1]
        after = [h for h in hits if h[0] >= m.end() - 1]
        if before and after:
            a, b = before[-1][2], after[0][2]
            if a["line"] != b["line"]:  # a stretch across the station list's labels: the whole line
                return []
            lo, hi = sorted((by_id(a), by_id(b)))
            return [s for s in stops if s["line"] == a["line"] and lo <= by_id(s) <= hi]
    if rng and not hits:
        lo, hi = sorted(int(x) for x in rng.groups())
        num = lambda s: re.match(r"(\d+) ", norm_place(s["stop_name"]) + " ")  # noqa: E731
        return [s for s in stops if (n := num(s)) and lo <= int(n.group(1)) <= hi]
    return [h[2] for h in hits]


def mega_key(agency: str, category: str, mega: str | None) -> str | None:
    if mega:
        return mega
    if agency == "Network Expansion":
        return NE_CATEGORY_MEGA.get(category)
    return None


def mta_units(con) -> dict[str, tuple[str, list[dict]]]:
    """ACEP -> (how its places were found, its units): each unit a site or station with its share of the ACEP's
    budget, whether it lies outside the city, and for a subway station complex its morning riders' shares.

    The places come from the first of: MTA's own points (mta_sites); the points of the other ACEPs of its mega
    project, weighted by their budgets; a subway line, Staten Island Railway, a Metro-North line or an LIRR branch
    named in the title (mta_lines.csv, mapped to MTA's station lists); every station of the LIRR or Metro-North for
    work on the railroad that names no place. Stations of a line or railroad share its budget equally."""
    outline = city_outline()
    users = {cid: (name, lat, lon, d, b) for cid, name, lat, lon, d, b in con.execute(
        "select complex_id, name, lat, lon, share_district, share_borough from subway_station_users").fetchall()}
    own = {cid: (district, set(ods.split(",")), set(obs.split(","))) for cid, district, ods, obs in con.execute(
        "select complex_id, district, own_districts, own_boroughs from subway_station_users").fetchall()}
    homes: dict[int, dict[str, dict[str, float]]] = {}
    for cid, kind, area, riders in con.execute(
            "select complex_id, kind, area, riders from subway_station_homes").fetchall():
        homes.setdefault(cid, {"district": {}, "borough": {}})[kind][area] = riders
    subway = json.loads((RAW_DIR / f"{SUBWAY_STATIONS}.json").read_text())
    rail = json.loads((RAW_DIR / f"{RAIL_STATIONS}.json").read_text())
    lines = load_lines()

    def unit(share, lon, lat, label, ridership=None, outside=None):
        out = outside if outside is not None else float(not in_city(outline, lon, lat))
        return {"share": share, "lon": lon, "lat": lat, "label": label, "outside": out, "ridership": ridership}

    def complex_unit(cid: int, share: float) -> dict:
        name, lat, lon, d, b = users[cid]
        return unit(share, lon, lat, name, {"district": d, "borough": b, "station": name, "complex": cid})

    def pool(us: list[dict], what: str) -> list[dict]:
        """Line work serves the riders of all its stations together: one measure for them all, the share of their
        pooled riders living in the stations' own districts (only when every station stands in one district, as
        work spanning several districts is at least regional) and in their own boroughs."""
        cids = {u["ridership"]["complex"] for u in us if u["ridership"]}
        if not cids:
            return us
        total = sum(sum(homes.get(c, {}).get("borough", {}).values()) for c in cids) or 1.0
        dists = set().union(*(own[c][1] for c in cids))
        boros = set().union(*(own[c][2] for c in cids))
        in_d = sum(v for c in cids for a, v in homes.get(c, {}).get("district", {}).items() if a in dists)
        in_b = sum(v for c in cids for a, v in homes.get(c, {}).get("borough", {}).items() if a in boros)
        one_district = len({own[c][0] for c in cids}) == 1
        r = {"district": in_d / total if one_district else 0.0, "borough": in_b / total,
             "station": f"{len(cids)} station{'s' * (len(cids) > 1)} pooled ({what})"}
        return [{**u, "ridership": {**r, "complex": u["ridership"]["complex"]}} if u["ridership"] else u for u in us]

    def stations_of(line: dict, title: str) -> list[dict]:
        if line["network"] in ("subway", "sir"):
            stops = [s for s in subway if any(s["line"] == lab and (b is None or s["borough"] == b)
                                              for lab, b in line["label_list"])]
            by_complex: dict[int, dict] = {}
            for s in stops:
                by_complex.setdefault(int(s["complex_id"]), s)
            return [{"complex": c, "stop": s} for c, s in by_complex.items()]
        if line["network"] in ("MNR", "LIRR"):
            branches = {lab for lab, _ in line["label_list"]}
            if not branches:  # the branch is the one the title names
                branches = {line["regex"].search(title).group(1).title()}
            return [{"rail": s} for s in rail if s["railroad"] == line["network"] and s["branch"] in branches]
        return []

    def units_of(stations: list[dict]) -> list[dict]:
        out = []
        for s in stations:
            share = 1 / len(stations)
            if "complex" in s and s["complex"] in users:
                out.append(complex_unit(s["complex"], share))
            else:
                st = s.get("stop") or s["rail"]
                lat = float(st.get("gtfs_latitude") or st.get("latitude"))
                lon = float(st.get("gtfs_longitude") or st.get("longitude"))
                out.append(unit(share, lon, lat, st.get("stop_name") or st.get("station_name")))
        return out

    sites: dict[str, list[tuple]] = {}
    for acep, lon, lat, share in con.execute(
            "select acep, lon, lat, share from mta_sites order by acep, site_no").fetchall():
        sites.setdefault(acep, []).append((lon, lat, share))
    near = {}
    for pts in sites.values():
        for lon, lat, _ in pts:
            if (lon, lat) not in near:
                dist, cid = min((haversine_m(lat, lon, u[1], u[2]), cid) for cid, u in users.items())
                near[(lon, lat)] = cid if dist <= STATION_RADIUS_M else None
    projects = con.execute("""select acep, agency, category, description, mega_project, current_budget
                              from mta_projects""").fetchall()
    mega_sites: dict[str, list[tuple]] = {}
    for acep, ag, cat, _, mega, budget in projects:
        if (k := mega_key(ag, cat, mega)) and acep in sites:
            mega_sites.setdefault(k, []).append((max(budget or 0.0, 0.0), sites[acep]))
    out: dict[str, tuple[str, list[dict]]] = {}
    for acep, ag, cat, title, mega, _ in projects:
        if acep in sites:
            at_station = ag in RIDERSHIP_AGENCIES and cat in RIDERSHIP_CATEGORIES
            us = []
            for lon, lat, share in sites[acep]:
                cid = near[(lon, lat)] if at_station else None
                us.append(complex_unit(cid, share) if cid is not None else unit(share, lon, lat, "MTA point"))
            out[acep] = ("MTA's points", pool(us, "line work") if cat in LINE_CATEGORIES else us)
            continue
        if (k := mega_key(ag, cat, mega)) and k in mega_sites:
            total = sum(b for b, _ in mega_sites[k]) or None
            us = [unit((b / total if total else 1 / len(mega_sites[k])) * share, lon, lat, f"{k} point")
                  for b, pts in mega_sites[k] for lon, lat, share in pts]
            out[acep] = (f"points of the other {k} ACEPs", us)
            continue
        network = ("subway" if ag in RIDERSHIP_AGENCIES
                   else "sir" if cat == "Staten Island Railway"
                   else {"Long Island Rail Road": "LIRR", "Metro-North Railroad": "MNR"}.get(ag))
        named = [ln for ln in lines if network and (ln["network"] == network or
                                                     (ln["network"] == "outside" and network == "MNR"))
                 and ln["regex"].search(title)]
        if named and named[0]["network"] == "outside":
            out[acep] = (f"line: {named[0]['line_id']}", [unit(1.0, None, None, "West of Hudson", outside=1.0)])
            continue
        stations = list({s.get("complex") or (s.get("stop") or s["rail"]).get("station_id") or s["rail"]["code"]: s
                         for ln in named for s in stations_of(ln, title)}.values())
        what = "line: " + ", ".join(ln["line_id"] for ln in named)
        if network == "subway" and named and cat not in LINE_CATEGORIES:  # line work serves the whole line
            rest = title
            for ln in named:  # the words naming the line are not a station
                rest = ln["regex"].sub(lambda m: " " * len(m.group(0)), rest)
            labels = {lab for ln in named for lab, _ in ln["label_list"]}
            if part := stretch([s for s in subway if s["line"] in labels], rest):
                stations, what = [{"complex": int(c), "stop": s} for c, s in
                                  {s["complex_id"]: s for s in part}.items()], what + " (stations named)"
        if stations:
            out[acep] = (what, pool(units_of(stations), what))
            continue
        if network in ("LIRR", "MNR"):
            out[acep] = (f"every {network} station", units_of([{"rail": s} for s in rail if s["railroad"] == network]))
    return out


def mta_projects(con) -> list[dict]:
    units = mta_units(con)
    out = []
    for a, ag, cat, desc, li in con.execute(
            "select acep, agency, category, description, location_indicator from mta_projects").fetchall():
        via, us = units.get(a, ("none", []))
        out.append({"program": "mta", "id": a, "theme": "Transportation", "subtheme": "Transit (MTA)", "agency": ag,
                    "category": cat, "title": desc, "location_indicator": li, "via": via, "units": us})
    return out


def serve(p: dict, rules: list[dict]) -> list[tuple]:
    """[(unit, rule, matched)] for each unit of the project (the whole project when it has none)."""
    units = p.get("units") or [{"share": 1.0, "lon": None, "lat": None, "label": None, "outside": p.get("outside"),
                                 "ridership": p.get("ridership")}]
    out = []
    for u in units:
        r, hit = classify({**p, "outside": u["outside"], "ridership": u["ridership"]}, rules)
        out.append((u, r, hit))
    return out


def main() -> int:
    rules = load_rules()
    bad = [r["rule_no"] for r in rules if r["area_class"] not in AREA_CLASSES or not r["basis"] or not r["rule_id"]]
    if len({r["rule_id"] for r in rules}) != len(rules):
        bad.append("duplicate rule_id")
    if bad:
        print(f"rules without a class or basis: {bad}", file=sys.stderr)
        return 1
    con = duckdb.connect(str(DB_PATH))
    rows, unit_rows = [], []
    for p in city_projects(con) + sca_projects(con) + mta_projects(con):
        served = serve(p, rules)
        shares = dict.fromkeys(AREA_CLASSES, 0.0)
        by_rule: dict[str, float] = {}
        for n, (u, r, hit) in enumerate(served, 1):
            shares[r["area_class"]] += u["share"]
            by_rule[r["rule_id"]] = by_rule.get(r["rule_id"], 0.0) + u["share"]
            unit_rows.append((p["program"], p["id"], n, round(u["share"], 6), u["label"], u["lon"], u["lat"],
                              u["outside"], r["area_class"], r["rule_id"], r["rule_no"], hit))
        top = max(by_rule, key=lambda k: (by_rule[k], -next(r["rule_no"] for _, r, _ in served if r["rule_id"] == k)))
        u, r, hit = next(x for x in served if x[1]["rule_id"] == top)
        if len(served) > 1:
            hit = f"{len(served)} places ({p['via']}); " + "; ".join(
                f"{k} {v:.0%}" for k, v in sorted(by_rule.items(), key=lambda kv: -kv[1]))
        cls = max(AREA_CLASSES, key=lambda c: shares[c])
        rows.append((p["program"], p["id"], cls, *(round(shares[c], 6) for c in AREA_CLASSES), p.get("via"),
                     r["rule_id"], r["rule_no"], r["kind"], r["basis"], hit, r["evidence"] or None, r["son"] or None,
                     r["status"], p.get("outside")))
    replace_table(con, "project_serving", "program varchar, id varchar, area_class varchar, share_local double, "
                  "share_regional double, share_citywide double, share_outside double, via varchar, rule_id varchar, "
                  "rule_no integer, kind varchar, basis varchar, matched varchar, evidence varchar, son varchar, "
                  "status varchar, outside_share double", rows)
    replace_table(con, "project_serving_units", "program varchar, id varchar, unit_no integer, share double, "
                  "label varchar, lon double, lat double, outside double, area_class varchar, rule_id varchar, "
                  "rule_no integer, matched varchar", unit_rows)
    replace_table(con, "serving_rule_son", "rule_id varchar, proposals integer, local integer, regional integer, "
                  "citywide integer", son_tally(con, rules))
    for prog, cls, n in con.execute("""select program, area_class, count(*) from project_serving
                                       group by all order by 1, 2""").fetchall():
        print(f"{prog:12} {cls:9} {n:6}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
