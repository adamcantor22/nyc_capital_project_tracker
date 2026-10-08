from datetime import date

from inflation import Indexes, construction_index, month_start, parse


def test_construction_index_rules():
    assert construction_index("sca", "Education", None)[0] == "ppi_school"
    assert construction_index("nyc_capital", "Education", None)[0] == "ppi_school"
    assert construction_index("nyc_capital", "Transportation", "Bridges")[0] == "nhcci"
    assert construction_index("nyc_capital", "Transportation", "Ferries")[0] == "bea_sl_structures"
    assert construction_index("mta", "Transportation", "Transit (MTA)")[0] == "bea_sl_structures"


def test_parse_formats():
    assert parse("nhcci", 'quarter,nhcci\n"2003 Q1",1\n"2003 Q3",1.02\n') == [(date(2003, 1, 1), 1.0),
                                                                             (date(2003, 7, 1), 1.02)]
    assert parse("cpi_ny", "observation_date,X\n2005-12-01,100\n2006-01-01,.\n") == [(date(2005, 12, 1), 100.0)]


def test_index_at_and_ratio():
    ix = Indexes({"bea_sl_structures": [(date(2020, 1, 1), 100.0), (date(2020, 4, 1), 110.0)]})
    assert ix.index_at("bea_sl_structures", date(2019, 12, 31)) is None
    assert ix.index_at("bea_sl_structures", date(2020, 3, 15)) == (100.0, False)
    assert ix.index_at("bea_sl_structures", date(2020, 6, 30)) == (110.0, False)
    assert ix.index_at("bea_sl_structures", date(2020, 7, 1)) == (110.0, True)  # past the last quarter
    assert ix.ratio("bea_sl_structures", month_start(202002), month_start(202005)) == 1.1
