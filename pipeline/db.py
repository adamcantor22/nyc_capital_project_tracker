"""Shared DuckDB paths and helpers."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "capital.duckdb"


def replace_table(con, table: str, ddl: str, rows: list[tuple]) -> None:
    """(Re)create `table` from Python tuples. Bulk-loads via newline-delimited JSON;
    DuckDB's executemany is far too slow at tens of thousands of rows."""
    con.execute(f"create or replace table {table} ({ddl})")
    if not rows:
        return
    cols = dict(c.split() for c in ddl.split(","))
    tmp = RAW_DIR / f"{table}.ndjson.tmp"
    with tmp.open("w") as f:
        for row in rows:
            f.write(json.dumps(dict(zip(cols, row))) + "\n")
    con.execute(f"insert into {table} select * from read_json(?, columns={cols!r})", [str(tmp)])
    tmp.unlink()
