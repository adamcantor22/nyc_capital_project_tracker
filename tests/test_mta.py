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
