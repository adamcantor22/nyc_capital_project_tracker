"""Download the School Construction Authority (SCA) capital datasets and DOE building capacity.

SCA runs its own capital plan for public schools, outside the city's capital project data. Its datasets
show only their current state, so each new version is also kept as data/raw/sca/<id>-<YYYYMMDD>.json:
those copies are the only record of how budgets and schedules change.

Writes data/raw/<id>.json and data/raw/<id>.meta.json. Skips a dataset whose source is unchanged; --force
refetches.
"""
import argparse
import datetime
import shutil
import sys

from socrata import RAW_DIR, client, fetch_json, is_current, remote_count, remote_meta, save_meta

ARCHIVE = RAW_DIR / "sca"

DATASETS = {
    "2xh6-psuq": "SCA capital project schedules and budgets (one row per project phase)",
    "8586-3zfm": "SCA active projects under construction (with building locations)",
    "24nr-gahi": "SCA five-year plan summary by capital category",
    "gkd7-3vk7": "DOE enrollment, capacity and utilization by building",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="refetch even if unchanged")
    args = ap.parse_args()
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    with client() as c:
        for ds, label in DATASETS.items():
            path = RAW_DIR / f"{ds}.json"
            meta = remote_meta(c, ds)
            if not args.force and is_current(meta, path):
                print(f"{ds}: unchanged, skipping")
                continue
            total = remote_count(c, ds)
            n = fetch_json(c, ds, path, total)
            save_meta(ds, meta, total)
            stamp = datetime.datetime.fromtimestamp(meta["rowsUpdatedAt"], datetime.UTC).strftime("%Y%m%d")
            shutil.copyfile(path, ARCHIVE / f"{ds}-{stamp}.json")
            flag = "" if n == total else "  <-- COUNT MISMATCH"
            print(f"{ds}: {label} | updated {stamp} | remote rows={total} fetched={n}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
