"""Place bridge projects by the Bridge Identification Number (BIN) in their text.

DOT and DDC bridge projects often quote the NYS BIN: 'BIN 2229579', '2-24013-7', 'BIN# 224501B',
'(2232000)', 'BINS: 2241139, 2243410'. NYC DOT's Bridge Ratings dataset (`4yue-vjfc`) gives each BIN's
coordinates. A BIN is an official identifier joined exactly to an official location, so
pipeline/locations.py uses these points as a Tier A source (`bridge_bin`). A bare 7-character number
counts only when it is a known BIN and the text mentions a bridge. Writes `bridge_matches`: one row
per project and BIN.

Also writes `bridge_inferred`, links to a bridge that are inferred rather than quoted, which locations.py
uses as Tier B:
  bridge_id    the BIN inside a DOT bridge FMS ID ('HBM245290' -> 2245290, the W 155 St footbridge), where
               it is a known BIN; when set, it was among the text's BINs for all 26 projects quoting both
  bridge_name  a bridge named in the title (else the description) by the road it carries, next to a bridge
               word ('E25TH STREET PEDESTRIAN BRIDGE', 'MADISON AVENUE BRIDGE') or before 'OVER'; what it
               crosses settles between bridges carrying the same road, a pedestrian bridge is preferred when
               the text says pedestrian, and a name whose remaining bridges lie over 500 m apart is dropped
               as ambiguous; each name left is a site
Run after pipeline/ingest.py and before pipeline/locations.py.
"""
import re
import sys

import duckdb

from db import DB_PATH, replace_table
from geo import haversine_m
from streets import normalize

BIN = r"[12]\d{5}[0-9A-Z]"
ANY_BIN = rf"(?:{BIN}|[12]-\d{{5}}-[0-9A-Z])"  # '2229579' or '2-24013-7'
KEYED = re.compile(rf"\bBINS?(?:\b|(?=\d))[\s#:.]*({ANY_BIN}(?:[\s,;&]+(?:AND\s+)?{ANY_BIN})*)"
                   rf"|\bBR\s*#\s*([12]-\d{{5}}-[0-9A-Z])|#\s*({BIN})\b|\(({BIN})\)")
HYPHENATED = re.compile(r"(?<![0-9-])([12])-(\d{5})-([0-9A-Z])\b")  # also glued to a word: 'HUD2-24140-9'
ONE_HYPHEN = re.compile(r"(?<![0-9-])([12])-(\d{6})(?![0-9-])")  # '2-075837': the second hyphen left out
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
        found += [b for b in ("".join(m.groups()) for m in ONE_HYPHEN.finditer(t)) if b in known]
    return list(dict.fromkeys(found))


ID_BIN = re.compile(r"(?<=\D)(\d{6})$")  # 'HBM245290': the BIN after its leading '2'
BOROUGHS = {"M": "Manhattan", "B": "Bronx", "K": "Brooklyn", "Q": "Queens", "R": "Staten Island"}
BRIDGE = r"(?:PED(?:ESTRIAN)? )?(?:BRIDGES?|BRDG|BRG|BR|OVERPASS)"
NOT_CARRIED = re.compile(r"\b(?:PED|PEDESTRIAN|BRDG|BRIDGE|BRG|BR|NB|SB|EB|WB|NTH|STH)\b|\(.*?\)")
AMBIGUOUS_M = 500
ORDINALS = {"FIRST": "1", "SECOND": "2", "THIRD": "3", "FOURTH": "4", "FIFTH": "5", "SIXTH": "6", "SEVENTH": "7",
            "EIGHTH": "8", "NINTH": "9", "TENTH": "10", "ELEVENTH": "11", "TWELFTH": "12"}


def fms_id_bin(fms: str, known: set[str]) -> str | None:
    """The BIN in a DOT bridge FMS ID, when it is a known BIN."""
    m = ID_BIN.search(fms) if fms.startswith("HB") else None
    return f"2{m.group(1)}" if m and f"2{m.group(1)}" in known else None


def bridge_text(text: str) -> str:
    """Normalised text with glued words split ('BridgeEast', 'Bridge3rd', 'E25TH') and ordinal words as
    numbers ('THIRD AVE' -> '3 AVE')."""
    t = re.sub(r"([a-z])([A-Z0-9])", r"\1 \2", text or "").upper()
    t = normalize(re.sub(r"\b([EWNS])(\d+(?:ST|ND|RD|TH)?)\b", r"\1 \2", t))
    return " ".join(ORDINALS.get(w, w) for w in t.split())


