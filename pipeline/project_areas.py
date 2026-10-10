"""Where each project's money counts in area measures (per resident by district or borough) -> project_areas.

One row per project, place and area: the share of the project's budget counted there, at the finest level both its
area-served class (serving.py, project_serving_units) and its location allow (CLAUDE.md, Totals and location
precision). A place is a site of the project (project_sites for city projects, the SCA building, MTA's units in
project_serving_units), each taking the unit's share times the site's share.

  outside   work at places outside the city: level `outside`, counted in no area measure; so is any site of a
            local or regional project outside the city (DCP's outline with water areas, serving.city_outline)
  citywide  level `citywide`, as is any local or regional work that is unplaced (no site)
  local     the community district of the site:
              Tier A or B  the district containing its point (`site_point`); a point in no district (a park,
                           airport or pier, which DCP's districts leave out) takes the nearest district the project's
                           record lists in that borough (`listed_district`), else the nearest one (`nearest_district`)
              Tier C       the district DCP nests the neighborhood in (its NTA's CDTA, `neighborhood_cdta`); a park
                           or airport NTA (CDTA numbered above the borough's districts) counts by borough
              Tier D       the listed district (`listed_district`), except DCAS energy projects whose boards are
                           placeholders (PLACEHOLDER_BOARDS: 'Brooklyn 01' whatever the site), which count by borough
              Tier E       the borough (`borough_only`)
  regional  the borough of the site (`site_borough`), except transit at stations, which counts in the districts its
            stations serve, spread by people:
              `riders_homes`       a subway station complex (ridership rules): where its morning riders live
                                   (ridership.py, subway_station_homes)
              `station_catchment`  stations not yet built (Second Avenue Subway, Penn Station Access, Interborough
                                   Express) or without origin-destination data (Staten Island Railway, LIRR and
                                   Metro-North stations in the city): the residents within 800 m (ridership.catchment,
                                   2020 census); a station not yet built has no riders to measure
            Either is kept to the station's own boroughs (those holding AREA_MIN of its catchment), with Brooklyn and
            Queens counted as one, since riders near their long land border live on either side of it. Depots and
            bus work serve routes, not a walk-up area, and count by borough.

Shares sum to 1 per project. Each row names the method and the site it came from (`evidence`).

area_population: the 2020 census population (census.py, ref_tract_population) of each district, borough and the
city, with the same district outlines as the money: each tract's people are split over the districts by the share
of its area in each (sampled on a POP_GRID_M grid; tracts too small to be sampled go whole to the district holding
their label point), so the districts sum exactly to their boroughs and the city.
"""
import json
import re
import sys
from collections import defaultdict
from functools import cache

import duckdb

from db import DB_PATH, RAW_DIR, replace_table
from geo import label_point
from locations import parse_districts
from ridership import AREA_MIN, M_LAT, area_m2, catchment, district_of, grid_index, lookup, m_lon
from serving import city_outline, in_city

CDTA_BOROUGH = {"MN": "1", "BX": "2", "BK": "3", "QN": "4", "SI": "5"}
PLACEHOLDER_BOARDS = re.compile(r"^(ACE|SOLAR|EO26)")  # docs/future-plans.md, Placeholder community boards
LEVELS = ("district", "borough", "citywide", "outside")
CATCHMENT_RULES = {"second-avenue-subway", "penn-station-access", "interborough-express", "sir", "lirr-stations",
                   "mnr-stations"}  # serving_rules.csv: stations not yet built or without origin-destination data
JOINED_BOROUGHS = {"Brooklyn", "Queens"}
TRACTS = "63ge-mke6"
POP_GRID_M = 100
POP_SOURCE = ("2020 census P1_001N per tract (ref_tract_population), tracts 63ge-mke6 split over community districts "
              "5crt-au7u by area")


