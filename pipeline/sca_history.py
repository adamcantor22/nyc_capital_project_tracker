"""SCA project history across versions of the published schedules and budgets (2xh6-psuq).

SCA publishes only its current state. Versions come from two places:
  - `archive`: Internet Archive captures of the official CSV export (pipeline/fetch_sca_archive.py,
    data/raw/sca/archive/index.json: capture time, archive URL, SHA-1 digest);
  - `own`: our dated copies (data/raw/sca/2xh6-psuq-<YYYYMMDD>.json, the date SCA last updated the rows).
A version's `as_of` is the capture or update date: the data is that state or older, not a quarter end.

A capture is unusable when most rows' building field is not a building code (May 2014: today's header over rows
in another layout). A capture whose rows equal an earlier one's (in any order) is recorded as `same_as` it and
not repeated. Every version is parsed by pipeline/sca.py's own rules (phase_rows, project_rows), including the
reviewed program figures in sca_repeats.csv.

A project is its DSF numbers at one building (sca.project_key), and its DSF set can change between versions. A
`lineage` joins project keys that share a DSF number at the same building, in any version; history stays one row
per (version, project key), so two keys of one lineage in the same version are never merged. Keys without DSF
numbers are their own lineage.

Writes sca_versions, sca_history_phases (every published row of every version, with its row number) and
sca_history (one row per version and project key). Run after pipeline/fetch_sca_archive.py and pipeline/sca.py.
"""
import csv
import hashlib
import json
import re
import sys

import duckdb

from db import DB_PATH, RAW_DIR, replace_table
from sca import load_links, load_repeats, parse_day, phase_rows, project_rows

ARCHIVE = RAW_DIR / "sca" / "archive"
OWN = RAW_DIR / "sca"
CODE = re.compile(r"^[KMQXR][A-Z0-9]{3}$")
USABLE_SHARE = 0.9  # share of rows whose building field is a building code
PLACEHOLDER = re.compile(r"^[A-Z]{2,5}$")  # 'PNS', 'IEH', 'FTK', 'DOER': program codes in date and budget fields
DATE_FIELDS = ["project_phase_actual_start_date", "project_phase_planned_end_date", "project_phase_actual_end_date"]
MONEY_FIELDS = ["final_estimate_of_actual_costs_through_end_of_phase_amount", "total_phase_actual_spending_amount"]


def api_name(header: str) -> str:
    """CSV header -> API field name: 'DSF Number(s)' -> 'dsf_number_s_', 'Project Type ' -> 'project_type_'."""
    return re.sub(r"[^a-z0-9]", "_", header.lower())


