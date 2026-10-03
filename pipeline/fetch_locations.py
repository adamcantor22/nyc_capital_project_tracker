"""Download location sources used to place capital projects on a map.

Join sources (keyed by FMS ID) are checked every run: CPDB points/polygons, Parks capital project
tracker, DOT/DEP intersections. Reference layers (FacDB, Parks Properties, Community Districts,
and the USGS GNIS names file for New York State) change rarely, so they are only checked with
--refresh-reference or when older than REFERENCE_MAX_AGE_DAYS. Only the columns the pipeline uses are downloaded.

Writes data/raw/<id>.json and data/raw/<id>.meta.json. --force refetches regardless.
"""
import argparse
import sys
import time

from socrata import RAW_DIR, check_columns, client, fetch_json, is_current, remote_count, remote_meta, save_meta

# USGS Geographic Names (GNIS) for New York State: official coordinates for upstate reservoirs.
GNIS_URL = ("https://prd-tnm.s3.amazonaws.com/StagedProducts/GeographicNames/DomesticNames/"
            "DomesticNames_NY_Text.zip")
GNIS_PATH = RAW_DIR / "gnis_ny.zip"

REFERENCE_MAX_AGE_DAYS = 180

# id -> (label, is_reference, columns used by pipeline/ingest.py)
DATASETS = {
    "h2ic-zdws": ("CPDB projects (points)", False, ["projectid", "magencyacro", "description", "the_geom"]),
    "9jkp-n57r": ("CPDB projects (polygons)", False, ["projectid", "magencyacro", "description", "the_geom"]),
    "4hcv-tc5r": ("Parks capital project tracker", False,
                  ["trackerid", "fmsid", "title", "latitude", "longitude", "borough", "totalfunding"]),
    "97nd-ff3i": ("DOT/DEP street reconstruction (intersections)", False,
                  ["fmsid", "projtitle", "leadagency", "the_geom"]),
    "ji82-xba5": ("DCP Facilities Database", True,
                  ["uid", "facname", "boro", "facgroup", "facsubgrp", "factype", "latitude", "longitude",
                   "opabbrev", "overabbrev"]),
    "enfh-gkve": ("Parks Properties", True, ["gispropnum", "signname", "borough", "typecategory", "multipolygon"]),
    "5crt-au7u": ("Community Districts", True, ["boro_cd", "the_geom"]),
    "4yue-vjfc": ("NYC DOT Bridge Ratings (BINs with coordinates)", True,
                  ["bin", "boro", "feature_carried", "feature_crossed", "x_coord_lat", "y_coord_lon", "cd"]),
    "9nt8-h7nd": ("Neighborhood Tabulation Areas (2020)", True,
                  ["nta2020", "ntaname", "boroname", "ntatype", "cdta2020", "the_geom"]),
    "inkn-q76z": ("Street centerline (CSCL)", True,
                  ["physicalid", "full_street_name", "stname_label", "boroughcode", "rw_type",
                   "segmentlength", "the_geom"]),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="refetch everything, even if unchanged")
    ap.add_argument("--refresh-reference", action="store_true", help="also check reference layers")
    args = ap.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with client() as c:
        for ds, (label, is_reference, columns) in DATASETS.items():
            path = RAW_DIR / f"{ds}.json"
            if is_reference and path.exists() and not (args.force or args.refresh_reference):
                age_days = (time.time() - path.stat().st_mtime) / 86400
                if age_days < REFERENCE_MAX_AGE_DAYS:
                    print(f"{ds}: reference layer, {age_days:.0f} days old, not checked")
                    continue
            meta = remote_meta(c, ds)
            check_columns(meta, columns)
            if not args.force and is_current(meta, path, columns):
                print(f"{ds}: unchanged, skipping")
                continue
            total = remote_count(c, ds)
            n = fetch_json(c, ds, path, total, columns)
            save_meta(ds, meta, total, columns)
            flag = "" if n == total else "  <-- COUNT MISMATCH"
            print(f"{ds}: {label} | remote rows={total} fetched={n}{flag}")

        age_days = (time.time() - GNIS_PATH.stat().st_mtime) / 86400 if GNIS_PATH.exists() else None
        if age_days is not None and age_days < REFERENCE_MAX_AGE_DAYS and not (args.force or args.refresh_reference):
            print(f"gnis: reference layer, {age_days:.0f} days old, not checked")
        else:
            r = c.get(GNIS_URL)
            r.raise_for_status()
            GNIS_PATH.write_bytes(r.content)
            print(f"gnis: USGS names for New York State | {len(r.content) / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
