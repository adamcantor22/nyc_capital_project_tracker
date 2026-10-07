"""Past versions of the Capital Projects Database (CPDB: fi59-268w funding, h2ic-zdws points, 9jkp-n57r
polygons), from Internet Archive captures.

The pipeline otherwise holds CPDB in its latest state only (fetch_locations.py). The archive captured each
dataset's official export, as CSV or JSON, at irregular times since November 2022; some versions survive in only
one format, so both are taken. pipeline/archive.py downloads each distinct capture once, checks it against the
archive's SHA-1 digest and records it in data/raw/cpdb/archive/index.json. Each row names its CPDB version
(`ccpversion`), so captures are tied to versions by their content, not their capture date.
"""
import sys

from archive import fetch
from db import RAW_DIR

DATASETS = ("fi59-268w", "h2ic-zdws", "9jkp-n57r")
OUT = RAW_DIR / "cpdb" / "archive"


def main() -> int:
    for d in DATASETS:
        index = fetch(d, OUT, formats=("csv", "json"), pause=2.0)
    print(f"{len(index)} archived files in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
