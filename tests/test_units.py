import pytest

from units import locate, parse_units


@pytest.mark.parametrize("text, expected", [
    ("BUILDING AUTOMATION CONTROLS AT EC276", {("ENGINE", 276)}),
    ("ENGINE COMPANY  65 RENOVATION", {("ENGINE", 65)}),
    ("Multi-Component Renovations - EC 33", {("ENGINE", 33)}),
    ("MULTI-COMPONENT RENOVATIONS - SQ288", {("SQUAD", 288)}),
    ("OVERHEAD DOOR - EC 326 / LADDER 160", {("ENGINE", 326), ("LADDER", 160)}),
    ("LADDDER 25 KITCHEN", {("LADDER", 25)}),                    # typo seen in titles
    ("SPEED DOOR - EMS STATION 4", {("EMS", 4)}),
    ("Marine 9 Roof Renovation", {("MARINE", 9)}),
    # FacDB side
    ("BATTALION 46/ENGINE 287/LADDER 136", {("ENGINE", 287), ("LADDER", 136)}),
    ("PIERS 35 AND 36, EMS ST.4/DIV.1", {("EMS", 4)}),
    ("ENG 46, LAD 27, 48 PRECINCT", {("ENGINE", 46), ("LADDER", 27), ("PRECINCT", 48)}),
    # precincts
    ("49th Precinct Locker Room", {("PRECINCT", 49)}),
    ("106 Pct.  Bathroom and Facade Renovation", {("PRECINCT", 106)}),
    ("RENOVATION OF OLD POLICE ACADEMY/13TH PCT", {("PRECINCT", 13)}),
    ("BOILERS AT 26TH, 42ND & 46TH PRECINCTS", {("PRECINCT", 26), ("PRECINCT", 42), ("PRECINCT", 46)}),
    ("BOILER REPLACEMENT AT 68TH AND 76TH PCTS", {("PRECINCT", 68), ("PRECINCT", 76)}),
    ("52ND PRECNCT / MOSHOLU PARKWAY", {("PRECINCT", 52)}),
    ("94TH POLICE PRECINCT", {("PRECINCT", 94)}),
    ("ENG 245,LAD 161,BAT 43, PRECINCT 60", {("ENGINE", 245), ("LADDER", 161), ("PRECINCT", 60)}),
    # DSNY district garages, title and FacDB forms
    ("BRONX 6/6A GARAGE REHAB", {("DSNY", "BX06"), ("DSNY", "BX06A")}),
    ("QUEENS 8/10/12  GARAGE REHAB", {("DSNY", "QN08"), ("DSNY", "QN10"), ("DSNY", "QN12")}),
    ("DSNY BK17 18 Completion of construction", {("DSNY", "BK17"), ("DSNY", "BK18")}),
    ("DSNY-Queens West 9 District Garage (Leased In)", {("DSNY", "QN09")}),
    ("Queens 7 A Hot Water Heaters Replacement", {("DSNY", "QN07A")}),
    ("Staten Island 1 and 3 Garage Construction", {("DSNY", "SI01"), ("DSNY", "SI03")}),
    ("BKS14G GARAGE", {("DSNY", "BK14")}),
    ("QW05A GARAGE", {("DSNY", "QN05A")}),
    ("SI01G/SI03G GARAGE", {("DSNY", "SI01"), ("DSNY", "SI03")}),
    # training campuses
    ("FORT TOTTEN BUILDING 318/332 RENOVATIONS", {("SITE", "FORT TOTTEN (US ARMY)")}),
    ("FT TOTTEN BUILDING RENOVATION", {("SITE", "FORT TOTTEN (US ARMY)")}),
    ("RANDALL'S ISLAND BUILDING #2", {("SITE", "FIRE DEPT.FIRE TRAINING ACAD")}),
    ("WINDOWS REPLACEMENT - HAZMAT OPERATION BUILDING AT RANDALLS", {("SITE", "FIRE DEPT.FIRE TRAINING ACAD")}),
    # DOC jails and island-wide work
    ("Emergency Work for AMKC", {("JAIL", "AMKC")}),
    ("ANNA M. KROSS CENTER (AMKC)", {("JAIL", "AMKC")}),
    ("REPLACEMENT OF ELECTRICAL DISTRIBUTION PANELS- RI POWERHOUSE", {("SITE", "RIKERS ISLAND")}),
    ("Replacement of Cogeneration Power Plant Turbines", {("SITE", "RIKERS ISLAND")}),
    ("Hurricane Sandy-harts island Reconstruct from storm damage", {("SITE", "HART ISLAND")}),
    ("Hurricane Sandy - AMKC Roof Reconstruction", {("JAIL", "AMKC")}),
    # not units
    ("E 72 ST SEWER", set()),
    ("TOTTENVILLE POOL", set()),
    ("LIGHTING UPGRADE AT 14 FDNY FIRE STATIONS", set()),
    ("BRONX FRONT DESK REPLACEMENT 42ND, 44TH, 46TH, 108TH", set()),
    ("MANHATTAN 128 WEST 17 ST REHAB", set()),
    ("Bronx 3 Sec 31 Roof Replacement Washington Ave", set()),         # a section station
    ("BRONX 8 Van Cortlandt Park Salt Shed Tent", set()),               # salt sheds stand apart
    ("Hurricane Sandy 26 St Manh Boro R/R", set()),
    ("63RD BATHROOM RENOVATION", set()),
])
def test_parse_units(text, expected):
    assert parse_units(text) == expected


