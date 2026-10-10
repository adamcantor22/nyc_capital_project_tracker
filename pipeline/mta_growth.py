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
    The dataset does not record every amendment on its date: many ACEPs carry an amendment's change only on the
    latest row, whose narrative names the earlier amendment ('reprogrammed per the MTA Board approved July 2013 Plan
    Amendment'), and money moved to a new ACEP keeps counting on the old one until then. So totals between a plan's
    first row and its latest overstate it; those rows say so in `note`. Each amendment's figures need MTA's own
    amendment documents.
  - `mta_mega_members`: every ACEP counted in a mega project: those the dashboard tags (`dashboard_tag`), and ACEPs
    of the funding plans never listed on the dashboard (finished before 2020) in a plan category whose tagged ACEPs
    all carry one mega project (`plan_category`: 25 East Side Access, 15 Second Avenue Subway and 7 Flushing Line
    Extension ACEPs of the 2005-09 plan when set). `evidence` names the category and its tagged ACEPs.
  - `mta_mega_plans`: one row per (mega project, plan): its members' allocation at the plan's first row and at the
    latest row, kept per plan, since a new plan's first allocation is more money for the project rather than growth
    of an earlier figure. The funding plans begin with the 2005-09 plan, whose ACEPs are mostly first listed on the
    latest row (`n_first`, `n_latest`), so money from earlier plans is not in them.
  - `mta_mega_series`: one row per (mega project, dashboard load): the summed current budget of every ACEP tagged
    with the mega project in any load (ehz8-ag3n), each at its latest current budget on or before the load, so an
    ACEP missing from a load (the 2026-03 load omits the 2005-09 plan) is carried, not counted as a cut. Loads that
    withhold current budgets (mta_loads) are skipped.

  - `mta_program_approvals`: each plan's approvals as MTA's own documents state them (mta_program_approvals.csv:
    board and CPRB dates, program total including B&T, CPRB portion, each figure quoted with its document page;
    fetch_mta_docs.py holds the PDFs). The funding plans dataset's dated rows are not these approvals, even at
    adoption: its first rows exceed the adopted totals (2020-24: $62.0B against $54.799B adopted), and its latest
    rows come within about 2% of the latest approved totals. Nothing for the 2005-09 plan was found in MTA's library.
  - `mta_mega_amendments`: each amendment book's Network Expansion table, line by line (mta_mega_amendments.csv:
    the step before and the step proposed, in millions as printed, each line quoted with its page). Consecutive books
    print the same step, one as proposed and the next as prior, and agree (a data check) except where `note` records
    a printing error. A book may compare across a letter amendment that had no book of its own (2020-24 #1 and #4).

Amendments move money between plans (deferrals) and add scope and funding, so these are signed allocation
changes, not cost growth alone. All amounts are nominal dollars.

Run after pipeline/mta.py.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import duckdb

from db import DB_PATH, RAW_DIR, replace_table

APPROVALS = Path(__file__).with_name("mta_program_approvals.csv")
MEGA_AMENDMENTS = Path(__file__).with_name("mta_mega_amendments.csv")
DOC_URL = "https://www.mta.info/document/{}"
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
BETWEEN_NOTE = ("may overstate the plan: changes some ACEPs carry only on the latest row, and money moved to new "
                "ACEPs still counted on the old ones")
MEMBER_RULE = "plan_category: never on the dashboard, in a plan category whose tagged ACEPs all carry this mega project"
MEGA_RULE = ("ACEPs tagged with the mega project in any ehz8-ag3n load, each at its latest current budget on or "
             "before the load; loads withholding current_budget skipped")


def fragments(quote: str) -> list[tuple[int, str]]:
    """'p2: text | p3: text' -> [(2, 'text'), (3, 'text')]: each quoted fragment with its PDF page (1-based)."""
    return [(int(m.group(1)), m.group(2)) for f in quote.split(" | ") if (m := re.fullmatch(r"p(\d+): (.+)", f))]


def approvals(path: Path = APPROVALS) -> list[tuple]:
    """mta_program_approvals.csv -> rows in dollars, with the document's URL."""
    def dollars(v):
        return round(float(v) * 1e9) if v else None
    with path.open() as f:
        return [(r["plan"], r["step"], r["outcome"], r["board_date"], r["cprb_date"] or None, dollars(r["total"]),
                 dollars(r["cprb_portion"]), r["document"], DOC_URL.format(r["document"]), r["quote"])
                for r in csv.DictReader(f)]


def mega_amendments(path: Path = MEGA_AMENDMENTS) -> list[tuple]:
    """mta_mega_amendments.csv -> rows in dollars, with the document's URL."""
    def dollars(v):
        return round(float(v) * 1e6) if v else None
    with path.open() as f:
        return [(r["plan"], r["prior_step"] or None, r["prior_label"] or None, r["step"], r["line"],
                 r["mega_project"] or None, dollars(r["prior"]), dollars(r["proposed"]), r["document"],
                 DOC_URL.format(r["document"]), r["quote"], r["note"] or None) for r in csv.DictReader(f)]


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


def mega_members(rows: list[dict], tags: dict[str, str], on_dashboard: set[str]) -> list[tuple]:
    """(acep, mega_project, capital_plan, category, basis, evidence): the dashboard's tags, plus never-listed ACEPs of a
    funding-plan category whose tagged ACEPs all carry one mega project."""
    key = {r["acep"]: (r["agency"], r["plan_id"], r["category"]) for r in rows}
    by_category = defaultdict(lambda: defaultdict(list))
    for acep, mega in tags.items():
        if acep in key:
            by_category[key[acep]][mega].append(acep)
    out = []
    for acep in sorted(set(key) | set(tags)):
        agency, plan, category = key.get(acep, (None, None, None))
        if acep in tags:
            out.append((acep, tags[acep], PLANS.get(plan), category, "dashboard_tag", f"{DASHBOARD} mega_project"))
        elif acep not in on_dashboard and len(megas := by_category.get(key[acep], {})) == 1:
            (mega, tagged), = megas.items()
            out.append((acep, mega, PLANS[plan], category, "plan_category",
                        f"{DATASET} agency {agency}, {PLANS[plan]}, category {category}; tagged {mega} on "
                        f"{DASHBOARD}: {', '.join(sorted(tagged))}"))
    return out


def mega_plans(members: list[tuple], allocs: list[tuple]) -> list[tuple]:
    """Per (mega project, plan): members' allocation at the plan's first row and at its latest row."""
    mega_of = {m[0]: m[1] for m in members}
    first_day = {}
    for a in allocs:
        first_day[a[0]] = min(first_day.get(a[0], a[3]), a[3])
    held = defaultdict(lambda: defaultdict(list))  # (mega, plan) -> acep -> rows in date order
    for a in allocs:
        if a[1] in mega_of:
            held[(mega_of[a[1]], a[0])][a[1]].append(a)
    out = []
    for (mega, plan), aceps in sorted(held.items()):
        day0 = first_day[plan]
        at_first = [rs[0][4] for rs in aceps.values() if rs[0][3] == day0]
        out.append((mega, plan, len(aceps), day0, len(at_first), sum(at_first),
                    max(rs[-1][3] for rs in aceps.values()), sum(rs[-1][4] for rs in aceps.values()),
                    sum(1 for rs in aceps.values() if rs[0][3] == max(a[3] for a in allocs if a[0] == plan)),
                    "members' allocation in this plan: at the plan's first row, and each member's latest row",
                    DATASET))
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
    tags = {acep: mega for _, acep, mega, _ in history if mega}
    members = mega_members(json.loads((RAW_DIR / f"{DATASET}.json").read_text()), tags, {h[1] for h in history})
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
    con.execute("""update mta_plan_amendments a set note = ? where note is null
        and approved > (select min(approved) from mta_plan_amendments b where b.capital_plan = a.capital_plan)""",
                [BETWEEN_NOTE])
    replace_table(con, "mta_program_approvals", "capital_plan varchar, step varchar, outcome varchar, "
                  "board_date varchar, cprb_date varchar, total double, cprb_portion double, document varchar, "
                  "url varchar, quote varchar", approvals())
    replace_table(con, "mta_mega_amendments", "capital_plan varchar, prior_step varchar, prior_label varchar, "
                  "step varchar, line varchar, mega_project varchar, prior double, proposed double, document varchar, "
                  "url varchar, quote varchar, note varchar", mega_amendments())
    replace_table(con, "mta_mega_members", "acep varchar, mega_project varchar, capital_plan varchar, "
                  "category varchar, basis varchar, evidence varchar", members)
    replace_table(con, "mta_mega_plans", "mega_project varchar, capital_plan varchar, n_aceps integer, "
                  "first_day date, n_first integer, first_allocation double, latest_day date, "
                  "latest_allocation double, n_latest_only integer, rule varchar, dataset varchar",
                  mega_plans(members, allocs))
    replace_table(con, "mta_mega_series",
                  "mega_project varchar, loaddate date, n_members integer, n_present integer, total double, "
                  "carried double, change double, rule varchar, dataset varchar", mega_series(history, loads))
    print(con.execute("""select capital_plan, approved, n_aceps, round(total / 1e9, 2), round(change / 1e9, 2),
                         round(new_allocation / 1e9, 2), round(changed_allocation / 1e9, 2)
                         from mta_plan_amendments order by 1, 2""").fetchall())
    for r in con.execute("""select mega_project, capital_plan, n_aceps, n_first, round(first_allocation / 1e9, 2),
                            n_latest_only, round(latest_allocation / 1e9, 2) from mta_mega_plans order by 1, 2"""
                         ).fetchall():
        print(*r, sep="\t")
    print(con.execute("""select mega_project, round(first(total order by loaddate) / 1e9, 2),
                         round(last(total order by loaddate) / 1e9, 2) from mta_mega_series group by 1 order by 1"""
                      ).fetchall())
    return 0


if __name__ == "__main__":
    sys.exit(main())