class Geography:
    def __init__(self, con):
        self.cds = [(str(cd), boro, json.loads(g)) for cd, boro, g in
                    con.execute("select boro_cd, borough, geojson from ref_community_districts").fetchall()]
        self.districts = grid_index([(g, cd, boro) for cd, boro, g in self.cds])
        self.borough_of_cd = {cd: boro for cd, boro, _ in self.cds}
        self.ntas = grid_index([(json.loads(g), name, cdta) for name, cdta, g in
                                con.execute("select name, cdta, geojson from ref_ntas").fetchall()])
        self.outline = city_outline()

    @cache  # noqa: B019 (one Geography per run)
    def district(self, lon: float, lat: float) -> tuple[str | None, str]:
        """(district containing the point or None, its borough or the nearest district's)."""
        hit = lookup(self.districts, lon, lat)
        if hit:
            return hit[0], hit[1]
        return None, district_of(self.cds, lon, lat)[1]

    @cache  # noqa: B019
    def inside(self, lon: float, lat: float) -> bool:
        return in_city(self.outline, lon, lat)

    @cache  # noqa: B019
    def nearest(self, lon: float, lat: float, among: tuple[str, ...] = ()) -> str:
        """The nearest district (of `among`, when given) to a point in the city but in no district."""
        return district_of([c for c in self.cds if not among or c[0] in among], lon, lat)[0]

    def nta_district(self, lon: float, lat: float) -> tuple[str | None, str | None]:
        """(district DCP nests the NTA containing the point in, or None for a park NTA; '<name> (CDTA <code>)')."""
        hit = lookup(self.ntas, lon, lat)
        if not hit:
            return None, None
        name, cdta = hit
        cd = CDTA_BOROUGH[cdta[:2]] + cdta[2:]
        return (cd if cd in self.borough_of_cd else None), f"{name} (CDTA {cdta})"


class Transit:
    """Districts a regional transit unit counts in: {district: weight} summing to 1, and a note."""

    def __init__(self, con, geo: Geography):
        self.geo = geo
        self.homes: dict[int, dict[str, float]] = defaultdict(dict)
        for cid, area, riders in con.execute(
                "select complex_id, area, riders from subway_station_homes where kind = 'district'").fetchall():
            self.homes[cid][area] = riders
        self.users = {cid: (name, set(b.split(","))) for cid, name, b in con.execute(
            "select complex_id, name, own_boroughs from subway_station_users").fetchall()}
        pop = dict(con.execute("select geoid, population from ref_tract_population").fetchall())
        tracts = json.loads((RAW_DIR / f"{TRACTS}.json").read_text())
        self.tracts = grid_index([(t["the_geom"], pop.get(t["geoid"], 0) / (area_m2(t["the_geom"]) or 1))
                                  for t in tracts])

    def clip(self, weights: dict[str, float], own: set[str]) -> dict[str, float]:
        if own & JOINED_BOROUGHS:
            own = own | JOINED_BOROUGHS
        kept = {d: w for d, w in weights.items() if self.geo.borough_of_cd.get(d) in own and w > 0}
        total = sum(kept.values())
        return {d: w / total for d, w in kept.items()} if total else {}

    def riders(self, cid: int) -> tuple[dict[str, float], str]:
        name, own = self.users[cid]
        return (self.clip(self.homes.get(cid, {}), own),
                f"{name}: riders' homes (subway_station_homes), within {', '.join(sorted(own))}")

    @cache  # noqa: B019
    def residents(self, lon: float, lat: float) -> tuple[dict[str, float], str]:
        c = catchment(self.tracts, self.geo.districts, lon, lat)
        total = sum(c.values()) or 1.0
        by_boro: dict[str, float] = defaultdict(float)
        for (_, boro), v in c.items():
            by_boro[boro] += v / total
        own = {b for b, v in by_boro.items() if v >= AREA_MIN}
        by_cd: dict[str, float] = defaultdict(float)
        for (cd, _), v in c.items():
            by_cd[cd] += v
        return self.clip(by_cd, own), f"residents within 800 m (2020 census), within {', '.join(sorted(own))}"


