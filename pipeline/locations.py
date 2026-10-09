"""Build `project_locations`: one best-available location per FMS ID, with a confidence tier.

  A   agency/DCP geometry joined on FMS ID   (Parks tracker > CPDB points > CPDB polygons > DOT/DEP intersections),
      then street addresses in the project text geocoded by NYC Geoclient (pipeline/geocode.py),
      then large named features from the gazetteer (pipeline/named_features.py; linear ones are Tier B),
      then street stretches between two cross streets on the centerline (pipeline/street_lines.py;
      a whole street within the project's district is Tier B),
      then CPDB points or polygons from an older release for projects the current release has no geometry for
      (pipeline/cpdb_history.py; matched_to names the release; Tier B when CPDB still lists the project, since
      dropping its geometry may have been a correction)
  B   the facility code in HHC/CUNY/DCLA FMS IDs (pipeline/facility_codes.py; same borough only), then
      FDNY unit and NYPD precinct numbers in the title (pipeline/units.py), then the project name matched to a DCP
      facility or Parks property in the same borough (approximate)
  D   community district centroid from the `community_board` field
  E   borough centroid (project names a borough but no district)
Tier C is reserved for named neighborhoods.
  Unplaced  Citywide projects and projects with no usable borough (no coordinates; the site lists them
            beside the map).

Also writes `location_validation`: the Tier B steps (facility code, unit, then name match) run on projects
that already have Tier A coordinates, measuring how often they land near the trusted location.
Run after pipeline/ingest.py.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import duckdb

from db import DB_PATH, replace_table
from facility_codes import code_key, load_codes, resolve
from geo import (
    central_point,
    contains,
    distance_to_polygon_m,
    haversine_m,
    label_point,
    mean_point,
    parts,
    polygon_centroid,
)
from neighborhoods import CROSSING, NeighborhoodIndex
from neighborhoods import SKIP_AGENCIES as NEIGHBORHOOD_SKIP
from units import build_index, locate, parse_units

SOURCE_ERRORS = Path(__file__).with_name("source_errors.csv")
TIER_A_SOURCES = [  # precedence order
    ("parks_tracker", "loc_parks_tracker"),
    ("bridge_bin", "bridge_matches"),  # optional: a BIN in the text, located by NYC DOT (pipeline/bridges.py);
                                       # exact, so ahead of CPDB, which misplaces several bridges by kilometres
    ("cpdb_points", "loc_cpdb_points"),
    ("cpdb_polygons", "loc_cpdb_polygons"),
    ("dot_intersections", "loc_dot_intersections"),
    ("geoclient_address", "geocoded_addresses"),  # optional: present once geocode.py has run
]
# CPDB geometry from an older release, for projects the current release has none for (pipeline/cpdb_history.py):
# below every current Tier A source, named features and street extents; errors recorded against the current
# source apply to the same point in an older release.
ARCHIVED_SOURCES = [
    ("cpdb_points_archived", "loc_cpdb_points_archived"),
    ("cpdb_polygons_archived", "loc_cpdb_polygons_archived"),
]
SAME_SOURCE = {"cpdb_points_archived": "cpdb_points", "cpdb_polygons_archived": "cpdb_polygons"}

# Words that describe the work or a generic place type, not a specific place.
GENERIC = set("""
THE OF AND AT FOR IN ON TO AN BY WITH FROM NYC NEW YORK CITY PHASE PH II III IV
RECONSTRUCTION RECONSTRUCT RECONS RECON RENOVATION RENOVATIONS RENOVATE REPLACEMENT REPLACE UPGRADE UPGRADES
IMPROVEMENT IMPROVEMENTS CONSTRUCTION CONSTRUCT REHABILITATION REHAB HVAC ROOF ROOFS BOILER BOILERS ADA
COMPLIANCE EXTERIOR INTERIOR SITE WORK WORKS PROJECT PROJECTS FACILITY FACILITIES BUILDING BUILDINGS BLDG
LIBRARY BRANCH SCHOOL PARK PARKS PLAYGROUND CENTER CENTRE HOSPITAL HEALTH CLINIC STATION HOUSE FIRE POLICE
PRECINCT COMMUNITY BOARD DEPARTMENT DEPT PLGD GARDEN GREENSTREET SQUARE PLAZA MEMORIAL TRIANGLE FIELD
AVE AVENUE ST STREET RD ROAD BLVD HEAVY MAINTENANCE FULL SCOPE MISC GENERAL CAPITAL EXPENSE REPAIR REPAIRS
INSTALL INSTALLATION NEW EAST WEST NORTH SOUTH UPPER LOWER MANHATTAN BRONX BROOKLYN QUEENS STATEN ISLAND
OFFICE OFFICES PROGRAM EQUIPMENT SYSTEM SYSTEMS ELECTRICAL MECHANICAL WINDOW WINDOWS ELEVATOR ELEVATORS
FACADE SECURITY LIGHTING DESIGN EMERGENCY VARIOUS LOCATIONS OUTFITTING ACQUISITION
ELECTRIC SERVICES SERVICE PROGRAMS EXCELLENCE CHILDREN CHILDRENS ARTS ART RESTORATION COURTHOUSE
COURT PUMPING HALL MUSEUM SHELTER POUND RAIL MARKET BEACH LITTLE LEAGUE SOLAR PANEL INFRASTRUCTURE
EXPANSION AMBULATORY CHILLER COOLING TOWER LOCAL LAW FAN COIL UNITS FIRST FLOOR
""".split())

# Linear/utility work: a place name in these titles is usually a street, not the work site.
LINEAR = re.compile(
    r"\b(SEWERS?|SWR|WATER\s*MAINS?|WM|STORM|SANITARY|SAN|VIADUCT|EXPWY|EXPRESSWAY|PKWY|PARKWAY|"
    r"BRIDGES?|HIGHWAY|HWY|RESURFAC\w*|LAMPPOSTS?|LIGHTPOLES?|SIDEWALKS?|CURBS?|STREETSCAPE|"
    r"RETAINING\s+WALL|BULKHEAD|SHORELINE|GREENWAY|CORRIDOR)\b")
# Multi-site work ('Life Safety Projects @ 17 Branch Libraries'): one named place isn't the work site.
MULTI_SITE = re.compile(r"\b(?:\d+|TWO|THREE|FOUR|FIVE|SIX|SEVERAL|VARIOUS|MULTIPLE)\s+(?:[A-Z]+\s+){0,2}"
                        r"(?:LIBRARIES|BRANCHES|SITES|LOCATIONS|FACILITIES|BUILDINGS|SCHOOLS|PARKS|STATIONS)\b")
SKIP_AGENCIES = {"DOT"}  # validation showed name matches for DOT work are mostly wrong

# Borough evidence in a title: Parks property codes ('Q106', 'B057-115M', 'XG-31650') and borough names.
TITLE_BOROUGH = {
    "Bronx": re.compile(r"\bX\d{3}[A-Z]?\b|\bXG-|\bBRONX\b|\bBX\b"),
    "Brooklyn": re.compile(r"\bB\d{3}[A-Z]?\b|\bBG-|\bBROOKLYN\b|\bBKLYN\b"),
    "Manhattan": re.compile(r"\bM\d{3}[A-Z]?\b|\bMG-|\bMANHATTAN\b"),
    "Queens": re.compile(r"\bQ\d{3}[A-Z]?\b|\bQG-|\bQUEENS\b"),
    "Staten Island": re.compile(r"\bR\d{3}[A-Z]?\b|\bRG-|\bSTATEN ISLAND\b|\bS\.?I\.?$|\bSI\b"),
}
BOROUGH_SLACK_M = 2000  # Rikers (legally the Bronx, inside a Queens district polygon) is 1.1-1.4 km out
AMBIGUOUS_M = 500  # equally good candidates further apart than this are rejected
NEAR_M = (500, 1000)  # validation thresholds


def tokens(s: str | None) -> list[str]:
    return [t for t in re.sub(r"[^A-Z0-9 ]", " ", (s or "").upper()).split() if len(t) > 1]


def distinctive(s: str | None) -> frozenset[str]:
    return frozenset(t for t in tokens(s) if t not in GENERIC)


AGENCY_PREFIX = re.compile(r"\s*([A-Z]{2,6})\s*[-:]\s")  # 'NYPD - 122ND PRECINCT', 'DHS - ...'
AGENCY_ALIASES = {"NYCHHC": "HHC", "NYCHH": "HHC", "NYCDSS": "DHS", "DSS": "DHS", "QBPL": "QPL"}


def normalize_agency(code: str | None) -> str | None:
    """Put FacDB operator/overseer codes ('NYCDPR', 'NYCHHC') and project agencies ('DPR', 'HHC')
    on one vocabulary. Homeless shelters are overseen by DSS, DHS's parent. NYCHA stays NYCHA."""
    if not code:
        return None
    c = code.strip().upper()
    if c in AGENCY_ALIASES:
        return AGENCY_ALIASES[c]
    if c.startswith("NYC") and c != "NYCHA" and len(c) > 4:
        return c[3:]
    return c


