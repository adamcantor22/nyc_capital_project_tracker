from sites import merge, shares


def test_merge_sums_weights_at_one_point():
    assert merge([(1.0, 2.0, 100), (1.000001, 2.0, 50), (3.0, 4.0, 10)]) == [(1.0, 2.0, 150), (3.0, 4.0, 10)]


def test_merge_keeps_unknown_weights_unknown():
    assert merge([(1.0, 2.0, None), (1.0, 2.0, 5)]) == [(1.0, 2.0, None)]


def test_shares_proportional_when_amounts_differ():
    s = shares([(0, 0, 732_000), (1, 1, 1_832_000)])
    assert [m for *_, m in s] == ["source_proportion"] * 2
    assert round(s[0][2], 3) == 0.285 and abs(sum(x[2] for x in s) - 1) < 1e-12


def test_shares_equal_when_amounts_repeat_or_missing():
    assert [x[2] for x in shares([(0, 0, 5), (1, 1, 5)])] == [0.5, 0.5]           # repeated project total
    assert {x[3] for x in shares([(0, 0, None), (1, 1, 3), (2, 2, 4)])} == {"equal"}


def test_single_point():
    assert shares([(0, 0, None)]) == [(0, 0, 1.0, "single")]
