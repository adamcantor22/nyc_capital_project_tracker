"""When each project finished, or left the listings unfinished, from every report held -> project_finishes.

One row per project of every program that finished or is no longer listed, read from the changes between reports
rather than from any one report, since the programs drop finished work unevenly (the city after Close-out or
(Completed), SCA after a year or so, MTA keeps it for years). A report holds a project as finished when:

  city  every PID of the FMS ID has an actual construction end on or before the report's month, or the phase
        (Completed). Close-out counts, since construction has ended and most Close-out projects are dropped without
        ever showing (Completed). Date: the latest PID's construction end (day).
  SCA   status complete. Date: SCA's finished date (day).
  MTA   phase Complete. Date: current completion (month, or year where MTA publishes only a year).

`outcome` is `finished` when the project's last listing holds it as finished (a finish followed by an unfinished
last listing is not one: MTA reopens some ACEPs); `first_reported` is the first report that held it as finished, and
the date comes from the latest report (later reports correct earlier ones). `reopened` marks a finish with an
unfinished report between its first finished report and its last listing: 296 of 305 such city projects when set
have no PID, whose phase alternates between (Completed) and (Pending). A report publishing every record without a
PID as (Pending) (PIDLESS_MIN or more such records; 202505: 2,495 of 2,495) is read as not publishing their phase:
each takes its phase in the previous report, and the report is listed in finish_issues. A finish with no usable date
keeps only its report (`basis` `reported_completed`, `mta_complete_undated`). `superseded` (MTA) is money passed to
other ACEPs, not a finish; `first_reported` starts its final Superseded run. `left_unfinished` is a project no
longer listed whose last listing was unfinished (SCA: under neither its key nor another key of its lineage);
`last_phase` says where it stood. Still-listed unfinished projects have no row.

`before_records` marks finishes held in the program's first report (city 2023-05, SCA 2015-10, MTA
2020-03): they finished before the records begin, whatever their date. Each row names its source dataset and rule.
OMB's Capital Project Detail Data (2019-2023) is not used: its construction dates, once passed, are seldom updated,
and agree with the actual construction end within 3 months for 18% of the projects both date.

Dates after their own report (city: after the report's month; MTA: a completion month or year after the load) or
before 1990 are not used and are listed in finish_issues (and data_issues).
"""
import calendar
import datetime
import sys
from collections import defaultdict

import duckdb

import phase_groups
import schedules
from db import DB_PATH, replace_table

FIRST_YEAR = 1990
PIDLESS_MIN = 1000
RULES = {
    "nyc_capital": "every PID has an actual construction end by the report's month, or phase (Completed), in the last "
                   "listing; date: the latest construction end",
    "sca": "status complete in the last listing; date: SCA's finished date",
    "mta": "phase Complete in the last listing; date: current completion (month, or year where only a year is "
           "published)",
}
SOURCES = {"nyc_capital": "fb86-vt7u", "sca": "2xh6-psuq", "mta": "ehz8-ag3n"}
NOT_USED = "date not used as the finish date"
DATED = {"nyc_capital": ("construction_end", "reported_completed"), "sca": ("sca_finished", "sca_finished_undated"),
         "mta": ("mta_complete", "mta_complete_undated")}


def month_end(period: int) -> datetime.date:
    y, m = divmod(period, 100)
    return datetime.date(y, m, calendar.monthrange(y, m)[1])


def pidless_unpublished(con) -> list[tuple]:
    """(period, rows) of reports publishing every record without a PID as (Pending)."""
    return con.execute("""select reporting_period, count(*) from project_budget_schedule where pid is null
                          group by 1 having count(*) >= ? and bool_and(current_phase = '(Pending)') order by 1""",
                       [PIDLESS_MIN]).fetchall()


def run_start(held: list[dict], holds) -> int:
    """Index of the first report of the final run of reports for which `holds` is true."""
    i = len(held)
    while i and holds(held[i - 1]):
        i -= 1
    return i


def outcome(program: str, pid: str, held: list[dict], first, last, still_listed: bool = False) -> dict | None:
    """One project's row from its reports in order, each {report, done, date, precision, phase, budget}."""
    end = held[-1]
    row = dict(program=program, project_id=pid, last_listed=str(end["report"]), last_phase=end["phase"],
               budget=next((h["budget"] for h in reversed(held) if h["budget"]), 0), source=SOURCES[program],
               finish_date=None, finish_precision=None, first_reported=None, before_records=False, reopened=False)
    if end["done"]:
        i = next(i for i, h in enumerate(held) if h["done"])
        dated = DATED[program][0 if end["date"] else 1]
        return {**row, "outcome": "finished", "finish_date": end["date"], "finish_precision": end["precision"],
                "basis": dated, "first_reported": str(held[i]["report"]), "before_records": held[i]["report"] == first,
                "reopened": not all(h["done"] for h in held[i:]), "rule": RULES[program]}
    if end["phase"] == "Superseded":
        i = run_start(held, lambda h: h["phase"] == "Superseded")
        return {**row, "outcome": "superseded", "basis": "mta_superseded", "first_reported": str(held[i]["report"]),
                "rule": "phase Superseded in the last listing: money passed to other ACEPs"}
    if end["report"] == last or still_listed:
        return None
    return {**row, "outcome": "left_unfinished", "basis": "not_listed",
            "rule": "listed in no later report, unfinished in its last listing"}


