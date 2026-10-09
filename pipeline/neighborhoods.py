"""Named neighborhoods in project titles, resolved to DCP 2020 Neighborhood Tabulation Areas (NTAs).

Titles such as 'SEQ - Laurelton Area - Part 1' or 'Governors Island Electrical Substation' name an area
rather than a site. NTA names are split into their parts ('Manhattanville-West Harlem' -> MANHATTANVILLE,
WEST HARLEM) and matched as whole words in the project's borough. A part followed by a street, water,
park or facility word ('Bedford Ave', 'Gravesend Bay', 'Elmhurst Hospital') names that thing, not the
area. pipeline/locations.py places matches as Tier C, the neighborhood centroid, only for projects that
would otherwise fall to a district or borough centroid.
"""
import json
import re
from collections import defaultdict

from geo import haversine_m, mean_point

NOT_AREA = re.compile(
    r"\s*(?:AVE\b|AVENUE|ST\b|STREET|BLVD|BOULEVARD|PKWY|PARKWAY|EXPWY|EXPRESSWAY|EXPY|RD\b|ROAD|PL\b|PLACE|"
    r"TPKE|[NSEW]\b|BAY\b|CREEK|RIVER|CANAL|MEADOWS|HOSPITAL|HOUSES|PARK\b|PLAYGROUND|PLGD|LIBRARY|HEALTH|"
    r"HIGH SCHOOL|HS\b|BRIDGE|YARD|TUNNEL|CHANNEL|INLET|BASIN|LANDFILL|CEMETERY|PLAZA|GREENWAY|ESPLANADE|"
    r"PIERS?\b|WATERFRONT|BEACH\b|STAGE|ARMORY|WPCP|WRRF|COURTHOUSE|HILL PARK|MEER|LITTLE LEAGUE|BUILDING|"
    r"OVER\b)")
NOT_AREA_BEFORE = re.compile(r"\bGRAND\s+$")  # 'Grand Concourse' is the street, not Concourse
STOP = {"GREEN"}            # parts of non-neighborhood names ('Green-Wood Cemetery')
SKIP_AGENCIES = {"DOT", "DEP"}  # validation: their neighborhood words are mostly corridors, bays and plants
MAX_SPREAD_M = 3000         # several named neighborhoods must be this close to share one centroid
CDTA_BORO = {"MN": 1, "BX": 2, "BK": 3, "QN": 4, "SI": 5}
# Neighborhood abbreviations as project titles use them, each checked against the titles ('LIC: Lump Sum', 'ENY:
# Capital Improvements'); DCP's own abbreviations (ntaabbrev, 'Grnpt') are map labels titles never use. Left out:
# PLG (titles mean playground), RI (Rikers Island in DOC titles), UES and UWS (unused).
ABBREVIATIONS = {"LIC": "LONG ISLAND CITY", "ENY": "EAST NEW YORK", "BED-STUY": "BEDFORD STUYVESANT",
                 "BEDSTUY": "BEDFORD STUYVESANT", "FIDI": "FINANCIAL DISTRICT"}
CITYWIDE = "Citywide"


class NeighborhoodIndex:
    def __init__(self, rows):
        """rows: (nta, name, borough, cdta, lon, lat, geojson)."""
        self.ntas = {}
        self.parts = defaultdict(set)  # (borough, part) -> NTA codes
        for nta, name, boro, cdta, lon, lat, gj in rows:
            cd = CDTA_BORO[cdta[:2]] * 100 + int(cdta[2:]) if cdta else None
            self.ntas[nta] = (name, boro, cd, lon, lat, json.loads(gj) if gj else None)
            for part in re.sub(r"\s*\(.*?\)", "", name).split("-"):
                part = part.strip().upper()
                if len(part) >= 4 and part not in STOP:
                    self.parts[(boro, part)].add(nta)

    def match(self, title: str, boro: str) -> tuple[list[str], set[str]]:
        """(parts named, NTA codes). A part counts only if no occurrence of it names a street etc.;
        a part inside a longer matched part ('HARLEM' in 'EAST HARLEM') is dropped."""
        t = title.upper()
        for short, full in ABBREVIATIONS.items():
            t = re.sub(rf"(?<![A-Z0-9-]){re.escape(short)}(?![A-Z0-9-])", full, t)
        found = []
        for (b, part), ntas in self.parts.items():
            if b != boro:
                continue
            ms = list(re.finditer(rf"\b{re.escape(part)}\b", t))
            if ms and (part.endswith(" PARK") or not any(
                    NOT_AREA.match(t, m.end()) or NOT_AREA_BEFORE.search(t[:m.start()]) for m in ms)):
                found.append((part, ntas))
        found = [(p, n) for p, n in found if not any(p != q and p in q for q, _ in found)]
        return sorted(p for p, _ in found), set().union(*(n for _, n in found)) if found else set()

    def locate(self, title: str, boro: str, districts: list[int]):
        """(lon, lat, n, spread_m, label, NTA codes) for the named neighborhood(s), or None. Rejected when the
        neighborhoods are far apart or lie outside every community district the project lists."""
        parts, ntas = self.match(title, boro)
        if boro == CITYWIDE:  # no borough listed: a neighborhood name found in one borough only
            hits = [(b, self.match(title, b)[1]) for b in {b for b, _ in self.parts}]
            hits = [(b, n) for b, n in hits if n]
            ntas = hits[0][1] if len(hits) == 1 else set()
        if not ntas:
            return None
        if districts and not any(self.ntas[n][2] in districts for n in ntas):
            return None
        pts = [self.ntas[n][3:5] for n in sorted(ntas)]
        spread = max((haversine_m(a[1], a[0], b[1], b[0]) for a in pts for b in pts), default=0)
        if spread > MAX_SPREAD_M:
            return None
        lon, lat = mean_point(pts)
        return lon, lat, len(pts), round(spread), " / ".join(self.ntas[n][0] for n in sorted(ntas)), sorted(ntas)
