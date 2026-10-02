"""Shared Socrata helpers for the fetch scripts."""
import json
from pathlib import Path

import httpx

BASE = "https://data.cityofnewyork.us"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PAGE = 50_000


def client() -> httpx.Client:
    return httpx.Client(timeout=120, follow_redirects=True)


def remote_count(c: httpx.Client, ds: str) -> int:
    r = c.get(f"{BASE}/resource/{ds}.json", params={"$select": "count(*)"})
    r.raise_for_status()
    return int(r.json()[0]["count"])


def save_meta(c: httpx.Client, ds: str, total: int) -> dict:
    r = c.get(f"{BASE}/api/views/{ds}.json")
    r.raise_for_status()
    meta = r.json()
    meta["_remote_count"] = total
    (RAW_DIR / f"{ds}.meta.json").write_text(json.dumps(meta, indent=2))
    return meta


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


def fetch_json(c: httpx.Client, ds: str, dest: Path, total: int) -> int:
    """Page the JSON endpoint (geometry columns arrive as GeoJSON) into one JSON array file."""
    rows: list[dict] = []
    for offset in range(0, total, PAGE):
        r = c.get(
            f"{BASE}/resource/{ds}.json",
            params={"$limit": PAGE, "$offset": offset, "$order": ":id"},
        )
        r.raise_for_status()
        rows.extend(r.json())
    tmp = dest.with_suffix(".json.part")
    tmp.write_text(json.dumps(rows))
    tmp.replace(dest)
    return len(rows)
