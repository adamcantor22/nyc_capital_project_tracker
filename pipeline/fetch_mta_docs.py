"""MTA documents cited by curated location rows -> data/raw/mta/docs.

Each PDF in DOCUMENTS is fetched once (--force refetches) from the MTA's document library. The index
(data/raw/mta/docs/index.json) records each one's URL, fetch time, size and SHA-1, so a cited page can be traced to the
exact file. The Interborough Express documents give its station list (ibx_stations.csv): the Draft Scoping Document's
Table 4 and the 2026 community board briefings, each naming the stations in its district.
"""
import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime

import httpx

from db import RAW_DIR
from socrata import RetryTransport

OUT = RAW_DIR / "mta" / "docs"
URL = "https://www.mta.info/document/{}"
DOCUMENTS = {
    "187036": "Interborough Express Draft Scoping Document, October 2025",
    "203446": "IBX community board briefing, Brooklyn CB 18, 2026-03-23",
    "203441": "IBX community board briefing, Queens CB 5, 2026-03-24",
    "204881": "IBX community board briefing, Brooklyn CB 14, 2026-03-26",
    "203436": "IBX community board briefing, Queens CB 4, 2026-03-31",
    "203961": "IBX community board briefing, Brooklyn CB 7, 2026-04-07",
    "203956": "IBX community board briefing, Brooklyn CB 10, 2026-04-13",
    "209791": "IBX community board briefing, Queens CB 2, 2026-05-05",
    "209766": "IBX community board briefing, Brooklyn CB 4, 2026-05-14",
    "209781": "IBX community board briefing, Brooklyn CB 12, 2026-05-26",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="refetch documents already held")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    index_path = OUT / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    # httpx's own user agent: the library answers 403 to some custom ones
    with httpx.Client(transport=RetryTransport(httpx.HTTPTransport()), timeout=120, follow_redirects=True) as c:
        for doc, label in DOCUMENTS.items():
            path = OUT / f"{doc}.pdf"
            if path.exists() and doc in index and not args.force:
                continue
            url = URL.format(doc)
            r = c.get(url)
            r.raise_for_status()
            if not r.content.startswith(b"%PDF"):
                print(f"{doc}: not a PDF ({r.headers.get('content-type')}), skipped", file=sys.stderr)
                continue
            path.write_bytes(r.content)
            index[doc] = {"url": url, "title": label, "bytes": len(r.content),
                          "sha1": hashlib.sha1(r.content).hexdigest(),
                          "fetched_at": datetime.now(UTC).isoformat(timespec="seconds")}
            print(f"{doc}: {label}, {len(r.content):,} bytes")
    index_path.write_text(json.dumps(index, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
