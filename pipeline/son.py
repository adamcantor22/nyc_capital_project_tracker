"""Citywide Statement of Needs proposals with their Area Served -> son_editions, son_proposals.

The Statement (DCP, City Charter section 204; fetched by fetch_son.py) lists each proposed new, expanded, reduced
or closed city facility with the area it serves. Editions to FY2019-20 use Local ("an area no larger than a
community district or community service district"), Regional ("two or more community districts or an entire
borough") and Citywide (son_17_18, p. 2); later editions use Community district, Borough and Citywide ("the
geography that the facility intends to serve", son_23_24). Both map to one `area_class`: local, regional or
citywide. "Regional - Citywide" is citywide.

Proposals are read from the PDFs' text by their field labels; a field's value is the rest of its line, or the next
lines when the line holds only the label. `page` is the PDF page (not the printed page number).
"""
import json
import re
import sys

import duckdb
import pypdf

from db import DB_PATH, RAW_DIR, replace_table

SON_DIR = RAW_DIR / "son"
LABELS = [  # longest first, so 'FACILITY TYPE' wins over 'FACILITY'
    "AREA SERVED", "FACILITY TYPE", "FACILITY DOMAIN", "PUBLIC FACING", "PUBLIC PURPOSE", "PROPOSED ACTION",
    "PROPOSED", "PROPOSAL", "AGENCY", "FACILITY", "DOMAIN", "LOCATION", "SIZE", "DCAS Project ID", "STATUS",
    "DCAS PROJECT ID", "FACILIY DOMAIN",  # as printed in son_25_26
    "SPACE USE TYPE", "SITING CRITERIA", "DESIRED DATE", "LAST", "FIRST", "APPEARED", "APPROVED",
]
LABEL = re.compile(r"^(" + "|".join(re.escape(x) for x in LABELS) + r")\b:?\s*(.*)$")
PAGE = re.compile(r"^=== page (\d+)$")
BOROUGHS = ("manhattan", "bronx", "brooklyn", "queens", "staten island", "stated island")


def area_class(raw: str | None) -> str | None:
    """Local, regional or citywide from an Area Served value, in either era's wording."""
    if not raw:
        return None
    s = raw.lower()
    if "citywide" in s or "city-wide" in s:
        return "citywide"
    if s.startswith(("regional", "region", "borough")):
        return "regional"
    if s.startswith(("local", "community district")) or re.search(r"\bcd\s*\d", s):
        return "local"
    if any(s.startswith(b) for b in BOROUGHS):
        return "regional"
    return None


def _label(line: str) -> tuple[str, str] | None:
    m = LABEL.match(line)
    return (m.group(1), m.group(2).strip()) if m else None


def _value(lines: list[str], i: int, rest: str) -> str:
    """The value of the label on line i: its rest plus following lines, up to a blank line or the next label."""
    parts = [rest] if rest else []
    j = i + 1
    if not rest:  # value on the next non-blank line
        while j < len(lines) and not lines[j]:
            j += 1
    while j < len(lines) and lines[j] and not _label(lines[j]) and not PAGE.match(lines[j]):
        parts.append(lines[j])
        j += 1
        if rest and len(parts) > 2:
            break
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def parse(text: str) -> list[dict]:
    """One row per Area Served entry, with the proposal and agency seen before it and the fields after it."""
    lines = [ln.strip() for ln in text.splitlines()]
    rows, page, proposal, agency = [], None, None, None
    for i, line in enumerate(lines):
        if m := PAGE.match(line):
            page = int(m.group(1))
            continue
        lab = _label(line)
        if not lab or line.split()[0].endswith(":") or (lab[0] != "AREA SERVED" and line.startswith(lab[0] + ":")):
            continue
        name, rest = lab
        if name == "PROPOSAL":
            proposal = _value(lines, i, rest)
        elif name == "AGENCY":
            agency = _value(lines, i, rest)
        elif name == "AREA SERVED" and not line.startswith("AREA SERVED:"):
            raw = _value(lines, i, rest)
            row = {"page": page, "proposal": proposal, "agency": agency, "area_served": raw,
                   "area_class": area_class(raw), "facility_type": None, "facility_domain": None}
            for k in range(i + 1, min(i + 12, len(lines))):
                nxt = _label(lines[k])
                if not nxt:
                    continue
                if nxt[0] in ("PROPOSAL", "AGENCY", "AREA SERVED"):
                    break
                if nxt[0] == "FACILITY TYPE":
                    row["facility_type"] = _value(lines, k, nxt[1])
                elif nxt[0] in ("FACILITY DOMAIN", "FACILIY DOMAIN", "DOMAIN"):
                    row["facility_domain"] = _value(lines, k, nxt[1])
            rows.append(row)
    return rows


def pdf_text(path) -> str:
    r = pypdf.PdfReader(path)
    return "\n".join(f"=== page {i + 1}\n{p.extract_text() or ''}" for i, p in enumerate(r.pages))


def main() -> int:
    index = json.loads((SON_DIR / "index.json").read_text())
    editions, proposals = [], []
    for eid, meta in sorted(index.items()):
        rows = parse(pdf_text(SON_DIR / f"{eid}.pdf"))
        editions.append((eid, meta["fiscal_years"], meta["url"], meta["sha1"], meta["fetched_at"], len(rows)))
        for n, r in enumerate(rows, 1):
            proposals.append((eid, n, r["page"], r["proposal"], r["agency"], r["area_served"], r["area_class"],
                              r["facility_type"], r["facility_domain"]))
        print(f"{eid}: {len(rows)} proposals, {sum(r['area_class'] is None for r in rows)} without a class")
    con = duckdb.connect(str(DB_PATH))
    replace_table(con, "son_editions", "edition varchar, fiscal_years varchar, url varchar, sha1 varchar, "
                  "fetched_at varchar, n_proposals integer", editions)
    replace_table(con, "son_proposals", "edition varchar, entry integer, page integer, proposal varchar, "
                  "agency varchar, area_served varchar, area_class varchar, facility_type varchar, "
                  "facility_domain varchar", proposals)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
