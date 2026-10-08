"""Download MTA's subway origin-destination ridership estimate, aggregated by the server (data.ny.gov).

The dataset (one per year; 2025 is y2qv-fytt) estimates average trips per origin and destination station complex,
month, day of week and hour, from OMNY and MetroCard swipes (about 121 million rows a year). We need only morning
trips, whose origin is usually where the rider lives, so the server sums them per station pair, one month at a
time (a whole year's sum outlasts the server's time limit), and the months are added here:
  data/raw/mta/od-<id>-am.json         [origin, destination, riders] for trips starting 05:00-11:59
  data/raw/mta/od-<id>-complexes.json  each station complex's id, name, latitude and longitude
  data/raw/mta/od-<id>.meta.json       the dataset's metadata, the queries and when they ran
`riders` sums MTA's monthly averages by day of week over the year's months, days of week and hours, so it is a
weight for shares, not a count of trips. Skips when the source is unchanged; --force refetches.
"""
import argparse
import datetime
import json
import sys
import time

import httpx

from socrata import NY_STATE, RAW_DIR, check_columns, client, remote_meta

DATASET = "y2qv-fytt"  # MTA Subway Origin-Destination Ridership Estimate: 2025
OUT = RAW_DIR / "mta"
PAGE = 50_000
AM = "hour_of_day between 5 and 11"
PAIRS = {"$select": "origin_station_complex_id as o, destination_station_complex_id as d, "
                    "sum(estimated_average_ridership) as riders",
         "$group": "o, d", "$order": "o, d"}
COMPLEXES = {"$select": "origin_station_complex_id as id, origin_station_complex_name as name, "
                        "origin_latitude as lat, origin_longitude as lon",
             "$group": "id, name, lat, lon", "$order": "id"}
COLUMNS = ["hour_of_day", "origin_station_complex_id", "destination_station_complex_id", "origin_station_complex_name",
           "origin_latitude", "origin_longitude", "estimated_average_ridership"]


def paged(c, params: dict) -> list[dict]:
    rows: list[dict] = []
    while True:
        for wait in (30, 120, None):  # the server is sometimes slow to aggregate: retry a timed-out page
            try:
                r = c.get(f"{NY_STATE}/resource/{DATASET}.json",
                          params={**params, "$limit": PAGE, "$offset": len(rows)}, timeout=300)
                break
            except httpx.ReadTimeout:
                if wait is None:
                    raise
                time.sleep(wait)
        r.raise_for_status()
        page = r.json()
        rows.extend(page)
        if len(page) < PAGE:
            return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="refetch even if unchanged")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    meta_path = OUT / f"od-{DATASET}.meta.json"
    with client() as c:
        meta = remote_meta(c, DATASET, NY_STATE)
        check_columns(meta, COLUMNS)
        if not args.force and meta_path.exists() and \
                json.loads(meta_path.read_text()).get("rowsUpdatedAt") == meta.get("rowsUpdatedAt"):
            print(f"{DATASET}: unchanged, skipping")
            return 0
        pairs: dict[tuple[int, int], float] = {}
        complexes: dict[str, dict] = {}
        months = []
        for m in range(1, 13):
            rows = paged(c, {**PAIRS, "$where": f"{AM} and month = {m}"})
            if not rows:
                continue
            months.append(m)
            for r in rows:
                k = (int(r["o"]), int(r["d"]))
                pairs[k] = pairs.get(k, 0.0) + float(r["riders"])
            if not complexes:
                complexes = {r["id"]: r for r in paged(c, {**COMPLEXES, "$where": f"month = {m} and hour_of_day = 8"})}
            print(f"  month {m}: {len(pairs)} pairs so far")
        missing = {i for k in pairs for i in k} - {int(i) for i in complexes}
        if missing:
            raise RuntimeError(f"station complexes missing from month {months[0]}'s list: {sorted(missing)}")
    (OUT / f"od-{DATASET}-am.json").write_text(json.dumps([[o, d, round(v, 2)] for (o, d), v in sorted(pairs.items())]))
    stations = sorted(complexes.values(), key=lambda r: int(r["id"]))
    (OUT / f"od-{DATASET}-complexes.json").write_text(json.dumps(stations))
    meta["_queries"] = {"pairs": {**PAIRS, "$where": f"{AM} and month = <each month>"},
                        "complexes": {**COMPLEXES, "$where": f"month = {months[0]} and hour_of_day = 8"},
                        "months": months}
    meta["_fetched_at"] = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"{DATASET}: {len(pairs)} station pairs (morning trips, {len(months)} months), {len(complexes)} complexes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
