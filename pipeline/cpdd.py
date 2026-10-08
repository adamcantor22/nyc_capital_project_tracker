"""OMB's Capital Project Detail Data: 14 editions (April 2019 to October 2023) of each city project's original budget,
planned commitments, delay reason, scope, and original and current milestone dates.

Sources: wa2y-rh4b (money, in thousands of dollars; stored in dollars) and s7yh-frbm (milestones), fetched once by
pipeline/fetch.py; OMB stopped updating them in January 2024, when the Capital Projects Dashboard replaced them.
`project_id` is the FMS ID. One edition's pub_date is published as '2021122' in the money dataset; the milestones
dataset dates it 20211122.

Milestone dates in the editions from April 2019 to August 2021 and March 2022 were published mangled: the source
held month and two-digit year, and the export read them as a date in 2022 (`2022-MM-YY`, e.g. 2022-03-11 is March
2011) or, where MM/YY is no valid day, as a year in the 1900s (1930-02-01 is February 2030). Such an edition is
recognised by most of its dates not falling on the 1st; there `2022-MM-DD` is read as month MM of 20DD and years
1930-1949 as 2030-2049; other dates are kept. Decoded original end dates match the clean October 2023 edition for
99.85% of milestones held in both (the rest are originals OMB restated). '1899-12-01' is a placeholder, read as empty.
Each milestone row keeps the published values (`raw_*`) and the rule applied (`date_rule`).

Writes cpdd_editions, cpdd_projects (one row per edition and FMS ID), cpdd_milestones (one per edition, FMS ID and
task) and cpdd_baseline (one per FMS ID: editions held, the original budget and original finish as first and last
published, the latest current finish and delay reason). The finish is the end of the first of FINISH_TASKS a
project's milestones list (substantial completion, construction completion, construction); close-out is not used.
"""
import csv
import sys
from collections import defaultdict
from datetime import date

import duckdb

from db import DB_PATH, RAW_DIR, replace_table

MONEY, MILESTONES = "wa2y-rh4b", "s7yh-frbm"
PLACEHOLDER = "1899-12-01"


PUB_FIXES = {"2021122": "20211122"}  # the milestones dataset publishes the same edition as 20211122


# The task whose end is the project's finish, by preference: comparable to the Capital Projects Dashboard's
# forecast completion; close-out ('PUNCHLIST COMPLETE, JOB CLOSED') comes later and is not used.
FINISH_TASKS = ("SUBSTANTIAL COMPLETION", "CONSTRUCTION COMPLETION", "CONSTRUCTION")


def pub(v: str) -> str:
    return PUB_FIXES.get(v.strip(), v.strip())


def mangled(values: list[str]) -> bool:
    """An edition whose dates were read from month and two-digit year: most do not fall on the 1st."""
    days = [v[8:10] for v in values if v]
    return sum(d != "01" for d in days) > len(days) / 2


def decode(v: str | None, mangled_edition: bool) -> tuple[date | None, str]:
    """(date, rule) for one published value."""
    if not v:
        return None, "empty"
    y, m, d = int(v[:4]), int(v[5:7]), int(v[8:10])
    if v[:10] == PLACEHOLDER:
        return None, "placeholder"
    if not mangled_edition:
        return date(y, m, d), "as published"
    if y == 2022:
        return date(2000 + d, m, 1), "month and two-digit year read as 2022-MM-YY"
    if 1930 <= y <= 1949:
        return date(y + 100, m, 1), "two-digit year read as 19YY"
    return date(y, m, d), "as published"


def thousands(v: str | None) -> float | None:
    return float(v) * 1000 if v not in (None, "") else None


def read(name: str) -> list[dict]:
    with (RAW_DIR / f"{name}.csv").open(encoding="utf-8-sig") as f:
        return [{k.lower(): v for k, v in r.items()} for r in csv.DictReader(f)]


