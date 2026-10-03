"""Numbered units in project titles, resolved to DCP Facilities Database rows.

FDNY titles name the unit housed in a firehouse ('EC287', 'Engine Company 287', 'SQ288',
'Marine 9', 'EMS Station 58'); FacDB names firehouses by the units they house
('BATTALION 46/ENGINE 287/LADDER 136'). Unit numbers are unique citywide, so a title's units
identify one building even when the project's borough is 'Citywide'. The same pattern parses both
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
FACTYPES = ("FIREHOUSE", "AMBULANCE STATION", "EMERGENCY MEDICL STN", "EMERGENCY MEDICAL STATION",
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
    return units | {("CAMPUS", name) for pattern, name in CAMPUSES.items() if re.search(pattern, t)}


def build_index(con) -> tuple[dict, list]:
    """unit -> (facility name, borough, lon, lat), plus units whose FacDB rows disagree on location."""
    rows = con.execute(f"""select name, borough, lon, lat from ref_facilities
        where operator = 'FDNY' and (factype in {FACTYPES} or name in {tuple(CAMPUSES.values())})""").fetchall()
    sites: dict[tuple, list] = {}
    for name, boro, lon, lat in rows:
        if name in CAMPUSES.values():
            sites.setdefault(("CAMPUS", name), []).append((name, boro, lon, lat))
            continue
        for u in parse_units(name):
            sites.setdefault(u, []).append((name, boro, lon, lat))
    index, conflicts = {}, []
    for u, ss in sites.items():
        if all(haversine_m(ss[0][3], ss[0][2], s[3], s[2]) <= SAME_SITE_M for s in ss[1:]):
            index[u] = ss[0]
        else:
            conflicts.append((u, [s[0] for s in ss]))
    return index, conflicts


def locate(title: str, boro: str | None, clients: frozenset[str], index: dict):
    """The one firehouse a project's units point to, or None (no units, units at several buildings,
    or a building outside the project's stated borough)."""
    if "FDNY" not in clients:
        return None
    hits = [index[u] for u in parse_units(title) if u in index]
    if not hits or any(haversine_m(hits[0][3], hits[0][2], h[3], h[2]) > SAME_SITE_M for h in hits[1:]):
        return None
    site = hits[0]
    if boro in ("Manhattan", "Bronx", "Brooklyn", "Queens", "Staten Island") and site[1] != boro:
        return None
    return site
