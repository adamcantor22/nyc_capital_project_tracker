"""One schedule model across programs: project_schedule, one row per project of every program.

Each source publishes schedules differently; this maps them to shared fields, and schedule_rule names how each row's
figures were derived. Dates carry a precision (day, month or year), and differences are taken at the coarser of the
two precisions (whole years when either date is a year only), so a month-precision figure is never shown in days.

- phase: shared names (planning, design, procurement, construction, close_out), or null where the source's phase is
  not a stage (MTA's Support, the city's holding codes). state: not_started, under_way, finished, ended or unknown.
- expected_finish: when the project is expected to finish, or did (finish_kind forecast, planned or actual).
- baseline_finish: what the finish is measured against. baseline_kind published (the source's own baseline) or
  first_held (the earliest we hold, labelled so).
- late_days: signed (positive = late); its meaning differs by program and schedule_rule says which:
  - nyc_capital: a project's finish is the latest of its PIDs' finishes (a project finishes when its last part does):
    schedule_history (95tx-snak) per PID, else the snapshot's forecast_completion (fb86-vt7u). The baseline is
    OMB's original finish (published) where its Capital Project Detail Data (2019-2023, pipeline/cpdd.py) holds one:
    the original end of the project's substantial completion, construction completion or construction task as first
    published, month precision, so late_days is taken in months. Otherwise late_days is the move since the first
    finish held (from 2023-05). Implausible dates (after
    LAST_PLAUSIBLE_YEAR) are skipped and never become a baseline. late_days and slip_days compare only PIDs dated in
    both reports, so a PID added or dropped is not read as a forecast move (pid_set_changed says so).
  - sca: SCA's own judged phase from sca_trends (sca_history.py): actual end, or the version date, minus the phase's
    planned end, set when the phase starts; null while not yet due. expected_finish only when that phase is
    Construction: its actual end, or its planned end while not yet due.
  - mta: current minus original completion (published); where MTA publishes no original, the first completion we
    hold (first_held). slip_days against the previous load with a completion.
- slip_days: the signed move since the previous report (slip_since names it).
- Reviewed forecasts (schedule_reviews.csv): a city PID's forecast in the listed reports that official records show is
  not the project's finish (a design or construction-start milestone) is left out, as if unreported, and the
  official finish is carried with its precision and evidence (official_finish, official_precision,
  official_source); schedule_rule says so.

project_phases: one row per project and phase with dates: shared phase, the source's phase name, start, end with
end_kind (actual, forecast, planned, or milestone where the source does not say), SCA's planned end (its baseline),
precision, as_of, source record and rule.
  - nyc_capital: the latest snapshot's actual milestone dates (design, procurement, construction; earliest start
    across PIDs, an end only when every PID reports one), and the current phase's start and forecast end.
  - sca: every published phase row with a date (row_no is the record).
  - mta: design and construction milestones (start and completion) as published, month or year precision.

Run after pipeline/sca_history.py and pipeline/mta.py.
"""
import csv
import datetime
import sys
from collections import defaultdict

import duckdb

import phase_groups
from db import DB_PATH, ROOT, replace_table
from export import LAST_PLAUSIBLE_YEAR

PRECISION = {"day": 0, "month": 1, "year": 2}
CITY_PHASES = {"predesign": "planning", "scopedevelopment": "planning", "preconstructionphase": "planning",
               "design": "design", "designbuild": "design", "designbuilt": "design",
               "constructionprocurement": "procurement", "construction": "construction",
               "closeout": "close_out"}
CITY_STATES = {"Done": "finished", "Ended early": "ended", "Moved or renamed": "ended", "Not started": "not_started",
               "Active": "under_way", "Stalled": "under_way"}
SCA_PHASES = {"Scope": "planning", "Design": "design", "Construction": "construction",
              "Purch & Install": "construction", "F&E": "construction"}
SCA_STATES = {"not_started": "not_started", "active": "under_way", "complete": "finished"}
MTA_PHASES = {"Planning": "planning", "Design": "design", "Construction": "construction"}
REVIEWS = ROOT / "pipeline" / "schedule_reviews.csv"
MTA_STATES = {"live": "under_way", "not_in_latest": "under_way", "complete": "finished", "superseded": "ended"}


