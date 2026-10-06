"""Original budgets and the budget series from the Capital Projects Dashboard's budget history (qj5n-h5qp).

The dataset is not a monthly series back to 2006. Per its description, "the earliest snapshot represents the
'original budget' of a project": each (FMS ID, managing agency) has at most one row without spend, its original
budget, dated when it was first recorded (2006 onward), and then one row with spend per reporting period from
2023-05 (Jan/May/Sep), which agree with project_budget_schedule's budgets wherever both have the record.

Rules, per (FMS ID, managing agency):
- The rows with spend are the series. The signed change is recomputed against the previous row, or the original row for
  the first one; the publisher's budget_variance is kept as publisher_change, for
  the check (it chains through the odd rows below, which this does not).
- The row without spend is the original when it is dated before the series begins, or in the same period with the
  same budget. Otherwise it is not used and is recorded in budget_history_issues: in the same period with a
  different budget (mostly DPR, often 1.3 times the budget the snapshot tables publish for that period), or dated
  after the series began (off-cycle months such as 202310).
- Without a usable original row, the original is the first row of the series (basis first_snapshot). A project
  not in qj5n-h5qp at all (dropped before it was published) takes its first record in project_budget_schedule
  (fb86-vt7u).

Writes budget_series, budget_original and budget_history_issues.
"""
import sys

import duckdb

from db import DB_PATH, replace_table

DATASET = "qj5n-h5qp"
SNAPSHOTS = "fb86-vt7u"


def classify(rows: list[tuple[int, float, float | None, float | None]]):
    """One (FMS ID, agency)'s rows as (period, budget, spend, publisher variance) ->
    (series [(period, budget, spend, change, publisher_change)], original (budget, period, basis, evidence) or None,
    issues [(period, budget, issue, action)])."""
    series_rows = sorted(r for r in rows if r[2] is not None)
    bare = [r for r in rows if r[2] is None]
    periods = [r[0] for r in series_rows]
    first = series_rows[0] if series_rows else None
    issues, original = [], None
    if len(set(periods)) != len(periods) or len(bare) > 1:
        raise ValueError(f"unexpected repeated rows: {rows}")
    if bare:
        period, budget, _, _ = bare[0]
        if first is None or period < first[0] or (period == first[0] and budget == first[1]):
            original = (budget, period, "original_row", f"{DATASET} row {period} without spend, the earliest")
        elif period == first[0]:
            issues.append((period, budget, "row without spend differs from the period's reported budget "
                           f"({budget:,.2f} vs {first[1]:,.2f}; the snapshot tables agree with the latter)",
                           "not used as the original; the first reported budget is"))
        else:
            issues.append((period, budget, f"row without spend dated after the series began ({first[0]})",
                           "not used as the original; the first reported budget is"))
    if original is None and first is not None:
        original = (first[1], first[0], "first_snapshot",
                    f"{DATASET} row {first[0]}, the first reported; no usable original row")
    series, prev = [], original[0] if original and original[2] == "original_row" else None
    for period, budget, spend, var in series_rows:
        series.append((period, budget, spend, None if prev is None else round(budget - prev, 2), var))
        prev = budget
    return series, original, issues


def main() -> int:
    con = duckdb.connect(str(DB_PATH))
    by_key = {}
    for f, ag, p, b, s, v in con.execute("""select fms_id, managing_agency, year_month_reported, total_budget,
            spend_to_date, budget_variance from budget_history order by all""").fetchall():
        by_key.setdefault((f, ag), []).append((p, b, s, v))
    series, originals, issues = [], [], []
    for (f, ag), rows in by_key.items():
        s, o, i = classify(rows)
        series += [(f, ag, *r, DATASET) for r in s]
        originals += [(f, ag, *o, DATASET)] if o else []
        issues += [(f, ag, *r, DATASET) for r in i]
    for f, ag, p, b in con.execute("""select fms_id, managing_agency, min(reporting_period),
            arg_min(total_budget, reporting_period) from project_budget_schedule group by all""").fetchall():
        if (f, ag) not in by_key:
            originals.append((f, ag, b, p, "first_snapshot",
                              f"{SNAPSHOTS} snapshot {p}, the first reported; not in {DATASET}", SNAPSHOTS))
    replace_table(con, "budget_series", "fms_id varchar, managing_agency varchar, period integer, budget double, "
                  "spend double, change double, publisher_change double, source varchar", series)
    replace_table(con, "budget_original", "fms_id varchar, managing_agency varchar, original_budget double, "
                  "original_period integer, basis varchar, evidence varchar, source varchar", originals)
    replace_table(con, "budget_history_issues", "fms_id varchar, managing_agency varchar, period integer, "
                  "budget double, issue varchar, action varchar, source varchar", issues)
    print(f"budget_series: {len(series)} rows; budget_history_issues: {len(issues)}")
    print(con.execute("""select source, basis, count(*), round(sum(original_budget) / 1e9, 1) from budget_original
                         group by all order by all""").fetchall())
    return 0


if __name__ == "__main__":
    sys.exit(main())
