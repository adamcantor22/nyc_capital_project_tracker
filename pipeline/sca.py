"""School Construction Authority (SCA) capital projects: phase rows, projects and money.

SCA builds public schools under its own capital plan, outside the city's capital project data. Its
'Capital Project Schedules and Budgets' (2xh6-psuq) has one row per phase of a project. This step writes:
  - `sca_phases`: every published row, with parsed dates and the amount counted;
  - `sca_projects`: one row per project, keyed by its DSF number(s) and building code.

Money: a phase's cost is its 'final estimate of actual costs' (the budget field is 0 on most rows). Rows are
additive: equal amounts at different schools are separate projects (Reso A grants are round sums per school)
and are never merged. The one exception is a program-level figure copied onto many schools' rows
(`sca_repeats.csv`, decision `program_figure`): such a row counts the school's own spending instead, and
the figure is kept apart in `program_figure`, out of every total. A data check fails on any new repeated
amount that is not in that list.

Run after pipeline/fetch_sca.py and pipeline/ingest.py.
"""
import csv
import datetime
import json
import sys
from collections import defaultdict
from pathlib import Path

import duckdb

from db import DB_PATH, RAW_DIR, replace_table

REPEATS = Path(__file__).with_name("sca_repeats.csv")
REPEAT_MIN = 10_000_000  # a repeated amount at least this large on 3+ buildings must be reviewed
PHASE_ORDER = ["Scope", "Design", "Construction", "CM", "CM,F&E", "CM,Art,F&E", "F&E", "Purch & Install"]
STATUS = {"Complete": "complete", "In-Progress": "in_progress", "PNS": "not_started"}  # PNS: phase not started


def parse_day(s: str | None) -> str | None:
    """'9/12/2003' -> '2003-09-12'. The date fields also hold placeholders ('PNS', 'FTK', 'DIIT'): None."""
    try:
        return datetime.datetime.strptime((s or "").strip(), "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None


def money(s: str | None) -> float | None:
    try:
        return float(s) if s not in (None, "") else None
    except ValueError:
        return None


def dsf_numbers(s: str | None) -> list[str]:
    """'DSF0001008800, DSF0000991942' -> both, sorted; 'NULL' or blank -> []."""
    return sorted({p.strip() for p in (s or "").split(",") if p.strip() and p.strip().upper() != "NULL"})


def project_key(dsfs: list[str], building: str, project_type: str, description: str) -> str:
    """A project is its DSF number(s) at one building. Rows without a DSF are keyed by what they are."""
    return f"{','.join(dsfs)}|{building}" if dsfs else f"NODSF|{building}|{project_type}|{description}"


def load_repeats(path: Path = REPEATS) -> dict[tuple, str]:
    with path.open() as f:
        return {(r["project_type"], r["description"], r["phase"], float(r["amount"])): r["decision"]
                for r in csv.DictReader(f)}


def project_status(statuses: list[str]) -> str:
    if all(s == "complete" for s in statuses):
        return "complete"
    if all(s == "not_started" for s in statuses):
        return "not_started"
    return "active"


def current_phase(phases: list[tuple[str, str, str | None]]) -> str | None:
    """(phase, status, start) rows -> the phase under way (latest started; on a tie the main phase, as
    construction management runs alongside construction), else the first not started."""
    going = [p for p in phases if p[1] == "in_progress"]
    if going:
        return max(going, key=lambda p: (p[2] or "", -(PHASE_ORDER.index(p[0]) if p[0] in PHASE_ORDER else 99)))[0]
    waiting = [p for p in phases if p[1] == "not_started"]
    if waiting:
        return min(waiting, key=lambda p: PHASE_ORDER.index(p[0]) if p[0] in PHASE_ORDER else 99)[0]
    return None


def main() -> int:
    rows = json.loads((RAW_DIR / "2xh6-psuq.json").read_text())
    repeats = load_repeats()
    phases = []
    for i, r in enumerate(rows):
        typ, desc, phase = r.get("project_type_") or "", r.get("project_description") or "", r.get("project_phase_name")
        bldg = (r.get("project_building_identifier") or "").strip()
        dsfs = dsf_numbers(r.get("dsf_number_s_"))
        est, spent = money(r.get("final_estimate_of_actual_costs_through_end_of_phase_amount")), money(
            r.get("total_phase_actual_spending_amount"))
        program = repeats.get((typ, desc, phase, est)) == "program_figure"
        phases.append((
            i, project_key(dsfs, bldg, typ, desc), ",".join(dsfs), bldg, r.get("project_school_name"),
            r.get("project_geographic_district_"), typ, desc, phase,
            STATUS.get(r.get("project_status_name"), "unknown"),
            parse_day(r.get("project_phase_actual_start_date")), parse_day(r.get("project_phase_planned_end_date")),
            parse_day(r.get("project_phase_actual_end_date")), money(r.get("project_budget_amount")), est, spent,
            (spent or 0.0) if program else (est or 0.0), est if program else None,
        ))

    by_project = defaultdict(list)
    for p in phases:
        by_project[p[1]].append(p)
    projects = []
    for key, ps in by_project.items():
        statuses = [p[9] for p in ps]
        status = project_status(statuses)
        starts = [p[10] for p in ps if p[10]]
        open_ends = [p[11] for p in ps if p[9] != "complete" and p[11]]
        done_ends = [p[12] for p in ps if p[12]]
        figures = sorted({p[17] for p in ps if p[17] is not None})
        projects.append((
            key, ps[0][2], ps[0][3], ps[0][4], ps[0][5],
            " / ".join(sorted({p[6] for p in ps})), " / ".join(sorted({p[7] for p in ps})),
            len({(p[6], p[7]) for p in ps}), len(ps), status,
            current_phase([(p[8], p[9], p[10]) for p in ps]) if status != "complete" else None,
            min(starts) if starts else None, max(open_ends) if open_ends else None,
            max(done_ends) if status == "complete" and done_ends else None,
            sum(p[16] for p in ps), sum(p[15] or 0.0 for p in ps), sum(figures) if figures else None,
        ))

    con = duckdb.connect(str(DB_PATH))
    replace_table(con, "sca_phases",
                  "row_no integer, project_key varchar, dsf varchar, building varchar, school_name varchar, "
                  "school_district varchar, project_type varchar, description varchar, phase varchar, "
                  "status varchar, start_date date, planned_end date, actual_end date, budget double, "
                  "estimate double, spent double, counted double, program_figure double", phases)
    replace_table(con, "sca_projects",
                  "project_key varchar, dsf varchar, building varchar, school_name varchar, school_district varchar, "
                  "project_types varchar, description varchar, n_components integer, n_phases integer, "
                  "status varchar, current_phase varchar, start_date date, forecast_end date, finished date, "
                  "cost double, spent double, program_figure double", projects)
    raw = sum(p[14] or 0.0 for p in phases)
    counted = sum(p[16] for p in phases)
    print(f"sca: {len(phases):,} phase rows -> {len(projects):,} projects; estimates as published ${raw / 1e9:.2f}B, "
          f"counted ${counted / 1e9:.2f}B; {sum(1 for p in phases if p[17] is not None)} rows carry a program figure")
    print(con.execute("select status, count(*), round(sum(cost) / 1e9, 2) from sca_projects group by 1 order by 1")
          .fetchall())
    return 0


if __name__ == "__main__":
    sys.exit(main())
