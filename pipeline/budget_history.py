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

Each original also records the phase the project was in when it was recorded (phase_at_original, phase_rule,
phase_evidence), the first of:
- snapshot: from 2023-05, the record's phase in the snapshot at or before the original's period, the most advanced
  over its PIDs (they differ in 337 of 31,313 record-periods when set); records without a PID publish no phase
  (no_phase), and a report publishing every such record as (Pending) is read as not publishing it (finishes.py).
- actual_start, actual_start_same_month: the record's earliest actual design, construction procurement or
  construction start in any snapshot, before or in the original's month (month precision; the same month is its own
  rule); actual_design_start_after: design began after it (planning).
- first_snapshot_bound: the record's first snapshot shows planning (planning) or design or procurement
  (before_construction); phases rarely move back (175 of 4,938 records with two or more snapshots ever do).
  actual_start_after: a procurement or construction start after it (before_construction).
- omb_schedule_bound: the first OMB Capital Project Detail Data edition from the original's month on schedules
  construction after the edition (before_construction). OMB's task starts can only bound the phase: they fall within
  3 months of the snapshots' actual starts for 25% of design and 18% of construction starts, but where an edition
  schedules construction after its own date, the actual start is also after it 86% of the time (when set,
  measured on projects with actual starts; the bound applies to those without).
- first_snapshot_no_phase (no_phase) or unknown.

Writes budget_series, budget_original and budget_history_issues.
"""
import datetime
import sys

import duckdb

import finishes
import phase_groups
from db import DB_PATH, replace_table
from export import LAST_PLAUSIBLE_YEAR
from schedules import CITY_PHASES

DATASET = "qj5n-h5qp"
SNAPSHOTS = "fb86-vt7u"
SERIES_START = 202305
PHASE_ORDER = ("planning", "design", "procurement", "construction", "close_out")
STARTS = (("construction", "actual_construction_start"), ("procurement", "actual_construction_procurement_start"),
          ("design", "actual_design_start"))
OMB_CONSTRUCTION = ("CONSTRUCTION START", "CONSTRUCTION", "CONSTRUCTION TO 25%")


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


def snapshot_phase(raws: list[str]) -> str:
    """The most advanced shared phase over a record's PIDs in one snapshot, else no_phase."""
    shared = [CITY_PHASES.get(phase_groups.key(r)) for r in raws]
    shared = [p for p in shared if p]
    return max(shared, key=PHASE_ORDER.index) if shared else "no_phase"


def phase_at(period: int, snaps: list[tuple[int, list[str]]], starts: dict[str, int], omb) -> tuple[str, str, str]:
    """Phase when an original dated `period` (YYYYMM) was recorded -> (phase, rule, evidence).
    snaps: [(report period, raw phases of the record's PIDs)], sorted; starts: shared phase -> earliest actual start
    (YYYYMM); omb: (edition, task, scheduled start, edition date) of the first edition from `period` on, or None."""
    held = [(p, r) for p, r in snaps if p <= period]
    if period >= SERIES_START and held:
        p, raws = held[-1]
        return snapshot_phase(raws), "snapshot", f"{SNAPSHOTS} {p}: {' / '.join(sorted(set(raws)))}"
    for phase, col in STARTS:
        start = starts.get(phase)
        if start is not None and start <= period:
            rule = "actual_start" if start < period else "actual_start_same_month"
            return phase, rule, f"{SNAPSHOTS} earliest {col} {start}"
    if starts.get("design") is not None:
        return "planning", "actual_design_start_after", f"{SNAPSHOTS} earliest actual_design_start {starts['design']}"
    first = (snaps[0][0], snapshot_phase(snaps[0][1]), snaps[0][1]) if snaps else None
    if first and first[1] == "planning":
        return "planning", "first_snapshot_bound", f"{SNAPSHOTS} {first[0]}: {' / '.join(sorted(set(first[2])))}"
    later = [(phase, col) for phase, col in STARTS if starts.get(phase) is not None]
    if later:
        phase, col = later[-1]
        return "before_construction", "actual_start_after", f"{SNAPSHOTS} earliest {col} {starts[phase]}"
    if first and first[1] in ("design", "procurement"):
        return ("before_construction", "first_snapshot_bound",
                f"{SNAPSHOTS} {first[0]}: {' / '.join(sorted(set(first[2])))}")
    if omb and omb[2] > omb[3]:
        return ("before_construction", "omb_schedule_bound",
                f"s7yh-frbm edition {omb[0]}: {omb[1]} scheduled to start {omb[2].isoformat()}")
    if first and first[1] == "no_phase":
        return "no_phase", "first_snapshot_no_phase", f"{SNAPSHOTS} {first[0]}: {' / '.join(sorted(set(first[2])))}"
    return "unknown", "unknown", "no snapshot phase, actual start or OMB schedule bounds it"


def phases_at_original(con, originals: list[tuple]) -> list[tuple]:
    """Each original row with (phase_at_original, phase_rule, phase_evidence) appended."""
    unpublished = {p for p, _ in finishes.pidless_unpublished(con)}
    snaps = {}
    for f, ag, p, raws in con.execute("""select fms_id, managing_agency, reporting_period, list(current_phase)
            from project_budget_schedule where current_phase is not null
              and not (pid is null and reporting_period in (select unnest(?::integer[])))
            group by all order by all""", [sorted(unpublished)]).fetchall():
        snaps.setdefault((f, ag), []).append((p, raws))
    cols = ", ".join(f"min(strftime({col}, '%Y%m')::integer) filter (where year({col}) between {finishes.FIRST_YEAR} "
                     f"and {LAST_PLAUSIBLE_YEAR})" for _, col in STARTS)
    starts = {(f, ag): {phase: v for (phase, _), v in zip(STARTS, vals, strict=True) if v is not None}
              for f, ag, *vals in con.execute(f"""select fms_id, managing_agency, {cols} from project_budget_schedule
                                                 group by all""").fetchall()}
    omb = {}
    tasks = ", ".join(f"'{t}'" for t in OMB_CONSTRUCTION)
    for f, pub, task, start in con.execute(f"""select fms_id, pub, arg_min(task, start_date), min(start_date)
            from cpdd_milestones where task in ({tasks}) and year(start_date) between {finishes.FIRST_YEAR}
              and {LAST_PLAUSIBLE_YEAR} group by all order by all""").fetchall():
        omb.setdefault(f, []).append((pub, task, start))
    out = []
    for row in originals:
        f, ag, period = row[0], row[1], row[3]
        ed = next(((pub, task, start, datetime.date(int(pub[:4]), int(pub[4:6]), int(pub[6:])))
                   for pub, task, start in omb.get(f, []) if int(pub[:6]) >= period), None)
        out.append((*row, *phase_at(period, snaps.get((f, ag), []), starts.get((f, ag), {}), ed)))
    return out


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
                  "original_period integer, basis varchar, evidence varchar, source varchar, "
                  "phase_at_original varchar, phase_rule varchar, phase_evidence varchar",
                  phases_at_original(con, originals))
    replace_table(con, "budget_history_issues", "fms_id varchar, managing_agency varchar, period integer, "
                  "budget double, issue varchar, action varchar, source varchar", issues)
    print(f"budget_series: {len(series)} rows; budget_history_issues: {len(issues)}")
    print(con.execute("""select source, basis, count(*), round(sum(original_budget) / 1e9, 1) from budget_original
                         group by all order by all""").fetchall())
    print(con.execute("""select basis, phase_at_original, count(*), round(sum(original_budget) / 1e9, 1)
                         from budget_original group by all order by all""").fetchall())
    return 0


if __name__ == "__main__":
    sys.exit(main())
