import pytest

from bridges import BridgeIndex, fms_id_bin, parse_bins

KNOWN = {"2075837", "2241409", "2229579", "2075351", "2075352", "2066671", "2241139", "2243410"}


@pytest.mark.parametrize("text, expected", [
    ("BOSTON ROAD OVER HUTCHINSON RIVER  BIN: 2229579", ["2229579"]),
    ("BRUCKNER EXPY EB/AMTRAK 2-07535-1 and SB 2-07535-2", ["2075351", "2075352"]),
    ("RAMP TO NB HHP OVER AMTRAK WEST SIDE BIN 222934A", ["222934A"]),
    ("MILL BASIN BR / BELT PARKWAY #2-23147-9/TN", ["2231479"]),
    ("RECON OF 5TH AVE BRIDGE OVER LIRR AND SEA BEACH, BR 2-243580", []),          # second hyphen left out, unknown
    ("WESTCHESTER AVE BR OVER HUTCH RIVER PKWY 2-075837", ["2075837"]),            # second hyphen left out, known
    ("GRAND CONCOURSE / METRO NORTH RR HUD2-24140-9", ["2241409"]),               # glued to a word
    ("DESIGN OF FLOOD GATES FOR BATTERY PARK TUNNEL (2232000)", ["2232000"]),
    ("WEST 79TH STREET BRIDGES ( BINS: 2241139, 2243410 )", ["2241139", "2243410"]),
    ("BRUCKNER EXPESSWAY SOUTHBOUND over BRONX RIVER 2066671", ["2066671"]),      # bare, known, bridge text
    ("CENTER DRIVE OVER TRANSVERSE RD #1 BIN2246100", ["2246100"]),                # no space after BIN
    ("CONTRACT 2066671 FOR PAVING", []),                                          # bare without bridge words
    ("BRIDGE OVER THE CREEK 3999999", []),                                        # not a BIN form
])
def test_parse_bins(text, expected):
    assert parse_bins(text, KNOWN) == expected


def test_fms_id_bin():
    assert fms_id_bin("HBM245290", {"2245290"}) == "2245290"
    assert fms_id_bin("HBM245290", set()) is None          # only known BINs
    assert fms_id_bin("SEK245290", {"2245290"}) is None    # only DOT bridge IDs


BRIDGES = BridgeIndex([
    ("2232070", "M", "E 25TH ST PED BRDG", "FDR DRIVE", -73.974, 40.737),
    ("2232071", "M", "E 25TH ST", "AMTRAK", -73.990, 40.745),
    ("2240069", "B", "THIRD AVE BRIDGE", "HARLEM RIVER", -73.933, 40.807),
    ("2241040", "B", "THIRD AVE", "CSX PT MORRIS - (ABANDONED)", -73.911, 40.822),
    ("2241010", "B", "E 156TH STREET", "CSX PT MORRIS - (ABANDONED)", -73.913, 40.818),
    ("3065090", "K", "BROOKLYN BRIDGE", "EAST RIVER", -73.997, 40.706),
    ("1240090", "BM", "MACOMBS DAM BRIDGE", "HARLEM RIVER", -73.932, 40.828),
])


def bins(text, borough):
    return [b["bin"] for b in BRIDGES.match(text, borough)]


def test_bridge_name_prefers_the_pedestrian_bridge_and_reads_glued_names():
    assert bins("SPARC E25TH STREET PEDESTRIAN BRIDGE OVER FDR", "Manhattan") == ["2232070"]


def test_bridge_name_settles_rivals_by_what_they_cross_or_rejects_them():
    text = "Filling of Five Bridges over Abandoned CSX Line East 156th Street Bridge3rd Avenue Bridge"
    assert sorted(bins(text, "Bronx")) == ["2241010", "2241040"]
    assert bins("3RD AVE BR & RAMP TO BRUCKNER BLVD", "Bronx") == []   # two Third Ave bridges 2.4 km apart


def test_bridge_name_skips_parks_and_other_boroughs_but_not_citywide():
    assert bins("Brooklyn Bridge Park Sole Source Master Agreement", "Brooklyn") == []
    assert bins("Macombs Dam Bridge- Bus Stop", "Queens") == []
    assert bins("Macombs Dam Bridge- Bus Stop", "Citywide") == ["1240090"]
