"""CPDB history: every release of the Capital Projects Database held, funding and geometry per project.

Sources: Internet Archive captures of the official exports (pipeline/fetch_cpdb_archive.py; capture time, archive
URL and SHA-1 digest in data/raw/cpdb/archive/index.json) and our current copies (data/raw/<id>.json, from
fetch_locations.py). Each row names its CPDB version (`ccpversion`, e.g. fisa_2025), but one label can cover
several releases, so a release is identified by content: files of a dataset with the same rows (in any order) are
one release, whatever their format or capture time. A release's `release` date is the dataset's rowsUpdatedAt
where a JSON export or our metadata records it, else its first capture (the state then or earlier).

Column names differ by era (2022-23 JSON point and polygon files use shapefile-truncated names, 'descriptio';
2024-26 point and polygon CSVs abbreviations, 'pctotal'); ALIASES maps each to one name. Releases before 2024
publish planned commitments only, so their commit_* fields are null. Geometry is WKT in the exports, GeoJSON in
our copies.

Writes:
  - cpdb_versions: one row per file: dataset, origin (archive or own), capture, archive URL, digest, ccpversion,
    rowsUpdatedAt, rows, content fingerprint, release date, `same_as` (the release's first file, when not this one);
  - cpdb_history_funding: one row per (release, projectid, agency) from fi59-268w: planned commitments by source
    (city, state, federal, other) and the published total, commitments to date by source where published;
  - cpdb_history_geoms: one row per (release, dataset, projectid, agency) from h2ic-zdws (points) and 9jkp-n57r
    (polygons): the geometry as GeoJSON and its point (polygons: label_point; points: central_point of those in
    the city), with the number of points in the city.
Every row carries its dataset and file.

Run after pipeline/fetch_cpdb_archive.py and fetch_locations.py.
"""
import csv
import datetime
import hashlib
import io
import json
import sys

import duckdb

from db import DB_PATH, RAW_DIR, replace_table
from geo import central_point, from_wkt, in_nyc, label_point, points

csv.field_size_limit(sys.maxsize)

ARCHIVE = RAW_DIR / "cpdb" / "archive"
FUNDING, POINTS, POLYGONS = "fi59-268w", "h2ic-zdws", "9jkp-n57r"
DATASETS = (FUNDING, POINTS, POLYGONS)
ALIASES = {  # one name -> the names it has had, in order of preference
    "ccpversion": ["ccpversion"],
    "projectid": ["projectid"],
    "agency": ["magencyacro", "magencyacr", "magenacro"],
    "description": ["description", "descriptio", "descript"],
    "plan_city": ["totalcityplannedcommit", "totalcityp", "plannedcommit_citycost", "pccc"],
    "plan_state": ["nccstate", "plannedcommit_nccstate", "pcnccstate"],
    "plan_federal": ["nccfederal", "plannedcommit_nccfederal", "pcnccfed"],
    "plan_other": ["nccother", "plannedcommit_nccother", "pcnccother"],
    "plan_total": ["totalplannedcommit", "totalplann", "plannedcommit_total", "pctotal"],
    "commit_city": ["commit_citycost", "cocc"],
    "commit_state": ["commit_nccstate", "conccstate"],
    "commit_federal": ["commit_nccfederal", "conccfed"],
    "commit_other": ["commit_nccother", "conccother"],
    "geom": ["the_geom", "geometry"],
}
MONEY = ["plan_city", "plan_state", "plan_federal", "plan_other", "plan_total",
         "commit_city", "commit_state", "commit_federal", "commit_other"]


def canonical(row: dict) -> dict:
    out = {}
    for name, olds in ALIASES.items():
        key = next((k for k in olds if k in row), None)
        out[name] = row[key] if key else None
    return out


def amount(v) -> float | None:
    return float(v) if v not in (None, "") else None


def geometry(v) -> dict | None:
    if isinstance(v, dict):
        return v
    return from_wkt(v) if isinstance(v, str) else None