def client_agencies(managing: str | None, sponsor: str | None, title: str) -> frozenset[str]:
    """Agencies a project is for: managing, sponsor, and an agency prefix in the title, as in
    DCAS-managed 'NYPD - 122ND PRECINCT' or 'DHS - ROSE MCCARTHY FAMILY RESIDENCE'."""
    out = {normalize_agency(managing), normalize_agency(sponsor)}
    m = AGENCY_PREFIX.match((title or "").upper())
    if m:
        out.add(normalize_agency(m.group(1)))
    return frozenset(a for a in out if a)


class PlaceIndex:
    """Inverted index over named places; a place matches when all of its distinctive tokens
    appear in the project title, it is in the same borough, and `acceptable()` allows it."""

    def __init__(self, places):
        self.places = []  # (name, borough, lon, lat, source, distinctive tokens, agencies)
        self.index = defaultdict(list)
        for name, boro, lon, lat, source, agencies in places:
            d = distinctive(name)
            if not d or sum(len(t) for t in d) < 5 or all(t.isdigit() for t in d):
                continue
            k = len(self.places)
            self.places.append((name, boro, lon, lat, source, d, frozenset(agencies)))
            for t in d:
                self.index[t].append(k)

    def match(self, title: str, boro: str, clients: frozenset[str]):
        pt = set(tokens(title))
        cands = {k for t in pt if t not in GENERIC for k in self.index.get(t, ())}
        hits = [self.places[k] for k in sorted(cands)  # sorted: ties resolve the same way every run
                if self.places[k][5] <= pt and self.places[k][1] == boro
                and acceptable(title, clients, self.places[k])]
        if not hits:
            return None
        def score(p):
            return len(p[5]), sum(len(t) for t in p[5])

        best = max(score(p) for p in hits)
        top = [p for p in hits if score(p) == best]
        # Tie-breaks: a place run by a client agency (an NYPL project and Fort Washington Library, not
        # Fort Washington Park); then, among those, the place whose full name best fits the title
        # ('EAST FLUSHING' over 'FLUSHING' only when the title says East). Not for Parks projects:
        # there they pick the centre of a large park (Fort Washington Park's is 4 km from the dog run).
        own = [p for p in top if p[6] & clients] if "DPR" not in clients else []
        if own:
            fit = {p[0]: sum(1 if t in pt else -1 for t in set(tokens(p[0]))) for p in own}
            top = [p for p in own if fit[p[0]] == max(fit.values())]
        if any(haversine_m(top[0][3], top[0][2], p[3], p[2]) > AMBIGUOUS_M for p in top[1:]):
            return None
        return top[0]


