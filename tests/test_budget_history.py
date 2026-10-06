import pytest

from budget_history import classify


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
