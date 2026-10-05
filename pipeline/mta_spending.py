"""What kind of spending each MTA ACEP is: physical work, a reserve, or overhead.

Much of an MTA capital plan is not work at a place: insurance (OCIP, protective liability), program administration,
independent engineers, consultants and program management, real estate, enterprise IT; and money not yet tied to
defined work (project and risk reserves, contingency, allowances, scope development and design for projects not yet
defined). Studies are overhead unless they concern work at a particular place, which makes them project development
of that work and so physical (reviewed per row). MTA also calls defined physical programs 'reserves' ('Purchase 1,140
New A-Division Cars' is "a reserve that will fund the purchase"); those are physical work not yet awarded and stay
physical, with the basis 'program reserve'. Soft costs, insurance, real estate and reserves that belong to one named
project (a mega project, or a title naming SAS, ESA, Penn Station Access, IBX or the LIRR Expansion) are that
project's cost and count as its physical work; only agency-wide ones are overhead or reserves.

`mta_spending.csv` holds one reviewed row per screened live ACEP: every ACEP with the `dollar` location indicator
(budget lines with no location), and every other ACEP whose title or scope matches SCREEN. Its `basis` says which rule
or review placed it and `evidence` quotes the ACEP's own record. Rows start as `draft` and become `reviewed` once
checked. Unscreened ACEPs are physical work. A data check fails when a screened live ACEP has no row.

    .venv/bin/python pipeline/mta_spending.py --draft   # append draft rows for screened live ACEPs not yet listed
"""
import argparse
import csv
import re
import sys
from pathlib import Path

import duckdb

from db import DB_PATH

CSV = Path(__file__).with_name("mta_spending.csv")
FIELDS = ["acep", "kind", "basis", "status", "evidence"]
KINDS = {"physical", "reserve", "overhead"}
SCREEN = (r"reserve|insurance|administration|independent engineer|program management|"
          r"general engineering consultant|\bgec\b|scope development|allowance|contingenc|integrity monitor|"
          r"real estate|enterprise asset|force account|support|construction management|engineering services|"
          r"\bstud(y|ies)\b|conceptual planning|^miscellaneous$|data management|sbdp|design/cps")
OVERHEAD_TITLE = [
    r"insurance", r"\bocip\b", r"owner controlled", r"protective liability", r"administration", r"independent engineer",
    r"integrity monitor", r"business development program", r"small business development",
    r"mentoring program administration", r"settlement", r"program control", r"construction management services",
    r"general engineering consultant", r"\bgec\b", r"project support", r"force account support",
    r"construction support", r"traffic checkers", r"traffic enforcement", r"operational readiness", r"real estate",
    r"enterprise asset management",
    r"\beam\b", r"information systems upgrades", r"upgrade information systems", r"data centers", r"program management",
    r"other regional investments support", r"amtrak access and protection", r"general order support", r"support costs",
    r"c&d project support", r"engineering and program support", r"project engineering & program administration",
    r"construction management", r"^engineering services$", r"c&d engineering",
    r"sbdp (business development|administration)", r"design/cps"]
OVERHEAD_SCOPE = [r"insurance", r"\bocip\b", r"protective liability", r"independent engineer",
                  r"general engineering consultant", r"\bgec\b", r"reserve for future support costs",
                  r"reserve for administrative needs"]
STUDY = [r"\bstud(y|ies)\b", r"feasibility", r"alternatives analysis", r"conceptual planning"]
RESERVE = [
    r"project reserve", r"is the project reserve", r"contingenc", r"scope development", r"program development",
    r"design reserve", r"reserve for preliminary designs", r"sets aside funds", r"undefined", r"for future projects",
    r"allowance", r"reserve for local match", r"project development", r"^miscellaneous$",
    r"miscellaneous design and administrative", r"provided design funding for various", r"funded the design of various"]


