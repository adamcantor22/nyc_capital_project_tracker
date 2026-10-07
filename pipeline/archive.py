"""Past versions of an Open Data dataset's official export, from Internet Archive captures.

Open Data keeps only a dataset's current state. The Internet Archive captured some datasets' official exports
(data.cityofnewyork.us/api/views/<id>/rows.csv or rows.json) at irregular times. Each capture is the publisher's
own file, unchanged; the archive is only where it is kept. Every distinct capture is downloaded once and checked
against the SHA-1 digest the archive recorded for it, so the file is byte for byte what was captured (stored after
undoing any gzip encoding the capture was served with).

`fetch()` writes <out>/<dataset>-<capture timestamp>.<csv|json> and index.json, one entry per file: the capture
timestamp, original URL, archive URL, digest (base32 SHA-1), row count, columns and when it was retrieved. Files
already present are skipped, so re-runs make one index request per dataset. Only whole exports are taken: SODA
calls (resource/<id>.csv) return the first 1,000 rows, and formatted variants (&format=true) repeat a version.
"""
import base64
import csv
import datetime
import gzip
import hashlib
import io
import json
import sys
import time
from pathlib import Path

import httpx

from socrata import RetryTransport

csv.field_size_limit(sys.maxsize)  # polygon exports hold WKT longer than the default limit
CDX = "https://web.archive.org/cdx/search/cdx"


def sha1_base32(data: bytes) -> str:
    """The archive's digest format: base32 of the payload's SHA-1."""
    return base64.b32encode(hashlib.sha1(data).digest()).decode()


def exports(dataset: str, formats: tuple[str, ...]) -> set[str]:
    """The original URLs of a dataset's whole export, as the archive records them (scheme stripped)."""
    base = f"data.cityofnewyork.us/api/views/{dataset}/rows"
    return {f"{base}.{f}{q}" for f in formats for q in ("", "?accessType=DOWNLOAD")}


def strip_scheme(url: str) -> str:
    return url.split("://", 1)[-1].removeprefix("www.")


def parse(data: bytes, ext: str) -> tuple[list[str], int]:
    """(columns, row count) of an export: CSV header names, or a JSON export's field names."""
    if ext == "csv":
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        return (rows[0] if rows else []), max(len(rows) - 1, 0)
    doc = json.loads(data)
    return [c["fieldName"] for c in doc["meta"]["view"]["columns"]], len(doc["data"])


def fetch(dataset: str, out: Path, formats: tuple[str, ...] = ("csv",), pause: float = 0.0) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    index_path = out / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else []
    have = {e["digest"] for e in index if e["dataset"] == dataset}
    wanted = exports(dataset, formats)
    with httpx.Client(transport=RetryTransport(httpx.HTTPTransport()), timeout=300, follow_redirects=False) as c:
        r = c.get(CDX, params={"url": f"data.cityofnewyork.us/api/views/{dataset}/rows.", "matchType": "prefix",
                               "output": "json", "fl": "timestamp,original,statuscode,digest",
                               "filter": "statuscode:200"})
        r.raise_for_status()
        captures = [row for row in r.json()[1:] if strip_scheme(row[1]) in wanted]
        first = {}  # digest -> earliest capture with that content
        for ts, original, _, digest in sorted(captures):
            first.setdefault(digest, (ts, original))
        for digest, (ts, original) in sorted(first.items(), key=lambda kv: kv[1][0]):
            if digest in have:
                continue
            ext = "json" if "/rows.json" in original else "csv"
            name = f"{dataset}-{ts}.{ext}"
            url = f"https://web.archive.org/web/{ts}id_/{original}"
            with c.stream("GET", url) as resp:
                if resp.is_redirect:  # the archive points to a different capture: no payload stored at this one
                    print(f"{name}: redirected to {resp.headers.get('location')}, skipped")
                    continue
                resp.raise_for_status()
                raw = b"".join(resp.iter_raw())
            time.sleep(pause)
            # The archive's digest is of the payload as captured. A capture stored gzipped matches before decoding;
            # one the archive gzips only in transit matches after. The content-encoding header doesn't tell them apart.
            gzipped = raw[:2] == b"\x1f\x8b"
            data = gzip.decompress(raw) if gzipped else raw
            if digest not in (sha1_base32(raw), sha1_base32(data)):
                print(f"{name}: digest mismatch, skipped")
                continue
            columns, n = parse(data, ext)
            (out / name).write_bytes(data)
            index.append({"file": name, "dataset": dataset, "captured": ts, "original_url": original,
                          "archive_url": url, "digest": digest, "gzipped": gzipped, "rows": n, "columns": columns,
                          "retrieved_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")})
            index.sort(key=lambda e: (e["captured"], e["dataset"]))
            index_path.write_text(json.dumps(index, indent=1))
            print(f"{name}: {n:,} rows, {len(columns)} columns")
    return index
