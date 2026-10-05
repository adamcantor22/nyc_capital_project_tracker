"""MTA capital program: ACEPs per quarterly load, and the latest state of each ACEP.

The MTA's capital projects are ACEPs ('T8041237': agency, category, element, project), each in one five-year
capital plan. The Capital Dashboard summary (ehz8-ag3n) publishes every ACEP in every quarterly load since
March 2020. This step writes:
  - `mta_loads`: one row per load, with any money field it withholds: a field that is 0 for every ACEP in a load is
    read as unpublished there, not as zero (the 2023-03-31 load gives every ACEP a current budget of 0);
  - `mta_history`: one row per (load, ACEP) as published, dates parsed;
  - `mta_projects`: one row per ACEP, from the latest load it appears in.

Status: `live` in the latest load and not Complete or Superseded; `complete` or `superseded` in the latest load;
`not_in_latest` when the latest load omits it (most are 2005-09 plan ACEPs, all complete). Superseded ACEPs passed
their money to others and stay out of live totals.

Budgets: MTA publishes original, latest-approved and current budgets. The original is restated for whole batches of
ACEPs at some loads, so it is the original as published in that load, not a fixed baseline. Two signed changes are
kept: `budget_vs_original` (current minus original, MTA's own measure in the latest load) and
`budget_change_held` (current minus the first current budget above zero that we hold, from March 2020 on; ACEPs
are often listed at $0 before they are funded, so a $0 start would count the whole budget as growth). Neither is a cost
growth measure on its own: MTA funds programs in reserve ACEPs ('Ada: 23 Stations') and moves money out to new ACEPs
as contracts are defined, so a reserve shrinks while the new ACEPs start at full size, and plan totals stay level.
Cost growth is measured over a group (a plan, a mega project) or with C&D's goal and estimated costs.

Spending kind (`spending_kind`: physical, reserve or overhead) comes from the reviewed rows in mta_spending.csv
(pipeline/mta_spending.py); other live ACEPs are physical work, and ACEPs no longer live without a row are left
unclassified.

Dates are month and year fields. A value outside 1-12 or 1990-2060 ('21', '3033', 'TBD') is not guessed: the date is
left empty and the raw value recorded in `date_issues`.

Run after pipeline/fetch_mta.py.
"""
import json
import re
import sys
from collections import defaultdict

import duckdb

from db import DB_PATH, RAW_DIR, replace_table
from mta_spending import load as load_spending

DATASET = "ehz8-ag3n"
LIVE_EXCLUDED = {"Complete", "Superseded"}
MONEY_FIELDS = ["original_budget", "latest_approved_budget", "current_budget"]
DATES = ["original_start", "current_start", "original_completion", "current_completion",
         "milestone_design_start", "milestone_design_completion", "milestone_construction_start",
         "milestone_construction_completion"]


def money(v: str | None) -> float | None:
    return float(v) if v not in (None, "") and re.match(r"^-?\d+(\.\d+)?$", v) else None


def month(r: dict, field: str) -> tuple[str | None, str | None]:
    """('2029-10' or '2029', None), or (None, the raw values) when a part is present but implausible."""
    mm, yyyy = (r.get(f"{field}_mm") or "").strip(), (r.get(f"{field}_yyyy") or "").strip()
    if not mm and not yyyy:
        return None, None
    if not re.fullmatch(r"\d{4}", yyyy) or not 1990 <= int(yyyy) <= 2060:
        return None, f"{field}: mm={mm!r} yyyy={yyyy!r}"
    if not mm:
        return yyyy, None
    if not re.fullmatch(r"\d{1,2}", mm) or not 1 <= int(mm) <= 12:
        return None, f"{field}: mm={mm!r} yyyy={yyyy!r}"
    return f"{yyyy}-{int(mm):02d}", None


