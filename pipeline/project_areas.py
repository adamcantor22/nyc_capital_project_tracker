"""Where each project's money counts in area measures (per resident by district or borough) -> project_areas.

One row per project, place and area: the share of the project's budget counted there, at the finest level both its
area-served class (serving.py, project_serving_units) and its location allow (CLAUDE.md, Totals and location
precision). A place is a site of the project (project_sites for city projects, the SCA building, MTA's units in
project_serving_units), each taking the unit's share times the site's share.

  outside   work at places outside the city: level `outside`, counted in no area measure
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
  regional  the borough of the site (`site_borough`)

Shares sum to 1 per project. Each row names the method and the site it came from (`evidence`).
"""
import json
import re
import sys
from collections import defaultdict
from functools import cache

import duckdb

from db import DB_PATH, replace_table
from locations import parse_districts
from ridership import district_of, grid_index, lookup
from serving import city_outline, in_city

CDTA_BOROUGH = {"MN": "1", "BX": "2", "BK": "3", "QN": "4", "SI": "5"}
PLACEHOLDER_BOARDS = re.compile(r"^(ACE|SOLAR|EO26)")  # docs/future-plans.md, Placeholder community boards
LEVELS = ("district", "borough", "citywide", "outside")


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
    def nearest(self, lon: float, lat: float, among: tuple[str, ...] = ()) -> str | None:
        """The nearest district (of `among`, when given) to a point in the city but in no district."""
        if not in_city(self.outline, lon, lat):
            return None
        return district_of([c for c in self.cds if not among or c[0] in among], lon, lat)[0]

    def nta_district(self, lon: float, lat: float) -> tuple[str | None, str | None]:
        """(district DCP nests the NTA containing the point in, or None for a park NTA; '<name> (CDTA <code>)')."""
        hit = lookup(self.ntas, lon, lat)
        if not hit:
            return None, None
        name, cdta = hit
        cd = CDTA_BOROUGH[cdta[:2]] + cdta[2:]
        return (cd if cd in self.borough_of_cd else None), f"{name} (CDTA {cdta})"


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
    if near := geo.nearest(lon, lat):
        return "district", near, "nearest_district", "point in no district"
    return "borough", boro, "site_borough", "point outside the city"


def units(con) -> dict[tuple[str, str], list[tuple]]:
    """(program, id) -> [(unit_no, share, class, lon, lat)] from project_serving_units."""
    out = defaultdict(list)
    for prog, pid, n, share, cls, lon, lat in con.execute("""select program, id, unit_no, share, area_class, lon, lat
            from project_serving_units order by 1, 2, 3""").fetchall():
        out[(prog, pid)].append((n, share, cls, lon, lat))
    return out


def rows(con, geo: Geography) -> list[tuple]:
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
        for n, ushare, cls, _, _ in ulist:
            for i, tier, src, lon, lat, share in sites.get(f) or [(None, None, None, None, None, 1.0)]:
                add(prog, f, n, i, ushare * share, cls, tier, lon, lat, bool(PLACEHOLDER_BOARDS.match(f)), b, src,
                    boards.get(f, ()))

    buildings = {k: r for k, *r in con.execute("""select p.project_key, b.tier, b.source, b.lon, b.lat, b.borough
            from sca_projects p left join sca_buildings b on b.building = p.building""").fetchall()}
    for (prog, key), ulist in us.items():
        if prog != "sca":
            continue
        tier, src, lon, lat, boro = buildings.get(key, (None,) * 5)
        for n, ushare, cls, _, _ in ulist:
            add(prog, key, n, 1 if tier else None, ushare, cls, tier, lon, lat, borough=boro, source=src)

    mta = dict(((a, (b, t)) for a, b, t in con.execute("select acep, borough, tier from mta_locations").fetchall()))
    for (prog, acep), ulist in us.items():
        if prog != "mta":
            continue
        boro, tier = mta.get(acep, (None, None))
        for n, ushare, cls, lon, lat in ulist:
            add(prog, acep, n, n if lon is not None else None, ushare, cls,
                "point" if lon is not None else tier, lon, lat, borough=boro,
                source="project_serving_units point" if lon is not None else None)
    return out


def main() -> int:
    con = duckdb.connect(str(DB_PATH))
    out = rows(con, Geography(con))
    replace_table(con, "project_areas", "program varchar, id varchar, unit_no integer, site_no integer, "
                  "area_class varchar, level varchar, area varchar, share double, method varchar, evidence varchar",
                  out)
    for r in con.execute("""select program, level, method, count(distinct id), round(sum(share), 1)
                            from project_areas group by all order by 1, 2, 3""").fetchall():
        print(*r, sep="\t")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
