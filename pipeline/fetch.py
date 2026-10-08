"""Download the four capital-project datasets from NYC Open Data (Socrata), plus OMB's Capital Project Detail Data
(money and milestones, 14 editions from 2019 to 2023; OMB stopped updating it in January 2024, so after the first
fetch it is always current and skipped).

Writes data/raw/<id>.csv and data/raw/<id>.meta.json. Skips a dataset when the local copy
matches the source's last update, unless --force.
"""
import argparse
import sys

from socrata import RAW_DIR, check_columns, client, fetch_csv, is_current, remote_count, remote_meta, save_meta

# id -> columns the pipeline relies on (checked against Socrata metadata on every run)
DATASETS = {
    "fb86-vt7u": ["reporting_period", "managing_agency", "sponsor_agency", "pid", "fms_id", "total_budget",
                  "spend_to_date", "spend_to_date_1", "fms_project_name", "agency_project_name",
                  "agency_project_description", "current_phase", "forecast_completion", "actual_construction",
                  "actual_construction_1", "borough", "community_board", "budget_line", "ten_year_plan_category"],
    "gyhf-rsr3": ["reporting_period", "managing_agency", "fms_id", "fiscal_year", "total_budget_city_non_city",
                  "spend"],
    "qj5n-h5qp": ["managing_agency", "fms_id", "year_month_reported", "total_budget", "spend_to_date_1",
                  "budget_variance", "budget_variance_1"],
    "95tx-snak": ["reporting_period", "managing_agency", "pid", "completion_date", "variance_day"],
    "wa2y-rh4b": ["pub_date", "managing_agcy", "project_id", "project_descr", "budget_line", "delay_desc", "scope_text",
                  "orig_bud_amt", "city_plan_total", "noncity_plan_total", "city_prior_actual", "noncity_prior_actual"],
    "s7yh-frbm": ["pub_date", "managing_agcy", "project_id", "seq_number", "task_description", "orig_start_date",
                  "orig_end_date", "task_start_date", "task_end_date"],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="refetch even if unchanged")
    args = ap.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with client() as c:
        for ds, required in DATASETS.items():
            csv_path = RAW_DIR / f"{ds}.csv"
            meta = remote_meta(c, ds)
            check_columns(meta, required)
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
