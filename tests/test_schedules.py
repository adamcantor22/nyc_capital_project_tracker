import datetime

from schedules import city_period_finishes, city_schedule, diff, mta_schedule, partial, sca_schedule

D = datetime.date


def test_partial_dates_end_their_period():
    assert partial("2027-08") == (D(2027, 8, 31), "month")
    assert partial("2026-12") == (D(2026, 12, 31), "month")
    assert partial("2024") == (D(2024, 12, 31), "year")
    assert partial(None) is None


def test_diff_uses_the_coarser_precision():
    assert diff(partial("2019"), partial("2019-06")) == (0, "year")
    assert diff(partial("2024"), partial("2027-08")) == (3 * 365, "year")
    assert diff(partial("2026-01"), partial("2026-03")) == (59, "month")


def test_schedule_history_wins_and_implausible_dates_are_skipped():
    out = city_period_finishes([(202305, 1, D(2026, 1, 1), "forecast", "fb86-vt7u"),
                                (202305, 1, D(2026, 6, 1), "forecast", "95tx-snak"),
                                (202305, 2, D(3026, 1, 1), "forecast", "95tx-snak"),
                                (202305, 3, D(2025, 1, 1), "forecast", "fb86-vt7u"),
                                (202305, 3, D(2025, 9, 1), "forecast", "fb86-vt7u")])
    assert out[202305][1] == (D(2026, 6, 1), "forecast", "95tx-snak")
    assert 2 not in out[202305]
    assert out[202305][3][0] == D(2025, 9, 1)


def test_city_late_is_the_move_since_the_first_finish_held():
    by = {202305: {1: (D(2025, 1, 1), "forecast", "95tx-snak")},
          202309: {1: (D(2025, 3, 1), "forecast", "95tx-snak")},
          202401: {1: (D(2025, 6, 1), "forecast", "95tx-snak")}}
    links = {p: {1} for p in by}
    s = city_schedule(by, links, 202401)
    assert s["expected_finish"] == D(2025, 6, 1) and s["baseline_finish"] == D(2025, 1, 1)
    assert s["late_days"] == 151 and s["slip_days"] == 92 and s["slip_since"] == "202309"
    assert not s["pid_set_changed"]


def test_city_added_pid_is_not_read_as_a_forecast_move():
    by = {202305: {1: (D(2025, 1, 1), "forecast", "95tx-snak")},
          202309: {1: (D(2025, 1, 1), "forecast", "95tx-snak"), 2: (D(2030, 1, 1), "forecast", "95tx-snak")}}
    s = city_schedule(by, {202305: {1}, 202309: {1, 2}}, 202309)
    assert s["expected_finish"] == D(2030, 1, 1)
    assert s["late_days"] == 0 and s["slip_days"] == 0 and s["pid_set_changed"]


def test_city_actual_only_when_every_pid_is_actual():
    by = {202305: {1: (D(2025, 1, 1), "actual", "95tx-snak"), 2: (D(2025, 2, 1), "forecast", "95tx-snak")}}
    assert city_schedule(by, {202305: {1, 2}}, 202305)["finish_kind"] == "forecast"


def test_sca_finish_only_from_construction_and_not_once_overdue():
    as_of = D(2026, 8, 4)
    assert sca_schedule("Construction", D(2027, 1, 1), None, None, as_of)["expected_finish"] == D(2027, 1, 1)
    assert sca_schedule("Construction", D(2026, 1, 1), None, 215, as_of)["expected_finish"] is None
    assert sca_schedule("Construction", D(2026, 1, 1), D(2026, 3, 1), 59, as_of)["finish_kind"] == "actual"
    s = sca_schedule("Design", D(2026, 1, 1), None, 215, as_of)
    assert s["expected_finish"] is None and s["late_days"] == 215 and s["baseline_kind"] == "published"


def test_mta_published_baseline_else_first_held():
    s = mta_schedule("2027-08", "2026-08", "2025", "2020-12-31", "2027-06")
    assert s["baseline_kind"] == "published" and s["late_days"] == 365 and s["late_precision"] == "month"
    assert s["slip_days"] == 62
    s = mta_schedule("2027-08", None, "2025", "2020-12-31", None)
    assert s["baseline_kind"] == "first_held" and s["late_precision"] == "year" and s["late_days"] == 2 * 365
    assert s["baseline_as_of"] == "2020-12-31" and s["slip_days"] is None


def test_reviews_load_reports_as_periods(tmp_path):
    from schedules import load_reviews
    f = tmp_path / "r.csv"
    f.write_text("pid,reports,verdict,official_finish,official_precision,official_milestone,evidence,notes\n"
                 "634,202305 202605,forecast_not_project_finish,2040-12,month,Construction Completion,x,y\n")
    r = load_reviews(f)
    assert r[634]["reports"] == {202305, 202605} and r[634]["official_finish"] == "2040-12"