def main() -> int:
    money, miles = read(MONEY), read(MILESTONES)
    by_pub = defaultdict(list)
    for r in miles:
        by_pub[pub(r["pub_date"])].extend(r[k] for k in ("orig_start_date", "orig_end_date", "task_start_date",
                                                         "task_end_date"))
    bad = {p: mangled(vs) for p, vs in by_pub.items()}
    projects = [(pub(r["pub_date"]), r["project_id"].strip(), r["managing_agcy"], r["project_descr"], r["budget_line"],
                 r["typ_category_name"], r["boro"], r["community_board"], r["delay_desc"] or None,
                 r["scope_text"] or None,
                 r["site_descr"] or None, thousands(r["orig_bud_amt"]), thousands(r["city_plan_total"]),
                 thousands(r["noncity_plan_total"]), thousands(r["city_prior_actual"]),
                 thousands(r["noncity_prior_actual"]), MONEY) for r in money]
    milestones = []
    for r in miles:
        p = pub(r["pub_date"])
        vals = [decode(r[k][:10] if r[k] else None, bad[p]) for k in ("orig_start_date", "orig_end_date",
                                                                       "task_start_date", "task_end_date")]
        rules = sorted({rule for _, rule in vals if rule not in ("empty", "as published")}) or ["as published"]
        milestones.append((p, r["project_id"].strip(), int(r["seq_number"]), r["task_description"],
                           *(d.isoformat() if d else None for d, _ in vals),
                           *(r[k][:10] or None for k in ("orig_start_date", "orig_end_date", "task_start_date",
                                                         "task_end_date")),
                           "; ".join(rules), MILESTONES))
    con = duckdb.connect(str(DB_PATH))
    replace_table(con, "cpdd_projects",
                  "pub varchar, fms_id varchar, managing_agency varchar, description varchar, budget_line varchar, "
                  "category varchar, borough varchar, community_board varchar, delay_reason varchar, scope varchar, "
                  "site varchar, original_budget double, city_plan_total double, noncity_plan_total double, "
                  "city_prior_actual double, noncity_prior_actual double, dataset varchar", projects)
    replace_table(con, "cpdd_milestones",
                  "pub varchar, fms_id varchar, seq integer, task varchar, orig_start date, orig_end date, "
                  "start_date date, end_date date, raw_orig_start varchar, raw_orig_end varchar, raw_start varchar, "
                  "raw_end varchar, date_rule varchar, dataset varchar", milestones)
    replace_table(con, "cpdd_editions", "pub varchar, mangled_dates boolean, n_projects integer, n_milestones integer",
                  [(p, bad[p], sum(1 for x in projects if x[0] == p), sum(1 for x in milestones if x[0] == p))
                   for p in sorted(bad)])
    finish = ", ".join(f"max({{col}}) filter (where task = '{t}')" for t in FINISH_TASKS)
    con.execute(f"""create or replace table cpdd_baseline as
        with f as (select fms_id, pub, coalesce({finish.format(col="orig_end")}) orig_finish,
                          coalesce({finish.format(col="end_date")}) finish,
                          coalesce({", ".join(f"max(case when task = '{t}' then task end)" for t in FINISH_TASKS)})
                              finish_task
                   from cpdd_milestones group by 1, 2),
        p as (select p.*, f.orig_finish, f.finish, f.finish_task from cpdd_projects p left join f using (fms_id, pub))
        select fms_id, count(*) n_editions, min(pub) first_pub, max(pub) last_pub,
               arg_min(original_budget, pub) original_budget_first, arg_max(original_budget, pub) original_budget_last,
               min(pub) filter (where orig_finish is not null) finish_pub,
               arg_min(orig_finish, pub) filter (where orig_finish is not null) original_finish_first,
               arg_min(finish_task, pub) filter (where orig_finish is not null) finish_task,
               arg_max(orig_finish, pub) original_finish_last, arg_max(finish, pub) finish_last,
               arg_max(delay_reason, pub) delay_reason_last, max(pub) filter (where delay_reason is not null)
               delay_reason_pub, 'wa2y-rh4b, s7yh-frbm' as datasets
        from p group by 1""")
    print(con.execute("select pub, mangled_dates, n_projects, n_milestones from cpdd_editions").fetchall())
    print(con.execute("""select count(*), count(original_finish_first), count_if(finish_last > original_finish_last),
                         round(sum(original_budget_first) / 1e9, 1) from cpdd_baseline""").fetchall())
    return 0


if __name__ == "__main__":
    sys.exit(main())