def place(geo: Geography, cls: str, tier: str | None, lon, lat, placeholder: bool = False,
          borough: str | None = None, listed: tuple[str, ...] = ()) -> tuple[str, str | None, str, str]:
    """(level, area, method, note) for one site of a project of class `cls`."""
    if cls == "outside":
        return "outside", None, "outside", ""
    if cls == "citywide":
        return "citywide", None, "citywide", ""
    if lon is None or tier in (None, "Unplaced"):
        return ("borough", borough, "borough_only", "no site point") if borough else (
            "citywide", None, "unplaced", "no site")
    cd, boro = geo.district(lon, lat)
    if cd is None and tier not in ("C", "D", "E") and not geo.inside(lon, lat):
        return "outside", None, "site_outside_city", "point outside the city"
    if cls == "regional" or tier == "E":
        return "borough", boro, "borough_only" if tier == "E" else "site_borough", ""
    if tier == "C":
        ncd, note = geo.nta_district(lon, lat)
        return ("district", ncd, "neighborhood_cdta", note) if ncd else ("borough", boro, "borough_only", note)
    if tier == "D":
        if placeholder:
            return "borough", boro, "placeholder_board", "DCAS energy board is a placeholder"
        return "district", cd, "listed_district", ""
    if cd:
        return "district", cd, "site_point", ""
    if own := tuple(d for d in listed if geo.borough_of_cd.get(d) == boro):
        return "district", geo.nearest(lon, lat, own), "listed_district", "point in no district"
    return "district", geo.nearest(lon, lat), "nearest_district", "point in no district"


def units(con) -> dict[tuple[str, str], list[tuple]]:
    """(program, id) -> [(unit_no, share, class, lon, lat, rule_id, complex_id)] from project_serving_units."""
    out = defaultdict(list)
    for prog, pid, *u in con.execute("""select program, id, unit_no, share, area_class, lon, lat, rule_id, complex_id
            from project_serving_units order by 1, 2, 3""").fetchall():
        out[(prog, pid)].append(tuple(u))
    return out


