"""Shared plumbing: .env loading, freshness checks, bulk table loads, the Geoclient cache."""
import csv
import json
from pathlib import Path

import duckdb

import db
import geoclient
import socrata


def test_load_env_does_not_override_existing(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\nA_KEY='quoted'\nB_KEY=from_file\n")
    monkeypatch.delenv("A_KEY", raising=False)
    monkeypatch.setenv("B_KEY", "from_env")
    socrata.load_env(env)
    assert socrata.os.environ["A_KEY"] == "quoted"
    assert socrata.os.environ["B_KEY"] == "from_env"


def test_is_current_compares_rows_updated_at(tmp_path, monkeypatch):
    monkeypatch.setattr(socrata, "RAW_DIR", tmp_path)
    data = tmp_path / "abcd-1234.csv"
    assert not socrata.is_current({"id": "abcd-1234", "rowsUpdatedAt": 5}, data)   # nothing local
    data.write_text("x")
    (tmp_path / "abcd-1234.meta.json").write_text(json.dumps({"rowsUpdatedAt": 5}))
    assert socrata.is_current({"id": "abcd-1234", "rowsUpdatedAt": 5}, data)
    assert not socrata.is_current({"id": "abcd-1234", "rowsUpdatedAt": 6}, data)


def test_is_current_refetches_when_selected_columns_change(tmp_path, monkeypatch):
    monkeypatch.setattr(socrata, "RAW_DIR", tmp_path)
    data = tmp_path / "abcd-1234.json"
    data.write_text("[]")
    socrata.save_meta("abcd-1234", {"id": "abcd-1234", "rowsUpdatedAt": 5}, 0, ["a", "b"])
    assert socrata.is_current({"id": "abcd-1234", "rowsUpdatedAt": 5}, data, ["a", "b"])
    assert not socrata.is_current({"id": "abcd-1234", "rowsUpdatedAt": 5}, data, ["a", "b", "c"])


def test_check_columns_reports_missing_columns():
    meta = {"id": "abcd-1234", "name": "Thing", "columns": [{"fieldName": "fms_id"}, {"fieldName": "borough"}]}
    socrata.check_columns(meta, ["fms_id", "borough"])
    try:
        socrata.check_columns(meta, ["fms_id", "pid", "total_budget"])
    except socrata.SchemaDrift as e:
        assert "pid, total_budget" in str(e) and "abcd-1234" in str(e)
    else:
        raise AssertionError("expected SchemaDrift")


def test_replace_table_bulk_loads_and_replaces(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "RAW_DIR", tmp_path)
    con = duckdb.connect()
    db.replace_table(con, "t", "a varchar, b double", [("x", 1.5), ("y", None)])
    assert con.execute("select * from t order by a").fetchall() == [("x", 1.5), ("y", None)]
    db.replace_table(con, "t", "a varchar, b double", [])
    assert con.execute("select count(*) from t").fetchone()[0] == 0
    assert not list(tmp_path.iterdir())           # temp file cleaned up


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeHttp:
    def __init__(self):
        self.calls = 0

    def get(self, url, params):
        self.calls += 1
        return FakeResponse({"status": "OK", "results": [{"status": "EXACT_MATCH", "level": "0", "response": {
            "latitude": 40.71, "longitude": -74.0, "communityDistrict": "101", "ignored": "x"}}]})

    def close(self):
        pass


def test_geoclient_caches_permanently(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOCLIENT_KEY", "test")
    monkeypatch.setattr(geoclient, "CACHE_PATH", tmp_path / "cache.json")
    gc = geoclient.Geoclient(delay_s=0)
    gc.http = FakeHttp()
    first = gc.search("2 Lafayette St, Manhattan")
    assert gc.search("2 Lafayette St, Manhattan") == first
    assert gc.http.calls == 1 and gc.requests == 1
    assert "ignored" not in first and first["status"] == "EXACT_MATCH"
    gc.close()

    again = geoclient.Geoclient(delay_s=0)        # a new run reads the cache from disk
    again.http = FakeHttp()
    assert again.search("2 Lafayette St, Manhattan") == first
    assert again.http.calls == 0


def test_golden_locations_csv_rows_have_five_fields():
    """An unquoted comma in an evidence note silently splits the row (DictReader drops the rest)."""
    with (Path(__file__).parent / "golden_locations.csv").open() as f:
        rows = list(csv.reader(f))
    assert [i for i, r in enumerate(rows, 1) if len(r) != len(rows[0])] == []


def test_parse_money():
    from ingest import parse_money
    assert parse_money("$1,501,000") == 1501000.0
    assert parse_money("") is None and parse_money(None) is None


def test_source_errors_csv_is_well_formed():
    with (Path(__file__).parents[1] / "pipeline" / "source_errors.csv").open() as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["fms_id", "source", "problem", "detail", "evidence"]
    assert [i for i, r in enumerate(rows, 1) if len(r) != 5] == []
    sources = {"parks_tracker", "cpdb_points", "cpdb_polygons", "dot_intersections", "bridge_bin",
               "geoclient_address"}
    problems = {"point_wrong", "listing_wrong", "generic_point", "unclear"}
    assert all(r[1] in sources and r[2] in problems and r[4] for r in rows[1:])
    assert len({(r[0], r[1]) for r in rows[1:]}) == len(rows) - 1   # one row per project and source
