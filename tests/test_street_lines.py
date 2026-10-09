import json

import pytest

from street_lines import Network, extents, parse, point_along
from streets import base

KNOWN = {"BAY ST", "SLOSSON TER", "MINTHORNE ST", "E 72 ST", "AVE L", "ROYCE PL", "GRANT AVE",
         "TRINITY PL", "THAMES ST", "RECTOR ST", "BROADWAY"}
KNOWN_BASE = {base(n) for n in KNOWN}


def p(text):
    return parse(text, KNOWN, KNOWN_BASE)


def test_parse_extent():
    assert p("WM RPLCMT IN BAY ST BETWEEN SLOSSON TER & MINTHORNE ST SI") == \
        ("extent", "BAY ST", "SLOSSON TER", "MINTHORNE ST")


def test_parse_extent_with_loose_cross_street_names():
    # 'THAMES' (no suffix) and 'RECTOR STR' still resolve
    assert p("RPLMT SE ON TRINITY PL BETW THAMES & RECTOR STR MN") == \
        ("extent", "TRINITY PL", "THAMES", "RECTOR ST")


def test_parse_street_only_list():
    assert p("SANITARY SEWERS & WM IN E 72ND ST, AVE L & ROYCE PL") == \
        ("street_only", ["E 72 ST", "AVE L", "ROYCE PL"])


def test_parse_rejects_park_named_after_street():
    assert p("RETAINING WALL WORK IN GRANT AVE PARK") is None


def test_parse_rejects_area_descriptions():
    assert p("INSTALL S-POLE LIGHTING- VARIOUS STREETS WEST OF BROADWAY") is None


def test_parse_ignores_unknown_streets():
    assert p("NEW BOILER IN BUILDING 4") is None


def seg(pid, street, a, b):
    coords = [list(a), list(b)]
    return (pid, street, 100.0, a[0], a[1], b[0], b[1],
            json.dumps({"type": "MultiLineString", "coordinates": [coords]}))


# A street X running west-east through nodes n0..n3, crossed by A at n1 and B at n3.
N = [(0.0, 0.0), (0.001, 0.0), (0.002, 0.0), (0.003, 0.0)]
NET = Network([
    seg("1", "X ST", N[0], N[1]), seg("2", "X ST", N[1], N[2]), seg("3", "X ST", N[3], N[2]),  # 3 is reversed
    seg("4", "A ST", N[1], (0.001, 0.001)),
    seg("5", "B AVE", (0.003, -0.001), N[3]),
])


def test_crossing_nodes_matches_exact_and_base_names():
    assert NET.crossing_nodes("X ST", "A ST") == {N[1]}
    assert NET.crossing_nodes("X ST", "B") == {N[3]}      # base-name match


def test_route_follows_street_between_crossings():
    length, path = NET.route("X ST", {N[1]}, {N[3]})
    assert length == pytest.approx(200)
    assert [s["id"] for _, s in path] == ["2", "3"]


def test_route_crosses_a_block_named_after_another_street():
    # X ST's two pieces meet through one block the centerline names after Y ST
    net = Network([seg("1", "X ST", N[0], N[1]), seg("2", "Y ST", N[1], N[2]), seg("3", "X ST", N[2], N[3]),
                   seg("4", "Y ST", N[2], (0.002, 0.001))])
    length, path = net.route("X ST", {N[0]}, {N[3]})
    assert [s["id"] for _, s in path] == ["1", "2", "3"]


def test_route_returns_none_when_unreachable():
    assert NET.route("X ST", {N[1]}, {(9.0, 9.0)}) is None


def test_point_along_halfway():
    assert point_along([(0, 0), (0, 1), (0, 3)], 0.5) == pytest.approx((0, 1.5))


MORE = KNOWN | {"4 AVE", "ATLANTIC AVE", "64 ST", "AVE J", "E 80 ST", "E 81 ST", "81 ST", "86 ST", "BAY 20 ST",
                "BAY 28 ST", "28 ST", "FLATBUSH AVE", "BEDFORD AVE", "224 ST", "223 ST"}
MORE_BASE = {base(n) for n in MORE}


@pytest.mark.parametrize("text, expected", [
    ("DTS WM RPLMT IN 4TH AV FR ATLANTIC AV TO 64TH ST", ("extent", "4 AVE", "ATLANTIC AVE", "64 ST")),
    ("ATLANTIC AVENUE RECONSTRUCTION - FLATBUSH TO BEDFORD", ("extent", "ATLANTIC AVE", "FLATBUSH", "BEDFORD")),
    ("SE RECON ON AVE J BTWN E 80TH & 81 ST", ("extent", "AVE J", "E 80", "E 81 ST")),   # not 81 St elsewhere
    ("DIST WM WORK IN 86TH ST BTW BAY 20TH & 28TH ST", ("extent", "86 ST", "BAY 20", "BAY 28 ST")),
    ("INSTALL STORM SANITARY SES AND WM ON 224 & 223 ST IN QUEENS", ("street_only", ["224 ST", "223 ST"])),
])
def test_parse_extent_variants(text, expected):
    assert parse(text, MORE, MORE_BASE) == expected


def test_extents_lists_every_stretch_in_order():
    known = MORE | {"7 ST", "3 AVE"}
    text = "WM IN 4TH AV FR ATLANTIC AV TO 64TH ST AND 86TH ST BTW BAY 20TH & 28TH ST"
    assert extents(text, known, {base(n) for n in known}) == [
        ("4 AVE", "ATLANTIC AVE", "64 ST"), ("86 ST", "BAY 20", "BAY 28 ST")]


def test_extents_shared_suffix_and_glued_street():
    known = {"7 ST", "3 AVE", "4 AVE", "3 ST"}
    assert extents("RELIEF SEWER AT 7ST B/T 3 & 4 AV", known, {base(n) for n in known}) == [("7 ST", "3 AVE", "4 AVE")]


def test_extents_bare_numbered_street_gives_each_direction():
    known = {"E 43 ST", "W 43 ST", "LEXINGTON AVE", "3 AVE"}
    text = "RECONSTRUCTION OF 43RD STREET BETWEEN LEXINGTON AVENUE AND 3RD AVENUE"
    assert extents(text, known, {base(n) for n in known}) == [
        ("E 43 ST", "LEXINGTON AVE", "3 AVE"), ("W 43 ST", "LEXINGTON AVE", "3 AVE")]
