"""Download the four capital-project datasets from NYC Open Data (Socrata).

Writes data/raw/<id>.csv and data/raw/<id>.meta.json. Skips a dataset when the local copy
matches the source's last update, unless --force.
"""
import argparse
import sys

from socrata import RAW_DIR, client, fetch_csv, is_current, remote_count, remote_meta, save_meta

DATASETS = ["fb86-vt7u", "gyhf-rsr3", "qj5n-h5qp", "95tx-snak"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="refetch even if unchanged")
    args = ap.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with client() as c:
        for ds in DATASETS:
            csv_path = RAW_DIR / f"{ds}.csv"
            meta = remote_meta(c, ds)
            if not args.force and is_current(meta, csv_path):
                print(f"{ds}: unchanged, skipping")
                continue
            total = remote_count(c, ds)
            fetch_csv(c, ds, csv_path, total)
            save_meta(ds, meta, total)  # after the data, so an interrupted fetch retries
            print(f"{ds}: {meta['name']} | remote rows={total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
