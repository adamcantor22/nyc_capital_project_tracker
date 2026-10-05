"""MTA capital program: ACEPs per quarterly load, and the latest state of each ACEP.

The MTA's capital projects are ACEPs ('T8041237': agency, category, element, project), each in one five-year
capital plan. The Capital Dashboard summary (ehz8-ag3n) publishes every ACEP in every quarterly load since
March 2020. This step writes:
  - `mta_loads`: one row per load, with whether its budgets were published (the 2023-03-31 load gives every ACEP
    a current budget of 0, so its budgets are read as unpublished, not as zero);
  - `mta_history`: one row per (load, ACEP) as published, dates parsed;
  - `mta_projects`: one row per ACEP, from the latest load it appears in.

Status: `live` in the latest load and not Complete or Superseded; `complete` or `superseded` in the latest load;
`not_in_latest` when the latest load omits it (most are 2005-09 plan ACEPs, all complete). Superseded ACEPs passed
their money to others and stay out of live totals.

Budgets: MTA publishes original, latest-approved and current budgets. The original is restated for whole batches of
ACEPs at some loads, so it is the original as published in that load, not a fixed baseline. Two signed changes are
kept: `budget_vs_original` (current minus original, MTA's own measure in the latest load) and
`budget_change_held` (current minus the first current budget we hold, from March 2020 on).

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

DATASET = "ehz8-ag3n"
LIVE_EXCLUDED = {"Complete", "Superseded"}
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
    loads = []
    for ld, rs in sorted(by_load.items()):
        published = any(money(r.get("current_budget")) for r in rs)
        loads.append((f"{ld[:4]}-{ld[4:6]}-{ld[6:]}", len(rs), published, len({r["capital_plan"] for r in rs}),
                      None if published else "every current_budget is 0: budgets not published in this load"))
    unpublished = {ld for ld, *_, note in loads if note}

    history = []
    for r in rows:
        ld = f"{r['loaddate'][:4]}-{r['loaddate'][4:6]}-{r['loaddate'][6:]}"
        parsed, issues = [], []
        for f in DATES:
            v, issue = month(r, f)
            parsed.append(v)
            if issue:
                issues.append(issue)
        cur = None if ld in unpublished else money(r.get("current_budget"))
        history.append((
            ld, r["proj_num"], r["capital_plan"], r.get("agency_code"), r.get("agency_name"),
            r.get("category_description"), r.get("element_description"), r.get("proj_description"),
            r.get("scope_objective"), r.get("mega_project"), r.get("phase"), r.get("needs_code"),
            None if ld in unpublished else money(r.get("original_budget")),
            None if ld in unpublished else money(r.get("latest_approved_budget")), cur,
            money(r.get("percentage_complete")), r.get("location_indicator") or None, *parsed,
            "; ".join(issues) or None,
        ))

    latest = max(ld for ld, *_ in loads)
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
        held = [h for h in hs if h[14] is not None]
        first_cur = held[0] if held else None
        cur, orig = last[14], last[12]
        completion_held = [h for h in hs if h[20] is not None]
        projects.append((
            acep, last[2], last[3], last[4], last[5], last[6], last[7], last[8], last[9], phase, last[11], status,
            hs[0][0], last[0], len(hs), cur, orig, last[13],
            None if cur is None or orig is None else cur - orig,
            first_cur[0] if first_cur else None, first_cur[14] if first_cur else None,
            None if cur is None or not first_cur else cur - first_cur[14],
            last[15], last[16], *last[17:25],
            completion_held[0][20] if completion_held else None, completion_held[0][0] if completion_held else None,
            DATASET,
        ))

    con = duckdb.connect(str(DB_PATH))
    replace_table(con, "mta_loads", "loaddate date, n_rows integer, budgets_published boolean, n_plans integer, "
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
                  f"{date_cols}, first_completion_held varchar, first_completion_load date, dataset varchar",
                  projects)
    print(con.execute("select * from mta_loads where not budgets_published").fetchall())
    print(con.execute("""select status, count(*), round(sum(current_budget) / 1e9, 1) from mta_projects
                         group by 1 order by 1""").fetchall())
    print(con.execute("""select capital_plan, count(*), round(sum(current_budget) / 1e9, 1) from mta_projects
                         where status = 'live' group by 1 order by 1""").fetchall())
    print("rows with date issues:", con.execute("select count(*) from mta_history where date_issues is not null"
                                                ).fetchone()[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
