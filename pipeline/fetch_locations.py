"""Download location sources used to place capital projects on a map.

Tier A (join on FMS ID): CPDB points/polygons, Parks capital project tracker, DOT/DEP intersections.
Tier B (name matching):  DCP Facilities Database, Parks Properties.
Tier C (district floor): Community Districts.

Writes data/raw/<id>.json and data/raw/<id>.meta.json. Skips existing files unless --force.
"""
import argparse
import sys

from socrata import RAW_DIR, client, fetch_json, remote_count, save_meta

DATASETS = {
    "h2ic-zdws": "CPDB projects (points)",
    "9jkp-n57r": "CPDB projects (polygons)",
    "4hcv-tc5r": "Parks capital project tracker",
    "97nd-ff3i": "DOT/DEP street reconstruction (intersections)",
    "ji82-xba5": "DCP Facilities Database",
    "enfh-gkve": "Parks Properties",
    "5crt-au7u": "Community Districts",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="refetch existing files")
    args = ap.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with client() as c:
        for ds, label in DATASETS.items():
            path = RAW_DIR / f"{ds}.json"
            if path.exists() and not args.force:
                print(f"{ds}: exists, skipping")
                continue
            total = remote_count(c, ds)
            save_meta(c, ds, total)
            n = fetch_json(c, ds, path, total)
            flag = "" if n == total else "  <-- COUNT MISMATCH"
            print(f"{ds}: {label} | remote rows={total} fetched={n}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
