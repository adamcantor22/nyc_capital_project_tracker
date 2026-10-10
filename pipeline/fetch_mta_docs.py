"""MTA documents cited by curated rows -> data/raw/mta/docs.

Each PDF in DOCUMENTS is fetched once (--force refetches) from the MTA's document library. The index
(data/raw/mta/docs/index.json) records each one's URL, fetch time, size and SHA-1, so a cited page can be traced to the
exact file. The Interborough Express documents give its station list (ibx_stations.csv): the Draft Scoping Document's
Table 4 and the 2026 community board briefings, each naming the stations in its district. The Penn Station Access
Environmental Assessment's Executive Summary gives its four Bronx stations' locations (psa_stations.csv). Capital
program amendments and board action items give each plan's approvals and totals (mta_program_approvals.csv).
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
    "90206": "Penn Station Access Environmental Assessment and Section 4(f) Evaluation, Executive Summary, May 2021",
    "155616": "2010-2014 Capital Program Amendment No. 7, as proposed to the MTA Board October 30, 2024",
    "155486": "MTA Board action items, October 30, 2024 (capital plan amendments)",
    "156256": "2015-2019 Capital Program Amendment No. 6, as approved by the MTA Board October 30, 2024 and the CPRB "
              "December 9, 2024",
    "193401": "2020-2024 Capital Program Amendment #5, as approved by the MTA Board October 29, 2025 and the CPRB "
              "December 2, 2025",
    "174176": "MTA Board action items, May 28, 2025 (2025-2029 Capital Plan resubmission)",
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
