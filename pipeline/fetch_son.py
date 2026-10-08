"""Citywide Statement of Needs for City Facilities (DCP, City Charter section 204) -> data/raw/son.

One PDF per edition, fiscal years 2015-16 to 2026-27, each fetched once (--force refetches). The index
(data/raw/son/index.json) records each edition's URL, fetch time, size and SHA-1, so a parsed proposal can be
traced to the exact file. The Statement lists each proposed facility with its Area Served (Local, Regional or
Citywide), which son.py parses.
"""
import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime

import httpx

from db import RAW_DIR
from socrata import RetryTransport

OUT = RAW_DIR / "son"
BASE = "https://www.nyc.gov/assets/planning/download/pdf/about/publications/son_{}_{}.pdf"
EDITIONS = [(y, y + 1) for y in range(15, 27)]  # fiscal years 20YY-20YY+1


def edition_id(first: int, second: int) -> str:
    return f"son_{first}_{second}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="refetch editions already held")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    index_path = OUT / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    headers = {"User-Agent": "Mozilla/5.0 (nyc-capital-project-tracker)"}
    with httpx.Client(transport=RetryTransport(httpx.HTTPTransport()), timeout=120, follow_redirects=True,
                      headers=headers) as c:
        for first, second in EDITIONS:
            eid = edition_id(first, second)
            path = OUT / f"{eid}.pdf"
            if path.exists() and eid in index and not args.force:
                continue
            url = BASE.format(first, second)
            r = c.get(url)
            r.raise_for_status()
            if not r.content.startswith(b"%PDF"):
                print(f"{eid}: not a PDF ({r.headers.get('content-type')}), skipped", file=sys.stderr)
                continue
            path.write_bytes(r.content)
            index[eid] = {"url": url, "fiscal_years": f"20{first}-20{second}", "bytes": len(r.content),
                          "sha1": hashlib.sha1(r.content).hexdigest(),
                          "fetched_at": datetime.now(UTC).isoformat(timespec="seconds")}
            print(f"{eid}: {len(r.content):,} bytes")
    index_path.write_text(json.dumps(index, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
