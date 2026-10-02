import json

import pytest

from street_lines import Network, parse, point_along
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


def test_route_returns_none_when_unreachable():
    assert NET.route("X ST", {N[1]}, {(9.0, 9.0)}) is None


def test_point_along_halfway():
    assert point_along([(0, 0), (0, 1), (0, 3)], 0.5) == pytest.approx((0, 1.5))
