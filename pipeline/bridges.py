"""Place bridge projects by the Bridge Identification Number (BIN) in their text.

DOT and DDC bridge projects often quote the NYS BIN: 'BIN 2229579', '2-24013-7', 'BIN# 224501B',
'(2232000)', 'BINS: 2241139, 2243410'. NYC DOT's Bridge Ratings dataset (`4yue-vjfc`) gives each BIN's
coordinates. A BIN is an official identifier joined exactly to an official location, so
pipeline/locations.py uses these points as a Tier A source (`bridge_bin`). A bare 7-character number
counts only when it is a known BIN and the text mentions a bridge. Writes `bridge_matches`: one row
per project and BIN.
Run after pipeline/ingest.py and before pipeline/locations.py.
"""
import re
import sys

import duckdb

from db import DB_PATH, replace_table

BIN = r"[12]\d{5}[0-9A-Z]"
ANY_BIN = rf"(?:{BIN}|[12]-\d{{5}}-[0-9A-Z])"  # '2229579' or '2-24013-7'
KEYED = re.compile(rf"\bBINS?(?:\b|(?=\d))[\s#:.]*({ANY_BIN}(?:[\s,;&]+(?:AND\s+)?{ANY_BIN})*)"
                   rf"|\bBR\s*#\s*([12]-\d{{5}}-[0-9A-Z])|#\s*({BIN})\b|\(({BIN})\)")
HYPHENATED = re.compile(r"\b([12])-(\d{5})-([0-9A-Z])\b")
BARE = re.compile(rf"\b({BIN})\b")
BRIDGE_WORDS = re.compile(r"\b(?:BRIDGES?|BR|BRS|OVER|VIADUCT|OVERPASS|UNDERPASS|BIN|BINS|OVERBUILD)\b")


def parse_bins(text: str, known: set[str]) -> list[str]:
    """BINs named in project text, normalised to 7 characters and in order of first mention."""
    t = text.upper()
    found = []
    for m in KEYED.finditer(t):
        for g in m.groups():
            if g:
                found += [b.replace("-", "") for b in re.findall(ANY_BIN, g)]
    found += ["".join(m.groups()) for m in HYPHENATED.finditer(t)]
    if BRIDGE_WORDS.search(t):
        found += [b for b in BARE.findall(t) if b in known]
    return list(dict.fromkeys(found))


def main() -> int:
    con = duckdb.connect(str(DB_PATH))
    bridges = {b: (lon, lat, f"{carried} over {crossed}") for b, carried, crossed, lon, lat in
               con.execute("select bin, carried, crossed, lon, lat from ref_bridges").fetchall()}
    projects = con.execute("""
        select fms_id, arg_max(coalesce(agency_project_name, '') || ' | ' || coalesce(fms_project_name, '')
                               || ' | ' || coalesce(agency_project_description, ''), reporting_period)
        from project_budget_schedule group by fms_id""").fetchall()
    out, unknown = [], 0
    for fms, text in projects:
        for b in parse_bins(text, set(bridges)):
            if b in bridges:
                lon, lat, label = bridges[b]
                out.append((fms, b, label, lon, lat))
            else:
                unknown += 1
    replace_table(con, "bridge_matches", "fms_id varchar, bin varchar, label varchar, lon double, lat double", out)
    print(f"BIN matches: {len(out)} ({len({o[0] for o in out})} projects); BINs not in Bridge Ratings: {unknown}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
