"""Past versions of SCA's capital project schedules and budgets (2xh6-psuq), from Internet Archive captures.

Our own dated copies (data/raw/sca/) start in August 2026. The archive captured the dataset's official CSV export
at irregular times since 2014; pipeline/archive.py downloads each distinct capture once, checks it against the
archive's SHA-1 digest and records it in data/raw/sca/archive/index.json.
"""
import sys

from archive import fetch
from db import RAW_DIR

DATASET = "2xh6-psuq"
OUT = RAW_DIR / "sca" / "archive"


def main() -> int:
    index = fetch(DATASET, OUT)
    print(f"{len(index)} archived versions in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
