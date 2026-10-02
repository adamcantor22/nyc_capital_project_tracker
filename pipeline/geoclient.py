"""NYC Geoclient v2 client with a permanent on-disk cache (one request per distinct query, ever).

Requires GEOCLIENT_KEY in .env (api-portal.nyc.gov, product "Geoclient v2 User").
"""
import json
import os
import time

import httpx

from db import RAW_DIR
from socrata import load_env

BASE = "https://api.nyc.gov/geoclient/v2"
CACHE_PATH = RAW_DIR / "geoclient_cache.json"
KEEP = ["latitude", "longitude", "bbl", "buildingIdentificationNumber", "communityDistrict",
        "firstBoroughName", "boroughCode1In", "normalizedHouseNumber", "firstStreetNameNormalized",
        "message", "geosupportReturnCode",
        # BBL (tax lot) lookups put coordinates and the lot's address under these keys instead
        "latitudeInternalLabel", "longitudeInternalLabel", "giLowHouseNumber1", "giStreetName1"]


class Geoclient:
    def __init__(self, delay_s: float = 0.05):
        load_env()
        self.key = os.environ["GEOCLIENT_KEY"]
        self.delay_s = delay_s
        self.cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
        self.http = httpx.Client(timeout=30, headers={"Ocp-Apim-Subscription-Key": self.key})
        self.requests = 0

    def search(self, text: str) -> dict:
        """Single-input search. Returns {'status', 'level', **KEEP fields} for the top result."""
        key = f"search|{text}"
        if key not in self.cache:
            r = self.http.get(f"{BASE}/search.json", params={"input": text})
            r.raise_for_status()
            self.requests += 1
            d = r.json()
            top = (d.get("results") or [{}])[0]
            resp = top.get("response", {})
            self.cache[key] = {"status": top.get("status") or d.get("status"), "level": top.get("level"),
                               **{k: resp.get(k) for k in KEEP if k in resp}}
            time.sleep(self.delay_s)
        return self.cache[key]

    def forget(self, text: str) -> None:
        """Drop a cached search so the next call re-requests it (e.g. after KEEP changed)."""
        self.cache.pop(f"search|{text}", None)

    def save(self) -> None:
        CACHE_PATH.write_text(json.dumps(self.cache, indent=1, sort_keys=True))

    def close(self) -> None:
        self.save()
        self.http.close()