def read(path) -> tuple[list[dict], int | None]:
    """Canonical rows and the export's rowsUpdatedAt (JSON exports only)."""
    if path.suffix == ".csv":
        return [canonical(r) for r in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig")))], None
    doc = json.loads(path.read_text())
    if isinstance(doc, list):  # our copy: SODA rows
        return [canonical(r) for r in doc], None
    cols = [c["fieldName"] for c in doc["meta"]["view"]["columns"]]
    return [canonical(dict(zip(cols, r, strict=True))) for r in doc["data"]], doc["meta"]["view"].get("rowsUpdatedAt")


def fingerprint(rows: list[dict]) -> str:
    """Content of a file, independent of format and row order: ids, money and geometry (6 decimals)."""
    def rounded(c):
        return [rounded(x) for x in c] if isinstance(c, list) else round(float(c), 6)

    def norm(r):
        g = geometry(r["geom"])
        coords = repr(rounded(g["coordinates"])) if g else ""
        return (r["projectid"] or "", r["agency"] or "", *(f"{amount(r[k]) or 0:.0f}" for k in MONEY[:5]), coords)
    return hashlib.sha1(repr(sorted(norm(r) for r in rows)).encode()).hexdigest()[:16]


def day(ts: int | None) -> datetime.date | None:
    return datetime.datetime.fromtimestamp(ts, datetime.UTC).date() if ts else None


def files() -> list[dict]:
    """Every file of the three datasets: archive captures, then our current copies."""
    out = [dict(e, origin="archive", path=ARCHIVE / e["file"])
           for e in json.loads((ARCHIVE / "index.json").read_text()) if e["dataset"] in DATASETS]
    for d in DATASETS:
        meta = json.loads((RAW_DIR / f"{d}.meta.json").read_text())
        out.append({"file": f"{d}.json", "dataset": d, "origin": "own", "path": RAW_DIR / f"{d}.json",
                    "captured": None, "archive_url": None, "digest": None,
                    "rows_updated": meta.get("rowsUpdatedAt")})
    return out


def main() -> int:
    versions, funding, geoms = [], [], []
    first = {}  # (dataset, fingerprint) -> release date and first file
    loaded = []
    for f in files():
        rows, updated = read(f["path"])
        updated = updated or f.get("rows_updated")
        captured = datetime.datetime.strptime(f["captured"], "%Y%m%d%H%M%S").date() if f["captured"] else None
        loaded.append((f, rows, fingerprint(rows), day(updated), captured))
    # a release's date: its earliest rowsUpdatedAt, else its earliest capture
    for f, _, fp, updated, captured in sorted(loaded, key=lambda x: (x[3] or x[4], x[0]["file"])):
        key = (f["dataset"], fp)
        if key not in first or (updated and not first[key][2]):
            first[key] = (updated or captured, f["file"], updated)
    for f, rows, fp, updated, captured in loaded:
        release, first_file, _ = first[(f["dataset"], fp)]
        labels = sorted({r["ccpversion"] for r in rows if r["ccpversion"]})
        versions.append((f["dataset"], f["file"], f["origin"], captured, f["archive_url"], f["digest"],
                         ",".join(labels) or None, updated, len(rows), fp, release,
                         None if first_file == f["file"] else first_file))
        if first_file != f["file"]:
            continue
        for r in rows:
            if not r["projectid"]:
                continue
            base = (release, r["ccpversion"], r["projectid"], r["agency"], r["description"])
            if f["dataset"] == FUNDING:
                funding.append((*base, *(amount(r[k]) for k in MONEY), f["dataset"], f["file"]))
                continue
            g = geometry(r["geom"])
            if not g:
                continue
            if f["dataset"] == POLYGONS:
                lon, lat = label_point(g)
                n = int(in_nyc(lat, lon))
            else:
                pts = [p for p in points(g) if in_nyc(p[1], p[0])]
                lon, lat = central_point(pts) if pts else (None, None)
                n = len(pts)
            kind = "polygon" if f["dataset"] == POLYGONS else "point"
            geoms.append((*base, kind, lon, lat, n, json.dumps(g), f["dataset"], f["file"]))
    con = duckdb.connect(str(DB_PATH))
    replace_table(con, "cpdb_versions",
                  "dataset varchar, file varchar, origin varchar, captured date, archive_url varchar, digest varchar, "
                  "ccpversion varchar, rows_updated date, n_rows integer, fingerprint varchar, release date, "
                  "same_as varchar", [tuple(x.isoformat() if isinstance(x, datetime.date) else x for x in v)
                                      for v in versions])
    head = "release date, ccpversion varchar, projectid varchar, agency varchar, description varchar, "
    replace_table(con, "cpdb_history_funding",
                  head + ", ".join(f"{k} double" for k in MONEY) + ", dataset varchar, file varchar",
                  [(r[0].isoformat(), *r[1:]) for r in funding])
    replace_table(con, "cpdb_history_geoms",
                  head + "kind varchar, lon double, lat double, n_points integer, geom varchar, dataset varchar, "
                  "file varchar", [(r[0].isoformat(), *r[1:]) for r in geoms])
    print(con.execute("""select dataset, release, string_agg(distinct ccpversion, ','), max(n_rows),
                         count(*) as n_files from cpdb_versions group by all order by 1, 2""").fetchall())
    return 0


if __name__ == "__main__":
    sys.exit(main())
