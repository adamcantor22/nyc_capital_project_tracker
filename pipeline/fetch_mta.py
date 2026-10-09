"""Download the MTA capital program datasets (data.ny.gov).

The MTA's capital projects are its ACEPs (agency, category, element, project: 'T8041237'), each in one five-year
capital plan. The Capital Dashboard summary (ehz8-ag3n) holds every quarterly load of every ACEP since March 2020,
with original, latest-approved and current budgets and dates, so it carries its own history. The other datasets
show their current state, so each new version is also kept as data/raw/mta/<id>-<YYYYMMDD>.json.

Writes data/raw/<id>.json and data/raw/<id>.meta.json. Skips a dataset whose source is unchanged; --force
refetches. Fails with SchemaDrift if a dataset drops or renames a column the pipeline uses.
"""
import argparse
import datetime
import shutil
import sys

from socrata import (
    NY_STATE,
    RAW_DIR,
    check_columns,
    client,
    fetch_json,
    is_current,
    remote_count,
    remote_meta,
    save_meta,
)

ARCHIVE = RAW_DIR / "mta"

# id -> (label, keep dated copies, columns the pipeline uses)
DATASETS = {
    "ehz8-ag3n": ("MTA Capital Dashboard: every quarterly load of every ACEP", False, [
        "proj_num", "capital_plan", "loaddate", "agency_code", "agency_name", "category_description",
        "element_description", "proj_description", "scope_objective", "mega_project", "phase", "needs_code",
        "original_budget", "latest_approved_budget", "current_budget", "original_start_mm", "original_start_yyyy",
        "current_start_mm", "current_start_yyyy", "original_completion_mm", "original_completion_yyyy",
        "current_completion_mm", "current_completion_yyyy", "percentage_complete", "location_indicator"]),
    "wcsa-vkhf": ("MTA Capital Dashboard project locations (points per ACEP)", True, [
        "project_number", "project_number_sequence", "capital_plan", "latitude", "longitude",
        "location_indicator"]),
    "9hy6-8j6t": ("MTA C&D capital project details (large projects)", True, [
        "project_id", "title", "stage", "phase", "districts", "goal_completion_date",
        "estimated_actual_completion_date", "goal_project_cost", "estimated_actual_project_cost"]),
    "nswv-d6bz": ("MTA C&D capital project schedule milestones", True, [
        "project_id", "phase", "phase_state", "phase_est_actual_start_date", "phase_est_actual_end_date",
        "update_date"]),
    "f6fd-xfps": ("MTA C&D capital project budgets by ACEP, monthly", False, [
        "update_date", "project_id", "acep", "current_budget", "baseline_budget", "expenditures"]),
    "6kvv-fcph": ("MTA capital plan allocations per ACEP and plan revision", False, [
        "acep", "plan_id", "plan_revision", "date", "total_allocation", "change_nar"]),
    "39hk-dx4f": ("MTA Subway Stations (line, complex, borough per station)", False, [
        "station_id", "complex_id", "line", "stop_name", "borough", "daytime_routes", "gtfs_latitude",
        "gtfs_longitude"]),
    "wxmd-5cpm": ("MTA Rail Stations (LIRR and Metro-North, with branch)", False, [
        "railroad", "code", "station_name", "branch", "latitude", "longitude"]),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="refetch even if unchanged")
    args = ap.parse_args()
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    with client() as c:
        for ds, (label, archive, columns) in DATASETS.items():
            path = RAW_DIR / f"{ds}.json"
            meta = remote_meta(c, ds, NY_STATE)
            check_columns(meta, columns)
            if not args.force and is_current(meta, path):
                print(f"{ds}: unchanged, skipping")
                continue
            total = remote_count(c, ds, base=NY_STATE)
            n = fetch_json(c, ds, path, total, base=NY_STATE)
            save_meta(ds, meta, total)
            stamp = datetime.datetime.fromtimestamp(meta["rowsUpdatedAt"], datetime.UTC).strftime("%Y%m%d")
            if archive:
                shutil.copyfile(path, ARCHIVE / f"{ds}-{stamp}.json")
            flag = "" if n == total else "  <-- COUNT MISMATCH"
            print(f"{ds}: {label} | updated {stamp} | remote rows={total} fetched={n}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