def rows(con, geo: Geography, transit: Transit) -> list[tuple]:
    us = units(con)
    out = []

    def add(prog, pid, n, site, share, cls, tier, lon, lat, placeholder=False, borough=None, source=None, listed=()):
        level, area, method, note = place(geo, cls, tier, lon, lat, placeholder, borough, listed)
        parts = (f"site {site}" if site is not None else None,
                 f"Tier {tier}" if tier in ("A", "B", "C", "D", "E") else None, source, note)
        evidence = "; ".join(x for x in parts if x)
        out.append((prog, pid, n, site, cls, level, area, round(share, 6), method, evidence or None))

    sites = defaultdict(list)
    for f, i, tier, src, lon, lat, share in con.execute(
            "select fms_id, site_no, tier, source, lon, lat, share from project_sites order by 1, 2").fetchall():
        sites[f].append((i, tier, src, lon, lat, share))
    cd_codes = {b: int(cd) // 100 for cd, b, _ in geo.cds}
    known = {int(cd) for cd, _, _ in geo.cds}
    boroughs, boards = {}, {}
    for f, b, board in con.execute("""select fms_id, any_value(borough), any_value(community_board) from (
            select fms_id, borough, community_board from project_budget_schedule
            qualify reporting_period = max(reporting_period) over (partition by fms_id)) group by 1""").fetchall():
        boroughs[f] = b
        boards[f] = tuple(str(c) for c in parse_districts(board, cd_codes, known))
    for (prog, f), ulist in us.items():
        if prog != "nyc_capital":
            continue
        b = boroughs.get(f) if boroughs.get(f) in geo.borough_of_cd.values() else None
        for n, ushare, cls, *_ in ulist:
            for i, tier, src, lon, lat, share in sites.get(f) or [(None, None, None, None, None, 1.0)]:
                add(prog, f, n, i, ushare * share, cls, tier, lon, lat, bool(PLACEHOLDER_BOARDS.match(f)), b, src,
                    boards.get(f, ()))

    buildings = {k: r for k, *r in con.execute("""select p.project_key, b.tier, b.source, b.lon, b.lat, b.borough
            from sca_projects p left join sca_buildings b on b.building = p.building""").fetchall()}
    for (prog, key), ulist in us.items():
        if prog != "sca":
            continue
        tier, src, lon, lat, boro = buildings.get(key, (None,) * 5)
        for n, ushare, cls, *_ in ulist:
            add(prog, key, n, 1 if tier else None, ushare, cls, tier, lon, lat, borough=boro, source=src)

    mta = dict(((a, (b, t)) for a, b, t in con.execute("select acep, borough, tier from mta_locations").fetchall()))
    for (prog, acep), ulist in us.items():
        if prog != "mta":
            continue
        boro, tier = mta.get(acep, (None, None))
        for n, ushare, cls, lon, lat, rule, cid in ulist:
            spread = ((transit.riders(cid) if cid is not None and cid in transit.users
                       else transit.residents(lon, lat) if rule in CATCHMENT_RULES and lon is not None else ({}, ""))
                      if cls == "regional" else ({}, ""))
            if spread[0]:
                method = "riders_homes" if cid is not None else "station_catchment"
                for cd, w in sorted(spread[0].items()):
                    out.append((prog, acep, n, n, cls, "district", cd, round(ushare * w, 9), method,
                                f"site {n}; {spread[1]}"))
                continue
            add(prog, acep, n, n if lon is not None else None, ushare, cls,
                "point" if lon is not None else tier, lon, lat, borough=boro,
                source="project_serving_units point" if lon is not None else None)
    return out


def population(con, geo: Geography) -> list[tuple]:
    """[(level, area, population, method)] for every district, borough and the city."""
    pop = dict(con.execute("select geoid, population from ref_tract_population").fetchall())
    tracts = [t for t in json.loads((RAW_DIR / f"{TRACTS}.json").read_text()) if pop.get(t["geoid"])]
    index = grid_index([(t["the_geom"], t["geoid"]) for t in tracts])
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    x0, x1, y0, y1 = -74.27, -73.69, 40.49, 40.92
    dy, dx = POP_GRID_M / M_LAT, POP_GRID_M / m_lon((y0 + y1) / 2)
    y = y0
    while y < y1:
        x = x0
        while x < x1:
            if (t := lookup(index, x, y)) and (d := lookup(geo.districts, x, y)):
                counts[t[0]][d[0]] += 1
            x += dx
        y += dy
    by_cd: dict[str, float] = defaultdict(float)
    for t in tracts:
        c = counts.get(t["geoid"])
        if not c:
            c = {(lookup(geo.districts, *label_point(t["the_geom"])) or [district_of(geo.cds, *label_point(
                t["the_geom"]))[0]])[0]: 1}
        n = sum(c.values())
        for cd, k in c.items():
            by_cd[cd] += pop[t["geoid"]] * k / n
    by_boro: dict[str, float] = defaultdict(float)
    for cd, v in by_cd.items():
        by_boro[geo.borough_of_cd[cd]] += v
    return ([("district", cd, round(v), POP_SOURCE) for cd, v in sorted(by_cd.items())]
            + [("borough", b, round(v), POP_SOURCE) for b, v in sorted(by_boro.items())]
            + [("citywide", None, round(sum(by_cd.values())), POP_SOURCE)])


def main() -> int:
    con = duckdb.connect(str(DB_PATH))
    geo = Geography(con)
    out = rows(con, geo, Transit(con, geo))
    replace_table(con, "project_areas", "program varchar, id varchar, unit_no integer, site_no integer, "
                  "area_class varchar, level varchar, area varchar, share double, method varchar, evidence varchar",
                  out)
    replace_table(con, "area_population", "level varchar, area varchar, population integer, source varchar",
                  population(con, geo))
    for r in con.execute("""select program, level, method, count(distinct id), round(sum(share), 1)
                            from project_areas group by all order by 1, 2, 3""").fetchall():
        print(*r, sep="\t")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
