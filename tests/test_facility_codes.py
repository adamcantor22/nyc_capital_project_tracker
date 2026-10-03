import pytest

from facility_codes import facility_code, load_codes

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
    ("CUNY", "CA091KG03", None),    # central administration program
    ("CUNY", "ACECUN216", None),
    ("DDC", "11202205", None),      # codes only apply under their own agency
    (None, "QC074-019", None),
])
def test_facility_code(agency, fms_id, expected):
    assert facility_code(agency, fms_id) == expected


def test_table_is_well_formed():
    assert all(r["facility"] and r["factype"] and r["title_pattern"] for r in CODES.values())
    assert {a for a, _ in CODES} == {"HHC", "CUNY"}


def test_network_and_program_codes_are_excluded():
    for key in [("HHC", "02"), ("HHC", "12"), ("HHC", "22"), ("HHC", "27"), ("CUNY", "CA"), ("CUNY", "HC")]:
        assert key not in CODES


@pytest.mark.parametrize("key, title", [
    (("HHC", "11"), "BEL - ED AMBULANCE BAY"),
    (("HHC", "24"), "NCB: FIRE ALARM REPLACEMENT"),
    (("HHC", "26"), "SBH: RENOVATION OF MOTHER-BABY & NICU"),
    (("CUNY", "MC"), "CUNY: BMCC, 199 CHAMBERS STREET - EE UPGRADE"),
])
def test_title_patterns_recognise_abbreviations(key, title):
    assert CODES[key]["regex"].search(title)
