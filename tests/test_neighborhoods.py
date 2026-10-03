import json

import pytest

from neighborhoods import NeighborhoodIndex

SQUARE = json.dumps({"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]})
ROWS = [
    ("QN1301", "Laurelton", "Queens", "QN13", -73.74, 40.67, SQUARE),
    ("BK0702", "Sunset Park (West)", "Brooklyn", "BK07", -74.01, 40.65, SQUARE),
    ("BK0703", "Sunset Park (Central)", "Brooklyn", "BK07", -74.00, 40.64, SQUARE),
    ("MN1001", "Harlem (South)", "Manhattan", "MN10", -73.95, 40.81, SQUARE),
    ("MN1101", "East Harlem (South)", "Manhattan", "MN11", -73.94, 40.79, SQUARE),
    ("BX0401", "Concourse-Concourse Village", "Bronx", "BX04", -73.92, 40.83, SQUARE),
    ("BK1501", "Gravesend (South)", "Brooklyn", "BK15", -73.97, 40.59, SQUARE),
    ("BK5591", "Green-Wood Cemetery", "Brooklyn", "BK55", -73.99, 40.65, SQUARE),
]
IDX = NeighborhoodIndex(ROWS)


@pytest.mark.parametrize("title, boro, parts", [
    ("SEQ - Laurelton Area - Part 1, Phase C", "Queens", ["LAURELTON"]),
    ("Sunset Park Waterfront Redevelopment", "Brooklyn", ["SUNSET PARK"]),
    ("NDF - EAST HARLEM SBS WORKFORCE1 CENTER", "Manhattan", ["EAST HARLEM"]),   # not plain HARLEM too
    ("LOWER CONCOURSE INITIATIVE", "Bronx", ["CONCOURSE"]),
    ("Laurelton Area", "Brooklyn", []),                                            # wrong borough
    ("GRAVESEND BAY CSO TRIB AREA", "Brooklyn", []),                               # water body
    ("LAURELTON PKWY RESURFACING", "Queens", []),                                  # street
    ("Grand Concourse Phase 5", "Bronx", []),                                      # street
    ("DEP GREEN INFRASTRUCTURE", "Brooklyn", []),                                  # 'Green-Wood' part
])
def test_match(title, boro, parts):
    assert IDX.match(title, boro)[0] == parts


def test_locate_averages_parts_of_one_neighborhood():
    lon, lat, n, spread, label, ntas = IDX.locate("Sunset Park Areawide Infrastructure", "Brooklyn", [])
    assert n == 2 and ntas == ["BK0702", "BK0703"] and spread < 3000


def test_locate_requires_a_listed_district():
    assert IDX.locate("SEQ - Laurelton Area", "Queens", [413]) is not None
    assert IDX.locate("SEQ - Laurelton Area", "Queens", [412]) is None
