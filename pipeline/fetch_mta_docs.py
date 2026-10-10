"""MTA documents cited by curated rows -> data/raw/mta/docs.

Each PDF in DOCUMENTS is fetched once (--force refetches) from the MTA's document library. The index
(data/raw/mta/docs/index.json) records each one's URL, fetch time, size and SHA-1, so a cited page can be traced to the
exact file. The Interborough Express documents give its station list (ibx_stations.csv): the Draft Scoping Document's
Table 4 and the 2026 community board briefings, each naming the stations in its district. The Penn Station Access
Environmental Assessment's Executive Summary gives its four Bronx stations' locations (psa_stations.csv). Capital
program amendments and board action items give each plan's approvals and totals (mta_program_approvals.csv).

Books MTA no longer serves (ARCHIVED: the 2015-19 adoption and Amendment #2, the 2010-14 December 2011 and December
2012 amendments) are taken from Internet Archive captures of MTA's own files (web.mta.info/capital/pdf), each
checked against the SHA-1 digest the archive recorded for it and refused on a mismatch; the index records the
original URL, the capture time and the archive URL. Their keys are slugs, never an mta.info document number.
"""
import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime

import httpx

from archive import sha1_base32
from db import RAW_DIR
from socrata import RetryTransport

OUT = RAW_DIR / "mta" / "docs"
URL = "https://www.mta.info/document/{}"
WAYBACK = "https://web.archive.org/web/{}{}/{}"  # capture timestamp, "id_" for the file as captured, original URL
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
    "90206": "Penn Station Access Environmental Assessment and Section 4(f) Evaluation, Executive Summary, May 2021",
    "156271": "2010-2014 Capital Program Amendment No. 7, as approved by the MTA Board October 30, 2024 and the CPRB "
              "December 9, 2024",
    "156256": "2015-2019 Capital Program Amendment No. 6, as approved by the MTA Board October 30, 2024 and the CPRB "
              "December 9, 2024",
    "193401": "2020-2024 Capital Program Amendment #5, as approved by the MTA Board October 29, 2025 and the CPRB "
              "December 2, 2025",
    "174176": "MTA Board action items, May 28, 2025 (2025-2029 Capital Plan resubmission)",
    "174186": "2025-2029 Capital Plan, The Future Rides With Us (the plan book, as resubmitted to the CPRB in 2025)",
    "10756": "2010-2014 Capital Program, as approved by the MTA Capital Program Review Board June 2010",
    "179731": "MTA Capital Program Committee meeting, July 2025 (minutes of the June 2025 meeting)",
    "2291": "2010-2014 Capital Program amendment, as approved by the MTA Board July 2013",
    "10781": "2010-2014 Capital Program amendment, as approved by the MTA Board May 24, 2017 and the CPRB July 31, "
             "2017",
    "10626": "2010-2014 Capital Program amendment, as proposed to the MTA Board September 25, 2019",
    "16641": "2015-2019 Capital Program Amendment No. 4, as approved by the MTA Board September 25, 2019 and the CPRB "
             "February 21, 2020",
    "91711": "2020-2024 Capital Program Amendment #2, draft as proposed to the MTA Board July 2022",
    "114171": "2020-2024 Capital Program Amendment #3, as approved by the MTA Board June 27, 2023 and the CPRB "
              "July 31, 2023",
}

# slug -> (title from the cover, original URL, capture timestamp)
ARCHIVED = {
    "ia-2015-19-adopted-2016": (
        "2015-2019 Capital Program, as approved by the MTA Board April 20, 2016 and the CPRB May 23, 2016",
        "http://web.mta.info/capital/pdf/ArchivalReports/2015-2019_Capital_Program/"
        "WEBApproved2015-2019Program-May2016.pdf", "20221108233008"),
    "ia-2015-19-amendment-2-2017": (
        "2015-2019 Capital Program Amendment No. 2, as proposed to the MTA Board May 2017",
        "http://web.mta.info/capital/pdf/WEB2015-2019Program_reduced.pdf", "20170606060700"),
    "ia-2010-14-amendment-2011": (
        "2010-2014 Capital Program amendment, as submitted to the MTA Capital Program Review Board January 2012",
        "http://web.mta.info:80/capital/pdf/ArchivalReports/2010%E2%80%932014_Capital_Program/"
        "WEBApproved2015-2019Program-December2011.pdf", "20190204041109"),
    "ia-2010-14-sandy-2012": (
        "2010-2014 Capital Program amendment for Hurricane Sandy recovery, as submitted to the MTA Board December 2012",
        "http://web.mta.info:80/capital/pdf/ArchivalReports/2010%E2%80%932014_Capital_Program/"
        "WEBApproved2015-2019Program-December2012.pdf", "20190303163317"),
}


def url(doc: str) -> str:
    """Where a cited document can be read: MTA's library, or the archive's copy of a book MTA no longer serves."""
    if doc in ARCHIVED:
        _, original, ts = ARCHIVED[doc]
        return WAYBACK.format(ts, "", original)
    return URL.format(doc)


def fetch_archived(c: httpx.Client, doc: str) -> tuple[bytes, dict]:
    """One archived book, checked against the archive's digest for that capture."""
    _, original, ts = ARCHIVED[doc]
    r = c.get("https://web.archive.org/cdx/search/cdx", params={
        "url": original, "from": ts, "to": ts, "output": "json", "fl": "timestamp,digest"})
    r.raise_for_status()
    digest = next(d for t, d in r.json()[1:] if t == ts)
    data = c.get(WAYBACK.format(ts, "id_", original)).content
    if sha1_base32(data) != digest:
        raise ValueError(f"{doc}: payload does not match the archive's digest {digest}")
    return data, {"original_url": original, "captured": ts, "digest": digest}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="refetch documents already held")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    index_path = OUT / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    # httpx's own user agent: the library answers 403 to some custom ones
    with httpx.Client(transport=RetryTransport(httpx.HTTPTransport()), timeout=120, follow_redirects=True) as c:
        for doc, label in DOCUMENTS.items() | {k: v[0] for k, v in ARCHIVED.items()}.items():
            path = OUT / f"{doc}.pdf"
            if path.exists() and doc in index and not args.force:
                continue
            extra = {}
            if doc in ARCHIVED:
                data, extra = fetch_archived(c, doc)
            else:
                r = c.get(URL.format(doc))
                r.raise_for_status()
                data = r.content
            if not data.startswith(b"%PDF"):
                print(f"{doc}: not a PDF, skipped", file=sys.stderr)
                continue
            path.write_bytes(data)
            index[doc] = {"url": url(doc), "title": label, "bytes": len(data), "sha1": hashlib.sha1(data).hexdigest(),
                          "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"), **extra}
            print(f"{doc}: {label}, {len(data):,} bytes")
    index_path.write_text(json.dumps(index, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
