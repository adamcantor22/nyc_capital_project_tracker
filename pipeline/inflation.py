"""Price indexes for constant-dollar comparisons, and which one each project uses.

Every amount in the data is nominal. A change across years (original to current budget, plan amendments) is
compared in constant dollars by the price index that fits the work:
  - `ppi_school`: BLS producer price index, new school building construction (PCU236222236222; monthly, from
    December 2005), for SCA projects and the city's Education theme (whether it covers college buildings is
    unverified);
  - `nhcci`: FHWA National Highway Construction Cost Index (quarterly, from 2003), for the city's streets,
    sidewalks, bridges, signals and lighting;
  - `bea_sl_structures`: BEA price index for state and local government gross investment in structures (NIPA,
    B842RG3; quarterly), for all other city work and the MTA;
  - `cpi_ny`: BLS consumer price index, all urban consumers, New York-Newark-Jersey City (CUURA101SA0; monthly),
    for "today's dollars" in general, not for construction.
The BEA and BLS series are fetched from FRED (the St. Louis Fed republishes them unchanged) and the NHCCI from
data.transportation.gov (r94d-n4f9); each row records the publisher's own series code and where it was fetched.
Indexes are fetched once into data/raw/inflation/ and refreshed with --refresh.

A value at a date is the observation of the period containing it (the latest observation on or before the date);
a date after the last observation takes the last one, and `index_at` reports that.

Writes price_index (index_id, period, value, publisher, series, fetched_from, frequency).
"""
import argparse
import csv
import io
import sys
from bisect import bisect_right
from datetime import date

import duckdb
import httpx

from db import DB_PATH, RAW_DIR, replace_table
from socrata import RetryTransport

OUT = RAW_DIR / "inflation"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
NHCCI = "https://datahub.transportation.gov/resource/r94d-n4f9.csv?$select=quarter,nhcci&$limit=5000"
INDEXES = {  # id -> (label, publisher, publisher series, fetch URL, fetched series, frequency)
    "bea_sl_structures": ("State and local government investment in structures", "BEA", "B842RG3",
                          FRED.format("B842RG3Q086SBEA"), "B842RG3Q086SBEA", "quarter"),
    "ppi_school": ("New school building construction", "BLS", "PCU236222236222",
                   FRED.format("PCU236222236222"), "PCU236222236222", "month"),
    "nhcci": ("National Highway Construction Cost Index", "FHWA", "NHCCI (r94d-n4f9)", NHCCI, "r94d-n4f9", "quarter"),
    "cpi_ny": ("Consumer prices, New York-Newark-Jersey City", "BLS", "CUURA101SA0",
               FRED.format("CUURA101SA0"), "CUURA101SA0", "month"),
}
CONSTRUCTION = ("bea_sl_structures", "ppi_school", "nhcci")
HIGHWAY_SUBTHEMES = {"Streets and sidewalks", "Bridges", "Signals and lighting"}


def construction_index(program: str, theme: str | None, subtheme: str | None) -> tuple[str, str]:
    """(index id, rule) for a project's construction work."""
    if program == "sca":
        return "ppi_school", "SCA school project"
    if program == "nyc_capital" and theme == "Education":
        return "ppi_school", "city Education theme"
    if program == "nyc_capital" and theme == "Transportation" and subtheme in HIGHWAY_SUBTHEMES:
        return "nhcci", f"city Transportation: {subtheme}"
    return "bea_sl_structures", "all other work"


def month_start(yyyymm: int | str) -> date:
    """A reporting period (202605) as the first day of its month."""
    return date(int(yyyymm) // 100, int(yyyymm) % 100, 1)


def parse(index_id: str, text: str) -> list[tuple[date, float]]:
    rows = list(csv.reader(io.StringIO(text)))[1:]
    out = []
    for period, value in rows:
        if value in ("", "."):
            continue
        if index_id == "nhcci":  # '2003 Q1'
            y, q = period.replace('"', "").split(" Q")
            d = date(int(y), 3 * int(q) - 2, 1)
        else:
            d = date.fromisoformat(period)
        out.append((d, float(value)))
    return sorted(out)


class Indexes:
    def __init__(self, rows: dict[str, list[tuple[date, float]]]):
        self.rows = rows
        self.dates = {k: [d for d, _ in v] for k, v in rows.items()}

    def index_at(self, index_id: str, day: date) -> tuple[float, bool] | None:
        """(value, extrapolated) of the period containing `day`; None before the series starts."""
        i = bisect_right(self.dates[index_id], day)
        if i == 0:
            return None
        return self.rows[index_id][i - 1][1], i == len(self.rows[index_id]) and day >= self._next(index_id)

    def _next(self, index_id: str) -> date:
        last = self.dates[index_id][-1]
        months = 3 if INDEXES[index_id][5] == "quarter" else 1
        m = last.month - 1 + months
        return date(last.year + m // 12, m % 12 + 1, 1)

    def ratio(self, index_id: str, frm: date, to: date) -> float | None:
        """Multiplier converting an amount recorded at `frm` into dollars of `to`."""
        a, b = self.index_at(index_id, frm), self.index_at(index_id, to)
        return b[0] / a[0] if a and b else None


def load(con) -> Indexes:
    rows = {}
    for k, d, v in con.execute("select index_id, period, value from price_index order by 1, 2").fetchall():
        rows.setdefault(k, []).append((d, v))
    return Indexes(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="refetch the indexes")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    out = []
    with httpx.Client(transport=RetryTransport(httpx.HTTPTransport()), timeout=60, follow_redirects=True) as c:
        for k, (_label, publisher, series, url, _fetched, freq) in INDEXES.items():
            path = OUT / f"{k}.csv"
            if args.refresh or not path.exists():
                r = c.get(url)
                r.raise_for_status()
                path.write_text(r.text)
            rows = parse(k, path.read_text())
            out += [(k, d.isoformat(), v, publisher, series, url, freq) for d, v in rows]
            print(f"{k}: {len(rows)} {freq}s, {rows[0][0]} to {rows[-1][0]}")
    con = duckdb.connect(str(DB_PATH))
    replace_table(con, "price_index", "index_id varchar, period date, value double, publisher varchar, "
                  "series varchar, fetched_from varchar, frequency varchar", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
