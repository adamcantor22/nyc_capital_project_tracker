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


def test_school_number_reads_both_spellings_but_not_addresses():
    from sca_locations import school_number
    assert school_number("P.S. 65 - BROOKLYN") == school_number("P.S. 065 THE CARROLL") == ("PS", "65")
    assert school_number("I.S. 136 - BROOKLYN") == ("IS", "136")
    assert school_number("P.S. @ 257 FRANKLIN STREET - BROOKLYN") is None
    assert school_number("MIDWOOD HS - BROOKLYN") is None


def test_match_school_by_number_name_and_ambiguity():
    from sca_locations import annex_like, match_school
    schools = [("P.S. 065 THE CARROLL", "Brooklyn", -73.98, 40.68), ("P.S. 065 OTHER", "Queens", -73.8, 40.7),
               ("MIDWOOD HIGH SCHOOL", "Brooklyn", -73.95, 40.63),
               ("JOHN DEWEY HIGH SCHOOL", "Brooklyn", -73.98, 40.59),
               ("JOHN DEWEY HIGH SCHOOL", "Brooklyn", -73.90, 40.70)]
    assert match_school("P.S. 65 - BROOKLYN", "Brooklyn", schools)[:2] == ("number", "P.S. 065 THE CARROLL")
    assert match_school("MIDWOOD HS - BROOKLYN", "Brooklyn", schools)[:2] == ("name", "MIDWOOD HIGH SCHOOL")
    assert match_school("JOHN DEWEY HS - BROOKLYN", "Brooklyn", schools)[0] == "ambiguous"
    assert match_school("MIDWOOD HS - QUEENS", "Queens", schools) is None
    assert annex_like("K347", "P.S. 321 - BROOKLYN") and not annex_like("K321", "P.S. 321 - BROOKLYN")
