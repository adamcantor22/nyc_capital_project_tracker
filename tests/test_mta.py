from mta import money, month


def test_month_parses_and_records_implausible_values():
    assert month({"x_mm": "10", "x_yyyy": "2029"}, "x") == ("2029-10", None)
    assert month({"x_mm": "", "x_yyyy": "2029"}, "x") == ("2029", None)
    assert month({}, "x") == (None, None)
    for mm, yyyy in [("1", "21"), ("5", "3033"), ("TB", "TBD"), ("0", "2025"), ("20", "2024"), ("4", "")]:
        value, issue = month({"x_mm": mm, "x_yyyy": yyyy}, "x")
        assert value is None and issue == f"x: mm={mm!r} yyyy={yyyy!r}"


def test_money():
    assert money("903307503.00") == 903307503.0 and money("") is None and money("TBD") is None


def test_read_point_fixes_swaps_and_rejects_the_rest():
    from mta_locations import read_point
    assert read_point({"latitude": "40.75", "longitude": "-73.99"}) == ((-73.99, 40.75), None)
    assert read_point({"latitude": "-73.95", "longitude": "40.79"}) == ((-73.95, 40.79), "swapped")
    assert read_point({"latitude": "40.746", "longitude": "-73964022"}) == (None, "outside_region")
    assert read_point({"latitude": ""}) == (None, "missing")


def test_spending_draft_rules():
    from mta_spending import draft
    assert draft("Owner Controlled Insurance Program", "")[0] == "overhead"
    kind, flag, basis = draft("Authority-Wide Contingency: 2020-2024", "")
    assert (kind, flag) == ("overhead", "yes") and basis.startswith("rule: agency-wide contingency")
    assert draft("Sas 2 Reserve", "This ACEP is the project Reserve.")[:2] == ("physical", "yes")
    assert draft("Scope Development And Design", "a reserve for scope development")[:2] == ("overhead", "yes")
    assert draft("Signal Modernization Design", "This project is a design reserve that will fund")[:2] == \
        ("physical", "yes")
    assert draft("Rail Simulation Study", "")[0] == "overhead"
    assert draft("Admin Support", "This is a reserve for administrative needs")[0] == "overhead"
    assert draft("Sas Ph 2: Pm/Cm/Support Reserve", "SAS Phase 2 reserve for future support costs")[0] == "physical"
    kind, flag, basis = draft("Purchase 1,140 New A-Division Cars", "a reserve that will fund the purchase")
    assert (kind, flag) == ("physical", "yes") and basis.startswith("program reserve")
    assert draft("Small Business Mentoring Program - Stations", "Construction contracts for Small Business")[0] == \
        "physical"
    assert draft("Small Business Mentoring Program Administration", "")[0] == "overhead"
    assert draft("Capital Revolving Fund 2024", "small-scale construction work")[0] == "physical"
    assert draft("Platform Screen Doors Pilot", "design-build activities")[:2] == ("physical", "")


def test_merge_points_keeps_sequences():
    from mta_locations import merge_points
    places = merge_points([(1, (-73.99, 40.75)), (2, (-73.9901, 40.7501)), (3, (-73.90, 40.70))])
    assert [p[2] for p in places] == [[1, 2], [3]]


def test_project_specific_costs_are_the_projects_physical_work():
    from mta_spending import draft
    assert draft("Sas 2 Owner Controlled Insurance Program", "", "Second Avenue Subway Phase II")[0] == "physical"
    assert draft("Project Management For Ibx", "")[0] == "physical"
    assert draft("Owner Controlled Insurance Program", "")[0] == "overhead"


def test_growth_allocations_amendments_and_mega_series():
    from datetime import date

    from mta_growth import allocations, amendments, mega_series
    rows = [{"acep": "T8010101", "plan_id": "8", "plan_revision": "0", "date": "2020-01-01T00:00:00.000",
             "total_allocation": "100", "change_nar": "nan"},
            {"acep": "T8010101", "plan_id": "8", "plan_revision": "1", "date": "2022-08-01T00:00:00.000",
             "total_allocation": "150", "change_nar": "Scope added"},
            {"acep": "T8010102", "plan_id": "8", "plan_revision": "0", "date": "2022-08-01T00:00:00.000",
             "total_allocation": "20"}]
    allocs = allocations(rows)
    assert [(a[3], a[4], a[5], a[6]) for a in allocs] == [
        ("2020-01-01", 100_000, None, None), ("2022-08-01", 150_000, 50_000, "Scope added"),
        ("2022-08-01", 20_000, None, None)]
    first, second = amendments(allocs)
    assert first[2:5] == (1, 100_000, None)
    assert second[2:10] == (2, 170_000, 70_000, 1, 20_000, 1, 50_000, 1)
    d1, d2, d3 = date(2020, 3, 31), date(2020, 6, 30), date(2020, 9, 30)
    hist = [(d1, "A", "SAS", 10.0), (d2, "A", "SAS", 12.0), (d1, "B", None, 5.0), (d3, "B", "SAS", 6.0)]
    series = mega_series(hist, [d1, d2, d3])
    assert [s[1:7] for s in series] == [("2020-03-31", 2, 2, 15.0, 0.0, None), ("2020-06-30", 2, 1, 17.0, 5.0, 2.0),
                                        ("2020-09-30", 2, 1, 18.0, 12.0, 1.0)]