def is_address(title: str, place_tokens: frozenset[str]) -> bool:
    """True when a matched token follows a house number ('851 GRAND CONCOURSE'), i.e. it is a street."""
    t = title.upper()
    return any(re.search(rf"\b\d+[A-Z]?\s+(?:[A-Z]+\s+){{0,2}}{re.escape(tok)}\b", t) for tok in place_tokens)


def lead_token(title: str) -> str | None:
    """First distinctive word of a title, after any agency prefix ('NYPD - 122ND PRECINCT' -> '122ND')."""
    ws = tokens(title)
    if AGENCY_PREFIX.match(title.upper()):
        ws = ws[1:]
    return next((w for w in ws if w not in GENERIC), None)


def acceptable(title: str, clients: frozenset[str], place) -> bool:
    """Rules from validation against Tier A coordinates:
    - address-like facility matches ('851 GRAND CONCOURSE') are street-name collisions;
    - multi-token matches are accepted;
    - single-token matches are mostly neighbourhood names ('Hollis Library' -> Hollis Playground)
      unless the place is run or overseen by one of the project's client agencies (a Parks project
      and a park; an NYPL project and an NYPL branch). For facilities the word must also lead the
      title ('MASPETH - HVAC'), which lifted precision from 86% to 90% (buried words: 61%)."""
    if is_address(title, place[5]) and place[4] != "parks_properties":
        return False
    if len(place[5]) > 1:
        return True
    if not place[6] & clients:
        return False
    return place[4] == "parks_properties" or lead_token(title) in place[5]


