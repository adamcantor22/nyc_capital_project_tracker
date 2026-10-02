"""Load data/raw/*.csv into data/capital.duckdb with friendly table names.

Rebuilds the tables on each run. Records load time and Socrata metadata in `_ingest_meta`.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "capital.duckdb"

# dataset id -> (table name, {socrata auto-suffixed column -> meaningful name})
TABLES = {
    "fb86-vt7u": ("project_budget_schedule", {
        "spend_to_date_1": "spend_to_date_pct",
        "actual_construction": "actual_construction_procurement_start",
        "actual_construction_1": "actual_construction_procurement_end",
    }),
    "gyhf-rsr3": ("budget_spend_by_fy", {}),
    "qj5n-h5qp": ("budget_history", {
        "spend_to_date_1": "spend_to_date_pct",
        "budget_variance_1": "budget_variance_pct",
    }),
    "95tx-snak": ("schedule_history", {}),
}


def main() -> int:
    if not RAW_DIR.exists() or not any(RAW_DIR.glob("*.csv")):
        print("No raw data; run pipeline/fetch.py first", file=sys.stderr)
        return 1
    con = duckdb.connect(str(DB_PATH))
    con.execute("create or replace table _ingest_meta (dataset_id varchar, table_name varchar, "
                "source_name varchar, source_rows_updated_at timestamp, remote_count bigint, "
                "loaded_rows bigint, loaded_at timestamp)")
    for ds, (table, renames) in TABLES.items():
        csv = RAW_DIR / f"{ds}.csv"
        meta = json.loads((RAW_DIR / f"{ds}.meta.json").read_text())
        con.execute(f"create or replace table {table} as "
                    f"select * from read_csv('{csv}', sample_size=-1)")
        for old, new in renames.items():
            con.execute(f'alter table {table} rename column {old} to {new}')
        n = con.execute(f"select count(*) from {table}").fetchone()[0]
        updated = datetime.fromtimestamp(meta["rowsUpdatedAt"], timezone.utc).replace(tzinfo=None)
        con.execute("insert into _ingest_meta values (?,?,?,?,?,?,now())",
                    [ds, table, meta["name"], updated, meta["_remote_count"], n])
        flag = "" if n == meta["_remote_count"] else "  <-- COUNT MISMATCH"
        print(f"{table}: {n} rows (remote {meta['_remote_count']}){flag}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
