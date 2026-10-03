"""Numbered units in project titles, resolved to DCP Facilities Database rows.

FDNY titles name the unit housed in a firehouse ('EC287', 'Engine Company 287', 'SQ288',
'Marine 9', 'EMS Station 58'); FacDB names firehouses by the units they house
('BATTALION 46/ENGINE 287/LADDER 136'). NYPD titles and FacDB police stations name precincts
('49TH PCT', 'NYPD 44 PRECINCT STATION HOUSE'), and DSNY titles name district garages ('Queens 8/10/12',
FacDB 'QE08G GARAGE'). DOC titles and FacDB jails share acronyms ('AMKC', 'ANNA M. KROSS CENTER
(AMKC)'). Unit numbers are unique citywide, so a title's units identify one building even when the
project's borough is 'Citywide'. The same patterns parse both sides. Named sites (FDNY's training
campuses; Rikers and Hart Island for DOC work that names no jail) resolve to their FacDB rows the
same way. pipeline/locations.py applies these as Tier B, only to projects whose client agencies
include the unit's agency.
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
# DSNY district garages. Titles: 'Bronx 6/6A', 'QUEENS 8/10/12', 'DSNY BK17 18', 'Queens West 9';
# FacDB: 'BX06A GARAGE', 'BKS14G GARAGE', 'SI01G/SI03G GARAGE' (G = garage, A = annex).
DSNY_BOROS = {"BX": r"BRONX|BRX|BX", "BK": r"BROOKLYN|BKLYN|BRKYN|BK", "MN": r"MANHATTAN|MANH|MAN|MN",
              "QN": r"QUEENS|QNS|QN", "SI": r"STATEN\s+ISLAND|S\.?\s?I\.?"}
DIST = r"\d{1,2}(?!\d)(?:\s?A\b)?"
DISTRICTS = re.compile(r"\b(?:" + "|".join(f"(?P<{k}>{v})" for k, v in DSNY_BOROS.items()) + r")\s*"
                       rf"(?:(?:NORTH|SOUTH|EAST|WEST)\s+)?(?P<d>{DIST}(?:\s*(?:/|&|,|AND|\s)\s*{DIST})*)"
                       r"(?!\s*SEC)")  # 'Bronx 3 Sec 31' is a section station, not the district garage
GARAGE_CODE = re.compile(r"\b(BX|BK|MN|Q|SI)[NSEW]?(\d\d)([GA])\b")
JAILS = re.compile(r"\b(AMKC|RMSC|RNDC|NIC|GRVC|OBCC|EMTC|WF|BHPW|EHPW|VCBC)\b")  # VCBC: the barge, not in FacDB
AGENCY = {"PRECINCT": "NYPD", "DSNY": "DSNY", "JAIL": "DOC"}  # unit kind -> agency; FDNY otherwise
FACTYPES = ("FIREHOUSE", "AMBULANCE STATION", "EMERGENCY MEDICL STN", "EMERGENCY MEDICAL STATION",
            "PUBLIC SAFETY FACILITY")
SITES = {  # title pattern -> (agency, FacDB name)
    r"\bF(?:OR)?T\.? TOTTEN\b": ("FDNY", "FORT TOTTEN (US ARMY)"),
    r"\bRANDALL'?S\b": ("FDNY", "FIRE DEPT.FIRE TRAINING ACAD"),
    # island-wide DOC work: the Rikers powerhouse, cogeneration plant and steam tunnels serve every jail
    r"\bRIKERS\b|\bRI\b|\bPOWER ?HOUSE\b|\bCOGEN|\bSTEAM (?:TUNNEL|LINE)": ("DOC", "RIKERS ISLAND"),
    r"\bHART'?S? ISLAND\b": ("DOC", "HART ISLAND"),
}
SITE_AGENCY = {name: agency for agency, name in SITES.values()}
CONTAINERS = {"RIKERS ISLAND"}  # sites that contain other units; a named jail is more precise
SAME_SITE_M = 150  # FacDB rows for one unit closer than this are the same building


def parse_units(text: str) -> set[tuple]:
    """'BUILDING AUTOMATION CONTROLS AT EC276' -> {('ENGINE', 276)}; 'FT TOTTEN BUILDING 420' ->
    {('SITE', 'FORT TOTTEN (US ARMY)')}."""
    t = text.upper()
    units = {(next(k for k in KINDS if m.group(k)), int(m.group("n"))) for m in UNIT.finditer(t)}
    for m in PRECINCTS.finditer(t):
        units |= {("PRECINCT", int(n)) for n in re.findall(r"\d+", m.group(1) or m.group(2))}
    # salt sheds often stand apart from the district garage ('BRONX 8 Van Cortlandt Park Salt Shed Tent')
    for m in ([] if re.search(r"\bSALT\b", t) else DISTRICTS.finditer(t)):
        boro = next(k for k in DSNY_BOROS if m.group(k))
        units |= {("DSNY", f"{boro}{int(n):02d}{a}") for n, a in re.findall(r"(\d+)(?:\s?(A)\b)?", m.group("d"))}
    for boro, n, suffix in GARAGE_CODE.findall(t):
        units.add(("DSNY", f"{'QN' if boro == 'Q' else boro}{n}{'A' if suffix == 'A' else ''}"))
    units |= {("JAIL", code) for code in JAILS.findall(t)}
    return units | {("SITE", name) for pattern, (_, name) in SITES.items() if re.search(pattern, t)}


def agency_of(unit: tuple) -> str:
    if unit[0] == "SITE":
        return SITE_AGENCY[unit[1]]
    return AGENCY.get(unit[0], "FDNY")


def build_index(con) -> tuple[dict, list]:
    """unit -> (facility name, borough, lon, lat), plus units whose FacDB rows disagree on location.
    Each row contributes only its operator's units ('ENG 46, LAD 27, 48 PRECINCT' is an NYPD row)."""
    rows = con.execute(f"""select name, borough, lon, lat, operator from ref_facilities
        where (operator = 'FDNY' and factype in {FACTYPES}) or name in {tuple(SITE_AGENCY)}
           or (operator = 'NYPD' and factype = 'POLICE STATION'
               and not regexp_matches(name, '^(FUTURE|FORMER|OLD) '))
           or (operator = 'NYCDSNY' and factype = 'DSNY GARAGE')
           or (operator = 'NYCDOC' and factype = 'CORRECTIONAL FACILITY')""").fetchall()
    sites: dict[tuple, list] = {}
    for name, boro, lon, lat, operator in rows:
        if name in SITE_AGENCY:
            sites.setdefault(("SITE", name), []).append((name, boro, lon, lat))
            continue
        for u in parse_units(name):
            if agency_of(u) == (operator or "").removeprefix("NYC"):
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
    units = sorted(u for u in parse_units(title) if agency_of(u) in clients)
    if any(u[0] != "SITE" or u[1] not in CONTAINERS for u in units):
        units = [u for u in units if u[0] != "SITE" or u[1] not in CONTAINERS]
    if not units or any(u not in index for u in units):
        return None
    hits = [index[u] for u in units]
    if any(haversine_m(hits[0][3], hits[0][2], h[3], h[2]) > SAME_SITE_M for h in hits[1:]):
        return None
    site = hits[0]
    if boro in ("Manhattan", "Bronx", "Brooklyn", "Queens", "Staten Island") and site[1] != boro:
        return None
    return agency_of(units[0]), site
