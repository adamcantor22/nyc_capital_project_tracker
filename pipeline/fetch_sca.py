"""Download the School Construction Authority (SCA) capital datasets, DOE building capacity, and DOE's
school location lists (which locate SCA building codes).

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

# id -> (label, keep dated copies). DOE's yearly school location lists locate building codes; they are
# no longer updated, so they are not archived.
DATASETS = {
    "2xh6-psuq": ("SCA capital project schedules and budgets (one row per project phase)", True),
    "8586-3zfm": ("SCA active projects under construction (with building locations)", True),
    "24nr-gahi": ("SCA five-year plan summary by capital category", True),
    "gkd7-3vk7": ("DOE enrollment, capacity and utilization by building", True),
    "wg9x-4ke6": ("DOE school locations 2019-20 (building code, coordinates)", False),
    "9ck8-hj3u": ("DOE school locations 2018-19 (building code, coordinates)", False),
    "p6h4-mpyy": ("DOE school locations 2017-18 (building code, coordinates)", False),
    "7a57-qgkz": ("DOE COVID-19 testing locations, Feb 2021 (building code, address)", False),
    "qybk-bjjc": ("DOE school safety report 2010-16 (building code, coordinates)", False),
}


FILINGS = "w9ak-ipjd"
FILINGS_PATH = RAW_DIR / "w9ak-ipjd-sca.json"
FILINGS_WHERE = ("upper(owner_s_business_name) like '%SCHOOL CONSTR%' or upper(owner_s_business_name) like '%NYCSCA%' "
                 "or upper(owner_s_business_name) like '%DEPT OF ED%' "
                 "or upper(owner_s_business_name) like '%DEPARTMENT OF EDUCATION%' "
                 "or upper(job_description) like '%SCHOOL%'")
FILINGS_COLUMNS = ["job_filing_number", "house_no", "street_name", "borough", "bin", "block", "lot",
                   "owner_s_business_name", "job_description", "filing_date"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="refetch even if unchanged")
    args = ap.parse_args()
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    with client() as c:
        for ds, (label, archive) in DATASETS.items():
            path = RAW_DIR / f"{ds}.json"
            meta = remote_meta(c, ds)
            if not args.force and is_current(meta, path):
                print(f"{ds}: unchanged, skipping")
                continue
            total = remote_count(c, ds)
            n = fetch_json(c, ds, path, total)
            save_meta(ds, meta, total)
            stamp = datetime.datetime.fromtimestamp(meta["rowsUpdatedAt"], datetime.UTC).strftime("%Y%m%d")
            if archive:
                shutil.copyfile(path, ARCHIVE / f"{ds}-{stamp}.json")
            flag = "" if n == total else "  <-- COUNT MISMATCH"
            print(f"{ds}: {label} | updated {stamp} | remote rows={total} fetched={n}{flag}")
        # DOB building filings by SCA or DOE, or about a school by anyone (the Trust for Governors Island filed
        # 'M533- HARBOR SCHOOL ...'): their descriptions name SCA building codes ('Q517- LANDSCAPE ...'). The full
        # dataset is large and updated daily, so only these rows are fetched, every run.
        total = remote_count(c, FILINGS, FILINGS_WHERE)
        n = fetch_json(c, FILINGS, FILINGS_PATH, total, FILINGS_COLUMNS, FILINGS_WHERE)
        print(f"{FILINGS}: DOB NOW job filings by SCA or DOE, or about a school | rows={total} fetched={n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
