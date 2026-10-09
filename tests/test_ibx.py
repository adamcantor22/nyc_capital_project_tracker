import json

import pytest

from ibx import TITLE, block_middle, load, meeting_point
from street_lines import Network


def test_meeting_point_where_lines_cross():
    point, gap = meeting_point([[(-73.90, 40.70), (-73.90, 40.71)]], [[(-73.91, 40.705), (-73.89, 40.705)]])
    assert gap == 0 and point == pytest.approx((-73.90, 40.705))


def test_meeting_point_nearest_on_rail_when_they_do_not_cross():
    # the street stops 0.0002 degrees of latitude (about 22 m) short of the rail line
    point, gap = meeting_point([[(-73.90, 40.70), (-73.90, 40.7048)]], [[(-73.91, 40.705), (-73.89, 40.705)]])
    assert gap == pytest.approx(22.1, abs=0.5) and point == pytest.approx((-73.90, 40.705))


def seg(pid, street, a, b):
    return (pid, street, 100.0, a[0], a[1], b[0], b[1], json.dumps({"type": "MultiLineString",
                                                                 "coordinates": [[list(a), list(b)]]}))


def test_block_middle():
    net = Network([seg("1", "2 AVE", (0.0, 0.0), (0.001, 0.0)), seg("2", "2 AVE", (0.001, 0.0), (0.003, 0.0)),
                   seg("3", "59 ST", (0.0, 0.0), (0.0, 0.001)), seg("4", "63 ST", (0.003, 0.0), (0.003, 0.001))])
    assert block_middle(net, "2 AVE", "59 ST", "63 ST") == pytest.approx((0.0015, 0.0))


def test_title_names_the_ibx():
    assert TITLE.search("Ibx: Project Development") and TITLE.search("Interborough Express Gec")
    assert not TITLE.search("Ibxyz Relay Room")


def test_station_rows_cite_the_scoping_document_and_say_how_to_place():
    rows = load()
    assert [int(r["no"]) for r in rows] == list(range(1, len(rows) + 1))
    for r in rows:
        assert "document 187036" in r["evidence"] and "Table 4" in r["evidence"]
        if r["status"] == "proposed":
            assert r["street"] and bool(r["rail_feature"]) != bool(r["between"])
    assert [r["station"] for r in rows if r["status"] == "dropped"] == ["Sutter Avenue"]
