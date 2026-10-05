from sca import current_phase, dsf_numbers, load_repeats, parse_day, project_key, project_status


def test_parse_day_reads_dates_and_drops_placeholders():
    assert parse_day("9/12/2003") == "2003-09-12"
    assert parse_day("PNS") is None and parse_day("DIIT") is None and parse_day(None) is None


def test_dsf_numbers_split_sort_and_drop_null():
    assert dsf_numbers("DSF0001008800, DSF0000991942") == ["DSF0000991942", "DSF0001008800"]
    assert dsf_numbers("NULL") == [] and dsf_numbers(None) == []


def test_project_key_is_dsf_at_building_else_what_it_is():
    assert project_key(["DSF1", "DSF2"], "K461", "SCA CIP", "ROOF") == "DSF1,DSF2|K461"
    key = project_key([], "M015", "DOE - Lead Paint", "LEAD PAINT ABATEMENT")
    assert key == "NODSF|M015|DOE - Lead Paint|LEAD PAINT ABATEMENT"


def test_project_status():
    assert project_status(["complete", "complete"]) == "complete"
    assert project_status(["not_started"]) == "not_started"
    assert project_status(["complete", "not_started"]) == "active"


def test_current_phase_prefers_latest_started_then_first_waiting():
    assert current_phase([("Design", "complete", "2021-01-01"), ("Construction", "in_progress", "2022-01-01"),
                          ("CM,F&E", "in_progress", "2022-01-01")]) == "Construction"
    assert current_phase([("Construction", "not_started", None), ("Design", "not_started", None)]) == "Design"


def test_repeats_list_reads():
    r = load_repeats()
    assert r[("DIIT - Project Connect", "CLASSROOM CONNECTIVITY", "Purch & Install", 445236066.0)] == "program_figure"


def test_name_address_needs_a_house_number():
    from sca_locations import code_borough, name_address
    assert name_address("P.S. @ 257 FRANKLIN STREET - BROOKLYN") == "257 FRANKLIN STREET, BROOKLYN"
    assert name_address("P.S. @ 1631-1659 ZEREGA AVENUE - BRONX") == "1631-1659 ZEREGA AVENUE, BRONX"
    assert name_address("CUNY @ MEDGAR EVERS HS ANNEX - BROOKLYN") is None
    assert code_borough("X626") == "Bronx" and code_borough("R125") == "Staten Island"
