from ingest import borough, load_community_districts, load_cpdb_points, load_parks_tracker, strip_agency_prefix

SQUARE = {"type": "MultiPolygon",
          "coordinates": [[[[-73.95, 40.75], [-73.94, 40.75], [-73.94, 40.76], [-73.95, 40.76], [-73.95, 40.75]]]]}


def test_borough_codes_include_parks_style_letters():
    assert borough("B") == "Brooklyn"          # Parks Properties: B = Brooklyn, X = Bronx
    assert borough("X") == "Bronx"
    assert borough("MANHATTAN") == "Manhattan"
    assert borough("5") == "Staten Island"
    assert borough(None) is None


def test_strip_agency_prefix():
    assert strip_agency_prefix("846 P-4BWIDEN") == "P-4BWIDEN"
    assert strip_agency_prefix("P-4BWIDEN") == "P-4BWIDEN"
    assert strip_agency_prefix("HWK1669B") == "HWK1669B"


def test_cpdb_points_explode_multipoints_and_drop_out_of_nyc():
    rows = [{"projectid": "X1", "description": "d",
             "the_geom": {"type": "MultiPoint", "coordinates": [[-73.95, 40.75], [-73.96, 40.76], [0, 0]]}}]
    assert [r[2:] for r in load_cpdb_points(rows)] == [(-73.95, 40.75), (-73.96, 40.76)]


def test_parks_tracker_skips_bad_coordinates():
    rows = [{"fmsid": "846 P-1", "trackerid": "1", "title": "t", "latitude": "40.75", "longitude": "-73.95"},
            {"fmsid": "846 P-2", "trackerid": "2", "title": "t", "latitude": "0", "longitude": "0"},
            {"fmsid": "846 P-3", "trackerid": "3", "title": "t"}]
    assert [r[0] for r in load_parks_tracker(rows)] == ["P-1"]


def test_community_districts_skip_joint_interest_areas():
    rows = [{"boro_cd": "101", "the_geom": SQUARE}, {"boro_cd": "164", "the_geom": SQUARE},
            {"boro_cd": "595", "the_geom": SQUARE}]
    out = list(load_community_districts(rows))
    assert [(r[0], r[1], r[2]) for r in out] == [(101, "Manhattan", 1)]
