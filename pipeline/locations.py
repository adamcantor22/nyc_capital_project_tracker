"""Build `project_locations`: one best-available location per FMS ID, with a confidence tier.

  A   agency/DCP geometry joined on FMS ID   (Parks tracker > CPDB points > CPDB polygons > DOT/DEP intersections)
  B   project name matched to a DCP facility or Parks property in the same borough (approximate)
  C   community district centroid from the `community_board` field
  C2  borough centroid (project names a borough but no district)
Citywide projects and projects with no usable borough are left unplaced.

Also writes `location_validation`: Tier B matcher run on projects that already have Tier A
coordinates, measuring how often the name match lands near the trusted location.
Run after pipeline/ingest.py.
"""
import json
import re
import sys
from collections import defaultdict

import duckdb

from db import DB_PATH, replace_table
from geo import haversine_m, mean_point, polygon_centroid

TIER_A_SOURCES = [  # precedence order
    ("parks_tracker", "loc_parks_tracker"),
    ("cpdb_points", "loc_cpdb_points"),
    ("cpdb_polygons", "loc_cpdb_polygons"),
    ("dot_intersections", "loc_dot_intersections"),
]

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
SKIP_AGENCIES = {"DOT"}  # validation showed name matches for DOT work are mostly wrong

AMBIGUOUS_M = 500  # equally good candidates further apart than this are rejected
NEAR_M = (500, 1000)  # validation thresholds


def tokens(s: str | None) -> list[str]:
    return [t for t in re.sub(r"[^A-Z0-9 ]", " ", (s or "").upper()).split() if len(t) > 1]


def distinctive(s: str | None) -> frozenset[str]:
    return frozenset(t for t in tokens(s) if t not in GENERIC)


class PlaceIndex:
    """Inverted index over named places; a place matches when all of its distinctive tokens
    appear in the project title and it is in the same borough."""

    def __init__(self, places):
        self.places = []  # (name, borough, lon, lat, source, distinctive tokens)
        self.index = defaultdict(list)
        for name, boro, lon, lat, source in places:
            d = distinctive(name)
            if not d or sum(len(t) for t in d) < 5 or all(t.isdigit() for t in d):
                continue
            k = len(self.places)
            self.places.append((name, boro, lon, lat, source, d))
            for t in d:
                self.index[t].append(k)

    def match(self, title: str, boro: str, agency: str):
        pt = set(tokens(title))
        cands = {k for t in pt if t not in GENERIC for k in self.index.get(t, ())}
        hits = [self.places[k] for k in cands
                if self.places[k][5] <= pt and self.places[k][1] == boro
                and acceptable(title, agency, self.places[k])]
        if not hits:
            return None
        score = lambda p: (len(p[5]), sum(len(t) for t in p[5]))
        best = max(score(p) for p in hits)
        top = [p for p in hits if score(p) == best]
        if any(haversine_m(top[0][3], top[0][2], p[3], p[2]) > AMBIGUOUS_M for p in top[1:]):
            return None
        return top[0]


def is_address(title: str, place_tokens: frozenset[str]) -> bool:
    """True when a matched token follows a house number ('851 GRAND CONCOURSE'), i.e. it is a street."""
    t = title.upper()
    return any(re.search(rf"\b\d+[A-Z]?\s+(?:[A-Z]+\s+){{0,2}}{re.escape(tok)}\b", t) for tok in place_tokens)


def acceptable(title: str, agency: str, place) -> bool:
    """Rules from validation against Tier A coordinates. Single-token matches are mostly
    neighbourhood or street names ('Hollis Library' -> Hollis Playground), except for Parks
    projects matched to a park; address-like facility matches are street-name collisions."""
    if len(place[5]) > 1:
        return place[4] == "parks_properties" or not is_address(title, place[5])
    return place[4] == "parks_properties" and agency == "DPR"


def eligible_for_name_match(agency: str, title: str) -> bool:
    return agency not in SKIP_AGENCIES and not LINEAR.search(title.upper())


def parse_districts(board: str | None, cd_codes: dict, known: set[int]) -> list[int]:
    """'Queens, Queens 07' -> [407]. Borough-only, 'Citywide' and placeholder codes
    (e.g. 'Brooklyn 99', meaning borough-wide) give []."""
    out = []
    for boro, num in re.findall(r"(Manhattan|Bronx|Brooklyn|Queens|Staten Island)\s+(\d{1,2})", board or ""):
        code = cd_codes[boro] * 100 + int(num)
        if code in known and code not in out:
            out.append(code)
    return out


