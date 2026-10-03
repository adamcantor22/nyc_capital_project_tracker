import pytest

from bridges import parse_bins

KNOWN = {"2229579", "2075351", "2075352", "2066671", "2241139", "2243410"}


@pytest.mark.parametrize("text, expected", [
    ("BOSTON ROAD OVER HUTCHINSON RIVER  BIN: 2229579", ["2229579"]),
    ("BRUCKNER EXPY EB/AMTRAK 2-07535-1 and SB 2-07535-2", ["2075351", "2075352"]),
    ("RAMP TO NB HHP OVER AMTRAK WEST SIDE BIN 222934A", ["222934A"]),
    ("MILL BASIN BR / BELT PARKWAY #2-23147-9/TN", ["2231479"]),
    ("RECON OF 5TH AVE BRIDGE OVER LIRR AND SEA BEACH, BR 2-243580", []),          # malformed BIN
    ("DESIGN OF FLOOD GATES FOR BATTERY PARK TUNNEL (2232000)", ["2232000"]),
    ("WEST 79TH STREET BRIDGES ( BINS: 2241139, 2243410 )", ["2241139", "2243410"]),
    ("BRUCKNER EXPESSWAY SOUTHBOUND over BRONX RIVER 2066671", ["2066671"]),      # bare, known, bridge text
    ("CENTER DRIVE OVER TRANSVERSE RD #1 BIN2246100", ["2246100"]),                # no space after BIN
    ("CONTRACT 2066671 FOR PAVING", []),                                          # bare without bridge words
    ("BRIDGE OVER THE CREEK 3999999", []),                                        # not a BIN form
])
def test_parse_bins(text, expected):
    assert parse_bins(text, KNOWN) == expected
