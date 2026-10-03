"""Roll the 60 raw `current_phase` spellings up into phase groups (pipeline/phase_groups.csv).

Spellings are compared after dropping case and punctuation, so '(On-Hold)', '(On-hold)' and '(On Hold)'
are one value. Bracketed active phases ('(Pre-Design)') are the same phases without a reported
schedule; they count as Active, and `has_schedule` in the export says which.
"""
import csv
import re
from pathlib import Path

TABLE = Path(__file__).with_name("phase_groups.csv")
UNKNOWN = "Unknown"


def key(phase: str | None) -> str:
    return re.sub(r"[^a-z]", "", (phase or "").lower())


def load() -> dict[str, str]:
    with TABLE.open() as f:
        return {key(r["phase"]): r["group"] for r in csv.DictReader(f)}


def group(phase: str | None, groups: dict[str, str]) -> str:
    return groups.get(key(phase), UNKNOWN)
