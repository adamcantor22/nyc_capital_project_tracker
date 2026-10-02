"""Shared plumbing: .env loading, freshness checks, bulk table loads, the Geoclient cache."""
import json

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
