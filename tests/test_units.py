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
    ("ENG 46, LAD 27, 48 PRECINCT", {("ENGINE", 46), ("LADDER", 27)}),
    # not units
    ("E 72 ST SEWER", set()),
    ("FORT TOTTEN BUILDING 318/332 RENOVATIONS", set()),
    ("LIGHTING UPGRADE AT 14 FDNY FIRE STATIONS", set()),
])
def test_parse_units(text, expected):
    assert parse_units(text) == expected


INDEX = {
    ("ENGINE", 287): ("BATTALION 46/ENGINE 287/LADDER 136", "Queens", -73.866, 40.727),
    ("LADDER", 136): ("BATTALION 46/ENGINE 287/LADDER 136", "Queens", -73.866, 40.727),
    ("ENGINE", 33): ("ENGINE 33/LADDER 9", "Manhattan", -73.992, 40.727),
}
FDNY = frozenset({"FDNY"})


def test_locate_citywide_project_by_unit():
    assert locate("ENGINE COMPANY 287", "Citywide", FDNY, INDEX)[0].startswith("BATTALION 46")


def test_locate_accepts_several_units_in_one_building():
    assert locate("EC287 / LADDER 136", "Queens", FDNY, INDEX) is not None


def test_locate_rejects_units_in_different_buildings():
    assert locate("EC287 AND EC33 ROOFS", "Citywide", FDNY, INDEX) is None


def test_locate_rejects_building_in_another_borough():
    assert locate("ENGINE 33 RENOVATION", "Queens", FDNY, INDEX) is None


def test_locate_requires_fdny_as_client():
    assert locate("ENGINE 33 RENOVATION", "Manhattan", frozenset({"DSNY"}), INDEX) is None
