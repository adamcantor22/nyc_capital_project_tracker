import pytest

from locations import (
    PlaceIndex,
    acceptable,
    client_agencies,
    distinctive,
    eligible_for_name_match,
    is_address,
    lead_token,
    normalize_agency,
    parse_districts,
)

CD_CODES = {"Manhattan": 1, "Bronx": 2, "Brooklyn": 3, "Queens": 4, "Staten Island": 5}
KNOWN = {101, 103, 312, 407, 501}


@pytest.mark.parametrize("board, expected", [
    ("Manhattan 01", [101]),
    ("Queens, Queens 07", [407]),
    ("Manhattan 01, Manhattan 03, Manhattan 01", [101, 103]),
    ("Queens", []),                      # borough only
    ("Citywide", []),
    ("Brooklyn 99", []),                 # borough-wide placeholder, not a district
    (None, []),
])
def test_parse_districts(board, expected):
    assert parse_districts(board, CD_CODES, KNOWN) == expected


def test_distinctive_drops_generic_words():
    assert distinctive("Frank White Memorial Garden Greenhouse Construction") == {"FRANK", "WHITE", "GREENHOUSE"}


def test_is_address_detects_street_numbers():
    assert is_address("851 GRAND CONCOURSE - COOLING TOWER", frozenset({"GRAND", "CONCOURSE"}))
    assert not is_address("GRAND CONCOURSE LIBRARY HVAC", frozenset({"GRAND", "CONCOURSE"}))


def place(name, source, agencies=(), boro="Brooklyn"):
    return (name, boro, -73.9, 40.7, source, distinctive(name), frozenset(agencies))


@pytest.mark.parametrize("raw, expected", [
    ("NYCDPR", "DPR"), ("NYCHHC", "HHC"), ("NYCDSS", "DHS"), ("NYCDCLA", "DCLA"),
    ("NYCHA", "NYCHA"),          # the Housing Authority, not 'HA'
    ("NYPD", "NYPD"), ("dpr", "DPR"), (None, None),
])
def test_normalize_agency(raw, expected):
    assert normalize_agency(raw) == expected


def test_client_agencies_include_sponsor_and_title_prefix():
    assert client_agencies("DCAS", None, "NYPD - 122ND PRECINCT") == {"DCAS", "NYPD"}
    assert client_agencies("DDC", "NYPL", "Webster - Facade") == {"DDC", "NYPL"}
    assert client_agencies("HHC", None, "BELLEVUE: CHILLER") == {"HHC"}


def test_lead_token_skips_agency_prefix_and_generic_words():
    assert lead_token("NYPD - 122ND PRECINCT") == "122ND"
    assert lead_token("MASPETH - HVAC") == "MASPETH"
    assert lead_token("RECONSTRUCTION OF THE POOL AT HARLEM MEER") == "POOL"


def test_acceptable_rules():
    park1 = place("Sunrise Playground", "parks_properties", {"DPR"})   # one distinctive token
    fac2 = place("Metropolitan Opera House", "facdb")                  # two distinctive tokens
    branch = place("Maspeth Library", "facdb", {"QPL"})
    assert acceptable("SUNRISE PLAYGROUND FENCE", {"DPR"}, park1)
    assert not acceptable("SUNRISE STABLES ACQUISITION", {"DCAS"}, park1)  # neighbourhood-style collision
    assert acceptable("METROPOLITAN OPERA WINDOW REPLACEMENT", {"DCAS"}, fac2)
    assert not acceptable("851 METROPOLITAN OPERA AVE", {"DCAS"}, fac2)     # address, i.e. a street
    assert acceptable("MASPETH - HVAC", {"QPL"}, branch)                   # operator matches, word leads
    assert not acceptable("MASPETH - HVAC", {"BPL"}, branch)               # someone else's facility
    assert not acceptable("HVAC UPGRADE NEAR MASPETH", {"QPL"}, branch)    # buried word


@pytest.mark.parametrize("agency, title, ok", [
    ("DPR", "BEDFORD PLAYGROUND RECONSTRUCTION", True),
    ("DOT", "ANYTHING AT ALL", False),
    ("DDC", "WM REPLACEMENT IN DELANCEY ST", False),            # linear work
    ("DPR", "CITYWIDE ROOFING SYSTEMS WAKEFIELD PLGD", False),  # citywide programme
])
def test_eligible_for_name_match(agency, title, ok):
    assert eligible_for_name_match(agency, title) is ok


def test_place_index_requires_same_borough():
    idx = PlaceIndex([("Frank White Memorial Garden", "Manhattan", -73.95, 40.81, "parks_properties", {"DPR"})])
    assert idx.match("FRANK WHITE MEMORIAL GARDEN GREENHOUSE", "Manhattan", {"DPR"})[0] == "Frank White Memorial Garden"
    assert idx.match("FRANK WHITE MEMORIAL GARDEN GREENHOUSE", "Bronx", {"DPR"}) is None


def test_place_index_rejects_far_apart_ties():
    idx = PlaceIndex([
        ("Joe Smith Park", "Queens", -73.80, 40.70, "parks_properties", {"DPR"}),
        ("Joe Smith Center", "Queens", -73.90, 40.75, "facdb", ()),       # same distinctive tokens, ~10 km away
    ])
    assert idx.match("JOE SMITH ROOF", "Queens", {"DPR"}) is None


def test_place_index_prefers_more_specific_place():
    idx = PlaceIndex([
        ("Harlem Art Park", "Manhattan", -73.94, 40.80, "parks_properties", {"DPR"}),
        ("Harlem River Park", "Manhattan", -73.93, 40.82, "parks_properties", {"DPR"}),
    ])
    hit = idx.match("HARLEM RIVER PARK ESPLANADE", "Manhattan", {"DPR"})
    assert hit[0] == "Harlem River Park"
