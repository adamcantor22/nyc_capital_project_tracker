import pytest

from geocode import extract_addresses


@pytest.mark.parametrize("text, expected", [
    ("2 LAFAYETTE ST - ELEVATOR MODERNIZATION", ["2 LAFAYETTE STREET"]),
    ("120-55 QUEENS BLVD COOLING PLANT REPLACEMENT", ["120-55 QUEENS BOULEVARD"]),
    ("RENOVATION AT 253 BROADWAY", ["253 BROADWAY"]),
    ("265 E161 ST", ["265 EAST 161 STREET"]),
    ("198 E.161 ST", ["198 EAST 161 STREET"]),
    ("2960 FREDERICK DOUGLAS BOULEVARD", ["2960 FREDERICK DOUGLAS BOULEVARD"]),
])
def test_extracts_real_addresses(text, expected):
    assert extract_addresses(text) == expected


@pytest.mark.parametrize("text", [
    "SEWER WORK IN EAST 79 STREET",                # a street, not an address
    "26 ST",
    "8 THIS PROJECT WILL PLANT STREET TREES",       # prose
    "3 ZIMMERMAN PLAYGROUND BASKETBALL COURT",
    "14 FY16 STREET",
    "31 ROOF REPLACEMENT WASHINGTON AVENUE",
    "PEDESTRIAN RAMP UPGRADES AT 91 NON-STANDARD LOCATIONS",
])
def test_rejects_non_addresses(text):
    assert extract_addresses(text) == []


def test_dedupes_spelling_variants():
    assert extract_addresses("215 E 161 ST AND 215 EAST 161 STREET") == ["215 EAST 161 STREET"]


def test_caps_addresses_per_project():
    text = "1 A ST, 2 B ST, 3 C ST, 4 D ST"
    assert extract_addresses(text) == ["1 A STREET", "2 B STREET", "3 C STREET"]