class BridgeIndex:
    """NYC DOT bridges by the name of the road they carry: a named bridge by its whole name ('MADISON AVE
    BRIDGE'), others by the road alone ('E 25 ST' for 'E 25TH ST PED BRDG')."""

    def __init__(self, rows):
        self.bridges = []
        for b, boro, carried, crossed, lon, lat in rows:
            words = carried.upper().split()
            named = "BRIDGE" in words and "PED" not in words
            text = bridge_text(re.sub(r"\(.*?\)", " ", carried))
            name = " ".join((text if named else NOT_CARRIED.sub(" ", text)).split())
            if not name or name.isdigit():
                continue
            crosses = NOT_CARRIED.sub(" ", normalize(crossed)).split()[:1]
            self.bridges.append({"bin": b, "boroughs": {BOROUGHS[c] for c in boro if c in BOROUGHS}, "name": name,
                                 "road": name.removesuffix(" BRIDGE"),
                                 "named": named, "crosses": crosses, "ped": "PED" in words, "lon": lon, "lat": lat,
                                 "label": f"{carried} over {crossed}"})

    def match(self, text: str, borough: str | None) -> list[dict]:
        t = bridge_text(text)
        if not re.search(rf"\b{BRIDGE}\b|\bOVER\b", t):
            return []
        after = t.split(" OVER ", 1)[1] if " OVER " in t else ""
        here = [br for br in self.bridges if borough not in BOROUGHS.values() or borough in br["boroughs"]]
        roads = set()
        for br in here:
            pat = re.escape(br["name"])
            if br["named"]:
                hit = re.search(rf"(?<!FORT )\b{pat}\b(?! PARK)", t)  # not Fort Washington, Brooklyn Bridge Park
            else:
                hit = re.search(rf"\b{pat} {BRIDGE}\b|\b{pat} OVER\b", t)
            if hit:
                roads.add(br["road"])
        # every bridge carrying a named road is a candidate: '3RD AVE BR' may be the Third Avenue Bridge or
        # Third Avenue over the CSX line
        by_name = {road: [br for br in here if br["road"] == road] for road in roads}
        out = []
        for cands in by_name.values():
            crossing = [c for c in cands if c["crosses"] and re.search(rf"\b{re.escape(c['crosses'][0])}\b", after)]
            cands = crossing or cands
            if re.search(r"\bPED(?:ESTRIAN)?\b", t) and any(c["ped"] for c in cands):
                cands = [c for c in cands if c["ped"]]
            if max(haversine_m(a["lat"], a["lon"], b["lat"], b["lon"]) for a in cands for b in cands) <= AMBIGUOUS_M:
                out += list({c["bin"]: c for c in cands}.values())
        return out


def main() -> int:
    con = duckdb.connect(str(DB_PATH))
    bridges = {b: (lon, lat, f"{carried} over {crossed}") for b, carried, crossed, lon, lat in
               con.execute("select bin, carried, crossed, lon, lat from ref_bridges").fetchall()}
    projects = con.execute("""
        select fms_id, arg_max(coalesce(agency_project_name, '') || ' | ' || coalesce(fms_project_name, ''),
                               reporting_period),
               arg_max(coalesce(agency_project_description, ''), reporting_period), arg_max(borough, reporting_period)
        from project_budget_schedule group by fms_id""").fetchall()
    index = BridgeIndex(con.execute("select bin, boro, carried, crossed, lon, lat from ref_bridges").fetchall())
    out, inferred, unknown = [], [], 0
    for fms, title, description, borough in projects:
        if b := fms_id_bin(fms, set(bridges)):
            inferred.append((fms, b, bridges[b][2], "bridge_id", f"FMS ID {fms}", bridges[b][0], bridges[b][1]))
        else:
            # the description only for a title about bridges: descriptions name bridges in passing
            fields = [("title", title)] + [("description", description)] * bool(BRIDGE_WORDS.search(title.upper()))
            for field, t in fields:
                if found := index.match(t, borough):
                    inferred += [(fms, br["bin"], br["label"], "bridge_name", f"{field}: {t[:200]}", br["lon"],
                                  br["lat"]) for br in found]
                    break
        for b in parse_bins(f"{title} | {description}", set(bridges)):
            if b in bridges:
                lon, lat, label = bridges[b]
                out.append((fms, b, label, lon, lat))
            else:
                unknown += 1
    replace_table(con, "bridge_matches", "fms_id varchar, bin varchar, label varchar, lon double, lat double", out)
    replace_table(con, "bridge_inferred", "fms_id varchar, bin varchar, label varchar, rule varchar, "
                  "evidence varchar, lon double, lat double", inferred)
    print(f"BIN matches: {len(out)} ({len({o[0] for o in out})} projects); BINs not in Bridge Ratings: {unknown}; "
          f"inferred: {len(inferred)} ({len({o[0] for o in inferred})} projects)")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
