"""Shared Socrata helpers for the fetch scripts.

Downloads are skipped when the local copy matches the source's `rowsUpdatedAt`, so a refresh
with nothing new costs one small metadata request per dataset.
"""
import json
import os
from pathlib import Path

import httpx

from db import RAW_DIR, ROOT

BASE = "https://data.cityofnewyork.us"
PAGE = 50_000


def load_env(path: Path = ROOT / ".env") -> None:
    """Minimal KEY=VALUE loader so we don't need python-dotenv. Existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def client() -> httpx.Client:
    load_env()
    headers = {}
    if token := os.environ.get("SOCRATA_APP_TOKEN"):
        headers["X-App-Token"] = token
    return httpx.Client(timeout=120, follow_redirects=True, headers=headers)


def remote_meta(c: httpx.Client, ds: str) -> dict:
    r = c.get(f"{BASE}/api/views/{ds}.json")
    r.raise_for_status()
    return r.json()


def local_meta(ds: str) -> dict | None:
    p = RAW_DIR / f"{ds}.meta.json"
    return json.loads(p.read_text()) if p.exists() else None


def is_current(meta: dict, data_path: Path) -> bool:
    """True when we already hold the source's latest version."""
    local = local_meta(meta["id"])
    return (data_path.exists() and local is not None
            and local.get("rowsUpdatedAt") == meta.get("rowsUpdatedAt"))


def remote_count(c: httpx.Client, ds: str) -> int:
    r = c.get(f"{BASE}/resource/{ds}.json", params={"$select": "count(*)"})
    r.raise_for_status()
    return int(r.json()[0]["count"])


def save_meta(ds: str, meta: dict, total: int) -> None:
    meta["_remote_count"] = total
    (RAW_DIR / f"{ds}.meta.json").write_text(json.dumps(meta, indent=2))


def fetch_csv(c: httpx.Client, ds: str, dest: Path, total: int) -> None:
    tmp = dest.with_suffix(".csv.part")
    with tmp.open("wb") as f:
        for offset in range(0, total, PAGE):
            r = c.get(
                f"{BASE}/resource/{ds}.csv",
                params={"$limit": PAGE, "$offset": offset, "$order": ":id"},
            )
            r.raise_for_status()
            header, _, body = r.content.partition(b"\n")
            if offset == 0:
                f.write(header + b"\n")
            f.write(body)
    tmp.replace(dest)


def fetch_json(c: httpx.Client, ds: str, dest: Path, total: int, select: list[str] | None = None) -> int:
    """Page the JSON endpoint (geometry columns arrive as GeoJSON) into one JSON array file.
    `select` limits the download to the columns we use."""
    rows: list[dict] = []
    params = {"$limit": PAGE, "$order": ":id"}
    if select:
        params["$select"] = ",".join(select)
    for offset in range(0, total, PAGE):
        r = c.get(f"{BASE}/resource/{ds}.json", params={**params, "$offset": offset})
        r.raise_for_status()
        rows.extend(r.json())
    tmp = dest.with_suffix(".json.part")
    tmp.write_text(json.dumps(rows))
    tmp.replace(dest)
    return len(rows)