INDEX = {
    ("ENGINE", 287): ("BATTALION 46/ENGINE 287/LADDER 136", "Queens", -73.866, 40.727),
    ("LADDER", 136): ("BATTALION 46/ENGINE 287/LADDER 136", "Queens", -73.866, 40.727),
    ("ENGINE", 33): ("ENGINE 33/LADDER 9", "Manhattan", -73.992, 40.727),
    ("PRECINCT", 46): ("NYPD 46TH PRECINCT", "Bronx", -73.903, 40.856),
    ("PRECINCT", 26): ("NYPD 26TH PRECINCT", "Manhattan", -73.957, 40.814),
}
FDNY = frozenset({"FDNY"})
NYPD = frozenset({"NYPD", "DCAS"})


def test_locate_citywide_project_by_unit():
    agency, site = locate("ENGINE COMPANY 287", "Citywide", FDNY, INDEX)
    assert agency == "FDNY" and site[0].startswith("BATTALION 46")


def test_locate_accepts_several_units_in_one_building():
    assert locate("EC287 / LADDER 136", "Queens", FDNY, INDEX) is not None


def test_locate_rejects_units_in_different_buildings():
    assert locate("EC287 AND EC33 ROOFS", "Citywide", FDNY, INDEX) is None


def test_locate_rejects_building_in_another_borough():
    assert locate("ENGINE 33 RENOVATION", "Queens", FDNY, INDEX) is None


def test_locate_requires_fdny_as_client():
    assert locate("ENGINE 33 RENOVATION", "Manhattan", frozenset({"DSNY"}), INDEX) is None


def test_locate_precinct_for_nypd_client():
    assert locate("46th PRECINCT ADA RAMP", "Bronx", NYPD, INDEX) == ("NYPD", INDEX[("PRECINCT", 46)])


def test_locate_rejects_precinct_list_across_buildings():
    assert locate("BOILERS AT 26TH & 46TH PRECINCTS", "Citywide", NYPD, INDEX) is None


def test_locate_rejects_when_a_listed_unit_is_unknown():
    # the 42nd isn't in the index, so the project may span two buildings
    assert locate("BOILERS AT 42ND & 46TH PRECINCTS", "Bronx", NYPD, INDEX) is None


def test_locate_ignores_units_of_non_client_agencies():
    # a joint firehouse/precinct campus, for NYPD: only the precinct counts
    assert locate("NYPD - ENGINE 33 AND 46TH PRECINCT", "Bronx", NYPD, INDEX)[0] == "NYPD"


def test_locate_dsny_garage_shared_by_districts():
    index = {("DSNY", f"QN{n}"): (f"QE{n}G GARAGE", "Queens", -73.8099, 40.6651) for n in ("08", "10", "12")}
    agency, site = locate("QUEENS 8/10/12  GARAGE REHAB", "Queens", frozenset({"DSNY"}), index)
    assert agency == "DSNY" and site[0] == "QE08G GARAGE"   # first unit in sorted order, every run


JAIL_INDEX = {
    ("JAIL", "AMKC"): ("ANNA M. KROSS CENTER (AMKC)", "Bronx", -73.8876, 40.792),
    ("SITE", "RIKERS ISLAND"): ("RIKERS ISLAND", "Bronx", -73.8818, 40.7893),
}
DOC = frozenset({"DOC"})


def test_locate_named_jail_beats_the_island():
    assert locate("RIKERS ISLAND AMKC ROOF", "Bronx", DOC, JAIL_INDEX)[1][0].startswith("ANNA M. KROSS")


def test_locate_island_wide_work():
    assert locate("New Boilers for Powerhouse", "Bronx", DOC, JAIL_INDEX)[1][0] == "RIKERS ISLAND"


def test_locate_jail_not_in_facdb_is_not_placed():
    assert locate("Hurricane Sandy - VCBC Reconstruction", "Bronx", DOC, JAIL_INDEX) is None
