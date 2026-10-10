import datetime

import pytest

from budget_history import classify, phase_at


def test_original_row_before_the_series_seeds_the_change():
    series, original, issues = classify([(201904, 100.0, None, None), (202305, 150.0, 0.0, 50.0),
                                         (202309, 140.0, 5.0, -10.0)])
    assert original[:3] == (100.0, 201904, "original_row")
    assert [s[3] for s in series] == [50.0, -10.0]
    assert issues == []


def test_same_period_original_with_the_same_budget_is_used():
    series, original, issues = classify([(202305, 100.0, 0.0, None), (202305, 100.0, None, None)])
    assert original[:3] == (100.0, 202305, "original_row")
    assert series[0][3] == 0.0 and issues == []


def test_same_period_row_with_a_different_budget_is_recorded_not_used():
    series, original, issues = classify([(202309, 520.0, None, None), (202309, 400.0, 0.0, -120.0),
                                         (202401, 400.0, 0.0, 0.0)])
    assert original[:3] == (400.0, 202309, "first_snapshot")
    assert [s[3] for s in series] == [None, 0.0]
    assert len(issues) == 1 and issues[0][:2] == (202309, 520.0)


def test_row_dated_after_the_series_began_is_recorded_not_used():
    _, original, issues = classify([(202309, 10.0, 0.0, None), (202310, 10.0, None, 0.0)])
    assert original[:3] == (10.0, 202309, "first_snapshot")
    assert "after the series began" in issues[0][2]


def test_no_original_row_takes_the_first_reported_budget():
    series, original, issues = classify([(202401, 7.0, 1.0, None), (202405, 9.0, 2.0, 2.0)])
    assert original[:3] == (7.0, 202401, "first_snapshot")
    assert [s[3] for s in series] == [None, 2.0]


def test_original_only_has_no_series():
    series, original, issues = classify([(201410, 3.0, None, None)])
    assert series == [] and original[:3] == (3.0, 201410, "original_row") and issues == []


def test_repeated_rows_raise():
    with pytest.raises(ValueError):
        classify([(202305, 1.0, 0.0, None), (202305, 2.0, 0.0, None)])


def test_phase_from_the_snapshot_at_or_before_the_original_most_advanced_pid():
    snaps = [(202305, ["Pre-Design"]), (202309, ["Design", "Construction"])]
    assert phase_at(202401, snaps, {}, None)[:2] == ("construction", "snapshot")
    assert phase_at(202305, snaps, {}, None)[:2] == ("planning", "snapshot")
    assert phase_at(202305, [(202305, ["(Pending)"])], {}, None)[:2] == ("no_phase", "snapshot")


def test_phase_from_actual_starts_before_the_series():
    starts = {"design": 201801, "construction": 202003}
    assert phase_at(202006, [], starts, None)[:2] == ("construction", "actual_start")
    assert phase_at(202003, [], starts, None)[:2] == ("construction", "actual_start_same_month")
    assert phase_at(201905, [], starts, None)[:2] == ("design", "actual_start")
    assert phase_at(201705, [], starts, None)[:2] == ("planning", "actual_design_start_after")


def test_phase_bounds_when_no_start_precedes_the_original():
    assert phase_at(201905, [(202305, ["Pre-Design"])], {}, None)[:2] == ("planning", "first_snapshot_bound")
    assert phase_at(201905, [(202305, ["Design"])], {}, None)[:2] == ("before_construction", "first_snapshot_bound")
    assert phase_at(201905, [], {"construction": 202101}, None)[:2] == ("before_construction", "actual_start_after")


def test_omb_schedule_only_bounds_the_phase():
    later = ("20190425", "CONSTRUCTION", datetime.date(2020, 6, 1), datetime.date(2019, 4, 25))
    passed = ("20190425", "CONSTRUCTION", datetime.date(2018, 6, 1), datetime.date(2019, 4, 25))
    assert phase_at(201810, [], {}, later)[:2] == ("before_construction", "omb_schedule_bound")
    assert phase_at(201810, [], {}, passed)[:2] == ("unknown", "unknown")
    assert phase_at(201810, [(202305, ["(Pending)"])], {}, passed)[:2] == ("no_phase", "first_snapshot_no_phase")
