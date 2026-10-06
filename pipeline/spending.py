"""What kind of spending each city and SCA project is (physical work or overhead), how it is delivered, and whether it
is money set aside: project_spending, with the MTA's classification (pipeline/mta_spending.py) carried in.

The rules follow docs/future-plans.md ("One spending classification across sources"): a cost of one named project or
place is its physical work; overhead is agency-wide administration, enterprise IT, studies not about a particular
place, and scope development for projects not yet defined; a reserve takes the kind of what it is for, with
reserve_flag set, and agency-wide money not yet tied to defined work is drafted as overhead for review.

- City: current projects in the phase group 'Not a discrete project' (their raw phase says how the work is delivered:
  funding agreement, lump sum, holding code, job order or requirements contract, pass-through fund, equipment, IT),
  and current projects whose title matches CITY_SCREEN. One row each in city_spending.csv.
- SCA: projects of the types or descriptions in SCA_SCREEN (leases, environmental hygiene testing, furniture and
  equipment). One row each in sca_spending.csv.
Unscreened current projects are physical work. Rows start as draft; a basis beginning 'review:' marks a judgement
call the rules leave open. delivery is in_house, funding_agreement, pass_through, job_order_contract,
requirements_contract or empty (an ordinary contract).

    .venv/bin/python pipeline/spending.py --draft   # append draft rows for screened projects not yet listed
    .venv/bin/python pipeline/spending.py           # write project_spending
"""
import argparse
import csv
import re
import sys
from pathlib import Path

import duckdb

import phase_groups
from db import DB_PATH, replace_table

HERE = Path(__file__).parent
CITY_CSV = HERE / "city_spending.csv"
SCA_CSV = HERE / "sca_spending.csv"
KINDS = {"physical", "overhead"}
FIELDS = ["kind", "reserve_flag", "delivery", "basis", "status", "evidence"]
CITY_SCREEN = re.compile(r"(?-i:\bIT\b)|data cent(er|re)|mainframe|software|wi-?fi|network infrastructure|cabling|"
                         r"holding code|outyear|\bstud(y|ies)\b(?! institute)|feasibility|consultant services|"
                         r"swing space|"
                         r"insurance|program management|contingenc|allowance|scope development", re.I)
SCA_SCREEN = {"types": ("SCA IEH", "SCA Furniture & Equipment"), "description": r"^LEASE$"}
DELIVERY = {"fundingagreement": "funding_agreement", "passthroughfund": "pass_through",
            "jobordercontract": "job_order_contract", "requirementscontract": "requirements_contract"}
IT = (r"(?-i:\bIT\b)|mainframe|software|wi-?fi|network infrastructure|cabling|cmms|order app|licenses|"
      r"implem[e]?ntation - space management")
STUDY = r"\bstud(y|ies)\b(?! institute)|feasibility"


def city_draft(title: str, phase: str | None) -> tuple[str, str, str, str]:
    """(kind, reserve flag, delivery, basis) for a screened city project."""
    t = title or ""
    key = phase_groups.key(phase)
    delivery = "in_house" if re.search(r"in-house|crews", t, re.I) else DELIVERY.get(key, "")
    if key == "itproject" or re.search(IT, t, re.I):
        return "overhead", "", delivery, "rule: enterprise IT"
    if re.search(r"data cent(er|re)", t, re.I):
        return "overhead", "", delivery, "review: a data centre; enterprise IT unless part of a building's own work"
    if re.search(r"holding code|outyear", t, re.I):
        return ("overhead", "yes", delivery, "review: money set aside; overhead unless it is for defined work "
                "(a reserve takes the kind of what it is for)")
    if re.search(STUDY, t, re.I):
        return "overhead", "", delivery, "review: a study; physical instead if it concerns work at a particular place"
    if re.search(r"swing space", t, re.I):
        return "overhead", "", delivery, "review: office space for an agency, not work at a project's place"
    if re.search(r"consultant services", t, re.I):
        return "physical", "", delivery, "rule: consultant services for a named place are that place's project cost"
    if key in ("capitallyineligible", "expense"):
        return "physical", "", delivery, f"review: the city lists it as '{phase}'"
    if re.search(r"lump sum - asset management", t, re.I):
        return "physical", "", delivery, "review: an agency's asset management lump sum; physical if it funds work"
    return "physical", "", delivery, f"rule: physical work, listed as {phase}" if key in DELIVERY or \
        key in ("lumpsum", "equipment", "holdingcode") else "rule: physical work"


