"""Facility codes embedded in HHC and CUNY FMS IDs.

HHC numbers projects `FFYYYYNN`, where `FF` is the facility (`11` = Bellevue, `48` = Woodhull).
CUNY uses `CCnnn-nnn`, where `CC` is the campus (`QC` = Queens College). Central-program IDs embed
the campus after the program prefix (`CA091KG03`, `SAND-KG03`, `SEED-YC27`).
`pipeline/facility_codes.csv` maps each code to one DCP Facilities Database row (name + factype);
coordinates always come from FacDB.

Codes are listed only when the project titles under them, or their projects' Tier A locations, show
a single site. Network codes (e.g. HHC `12`, Gouverneur + Judson) and program codes (CUNY `CA` with
no campus, HHC `AC`, HHC `02` central office) are left out. pipeline/locations.py applies these as
Tier B, ahead of title name-matching, and only when the facility is in the project's borough.
"""
import csv
import re
from pathlib import Path

TABLE = Path(__file__).with_name("facility_codes.csv")
PATTERNS = {
    "HHC": re.compile(r"^(\d\d)\d{6}$"),
    "CUNY": re.compile(r"^([A-Z]{2})\d{3}-?\d{3}$|^CA\d{3}([A-Z]{2})\d\d$|^(?:SAND|SEED)-([A-Z]{2})\d\d$"),
}


def load_codes() -> dict[tuple[str, str], dict]:
    with TABLE.open() as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["regex"] = re.compile(r["title_pattern"])
    return {(r["agency"], r["code"]): r for r in rows}


def facility_code(agency: str | None, fms_id: str) -> str | None:
    pattern = PATTERNS.get(agency or "")
    m = pattern.match(fms_id) if pattern else None
    return next(g for g in m.groups() if g) if m else None


def resolve(con, codes: dict) -> tuple[dict, list]:
    """(agency, code) -> (facility, borough, lon, lat) from ref_facilities, plus the codes that did not
    resolve to exactly one FacDB row."""
    found, missing = {}, []
    for key, r in codes.items():
        rows = con.execute("select borough, lon, lat from ref_facilities where name = ? and factype = ?",
                           [r["facility"], r["factype"]]).fetchall()
        if len(rows) == 1:
            found[key] = (r["facility"], *rows[0])
        else:
            missing.append((key, len(rows)))
    return found, missing