PROJECTS = [(r"^(sas|second ave)|sas ph|sas 2|125th street subway", "Second Avenue Subway Phase II"),
            (r"^esa|east side access|regional investment", "East Side Access"),
            (r"^psa|penn station access|penn access", "Penn Station Access"),
            (r"\bibx\b|interborough express", "Interborough Express"),
            (r"lirr expansion", "LIRR Expansion Project")]


def project_of(title: str, mega_project: str | None) -> str | None:
    """The one named project an ACEP's cost belongs to, if any."""
    return mega_project or next((n for p, n in PROJECTS if re.search(p, title.lower())), None)


def draft(title: str, scope: str, mega_project: str | None = None) -> tuple[str, str]:
    """(kind, basis): the rules below, then an overhead or reserve of one named project counted as its physical
    work."""
    kind, basis = draft_kind(title, scope)
    project = project_of(title, mega_project)
    if kind != "physical" and project:
        return "physical", f"rule: project-specific cost of {project} ({kind}: {basis.removeprefix('rule: ')})"
    return kind, basis


def draft_kind(title: str, scope: str) -> tuple[str, str]:
    """(kind, basis) by rule: the title first, then the scope text."""
    t, text = title.lower(), f"{title} {scope}".lower()
    for p in OVERHEAD_TITLE:
        if re.search(p, t):
            return "overhead", f"rule: title matches '{p}'"
    for p in RESERVE:
        if re.search(p, t):
            return "reserve", f"rule: title matches '{p}'"
    for p in OVERHEAD_SCOPE:
        if re.search(p, text):
            return "overhead", f"rule: scope matches '{p}'"
    for p in STUDY:
        if re.search(p, text):
            return "overhead", f"rule: a study ('{p}'); physical instead if it concerns work at a particular place"
    for p in RESERVE:
        if re.search(p, text):
            return "reserve", f"rule: scope matches '{p}'"
    if re.search(r"revolving fund", t):
        return "physical", "small-scale construction work or equipment purchases (capital revolving fund)"
    if re.search(r"retroactive wage", t):
        return "overhead", "retroactive wage adjustment"
    if re.search(r"small business mentoring", text):
        return "physical", "construction contracts through the Small Business Mentoring Program"
    if re.search(r"is a reserve|\breserve\b", text):
        return "physical", "program reserve: defined physical work not yet awarded"
    return "physical", "physical work"


def load(path: Path = CSV) -> dict[str, dict]:
    with path.open() as f:
        return {r["acep"]: r for r in csv.DictReader(f)}


def screened(con) -> list[tuple]:
    """Live ACEPs that need a reviewed row: (acep, indicator, title, scope, last load, mega project)."""
    return con.execute(f"""select acep, location_indicator, description, coalesce(scope, ''), last_load, mega_project
        from mta_projects where status = 'live' and (location_indicator = 'dollar'
        or regexp_matches(lower(description || ' ' || coalesce(scope, '')), '{SCREEN}')) order by acep""").fetchall()


def evidence(acep: str, indicator: str | None, title: str, scope: str, load_date) -> str:
    return (f"ehz8-ag3n load {load_date}, location indicator '{indicator or ''}': '{title}': "
            f"{' '.join(scope.split())[:240]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", action="store_true", help="append draft rows for screened live ACEPs not yet listed")
    args = ap.parse_args()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    listed = load() if CSV.exists() else {}
    missing = [r for r in screened(con) if r[0] not in listed]
    print(f"{len(listed)} rows in {CSV.name}; {len(missing)} screened live ACEPs without one")
    if args.draft and missing:
        rows = list(listed.values()) + [
            dict(zip(FIELDS, (a, *draft(t, s, m), "draft", evidence(a, i, t, s, ld)), strict=True))
            for a, i, t, s, ld, m in missing]
        with CSV.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
            w.writeheader()
            w.writerows(sorted(rows, key=lambda r: r["acep"]))
        print(f"appended {len(missing)} draft rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