def main() -> int:
    rows = json.loads((RAW_DIR / f"{DATASET}.json").read_text())
    by_load = defaultdict(list)
    for r in rows:
        by_load[r["loaddate"]].append(r)
    loads, withheld = [], {}
    for ld, rs in sorted(by_load.items()):
        day = f"{ld[:4]}-{ld[4:6]}-{ld[6:]}"
        withheld[day] = {f for f in MONEY_FIELDS if not any(money(r.get(f)) for r in rs)}
        loads.append((day, len(rs), ", ".join(sorted(withheld[day])) or None, len({r["capital_plan"] for r in rs}),
                      "0 for every ACEP: read as not published in this load" if withheld[day] else None))

    history = []
    for r in rows:
        ld = f"{r['loaddate'][:4]}-{r['loaddate'][4:6]}-{r['loaddate'][6:]}"
        parsed, issues = [], []
        for f in DATES:
            v, issue = month(r, f)
            parsed.append(v)
            if issue:
                issues.append(issue)
        orig, approved, cur = (None if f in withheld[ld] else money(r.get(f)) for f in MONEY_FIELDS)
        history.append((
            ld, r["proj_num"], r["capital_plan"], r.get("agency_code"), r.get("agency_name"),
            r.get("category_description"), r.get("element_description"), r.get("proj_description"),
            r.get("scope_objective"), r.get("mega_project"), r.get("phase"), r.get("needs_code"),
            orig, approved, cur,
            money(r.get("percentage_complete")), r.get("location_indicator") or None, *parsed,
            "; ".join(issues) or None,
        ))

    latest = max(ld for ld, *_ in loads)
    spending = load_spending()
    per_acep = defaultdict(list)
    for h in history:
        per_acep[h[1]].append(h)
    projects = []
    for acep, hs in per_acep.items():
        hs.sort()
        last = hs[-1]
        phase = last[10]
        status = ("not_in_latest" if last[0] != latest else "superseded" if phase == "Superseded"
                  else "complete" if phase == "Complete" else "live")
        held = [h for h in hs if h[14]]
        first_cur = held[0] if held else None
        cur, orig = last[14], last[12]
        completion_held = [h for h in hs if h[20] is not None]
        reviewed = spending.get(acep)
        kind, basis = ((reviewed["kind"], f"{reviewed['status']}: {reviewed['basis']}") if reviewed
                       else ("physical", "not screened: physical work") if status == "live" else (None, None))
        projects.append((
            acep, last[2], last[3], last[4], last[5], last[6], last[7], last[8], last[9], phase, last[11], status,
            hs[0][0], last[0], len(hs), cur, orig, last[13],
            None if cur is None or orig is None else cur - orig,
            first_cur[0] if first_cur else None, first_cur[14] if first_cur else None,
            None if cur is None or not first_cur else cur - first_cur[14],
            last[15], last[16], *last[17:25],
            completion_held[0][20] if completion_held else None, completion_held[0][0] if completion_held else None,
            kind, basis, DATASET,
        ))

    con = duckdb.connect(str(DB_PATH))
    replace_table(con, "mta_loads", "loaddate date, n_rows integer, withheld_fields varchar, n_plans integer, "
                  "note varchar", loads)
    date_cols = ", ".join(f"{f} varchar" for f in DATES)
    replace_table(con, "mta_history",
                  "loaddate date, acep varchar, capital_plan varchar, agency_code varchar, agency varchar, "
                  "category varchar, element varchar, description varchar, scope varchar, mega_project varchar, "
                  "phase varchar, needs_code varchar, original_budget double, latest_approved_budget double, "
                  f"current_budget double, pct_complete double, location_indicator varchar, {date_cols}, "
                  "date_issues varchar", history)
    replace_table(con, "mta_projects",
                  "acep varchar, capital_plan varchar, agency_code varchar, agency varchar, category varchar, "
                  "element varchar, description varchar, scope varchar, mega_project varchar, phase varchar, "
                  "needs_code varchar, status varchar, first_load date, last_load date, n_loads integer, "
                  "current_budget double, original_budget double, latest_approved_budget double, "
                  "budget_vs_original double, first_budget_load date, first_budget_held double, "
                  "budget_change_held double, pct_complete double, location_indicator varchar, "
                  f"{date_cols}, first_completion_held varchar, first_completion_load date, spending_kind varchar, "
                  "spending_basis varchar, dataset varchar",
                  projects)
    print(con.execute("select * from mta_loads where withheld_fields is not null").fetchall())
    print(con.execute("""select status, count(*), round(sum(current_budget) / 1e9, 1) from mta_projects
                         group by 1 order by 1""").fetchall())
    print(con.execute("""select capital_plan, count(*), round(sum(current_budget) / 1e9, 1) from mta_projects
                         where status = 'live' group by 1 order by 1""").fetchall())
    print(con.execute("""select spending_kind, count(*), round(sum(current_budget) / 1e9, 1) from mta_projects
                         where status = 'live' group by 1 order by 1""").fetchall())
    print("rows with date issues:", con.execute("select count(*) from mta_history where date_issues is not null"
                                                ).fetchone()[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
