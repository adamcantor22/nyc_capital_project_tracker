"""Numbered units in project titles, resolved to DCP Facilities Database rows.

FDNY titles name the unit housed in a firehouse ('EC287', 'Engine Company 287', 'SQ288',
'Marine 9', 'EMS Station 58'); FacDB names firehouses by the units they house
('BATTALION 46/ENGINE 287/LADDER 136'). NYPD titles and FacDB police stations name precincts
('49TH PCT', 'NYPD 44 PRECINCT STATION HOUSE'). Unit numbers are unique citywide, so a title's units
identify one building even when the project's borough is 'Citywide'. The same patterns parse both
sides. FDNY's two training campuses, named rather than numbered in titles, resolve to their FacDB
rows the same way. pipeline/locations.py applies these as Tier B, only to projects whose client
agencies include the unit's agency.
"""
import re

from geo import haversine_m

KINDS = {  # unit kind -> spellings seen in project titles and FacDB names
    "ENGINE": r"EC|ENG|ENGINE(?:\s+CO(?:MPANY)?)?",
    "LADDER": r"LADD?DER(?:\s+CO(?:MPANY)?)?|LAD|LC",
    "SQUAD": r"SQ|SQUAD",
    "RESCUE": r"RESCUE",
    "MARINE": r"MARINE",
    "EMS": r"EMS(?:\s+(?:STATION|STN|ST\.?))?",
}
UNIT = re.compile(r"\b(?:" + "|".join(f"(?P<{k}>{v})" for k, v in KINDS.items()) + r")\s*[-#.]?\s*(?P<n>\d{1,3})\b")
ORD = r"\d{1,3}(?:ST|ND|RD|TH)"
# '49TH PCT', '106 Pct.', '52ND PRECNCT', and lists ('26TH, 42ND & 46TH PRECINCTS'), or 'PRECINCT 60'
PRECINCTS = re.compile(rf"\b((?:{ORD}\s*(?:,|&|AND)\s*)*\d{{1,3}}(?:ST|ND|RD|TH)?)"
                       r"\s*(?:POLICE\s+)?(?:PCTS?|PRECI?NCTS?)\b|\bPRECINCT\s+(\d{1,3})\b")
AGENCY = {"PRECINCT": "NYPD"}  # unit kind -> agency; every other kind is FDNY
FACTYPES =("FIREHOUSE", "AMBULANCE STATION", "EMERGENCY MEDICL STN", "EMERGENCY MEDICAL STATION",
            "PUBLIC SAFETY FACILITY")
CAMPUSES = {  # title pattern -> FacDB name (operator FDNY)
    r"\bF(?:OR)?T\.? TOTTEN\b": "FORT TOTTEN (US ARMY)",
    r"\bRANDALL'?S\b": "FIRE DEPT.FIRE TRAINING ACAD",
}
SAME_SITE_M = 150  # FacDB rows for one unit closer than this are the same building


def parse_units(text: str) -> set[tuple]:
    """'BUILDING AUTOMATION CONTROLS AT EC276' -> {('ENGINE', 276)}; 'FT TOTTEN BUILDING 420' ->
    {('CAMPUS', 'FORT TOTTEN (US ARMY)')}."""
    t = text.upper()
    units = {(next(k for k in KINDS if m.group(k)), int(m.group("n"))) for m in UNIT.finditer(t)}
    for m in PRECINCTS.finditer(t):
        units |= {("PRECINCT", int(n)) for n in re.findall(r"\d+", m.group(1) or m.group(2))}
    return units | {("CAMPUS", name) for pattern, name in CAMPUSES.items() if re.search(pattern, t)}


def agency_of(unit: tuple) -> str:
    return AGENCY.get(unit[0], "FDNY")


def build_index(con) -> tuple[dict, list]:
    """unit -> (facility name, borough, lon, lat), plus units whose FacDB rows disagree on location.
    Each row contributes only its operator's units ('ENG 46, LAD 27, 48 PRECINCT' is an NYPD row)."""
    rows = con.execute(f"""select name, borough, lon, lat, operator from ref_facilities
        where (operator = 'FDNY' and (factype in {FACTYPES} or name in {tuple(CAMPUSES.values())}))
           or (operator = 'NYPD' and factype = 'POLICE STATION'
               and not regexp_matches(name, '^(FUTURE|FORMER|OLD) '))""").fetchall()
    sites: dict[tuple, list] = {}
    for name, boro, lon, lat, operator in rows:
        if name in CAMPUSES.values():
            sites.setdefault(("CAMPUS", name), []).append((name, boro, lon, lat))
            continue
        for u in parse_units(name):
            if agency_of(u) == operator:
                sites.setdefault(u, []).append((name, boro, lon, lat))
    index, conflicts = {}, []
    for u, ss in sites.items():
        if all(haversine_m(ss[0][3], ss[0][2], s[3], s[2]) <= SAME_SITE_M for s in ss[1:]):
            index[u] = ss[0]
        else:
            conflicts.append((u, [s[0] for s in ss]))
    return index, conflicts


def locate(title: str, boro: str | None, clients: frozenset[str], index: dict):
    """(agency, site) for the one building a project's units point to, or None (no units of a client
    agency, units at several buildings, or a building outside the project's stated borough). A unit
    missing from the index also rejects: the project may span a building FacDB doesn't list."""
    units = [u for u in parse_units(title) if agency_of(u) in clients]
    if not units or any(u not in index for u in units):
        return None
    hits = [index[u] for u in units]
    if any(haversine_m(hits[0][3], hits[0][2], h[3], h[2]) > SAME_SITE_M for h in hits[1:]):
        return None
    site = hits[0]
    if boro in ("Manhattan", "Bronx", "Brooklyn", "Queens", "Staten Island") and site[1] != boro:
        return None
    return agency_of(units[0]), site
