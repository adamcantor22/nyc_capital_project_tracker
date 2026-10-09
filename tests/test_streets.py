import pytest

from streets import base, normalize


@pytest.mark.parametrize("raw, expected", [
    ("EAST 72ND STREET", "E 72 ST"),
    ("E 72ND ST", "E 72 ST"),
    ("E  72 ST", "E 72 ST"),                        # centerline style, double space
    ("Francis Lewis Boulevard", "FRANCIS LEWIS BLVD"),
    ("RECTOR STR", "RECTOR ST"),
    ("Beach 43rd Street", "BCH 43 ST"),
    ("Slosson Terrace", "SLOSSON TER"),
    ("B'way", "B WAY"),
    ("1ST AVE", "1 AVE"),
    ("23RD ST", "23 ST"),
    ("7ST B/T 3 & 4 AV", "7 ST B T 3 4 AVE"),          # a glued suffix that is no ordinal of its number
    (None, ""),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


def test_normalize_keeps_directionals_distinct():
    # Brooklyn has both '72 ST' and 'E 72 ST'
    assert normalize("72nd Street") != normalize("East 72nd Street")


def test_base_drops_only_known_suffixes():
    assert base("RECTOR ST") == "RECTOR"
    assert base("FRANCIS LEWIS BLVD") == "FRANCIS LEWIS"
    assert base("BROADWAY") == "BROADWAY"
