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
    # training campuses
    ("FORT TOTTEN BUILDING 318/332 RENOVATIONS", {("CAMPUS", "FORT TOTTEN (US ARMY)")}),
    ("FT TOTTEN BUILDING RENOVATION", {("CAMPUS", "FORT TOTTEN (US ARMY)")}),
    ("RANDALL'S ISLAND BUILDING #2", {("CAMPUS", "FIRE DEPT.FIRE TRAINING ACAD")}),
    ("WINDOWS REPLACEMENT - HAZMAT OPERATION BUILDING AT RANDALLS", {("CAMPUS", "FIRE DEPT.FIRE TRAINING ACAD")}),
    # not units
    ("E 72 ST SEWER", set()),
    ("TOTTENVILLE POOL", set()),
    ("LIGHTING UPGRADE AT 14 FDNY FIRE STATIONS", set()),
    ("BRONX FRONT DESK REPLACEMENT 42ND, 44TH, 46TH, 108TH", set()),
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
