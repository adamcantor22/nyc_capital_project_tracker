import pytest

from facility_codes import code_key, facility_code, load_codes

CODES = load_codes()


@pytest.mark.parametrize("agency, fms_id, expected", [
    ("HHC", "11202205", "11"),
    ("HHC", "48201515", "48"),
    ("HHC", "AC000123", None),      # energy program, not a facility
    ("HHC", "1120220", None),       # wrong length
    ("CUNY", "QC074-019", "QC"),
    ("CUNY", "LM029016", "LM"),     # dash sometimes missing
    ("CUNY", "SAND-KG03", "KG"),
    ("CUNY", "SEED-YC27", "YC"),
    ("CUNY", "CA091KG03", "KG"),    # central program, campus embedded
    ("CUNY", "CA001-021", "CA"),    # central program with no campus; CA is not in the table
    ("CUNY", "CA200CW21", "CW"),    # parsed, but CW is not in the table
    ("CUNY", "ACECUN216", None),
    ("DDC", "11202205", None),      # codes only apply under their own agency
    (None, "QC074-019", None),
])
def test_facility_code(agency, fms_id, expected):
    assert facility_code(agency, fms_id) == expected


def test_table_is_well_formed():
    assert all(r["facility"] and r["factype"] and r["title_pattern"] for r in CODES.values())
    assert {a for a, _ in CODES} == {"HHC", "CUNY", "DCLA"}


@pytest.mark.parametrize("agency, fms_id, expected", [
    ("DCLA", "PV022ANEG", ("DCLA", "022")),
    ("DDC", "PV176MONK", ("DCLA", "176")),    # institution code, whichever agency manages
    ("EDC", "PV471SWA2", ("DCLA", "471")),
    ("HHC", "48201515", ("HHC", "48")),
    ("DDC", "48201515", None),
])
def test_code_key(agency, fms_id, expected):
    assert code_key(agency, fms_id) == expected


def test_network_and_program_codes_are_excluded():
    for key in [("HHC", "02"), ("HHC", "12"), ("HHC", "22"), ("HHC", "27"), ("CUNY", "CA"), ("CUNY", "HC"),
                ("DCLA", "467"), ("DCLA", "289")]:  # Percent for Art fund; Public Theater (two sites)
        assert key not in CODES


@pytest.mark.parametrize("key, title", [
    (("HHC", "11"), "BEL - ED AMBULANCE BAY"),
    (("HHC", "24"), "NCB: FIRE ALARM REPLACEMENT"),
    (("HHC", "26"), "SBH: RENOVATION OF MOTHER-BABY & NICU"),
    (("CUNY", "MC"), "CUNY: BMCC, 199 CHAMBERS STREET - EE UPGRADE"),
])
def test_title_patterns_recognise_abbreviations(key, title):
    assert CODES[key]["regex"].search(title)