def match_rule(place) -> str:
    """Which acceptance rule admitted a match, for validation breakdowns."""
    return "multi_token" if len(place[5]) > 1 else f"single_token_{place[4]}"


def eligible_for_name_match(agency: str, title: str) -> bool:
    """Citywide programs ('Citywide Roofing ... Wakefield') name one example site, not the work site."""
    t = title.upper()
    return (agency not in SKIP_AGENCIES and not LINEAR.search(t) and not MULTI_SITE.search(t)
            and "CITYWIDE" not in t)


def parse_districts(board: str | None, cd_codes: dict, known: set[int]) -> list[int]:
    """'Queens, Queens 07' -> [407]. Borough-only, 'Citywide' and placeholder codes
    (e.g. 'Brooklyn 99', meaning borough-wide) give []."""
    out = []
    for boro, num in re.findall(r"(Manhattan|Bronx|Brooklyn|Queens|Staten Island)\s+(\d{1,2})", board or ""):
        code = cd_codes[boro] * 100 + int(num)
        if code in known and code not in out:
            out.append(code)
    return out


def borough_centroids(con) -> dict[str, tuple[float, float]]:
    """Tier E points: each borough's centroid, from the union of its community districts."""
    by_boro = defaultdict(list)
    for b, gj in con.execute("select borough, geojson from ref_community_districts").fetchall():
        g = json.loads(gj)
        by_boro[b].extend(g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]])
    return {b: polygon_centroid({"type": "MultiPolygon", "coordinates": polys}) for b, polys in by_boro.items()}