def main() -> int:
    con = duckdb.connect(str(DB_PATH))

    # Latest descriptive fields per FMS ID across all snapshots.
    projects = con.execute("""
        select fms_id,
               arg_max(managing_agency, reporting_period),
               arg_max(coalesce(agency_project_name, '') || ' ' || coalesce(fms_project_name, ''), reporting_period),
               arg_max(borough, reporting_period),
               arg_max(community_board, reporting_period)
        from project_budget_schedule group by fms_id""").fetchall()

    # Tier A: representative point per FMS ID per source.
    tier_a = {}
    for source, table in TIER_A_SOURCES:
        rows = con.execute(f"select fms_id, list(lon), list(lat) from {table} group by fms_id").fetchall()
        for fms, lons, lats in rows:
            if fms in tier_a:
                continue
            pts = list(zip(lons, lats))
            lon, lat = mean_point(pts)
            spread = max(haversine_m(lat, lon, la, lo) for lo, la in pts)
            tier_a[fms] = (source, lon, lat, len(pts), spread)

    # Tier B index: DCP facilities + Parks properties.
    places = con.execute("""
        select name, borough, lon, lat, 'facdb' from ref_facilities where borough is not null
        union all
        select name, borough, lon, lat, 'parks_properties' from ref_parks_properties where borough is not null
    """).fetchall()
    index = PlaceIndex(places)

    # Tier C: district centroids, and borough centroids from the union of each borough's districts.
    cds = con.execute("select boro_cd, borough, lon, lat, geojson from ref_community_districts").fetchall()
    cd_centroid = {c: (lon, lat) for c, _, lon, lat, _ in cds}
    cd_codes = {b: c // 100 for c, b, *_ in cds}
    by_boro = defaultdict(list)
    for _, b, _, _, gj in cds:
        g = json.loads(gj)
        by_boro[b].extend(g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]])
    boro_centroid = {b: polygon_centroid({"type": "MultiPolygon", "coordinates": polys})
                     for b, polys in by_boro.items()}

    out = []
    for fms, agency, title, boro, board in projects:
        if fms in tier_a:
            source, lon, lat, n, spread = tier_a[fms]
            out.append((fms, "A", source, lon, lat, n, round(spread), None))
            continue
        if boro in boro_centroid and eligible_for_name_match(agency or "", title):
            hit = index.match(title, boro, agency)
            if hit:
                out.append((fms, "B", hit[4], hit[2], hit[3], 1, 0, hit[0]))
                continue
        districts = parse_districts(board, cd_codes, set(cd_centroid))
        if districts:
            lon, lat = mean_point([cd_centroid[d] for d in districts])
            out.append((fms, "C", "community_district", lon, lat, len(districts), None,
                        ",".join(map(str, districts))))
        elif boro in boro_centroid:
            lon, lat = boro_centroid[boro]
            out.append((fms, "C2", "borough", lon, lat, 1, None, boro))

    replace_table(con, "project_locations",
                  "fms_id varchar, tier varchar, source varchar, lon double, lat double, "
                  "n_points integer, spread_m integer, matched_to varchar", out)

    # Validation: run the Tier B matcher on projects whose Tier A location we already trust.
    val = []
    for fms, agency, title, boro, board in projects:
        if fms not in tier_a or boro not in boro_centroid:
            continue
        source, lon, lat, *_ = tier_a[fms]
        eligible = eligible_for_name_match(agency or "", title)
        hit = index.match(title, boro, agency) if eligible else None
        dist = round(haversine_m(lat, lon, hit[3], hit[2])) if hit else None
        val.append((fms, agency, source, eligible, hit is not None, dist))
    replace_table(con, "location_validation",
                  "fms_id varchar, managing_agency varchar, truth_source varchar, eligible boolean, "
                  "matched boolean, distance_m integer", val)

    print(con.sql("select tier, count(*) n from project_locations group by 1 order by 1"))
    print(con.sql(f"""select truth_source, count_if(eligible) as n_eligible, count_if(matched) as n_matched,
        count_if(distance_m <= {NEAR_M[0]}) as within_{NEAR_M[0]}m, count_if(distance_m <= {NEAR_M[1]}) as within_{NEAR_M[1]}m,
        round(100.0 * count_if(distance_m <= {NEAR_M[0]}) / nullif(count_if(matched), 0), 1) as precision_{NEAR_M[0]}m_pct
        from location_validation group by 1 order by 1"""))
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
