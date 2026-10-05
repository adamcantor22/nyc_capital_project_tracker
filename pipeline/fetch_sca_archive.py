"""Past versions of SCA's capital project schedules and budgets (2xh6-psuq), from Internet Archive captures.

Open Data keeps only a dataset's current state, and our own dated copies (data/raw/sca/) start in August 2026.
The Internet Archive captured the dataset's official CSV export (data.cityofnewyork.us/api/views/2xh6-psuq/
rows.csv) at irregular times since 2014. Each capture is SCA's own file, unchanged; the archive is only where
it is kept. Every distinct capture is downloaded once and checked against the SHA-1 digest the archive recorded
for it, so the file is byte for byte what was captured
(stored after undoing any gzip encoding the capture was served with).

Writes data/raw/sca/archive/2xh6-psuq-<capture timestamp>.csv and index.json, one entry per file: the capture
timestamp, original URL, archive URL, digest (base32 SHA-1), row count, columns and when it was retrieved.
Files already
present are skipped, so re-runs make one index request.
"""
import base64
import csv
import datetime
import gzip
import hashlib
import io
import json
import sys

import httpx

from db import RAW_DIR
from socrata import RetryTransport

DATASET = "2xh6-psuq"
ORIGINAL = f"data.cityofnewyork.us/api/views/{DATASET}/rows.csv"
CDX = "https://web.archive.org/cdx/search/cdx"
OUT = RAW_DIR / "sca" / "archive"


def sha1_base32(data: bytes) -> str:
    """The archive's digest format: base32 of the payload's SHA-1."""
    return base64.b32encode(hashlib.sha1(data).digest()).decode()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    index_path = OUT / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else []
    have = {e["digest"] for e in index}
    with httpx.Client(transport=RetryTransport(httpx.HTTPTransport()), timeout=120, follow_redirects=False) as c:
        r = c.get(CDX, params={"url": ORIGINAL, "matchType": "prefix", "output": "json",
                               "fl": "timestamp,original,statuscode,digest", "filter": "statuscode:200"})
        r.raise_for_status()
        captures = r.json()[1:]
        first = {}  # digest -> earliest capture with that content
        for ts, original, _, digest in sorted(captures):
            first.setdefault(digest, (ts, original))
        for digest, (ts, original) in sorted(first.items(), key=lambda kv: kv[1][0]):
            if digest in have:
                continue
            url = f"https://web.archive.org/web/{ts}id_/{original}"
            with c.stream("GET", url) as resp:
                if resp.is_redirect:  # the archive points to a different capture: no payload stored at this one
                    print(f"{ts}: redirected to {resp.headers.get('location')}, skipped")
                    continue
                resp.raise_for_status()
                raw = b"".join(resp.iter_raw())
                gzipped = resp.headers.get("content-encoding") == "gzip"
            # The archive's digest is of the payload as captured, before any content encoding is undone.
            if sha1_base32(raw) != digest:
                print(f"{ts}: digest mismatch, skipped")
                continue
            data = gzip.decompress(raw) if gzipped else raw
            rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
            name = f"{DATASET}-{ts}.csv"
            (OUT / name).write_bytes(data)
            index.append({"file": name, "dataset": DATASET, "captured": ts, "original_url": original,
                          "archive_url": url, "digest": digest, "gzipped": gzipped,
                          "rows": len(rows) - 1, "columns": rows[0] if rows else [],
                          "retrieved_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")})
            print(f"{ts}: {len(rows) - 1:,} rows, {len(rows[0]) if rows else 0} columns")
    index.sort(key=lambda e: e["captured"])
    index_path.write_text(json.dumps(index, indent=1))
    print(f"{len(index)} archived versions in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
