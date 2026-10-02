"""Download the four capital-project datasets from NYC Open Data (Socrata).

Writes data/raw/<id>.csv and data/raw/<id>.meta.json. Skips existing files unless --force.
"""
import argparse
import json
import sys
from pathlib import Path

import httpx

BASE = "https://data.cityofnewyork.us"
DATASETS = ["fb86-vt7u", "gyhf-rsr3", "qj5n-h5qp", "95tx-snak"]
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PAGE = 50_000


def remote_count(client: httpx.Client, ds: str) -> int:
    r = client.get(f"{BASE}/resource/{ds}.json", params={"$select": "count(*)"})
    r.raise_for_status()
    return int(r.json()[0]["count"])


def fetch_csv(client: httpx.Client, ds: str, dest: Path, total: int) -> None:
    tmp = dest.with_suffix(".csv.part")
    with tmp.open("wb") as f:
        for offset in range(0, total, PAGE):
            r = client.get(
                f"{BASE}/resource/{ds}.csv",
                params={"$limit": PAGE, "$offset": offset, "$order": ":id"},
            )
            r.raise_for_status()
            header, _, body = r.content.partition(b"\n")
            if offset == 0:
                f.write(header + b"\n")
            f.write(body)
    tmp.replace(dest)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="refetch existing files")
    args = ap.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for ds in DATASETS:
            csv_path = RAW_DIR / f"{ds}.csv"
            meta_path = RAW_DIR / f"{ds}.meta.json"
            if csv_path.exists() and not args.force:
                print(f"{ds}: exists, skipping")
                continue
            r = client.get(f"{BASE}/api/views/{ds}.json")
            r.raise_for_status()
            meta = r.json()
            meta["_remote_count"] = remote_count(client, ds)
            meta_path.write_text(json.dumps(meta, indent=2))
            fetch_csv(client, ds, csv_path, meta["_remote_count"])
            print(f"{ds}: {meta['name']} | remote rows={meta['_remote_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