def sca_draft(types: str, description: str) -> tuple[str, str, str, str]:
    if re.search(SCA_SCREEN["description"], description or ""):
        return ("physical", "", "", "review: a lease for one school; physical under the project-specific real "
                "estate rule")
    if "SCA IEH" in types:
        return "physical", "", "", "review: environmental hygiene testing at one school (work at a particular place)"
    return "physical", "", "", "review: furniture and equipment for one school"


def load(path: Path, key: str) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open() as f:
        return {r[key]: r for r in csv.DictReader(f)}


def city_projects(con) -> list[tuple]:
    """Current city projects: (fms_id, title, agency project name, raw phase, budget line, period, budget)."""
    return con.execute("""with last as (select max(reporting_period) p from project_budget_schedule)
        select fms_id, arg_max(fms_project_name, total_budget), arg_max(agency_project_name, total_budget),
               arg_max(current_phase, total_budget), arg_max(budget_line, total_budget), any_value(reporting_period)
        from project_budget_schedule where reporting_period = (select p from last) group by 1 order by 1""").fetchall()


def city_screened(con) -> list[tuple]:
    groups = phase_groups.load()
    return [r for r in city_projects(con)
            if phase_groups.group(r[3], groups) == "Not a discrete project" or CITY_SCREEN.search(r[1] or "")]


def sca_projects(con) -> list[tuple]:
    as_of = con.execute("select max(as_of) from sca_history").fetchone()[0]
    return [(*r, as_of) for r in con.execute("""select project_key, project_types, description, building, school_name
        from sca_projects order by 1""").fetchall()]


def sca_screened(con) -> list[tuple]:
    return [r for r in sca_projects(con) if any(t in (r[1] or "") for t in SCA_SCREEN["types"])
            or re.search(SCA_SCREEN["description"], r[2] or "")]


def city_evidence(fms, title, aname, phase, line, period) -> str:
    name = f" / '{aname}'" if aname and aname != title else ""
    return f"fb86-vt7u report {period}, phase '{phase or ''}', budget line '{line or ''}': '{title}'{name}"


def sca_evidence(key, types, desc, building, school, as_of) -> str:
    return f"2xh6-psuq version {as_of}, {key}: {types}: '{desc}' at {building} ({school})"


def write(path: Path, key: str, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[key, *FIELDS], lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r[key]))


def draft_missing(con) -> None:
    city = load(CITY_CSV, "fms_id")
    new = [dict(zip(["fms_id", *FIELDS], (f, *city_draft(t, ph), "draft", city_evidence(f, t, a, ph, bl, p)),
                    strict=True)) for f, t, a, ph, bl, p in city_screened(con) if f not in city]
    if new:
        write(CITY_CSV, "fms_id", list(city.values()) + new)
    sca = load(SCA_CSV, "project_key")
    new_sca = [dict(zip(["project_key", *FIELDS], (k, *sca_draft(ty, d), "draft", sca_evidence(k, ty, d, b, s, v)),
                        strict=True)) for k, ty, d, b, s, v in sca_screened(con) if k not in sca]
    if new_sca:
        write(SCA_CSV, "project_key", list(sca.values()) + new_sca)
    print(f"appended {len(new)} city and {len(new_sca)} SCA draft rows")


def rows(con) -> list[tuple]:
    out = []
    for program, listed, projects in (("nyc_capital", load(CITY_CSV, "fms_id"), city_projects(con)),
                                      ("sca", load(SCA_CSV, "project_key"), sca_projects(con))):
        for key, *_ in projects:
            r = listed.get(key)
            out.append((program, key, *((r["kind"], r["reserve_flag"] == "yes", r["delivery"] or None,
                                         f"{r['status']}: {r['basis']}") if r else
                                        ("physical", False, None, "not screened: physical work"))))
    for acep, kind, reserve, basis in con.execute("""select acep, spending_kind, mta_calls_reserve, spending_basis
            from mta_projects where spending_kind is not null""").fetchall():
        out.append(("mta", acep, kind, reserve, None, basis))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", action="store_true", help="append draft rows for screened projects not yet listed")
    args = ap.parse_args()
    con = duckdb.connect(str(DB_PATH))
    if args.draft:
        draft_missing(con)
    replace_table(con, "project_spending", "program varchar, project_id varchar, kind varchar, reserve_flag boolean, "
                  "delivery varchar, basis varchar", rows(con))
    print(con.execute("""select program, kind, reserve_flag, count(*) from project_spending
                         group by all order by all""").fetchall())
    return 0


if __name__ == "__main__":
    sys.exit(main())