def partial(s: str | None) -> tuple[datetime.date, str] | None:
    """'2027-08' -> (end of August 2027, 'month'); '2024' -> (31 Dec 2024, 'year')."""
    if not s:
        return None
    if len(s) == 4:
        return datetime.date(int(s), 12, 31), "year"
    y, m = int(s[:4]), int(s[5:7])
    nxt = datetime.date(y + m // 12, m % 12 + 1, 1)
    return nxt - datetime.timedelta(days=1), "month"


def coarser(a: str, b: str) -> str:
    return max(a, b, key=PRECISION.get)


def diff(a: tuple[datetime.date, str], b: tuple[datetime.date, str]) -> tuple[int, str]:
    """b minus a in days, at the coarser precision: whole years when either is a year only."""
    p = coarser(a[1], b[1])
    if p == "year":
        return (b[0].year - a[0].year) * 365, p
    return (b[0] - a[0]).days, p


def load_reviews(path=REVIEWS) -> dict[int, dict]:
    """pid -> its review row, with `reports` as a set of report periods."""
    with path.open() as f:
        return {int(r["pid"]): {**r, "reports": {int(p) for p in r["reports"].split()}} for r in csv.DictReader(f)}


def city_period_finishes(rows) -> dict[int, dict[int, tuple]]:
    """(period, pid, date, kind, source) rows -> period -> pid -> (date, kind, source); schedule_history wins, the
    snapshot's forecast fills, and of differing snapshot forecasts for one PID the latest is taken."""
    out = defaultdict(dict)
    for period, pid, date, kind, source in rows:
        if date is None or date.year > LAST_PLAUSIBLE_YEAR:
            continue
        have = out[period].get(pid)
        if have is None or (have[2] == source and date > have[0]) or (have[2] != "95tx-snak" and source == "95tx-snak"):
            out[period][pid] = (date, kind, source)
    return out


def latest_of(finishes: dict[int, tuple], pids) -> tuple | None:
    dated = [(finishes[p][0], p) for p in pids if p in finishes]
    return max(dated) if dated else None


def city_schedule(by_period: dict[int, dict[int, tuple]], links: dict[int, set[int]], last: int):
    """One project's schedule from its PIDs' finishes per period and its PID links per period."""
    periods = sorted(p for p in by_period if p <= last and links.get(p) and
                     any(pid in by_period[p] for pid in links[p]))
    now = by_period.get(last, {})
    pids_now = [p for p in links.get(last, ()) if p in now]
    if not pids_now:
        return None
    finish_date, finish_pid = latest_of(now, pids_now)
    kind = "actual" if all(now[p][1] == "actual" for p in pids_now) else "forecast"
    base_p = periods[0]
    base = latest_of(by_period[base_p], links[base_p])
    changed = False
    late = slip = slip_since = None
    common = [p for p in pids_now if p in by_period[base_p] and p in links[base_p]]
    changed |= set(common) != set(pids_now) or set(common) != {p for p in links[base_p] if p in by_period[base_p]}
    if common:
        late = (latest_of(now, common)[0] - latest_of(by_period[base_p], common)[0]).days
    prev = [p for p in periods if p < last]
    if prev:
        slip_since = prev[-1]
        before = by_period[slip_since]
        common = [p for p in pids_now if p in before and p in links[slip_since]]
        changed |= set(common) != set(pids_now)
        if common:
            slip = (latest_of(now, common)[0] - latest_of(before, common)[0]).days
    return {"expected_finish": finish_date, "finish_kind": kind,
            "finish_source": f"{now[finish_pid][2]} PID {finish_pid}, report {last}",
            "baseline_finish": base[0], "baseline_kind": "first_held", "baseline_as_of": str(base_p),
            "baseline_source": f"{by_period[base_p][base[1]][2]} PID {base[1]}, report {base_p}",
            "late_days": late, "slip_days": slip, "slip_since": None if slip_since is None else str(slip_since),
            "pid_set_changed": changed}


def sca_schedule(phase, planned, actual, days_late, as_of) -> dict:
    finish = kind = None
    if phase == "Construction":
        if actual:
            finish, kind = actual, "actual"
        elif planned and planned >= as_of:
            finish, kind = planned, "planned"
    return {"expected_finish": finish, "finish_kind": kind, "baseline_finish": planned,
            "baseline_kind": "published" if planned else None, "late_days": days_late}


def mta_schedule(current, original, first_held, first_load, prev_current) -> dict:
    cur, orig, held, prev = partial(current), partial(original), partial(first_held), partial(prev_current)
    base, kind, base_as_of = (orig, "published", None) if orig else (held, "first_held", first_load)
    late = diff(base, cur) if cur and base else (None, None)
    slip = diff(prev, cur) if cur and prev else (None, None)
    return {"expected_finish": cur and cur[0], "finish_precision": cur and cur[1],
            "baseline_finish": base and base[0], "baseline_kind": kind if base else None,
            "baseline_precision": base and base[1], "baseline_as_of": base_as_of,
            "late_days": late[0], "late_precision": late[1], "slip_days": slip[0], "slip_precision": slip[1]}


COLUMNS = ["program", "project_id", "as_of", "phase", "state", "expected_finish", "finish_kind",
           "finish_precision", "finish_source", "baseline_finish", "baseline_kind", "baseline_precision",
           "baseline_as_of", "baseline_source", "late_days", "late_precision", "late_phase", "slip_days",
           "slip_precision", "slip_since", "pid_set_changed", "official_finish", "official_precision",
           "official_source", "schedule_rule"]
DDL = ("program varchar, project_id varchar, as_of varchar, phase varchar, state varchar, expected_finish date, "
       "finish_kind varchar, finish_precision varchar, finish_source varchar, baseline_finish date, "
       "baseline_kind varchar, baseline_precision varchar, baseline_as_of varchar, baseline_source varchar, "
       "late_days integer, late_precision varchar, late_phase varchar, slip_days integer, slip_precision varchar, "
       "slip_since varchar, pid_set_changed boolean, official_finish date, official_precision varchar, "
       "official_source varchar, schedule_rule varchar")


def row(**kw) -> tuple:
    for k in ("expected_finish", "baseline_finish", "official_finish"):
        if kw.get(k) is not None:
            kw[k] = kw[k].isoformat()
    return tuple(kw.get(c) for c in COLUMNS)


def city_rows(con, reviews=None) -> list[tuple]:
    reviews = load_reviews() if reviews is None else reviews
    finishes = city_period_finishes(r for r in con.execute("""
        select reporting_period, pid, completion_date::date, lower(completion_date_type), '95tx-snak'
        from schedule_history
        union all select distinct reporting_period, pid, forecast_completion::date, 'forecast', 'fb86-vt7u'
        from project_budget_schedule where pid is not null""").fetchall()
        if r[0] not in reviews.get(r[1], {}).get("reports", ()))
    links = defaultdict(lambda: defaultdict(set))
    for f, p, pid in con.execute("select distinct fms_id, reporting_period, pid from project_budget_schedule "
                                 "where pid is not null").fetchall():
        links[f][p].add(pid)
    groups = phase_groups.load()
    omb = {}  # OMB's original finish (pipeline/cpdd.py), a published baseline
    if con.execute("select count(*) from duckdb_tables() where table_name = 'cpdd_baseline'").fetchone()[0]:
        omb = {f: rest for f, *rest in con.execute("""select fms_id, original_finish_first, finish_pub, finish_task
                from cpdd_baseline where original_finish_first is not null""").fetchall()}
    out = []
    for f, last, phase in con.execute("""select fms_id, max(reporting_period),
            arg_max(current_phase, reporting_period) from project_budget_schedule group by 1""").fetchall():
        group = phase_groups.group(phase, groups)
        s = city_schedule(finishes, links[f], last) or {}
        precision = {"finish_precision": "day" if s else None, "baseline_precision": "day" if s else None,
                     "late_precision": "day" if s.get("late_days") is not None else None}
        published = bool(s) and f in omb
        if published:
            orig, edition, task = omb[f]
            late = diff((orig, "month"), (s["expected_finish"], "day"))
            s.update(baseline_finish=orig, baseline_kind="published", baseline_as_of=edition, late_days=late[0],
                     baseline_source=f"s7yh-frbm {f}: original end of {task.lower()}, edition {edition}")
            precision.update(baseline_precision="month", late_precision=late[1])
        state = "finished" if s.get("finish_kind") == "actual" else CITY_STATES.get(group, "unknown")
        reviewed = [reviews[p] for p in sorted(set().union(*links[f].values())) if p in reviews]
        official = {}
        if reviewed:
            r = reviewed[0]
            d = partial(r["official_finish"])
            official = {"official_finish": d and d[0], "official_precision": d and d[1],
                        "official_source": f"{r['official_milestone']}: {r['evidence']}"}
        out.append(row(program="nyc_capital", project_id=f, as_of=str(last), state=state,
                       phase=CITY_PHASES.get(phase_groups.key(phase)), **s, **precision,
                       slip_precision="day" if s.get("slip_days") is not None else None,
                       late_phase="project" if s else None, **official,
                       schedule_rule=(("city: latest PID finish; late = finish minus OMB's original finish "
                                       "(Capital Project Detail Data)") if published else
                                      "city: latest PID finish; late = move since first finish held" if s else
                                      "city: no dated finish")
                       + ("; reviewed forecasts left out (schedule_reviews.csv)" if reviewed else "")))
    return out


def sca_rows(con) -> list[tuple]:
    as_of = con.execute("select max(as_of) from sca_history").fetchone()[0]
    out = []
    for key, status, phase, jphase, planned, actual, late in con.execute("""select p.project_key, p.status,
            p.current_phase, t.schedule_phase, t.planned_end, t.actual_end, t.days_late
            from sca_projects p left join sca_trends t using (project_key)""").fetchall():
        s = sca_schedule(jphase, planned, actual, late, as_of) if jphase else {}
        src = f"2xh6-psuq {jphase} phase of {key}, version {as_of}"
        out.append(row(program="sca", project_id=key, as_of=as_of.isoformat(), phase=SCA_PHASES.get(phase),
                       state=SCA_STATES.get(status, "unknown"), **s,
                       finish_precision="day" if s.get("expected_finish") else None,
                       finish_source=src if s.get("expected_finish") else None,
                       baseline_precision="day" if s.get("baseline_finish") else None,
                       baseline_as_of=as_of.isoformat() if s.get("baseline_finish") else None,
                       baseline_source=f"{src} (planned end)" if s.get("baseline_finish") else None,
                       late_precision="day" if s.get("late_days") is not None else None,
                       late_phase=jphase, pid_set_changed=None,
                       schedule_rule="sca: judged phase (sca_trends); late = actual or version date minus planned end"
                       if jphase else "sca: no phase with a planned end"))
    return out


def mta_rows(con) -> list[tuple]:
    prev = {}
    for acep, cur in con.execute("""select h.acep, arg_max(h.current_completion, h.loaddate)
            from mta_history h join mta_projects p on p.acep = h.acep
            where h.loaddate < p.last_load and h.current_completion is not null group by 1""").fetchall():
        prev[acep] = cur
    prev_load = dict(con.execute("""select h.acep, max(h.loaddate) from mta_history h join mta_projects p
            on p.acep = h.acep where h.loaddate < p.last_load and h.current_completion is not null
            group by 1""").fetchall())
    out = []
    for acep, status, phase, last, cur, orig, held, held_load in con.execute("""select acep, status, phase,
            last_load, current_completion, original_completion, first_completion_held, first_completion_load
            from mta_projects""").fetchall():
        s = mta_schedule(cur, orig, held, held_load and held_load.isoformat(), prev.get(acep))
        load = f"ehz8-ag3n {acep}, load {last}"
        if s["baseline_finish"] and not s["baseline_as_of"]:
            s["baseline_as_of"] = last.isoformat()
        out.append(row(program="mta", project_id=acep, as_of=last.isoformat(), phase=MTA_PHASES.get(phase),
                       state=MTA_STATES.get(status, "unknown"), **s,
                       finish_kind=("actual" if phase == "Complete" else "forecast") if cur else None,
                       finish_source=f"{load} current_completion" if cur else None,
                       baseline_source=(f"{load} original_completion" if s["baseline_kind"] == "published" else
                                        f"ehz8-ag3n {acep} first completion held, load {held_load}")
                       if s["baseline_finish"] else None,
                       late_phase="project" if s["late_days"] is not None else None,
                       slip_since=prev_load[acep].isoformat() if s["slip_days"] is not None else None,
                       pid_set_changed=None,
                       schedule_rule="mta: current minus original completion" if s["baseline_kind"] == "published"
                       else "mta: current completion minus the first held" if s["baseline_finish"]
                       else "mta: no completion"))
    return out


PHASE_COLUMNS = ["program", "project_id", "phase", "source_phase", "start", "end_date", "end_kind", "planned_end",
                 "precision", "as_of", "source", "rule"]
PHASE_DDL = ("program varchar, project_id varchar, phase varchar, source_phase varchar, start date, end_date date, "
             "end_kind varchar, planned_end date, precision varchar, as_of varchar, source varchar, rule varchar")
CITY_MILESTONES = [("design", "design", "actual_design_start", "actual_design_end"),
                   ("procurement", "construction procurement", "actual_construction_procurement_start",
                    "actual_construction_procurement_end"),
                   ("construction", "construction", "actual_construction_start", "actual_construction_end")]


def plausible(d):
    return d if d is not None and d.year <= LAST_PLAUSIBLE_YEAR else None


def iso(d):
    return None if d is None else d.isoformat()


def city_phase_rows(con) -> list[tuple]:
    cols = ", ".join(f"min({a}::date), case when bool_and({b} is not null) then max({b}::date) end"
                     for _, _, a, b in CITY_MILESTONES)
    last_cte = "with last as (select fms_id, max(reporting_period) p from project_budget_schedule group by 1)"
    phases = {}
    for f, p, *dates in con.execute(f"""{last_cte} select b.fms_id, l.p, {cols} from project_budget_schedule b
            join last l on b.fms_id = l.fms_id and b.reporting_period = l.p group by all""").fetchall():
        for i, (shared, name, _, _) in enumerate(CITY_MILESTONES):
            start, end = plausible(dates[2 * i]), plausible(dates[2 * i + 1])
            if start or end:
                phases[(f, shared)] = {"p": p, "name": name, "start": start, "end": end,
                                       "end_kind": "actual" if end else None,
                                       "rule": "actual milestone dates (earliest start; an end only when every PID "
                                               "reports one)"}
    for f, p, phase, start, end in con.execute(f"""{last_cte} select b.fms_id, l.p, b.current_phase,
            min(b.current_phase_start::date), max(b.forecast_current_phase_end::date) from project_budget_schedule b
            join last l on b.fms_id = l.fms_id and b.reporting_period = l.p group by all""").fetchall():
        shared = CITY_PHASES.get(phase_groups.key(phase))
        start, end = plausible(start), plausible(end)
        if not shared or not (start or end):
            continue
        ph = phases.setdefault((f, shared), {"p": p, "name": phase, "start": None, "end": None, "end_kind": None,
                                             "rule": "current phase: start and forecast end"})
        ph["start"] = ph["start"] or start
        if not ph["end"] and end:
            ph["end"], ph["end_kind"] = end, "forecast"
            if ph["rule"].startswith("actual"):
                ph["rule"] += "; forecast end of the current phase"
    return [("nyc_capital", f, shared, ph["name"], iso(ph["start"]), iso(ph["end"]), ph["end_kind"], None, "day",
             str(ph["p"]), f"fb86-vt7u {f}, report {ph['p']}", ph["rule"])
            for (f, shared), ph in sorted(phases.items())]


def sca_phase_rows(con) -> list[tuple]:
    as_of = con.execute("select max(as_of) from sca_history").fetchone()[0].isoformat()
    out = []
    for key, row_no, phase, start, planned, actual in con.execute("""select project_key, row_no, phase, start_date,
            planned_end, actual_end from sca_phases where coalesce(start_date, planned_end, actual_end) is not null
            order by 1, 2""").fetchall():
        end, kind = (actual, "actual") if actual else (planned, "planned") if planned else (None, None)
        out.append(("sca", key, SCA_PHASES.get(phase, "construction"), phase, iso(start), iso(end), kind,
                    iso(planned), "day", as_of, f"2xh6-psuq row {row_no}, version {as_of}",
                    "published phase row: actual end, else planned end"))
    return out


def mta_phase_rows(con) -> list[tuple]:
    out = []
    for acep, last, *dates in con.execute("""select acep, last_load, milestone_design_start,
            milestone_design_completion, milestone_construction_start, milestone_construction_completion
            from mta_projects order by 1""").fetchall():
        for shared, start, end in (("design", dates[0], dates[1]), ("construction", dates[2], dates[3])):
            st, en = partial(start), partial(end)
            if st or en:
                out.append(("mta", acep, shared, shared, iso(st and st[0]), iso(en and en[0]),
                            "milestone" if en else None, None, coarser((st or en)[1], (en or st)[1]),
                            last.isoformat(), f"ehz8-ag3n {acep}, load {last}",
                            f"milestone_{shared}_start and _completion as published (month or year)"))
    return out


def main() -> int:
    con = duckdb.connect(str(DB_PATH))
    rows = city_rows(con) + sca_rows(con) + mta_rows(con)
    replace_table(con, "project_schedule", DDL, rows)
    replace_table(con, "project_phases", PHASE_DDL, city_phase_rows(con) + sca_phase_rows(con) + mta_phase_rows(con))
    print(con.execute("""select program, phase, count(*), count(start), count(end_date), count(planned_end)
            from project_phases group by all order by all""").fetchall())
    print(con.execute("""select program, count(*), count(expected_finish), count(late_days),
            count(*) filter (where late_days > 0), median(late_days) filter (where late_days is not null)
            from project_schedule group by 1 order by 1""").fetchall())
    return 0


if __name__ == "__main__":
    sys.exit(main())
