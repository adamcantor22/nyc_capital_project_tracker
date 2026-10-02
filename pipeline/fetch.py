"""Download the four capital-project datasets from NYC Open Data (Socrata).

Writes data/raw/<id>.csv and data/raw/<id>.meta.json. Skips existing files unless --force.
"""
import argparse
import sys

from socrata import RAW_DIR, client, fetch_csv, remote_count, save_meta

DATASETS = ["fb86-vt7u", "gyhf-rsr3", "qj5n-h5qp", "95tx-snak"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="refetch existing files")
    args = ap.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with client() as c:
        for ds in DATASETS:
            csv_path = RAW_DIR / f"{ds}.csv"
            if csv_path.exists() and not args.force:
                print(f"{ds}: exists, skipping")
                continue
            meta = save_meta(c, ds, remote_count(c, ds))
            fetch_csv(c, ds, csv_path, meta["_remote_count"])
            print(f"{ds}: {meta['name']} | remote rows={meta['_remote_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
