from datetime import date

from cpdd import decode, mangled, pub


def test_decode_mangled_month_and_two_digit_year():
    assert decode("2022-03-11", True) == (date(2011, 3, 1), "month and two-digit year read as 2022-MM-YY")
    assert decode("2022-05-22", True)[0] == date(2022, 5, 1)
    assert decode("1930-02-01", True) == (date(2030, 2, 1), "two-digit year read as 19YY")
    assert decode("1996-08-01", True) == (date(1996, 8, 1), "as published")
    assert decode("1899-12-01", True) == (None, "placeholder")
    assert decode("2022-03-11", False) == (date(2022, 3, 11), "as published")
    assert decode(None, True) == (None, "empty")


def test_mangled_edition_and_pub_fix():
    assert mangled(["2022-03-11", "2022-06-12", "2001-01-01"]) and not mangled(["2023-01-01", "2024-05-01"])
    assert pub("2021122") == "20211122" and pub("20231026") == "20231026"
