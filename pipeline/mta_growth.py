"""MTA allocation change per capital plan (by plan approval) and per mega project (by dashboard load).

An ACEP's own budget is no measure of cost growth: MTA funds programs in reserve ACEPs and moves money to new
ACEPs as contracts are defined (pipeline/mta.py). Change is measured over groups instead. This step writes:
  - `mta_allocations`: one row per ACEP per plan revision as published in MTA's funding plans (6kvv-fcph):
    `allocation` in dollars (published in thousands), approval date, signed change from the ACEP's previous row and
    MTA's change narrative. `plan_revision` counts each ACEP's own revisions (0 is its first row), so revisions of
    different ACEPs with the same number can belong to different approvals; dates group them.
  - `mta_plan_amendments`: one row per (plan, approval date): the plan's total then (each ACEP's latest row on or
    before the date), the signed change since the previous date, split into money on ACEPs first listed at this
    date and changes to ACEPs already listed. A first listing is not always new work: 733 ACEPs of the 2005-09 plan
    (B&T among them) first appear at the latest date. The latest date's totals equal the dashboard's current
    budgets for each plan in its latest load (a data check), so that date may be the current state rather than an
    approval (unverified); those rows say so in `note`.
  - `mta_mega_series`: one row per (mega project, dashboard load): the summed current budget of every ACEP tagged
    with the mega project in any load (ehz8-ag3n), each at its latest current budget on or before the load, so an
    ACEP missing from a load (the 2026-03 load omits the 2005-09 plan) is carried, not counted as a cut. Loads that
    withhold current budgets (mta_loads) are skipped.

Amendments move money between plans (deferrals) and add scope and funding, so these are signed allocation
changes, not cost growth alone. All amounts are nominal dollars.

Run after pipeline/mta.py.
"""
import json
import sys
from collections import defaultdict

import duckdb

from db import DB_PATH, RAW_DIR, replace_table

DATASET = "6kvv-fcph"
DASHBOARD = "ehz8-ag3n"
# plan_id -> the dashboard's capital_plan; every ACEP in both sources agrees (a data check)
PLANS = {"5": "Capital Plan 2005 - 2009", "6": "Capital Plan 2010 - 2014", "7": "Capital Plan 2015 - 2019",
         "8": "Capital Plan 2020 - 2024", "9": "Capital Plan 2025 - 2029"}
AMENDMENT_RULE = "each ACEP's latest 6kvv-fcph row approved on or before the date, summed per plan"
LATEST_NOTE = ("totals equal the dashboard's current budgets in its latest load; may be the current state rather "
               "than a CPRB approval (unverified)")
UNCOMPARED_NOTE = ("the date of the other plans' current-state rows; the dashboard's latest load omits this plan, so "
                   "its total cannot be compared (unverified)")
MEGA_RULE = ("ACEPs tagged with the mega project in any ehz8-ag3n load, each at its latest current budget on or "
             "before the load; loads withholding current_budget skipped")


def narrative(v: str | None) -> str | None:
    v = (v or "").strip()
    return None if v in ("", "nan") else v


def allocations(rows: list[dict]) -> list[tuple]:
    """(capital_plan, acep, revision, approved, allocation, change, narrative, dataset), in date order per ACEP."""
    by_acep = defaultdict(list)
    for r in rows:
        by_acep[r["acep"]].append(r)
    out = []
    for acep, rs in by_acep.items():
        prev = None
        for r in sorted(rs, key=lambda r: (r["date"], int(r["plan_revision"]))):
            amount = float(r["total_allocation"]) * 1000
            out.append((PLANS[r["plan_id"]], acep, int(r["plan_revision"]), r["date"][:10], amount,
                        None if prev is None else amount - prev, narrative(r.get("change_nar")), DATASET))
            prev = amount
    return out