def read_csv(path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [{api_name(k): v for k, v in r.items()} for r in csv.DictReader(f)]


def unparsed(rows: list[dict]) -> int:
    """Non-empty date or money values that are neither parseable nor a program code: data that would be lost."""
    n = 0
    for r in rows:
        for k in DATE_FIELDS:
            v = (r.get(k) or "").strip()
            n += bool(v) and not PLACEHOLDER.match(v) and parse_day(v) is None
        for k in MONEY_FIELDS:
            v = (r.get(k) or "").strip()
            n += bool(v) and not PLACEHOLDER.match(v) and not re.match(r"^-?\d+(\.\d+)?$", v)
    return n


def fingerprint(rows: list[dict]) -> str:
    return hashlib.sha1("\n".join(sorted(json.dumps(r, sort_keys=True) for r in rows)).encode()).hexdigest()


def lineages(keys_by_version: dict[str, set[tuple[str, str, str]]]) -> dict[str, str]:
    """(project_key, dsf, building) across versions -> project_key: lineage id, joining keys that share a DSF
    number at the same building. The id is the smallest DSF number and the building."""
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    all_keys = {k for ks in keys_by_version.values() for k in ks}
    for key, dsf, bldg in all_keys:
        for d in filter(None, dsf.split(",")):
            parent[find(("k", key))] = find(("d", d, bldg))
    groups = {}
    for key, dsf, bldg in all_keys:
        groups.setdefault(find(("k", key)), set()).update((d, bldg) for d in filter(None, dsf.split(",")))
    out = {}
    for key, _dsf, _ in all_keys:
        members = groups[find(("k", key))]
        out[key] = f"{min(members)[0]}|{min(members)[1]}" if members else key
    return out


def main() -> int:
    repeats, links = load_repeats(), load_links()
    sources = []  # (as_of, origin, file, captured, archive_url, digest, rows)
    for e in json.loads((ARCHIVE / "index.json").read_text()):
        c = e["captured"]
        sources.append((f"{c[:4]}-{c[4:6]}-{c[6:8]}", "archive", e["file"], c, e["archive_url"], e["digest"],
                        read_csv(ARCHIVE / e["file"])))
    for path in sorted(OWN.glob("2xh6-psuq-*.json")):
        d = path.stem.rsplit("-", 1)[1]
        sources.append((f"{d[:4]}-{d[4:6]}-{d[6:8]}", "own", path.name, None, None, None, json.loads(path.read_text())))
    sources.sort(key=lambda s: s[0])

    versions, kept, seen = [], [], {}
    for as_of, origin, file, captured, url, digest, rows in sources:
        codes = sum(bool(CODE.match((r.get("project_building_identifier") or "").strip())) for r in rows)
        usable = bool(rows) and codes / len(rows) >= USABLE_SHARE
        fp = fingerprint(rows)
        same = seen.get(fp) if usable else None
        note = (None if usable else f"{codes:,} of {len(rows):,} rows have a building code: another layout")
        versions.append((as_of, origin, file, captured, url, digest, len(rows), usable, same, unparsed(rows), note))
        if usable and not same:
            seen[fp] = as_of
            kept.append((as_of, rows))

    history_phases, history, keys_by_version = [], [], {}
    for as_of, rows in kept:
        phases = phase_rows(rows, repeats)
        projects = project_rows(phases, links)
        history_phases += [(as_of, *p) for p in phases]
        history += [(as_of, *p) for p in projects]
        keys_by_version[as_of] = {(p[0], p[1], p[2]) for p in projects}
    lineage = lineages(keys_by_version)

    con = duckdb.connect(str(DB_PATH))
    replace_table(con, "sca_versions",
                  "as_of date, origin varchar, file varchar, captured varchar, archive_url varchar, digest varchar, "
                  "n_rows integer, usable boolean, same_as date, unparsed integer, note varchar",
                  versions)
    replace_table(con, "sca_history_phases",
                  "as_of date, row_no integer, project_key varchar, dsf varchar, building varchar, "
                  "school_name varchar, school_district varchar, project_type varchar, description varchar, "
                  "phase varchar, "
                  "status varchar, start_date date, planned_end date, actual_end date, budget double, "
                  "estimate double, spent double, counted double, program_figure double", history_phases)
    replace_table(con, "sca_history",
                  "as_of date, project_key varchar, lineage varchar, dsf varchar, building varchar, status varchar, "
                  "current_phase varchar, start_date date, forecast_end date, finished date, cost double, "
                  "spent double, program_figure double",
                  [(h[0], h[1], lineage[h[1]], h[2], h[3], h[10], h[11], h[12], h[13], h[14], h[15], h[16], h[17])
                   for h in history])
    print(con.execute("""select v.as_of, v.origin, v.n_rows, v.usable, v.same_as, v.unparsed,
                                count(h.project_key), round(sum(h.cost) / 1e9, 2)
                         from sca_versions v left join sca_history h using (as_of)
                         group by all order by 1""").fetchall())
    print("lineages:", con.execute("select count(distinct lineage) from sca_history").fetchone()[0],
          "| lineages with 2+ keys in one version:", con.execute(
              "select count(distinct lineage) from (select as_of, lineage from sca_history group by all "
              "having count(*) > 1)").fetchone()[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