def city_rows(con) -> tuple[list[dict], list[tuple]]:
    groups = phase_groups.load()
    reports = defaultdict(lambda: defaultdict(list))
    budget = defaultdict(lambda: defaultdict(dict))
    blank = pidless_unpublished(con)
    issues = [("nyc_capital", "fb86-vt7u", f"report {p}", str(p), f"{n:,} records without a PID",
               "every record without a PID published as (Pending)",
               "read as unpublished: each takes its phase in the previous report") for p, n in blank]
    blank = {p for p, _ in blank}
    pidless_phase = {}
    for period, fms, agency, pid, phase, end, b in con.execute(
            """select reporting_period, fms_id, managing_agency, pid, any_value(current_phase),
                      max(actual_construction_end)::date, max(total_budget)
               from project_budget_schedule group by 1, 2, 3, 4 order by 1""").fetchall():
        if end is not None and (end > month_end(period) or end.year < FIRST_YEAR):
            issues.append(("nyc_capital", "fb86-vt7u", f"{fms} PID {pid}", str(period), end.isoformat(),
                           "actual construction end " + ("after the report's month" if end.year >= FIRST_YEAR
                                                         else f"before {FIRST_YEAR}"), NOT_USED))
            end = None
        if pid is None:
            if period in blank:
                phase = pidless_phase.get((fms, agency), phase)
            pidless_phase[(fms, agency)] = phase
        reports[fms][period].append((phase_groups.group(phase, groups), phase, end))
        budget[fms][period][agency] = max(budget[fms][period].get(agency, 0), b or 0)
    periods = sorted({p for r in reports.values() for p in r})
    out = []
    for fms, by_period in reports.items():
        held = []
        for p in sorted(by_period):
            pids = by_period[p]
            ends = [end for _, _, end in pids if end]
            held.append({"report": p, "done": all(g == "Done" or end for g, _, end in pids),
                         "date": max(ends) if ends else None, "precision": "day" if ends else None,
                         "phase": "; ".join(sorted({ph or "" for _, ph, _ in pids})),
                         "budget": sum(budget[fms][p].values())})
        if r := outcome("nyc_capital", fms, held, periods[0], periods[-1]):
            out.append(r)
    return out, issues


def sca_rows(con) -> list[dict]:
    held = defaultdict(list)
    lineage_last = {}
    for as_of, key, lineage, status, phase, finished, cost in con.execute(
            """select as_of, project_key, lineage, status, current_phase, finished, cost from sca_history
               order by as_of""").fetchall():
        held[key].append({"report": as_of, "done": status == "complete", "date": finished,
                          "precision": "day" if finished else None, "phase": phase, "budget": cost or 0,
                          "lineage": lineage})
        lineage_last[lineage] = as_of
    versions = sorted(lineage_last.values())
    first = min(h[0]["report"] for h in held.values())
    return [r for key, h in held.items()
            if (r := outcome("sca", key, h, first, versions[-1],
                             still_listed=lineage_last[h[-1]["lineage"]] > h[-1]["report"]))]


def mta_rows(con) -> tuple[list[dict], list[tuple]]:
    held = defaultdict(list)
    issues = []
    for load, acep, phase, completion, budget in con.execute(
            """select loaddate, acep, phase, current_completion, current_budget from mta_history
               order by loaddate""").fetchall():
        date, precision = schedules.partial(completion) or (None, None)
        if date and phase == "Complete" and (date.year > load.year if precision == "year" else
                                             (date.year, date.month) > (load.year, load.month)):
            issues.append(("mta", "ehz8-ag3n", acep, load.isoformat(), completion,
                           "phase Complete with a completion after the load", NOT_USED))
            date = precision = None
        held[acep].append({"report": load, "done": phase == "Complete", "date": date, "precision": precision,
                           "phase": phase, "budget": budget})
    loads = sorted({h["report"] for hs in held.values() for h in hs})
    return [r for acep, h in held.items() if (r := outcome("mta", acep, h, loads[0], loads[-1]))], issues


COLUMNS = ["program", "project_id", "outcome", "finish_date", "finish_precision", "basis", "first_reported",
           "last_listed", "last_phase", "budget", "before_records", "reopened", "source", "rule"]
DDL = ("program varchar, project_id varchar, outcome varchar, finish_date date, finish_precision varchar, "
       "basis varchar, first_reported varchar, last_listed varchar, last_phase varchar, budget double, "
       "before_records boolean, reopened boolean, source varchar, rule varchar")


def main() -> int:
    con = duckdb.connect(str(DB_PATH))
    city, city_issues = city_rows(con)
    mta, mta_issues = mta_rows(con)
    rows = city + sca_rows(con) + mta
    replace_table(con, "project_finishes", DDL,
                  [tuple(schedules.iso(v) if isinstance(v, datetime.date) else v for v in (r[c] for c in COLUMNS))
                   for r in rows])
    replace_table(con, "finish_issues", "program varchar, dataset varchar, record_key varchar, report varchar, "
                  "value varchar, problem varchar, action varchar", city_issues + mta_issues)
    for r in con.execute("""select program, outcome, basis, before_records, count(*), round(sum(budget) / 1e9, 2)
                            from project_finishes group by all order by all""").fetchall():
        print(*r, sep="\t")
    print(con.execute("select program, problem, count(*) from finish_issues group by 1, 2").fetchall())
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