def amendments(allocs: list[tuple]) -> list[tuple]:
    """Per plan and approval date: total, signed change, new and already-listed parts, narratives."""
    by_plan = defaultdict(list)
    for a in allocs:
        by_plan[a[0]].append(a)
    out = []
    for plan, rows in by_plan.items():
        prev_total = None
        for day in sorted({a[3] for a in rows}):
            at = [a for a in rows if a[3] == day]
            latest = {}
            for a in rows:
                if a[3] <= day:
                    latest[a[1]] = a[4]  # rows are in date order per ACEP
            total = sum(latest.values())
            new = [a for a in at if a[5] is None]
            changed = [a for a in at if a[5]]
            out.append((plan, day, len(latest), total, None if prev_total is None else total - prev_total,
                        len(new), sum(a[4] for a in new), len(changed), sum(a[5] for a in changed),
                        sum(1 for a in at if a[6]), AMENDMENT_RULE, DATASET, None))
            prev_total = total
    return out


def mega_series(history: list[tuple], loads: list) -> list[tuple]:
    """history: (loaddate, acep, mega_project, current_budget); loads: dates with published current budgets."""
    members = defaultdict(set)
    values = defaultdict(dict)
    for day, acep, mega, cur in history:
        if mega:
            members[mega].add(acep)
        if day in loads:
            values[acep][day] = cur
    out = []
    for mega, aceps in sorted(members.items()):
        prev = None
        for day in loads:
            total = carried = 0.0
            n_members = n_present = 0
            for acep in aceps:
                held = [d for d in values[acep] if d <= day]
                if not held:
                    continue
                v = values[acep][max(held)] or 0.0
                n_members += 1
                total += v
                if day in values[acep]:
                    n_present += 1
                else:
                    carried += v
            if not n_members:
                continue
            out.append((mega, day.isoformat(), n_members, n_present, total, carried,
                        None if prev is None else total - prev, MEGA_RULE, DASHBOARD))
            prev = total
    return out


def main() -> int:
    allocs = allocations(json.loads((RAW_DIR / f"{DATASET}.json").read_text()))
    con = duckdb.connect(str(DB_PATH))
    loads = [d for (d,) in con.execute("""select loaddate from mta_loads
        where coalesce(withheld_fields, '') not like '%current_budget%' order by 1""").fetchall()]
    history = con.execute("select loaddate, acep, mega_project, current_budget from mta_history").fetchall()
    replace_table(con, "mta_allocations", "capital_plan varchar, acep varchar, plan_revision integer, approved date, "
                  "allocation double, change double, narrative varchar, dataset varchar", allocs)
    replace_table(con, "mta_plan_amendments",
                  "capital_plan varchar, approved date, n_aceps integer, total double, change double, "
                  "n_new integer, new_allocation double, n_changed integer, changed_allocation double, "
                  "n_narratives integer, rule varchar, dataset varchar, note varchar", amendments(allocs))
    con.execute("""update mta_plan_amendments a set note = ?
        from (select capital_plan, sum(current_budget) as cur from mta_history
              where loaddate = (select max(loaddate) from mta_history) group by 1) d
        where a.capital_plan = d.capital_plan and abs(a.total - d.cur) < 1e6
          and a.approved = (select max(approved) from mta_plan_amendments b where b.capital_plan = a.capital_plan)""",
                [LATEST_NOTE])
    con.execute("""update mta_plan_amendments set note = ? where note is null
        and approved = (select max(approved) from mta_plan_amendments where note is not null)""", [UNCOMPARED_NOTE])
    replace_table(con, "mta_mega_series",
                  "mega_project varchar, loaddate date, n_members integer, n_present integer, total double, "
                  "carried double, change double, rule varchar, dataset varchar", mega_series(history, loads))
    print(con.execute("""select capital_plan, approved, n_aceps, round(total / 1e9, 2), round(change / 1e9, 2),
                         round(new_allocation / 1e9, 2), round(changed_allocation / 1e9, 2)
                         from mta_plan_amendments order by 1, 2""").fetchall())
    print(con.execute("""select mega_project, round(first(total order by loaddate) / 1e9, 2),
                         round(last(total order by loaddate) / 1e9, 2) from mta_mega_series group by 1 order by 1"""
                      ).fetchall())
    return 0


if __name__ == "__main__":
    sys.exit(main())