def main() -> int:
    con = duckdb.connect(str(DB_PATH))

    # Latest descriptive fields per FMS ID across all snapshots.
    projects = con.execute("""
        select fms_id,
               arg_max(managing_agency, reporting_period),
               arg_max(coalesce(agency_project_name, '') || ' ' || coalesce(fms_project_name, ''), reporting_period),
               arg_max(borough, reporting_period),
               arg_max(community_board, reporting_period),
               arg_max(sponsor_agency, reporting_period)
        from project_budget_schedule group by fms_id""").fetchall()

    # Tier A: representative point per FMS ID per source.
    # Borough check: an agency point well outside the borough the project lists is a same-name mix-up in the
    # source (CPDB put Tony Dapolito Recreation Center, in Greenwich Village, on Staten Island). Such a source
    # is skipped and the next one, or a later tier, is used, unless the title backs the point's borough, in
    # which case the project's borough field is the error. Both go to `borough_conflicts`.
    cd_geoms = [(c, b, json.loads(g)) for c, b, g in
                con.execute("select boro_cd, borough, geojson from ref_community_districts").fetchall()]
    listed_boro = {fms: boro for fms, _a, _t, boro, *_ in projects}
    # pipeline/source_errors.csv: hand-verified errors in the sources, with evidence. A source marked
    # point_wrong or generic_point is skipped for that project; listing_wrong keeps a point that fails the
    # borough check because the project's borough field is the error.
    with SOURCE_ERRORS.open() as f:
        location_sources = {s for s, _ in TIER_A_SOURCES + ARCHIVED_SOURCES}  # the list also records schedule errors
        known = {(r["fms_id"], r["source"]): r["problem"] for r in csv.DictReader(f)
                 if r["source"] in location_sources}

    def problem(fms, source):
        return known.get((fms, source)) or known.get((fms, SAME_SOURCE.get(source)))
    titles = {fms: (title or "").upper() for fms, _a, title, *_ in projects}

    def borough_conflict(fms, lon, lat):
        """(point borough, metres outside the listed borough, verdict) when the point is more than
        BOROUGH_SLACK_M outside the listed borough. Verdict 'listing_wrong' when the title names the
        point's borough and not the listed one ('Mahoney Park, SI' listed as Manhattan); else 'point_wrong'."""
        boro = listed_boro.get(fms)
        if not any(b == boro for _, b, _ in cd_geoms):
            return None
        found = next((b for _, b, g in cd_geoms if contains(g, lon, lat)), None)
        if found is None or found == boro:  # parkland/airports outside every district are not judged
            return None
        d = min(distance_to_polygon_m(g, lon, lat) for _, b, g in cd_geoms if b == boro)
        if d <= BOROUGH_SLACK_M:
            return None
        named = {b for b, rx in TITLE_BOROUGH.items() if rx.search(titles[fms])}
        return found, round(d), "listing_wrong" if found in named and boro not in named else "point_wrong"

    def in_listed_borough(fms, lon, lat):
        return any(b == listed_boro.get(fms) and contains(g, lon, lat) for _, b, g in cd_geoms)

    def verdict(fms, source, auto):
        k = problem(fms, source)
        return k if k in ("point_wrong", "listing_wrong") else auto

    rejected = []
    tables = {t for (t,) in con.execute("select table_name from duckdb_tables()").fetchall()}

    def place(sources, skip=()):
        """FMS ID -> (source, lon, lat, n_points, spread) from the first source in `sources` that has it."""
        placed = {}
        for source, table in sources:
            if table not in tables:
                print(f"note: {table} not found; skipping {source}", file=sys.stderr)
                continue
            if "polygons" in table:  # each part of a footprint is a site
                rows = [(fms, [label_point({"type": "Polygon", "coordinates": p})
                               for g in gs for p in parts(json.loads(g))])
                        for fms, gs in con.execute(f"select fms_id, list(geojson) from {table} group by fms_id"
                                                   ).fetchall()]
            else:
                rows = [(fms, list(zip(lons, lats, strict=True))) for fms, lons, lats in
                        con.execute(f"select fms_id, list(lon), list(lat) from {table} group by fms_id").fetchall()]
            for fms, pts in rows:
                if fms in placed or fms in skip:
                    continue
                if problem(fms, source) in ("point_wrong", "generic_point"):
                    continue
                # The most central site, among those in the listed borough when there are any: a multi-borough
                # project ('Multi-Site Pedestrian Safety', Brooklyn) sits at one of its Brooklyn sites.
                home = [p for p in pts if in_listed_borough(fms, *p)] if len(pts) > 1 else []
                lon, lat = central_point(home or pts)
                off = borough_conflict(fms, lon, lat)
                if off:
                    rejected.append((fms, source, lon, lat, listed_boro[fms], *off[:2],
                                     verdict(fms, source, off[2])))
                    if rejected[-1][-1] == "point_wrong":
                        continue
                spread = max(haversine_m(lat, lon, la, lo) for lo, la in pts)
                placed[fms] = (source, lon, lat, len(pts), spread)
        return placed

    tier_a = place(TIER_A_SOURCES)
    archived = place(ARCHIVED_SOURCES, skip=tier_a)
    releases, listed = {}, set()
    for _, table in ARCHIVED_SOURCES:
        if table in tables:
            for fms, rel, still in con.execute(f"select fms_id, max(release), bool_or(listed) from {table} group by 1"
                                               ).fetchall():
                releases[fms] = rel
                if still:
                    listed.add(fms)
    replace_table(con, "borough_conflicts",
                  "fms_id varchar, source varchar, lon double, lat double, listed_borough varchar, "
                  "point_borough varchar, distance_m integer, verdict varchar", rejected)

    # Tier B index: DCP facilities + Parks properties.
    places = con.execute("""
        select name, borough, lon, lat, 'facdb', operator, overseer from ref_facilities where borough is not null
        union all
        select name, borough, lon, lat, 'parks_properties', 'DPR', null from ref_parks_properties
        where borough is not null
        order by 5 desc, 1, 3, 4  -- ties between equal matches go to the park, then by name
    """).fetchall()
    index = PlaceIndex([(n, b, lo, la, src, {normalize_agency(op), normalize_agency(ov)} - {None})
                        for n, b, lo, la, src, op, ov in places])

    # Tier B: facility codes in HHC/CUNY/DCLA FMS IDs, resolved to FacDB rows, then title name matching.
    code_sites, unresolved = resolve(con, load_codes())
    for key, n in unresolved:
        print(f"warning: facility code {key} matched {n} FacDB rows; skipped", file=sys.stderr)
    unit_index, conflicts = build_index(con)
    for unit, names in conflicts:
        print(f"note: unit {unit} is at several FacDB locations {names}; skipped", file=sys.stderr)

    def tier_b(fms, agency, title, boro, sponsor):
        """(source, lon, lat, matched_to, rule) from the Tier B steps, or None. A facility code beats a
        title name match: where both fired, the code was right in every disagreement."""
        site = code_sites.get(code_key(agency, fms))
        if site and site[1] == boro:
            return "facility_code", site[2], site[3], site[0], "facility_code"
        unit = locate(title, boro, client_agencies(agency, sponsor, title), unit_index)
        if unit:
            owner, site = unit
            source = f"{owner.lower()}_unit"
            return source, site[2], site[3], site[0], source
        if boro in boro_centroid and eligible_for_name_match(agency or "", title):
            hit = index.match(title, boro, client_agencies(agency, sponsor, title))
            if hit:
                return hit[4], hit[2], hit[3], hit[0], match_rule(hit)
        return None

    # Tiers D and E: district centroids, and borough centroids from the union of each borough's districts.
    cds = con.execute("select boro_cd, borough, lon, lat, geojson from ref_community_districts").fetchall()
    cd_centroid = {c: (lon, lat) for c, _, lon, lat, _ in cds}
    cd_codes = {b: c // 100 for c, b, *_ in cds}
    boro_centroid = borough_centroids(con)

    # Tier C: a neighborhood named in the title (pipeline/neighborhoods.py).
    nbhd = None
    if "ref_ntas" in tables:
        nbhd = NeighborhoodIndex(con.execute(
            "select nta, name, borough, cdta, lon, lat, geojson from ref_ntas").fetchall())

    def tier_c(agency, title, boro, districts):
        t = (title or "").upper()
        if not nbhd or agency in NEIGHBORHOOD_SKIP or "CITYWIDE" in t or MULTI_SITE.search(t) or (
                agency == "DOT" and CROSSING.search(t)):
            return None
        return nbhd.locate(title, boro, districts)

    # Named features from the gazetteer (pipeline/named_features.py): point/area features are as good
    # as Tier A; linear ones (tunnels, corridors) are one stand-in point, so Tier B.
    named = {}
    if "named_feature_matches" in tables:
        named = {fms: (name, extent, lon, lat) for fms, name, extent, lon, lat in
                 con.execute("select fms_id, name, extent, lon, lat from named_feature_matches").fetchall()}
    # Street lines (pipeline/street_lines.py): a routed stretch between two cross streets is Tier A;
    # a whole street within the project's district(s) is Tier B. spread_m holds the line length.
    street = {}
    if "street_lines" in tables:
        street = {fms: rest for fms, *rest in
                  con.execute("select fms_id, kind, label, length_m, lon, lat from street_lines").fetchall()}

    out = []
    for fms, agency, title, boro, board, sponsor in projects:
        if fms in tier_a:
            source, lon, lat, n, spread = tier_a[fms]
            out.append((fms, "A", source, lon, lat, n, round(spread), None))
            continue
        if fms in named and named[fms][1] != "linear":
            name, _, lon, lat = named[fms]
            out.append((fms, "A", "named_feature", lon, lat, 1, None, name))
            continue
        if fms in street and street[fms][0] == "extent":
            _, label, length, lon, lat = street[fms]
            out.append((fms, "A", "street_extent", lon, lat, 1, length, label))
            continue
        if fms in archived:  # Tier B when CPDB still lists the project but dropped its geometry (maybe a correction)
            source, lon, lat, n, spread = archived[fms]
            out.append((fms, "B" if fms in listed else "A", source, lon, lat, n, round(spread),
                        f"CPDB release {releases[fms]}"))
            continue
        if fms in named:
            name, _, lon, lat = named[fms]
            out.append((fms, "B", "named_feature_linear", lon, lat, 1, None, name))
            continue
        if fms in street:
            kind, label, length, lon, lat = street[fms]
            out.append((fms, "B", f"street_{kind}", lon, lat, 1, length, label))
            continue
        hit = tier_b(fms, agency, title, boro, sponsor)
        if hit:
            source, lon, lat, name, _ = hit
            out.append((fms, "B", source, lon, lat, 1, 0, name))
            continue
        districts = parse_districts(board, cd_codes, set(cd_centroid))
        hit = tier_c(agency, title, boro, districts)
        if hit:
            lon, lat, n, spread, label, _ = hit
            out.append((fms, "C", "neighborhood", lon, lat, n, spread, label))
            continue
        if districts:
            lon, lat = mean_point([cd_centroid[d] for d in districts])
            out.append((fms, "D", "community_district", lon, lat, len(districts), None,
                        ",".join(map(str, districts))))
        elif boro in boro_centroid:
            lon, lat = boro_centroid[boro]
            out.append((fms, "E", "borough", lon, lat, 1, None, boro))
        else:
            out.append((fms, "Unplaced", "citywide" if boro == "Citywide" else "no_borough",
                        None, None, 0, None, boro))

    # source_flag: what source_errors.csv says about the placement shown, so the site can note it.
    def source_flag(fms, source):
        mine = {s: p for (f, s), p in known.items() if f == fms}
        if "listing_wrong" in mine.values():
            return "borough_field_wrong"   # point right, the project's borough field wrong
        if mine.get(source) == "unclear" or mine.get(SAME_SOURCE.get(source)) == "unclear":
            return "point_disputed"        # the point shown is in doubt
        return "official_point_rejected" if mine else None  # shown location is a fallback

    out = [(*row, source_flag(row[0], row[2])) for row in out]
    replace_table(con, "project_locations",
                  "fms_id varchar, tier varchar, source varchar, lon double, lat double, "
                  "n_points integer, spread_m integer, matched_to varchar, source_flag varchar", out)

    # Validation: run the Tier B steps on projects whose Tier A location is already known.
    val = []
    for fms, agency, title, boro, _board, sponsor in projects:
        if fms not in tier_a or boro not in boro_centroid:
            continue
        source, lon, lat, *_ = tier_a[fms]
        eligible = (eligible_for_name_match(agency or "", title) or code_key(agency, fms) is not None
                    or bool(parse_units(title)))
        hit = tier_b(fms, agency, title, boro, sponsor)
        dist = round(haversine_m(lat, lon, hit[2], hit[1])) if hit else None
        val.append((fms, agency, source, eligible, hit is not None, dist, hit[4] if hit else None))
    replace_table(con, "location_validation",
                  "fms_id varchar, managing_agency varchar, truth_source varchar, eligible boolean, "
                  "matched boolean, distance_m integer, rule varchar", val)

    # Validation of Tier C: distance from the Tier A point to the named neighborhood (0 when inside).
    nval = []
    for fms, agency, title, boro, board, _sponsor in projects:
        if fms not in tier_a or (boro not in boro_centroid and boro != "Citywide"):
            continue
        hit = tier_c(agency, title, boro, parse_districts(board, cd_codes, set(cd_centroid)))
        if hit:
            source, lon, lat, *_ = tier_a[fms]
            dist = min(distance_to_polygon_m(nbhd.ntas[n][5], lon, lat) for n in hit[5])
            nval.append((fms, agency, source, hit[4], round(dist)))
    replace_table(con, "neighborhood_validation",
                  "fms_id varchar, managing_agency varchar, truth_source varchar, neighborhood varchar, "
                  "distance_m integer", nval)

    print(con.sql("select tier, count(*) n from project_locations group by 1 order by 1"))
    print(con.sql(f"""select truth_source, count_if(eligible) as n_eligible, count_if(matched) as n_matched,
        count_if(distance_m <= {NEAR_M[0]}) as within_{NEAR_M[0]}m,
        count_if(distance_m <= {NEAR_M[1]}) as within_{NEAR_M[1]}m,
        round(100.0 * count_if(distance_m <= {NEAR_M[0]}) / nullif(count_if(matched), 0), 1)
            as precision_{NEAR_M[0]}m_pct
        from location_validation group by 1 order by 1"""))
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
