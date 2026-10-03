"""Roll `ten_year_plan_category` and agencies up into about a dozen themes (pipeline/themes.csv).

Many categories are specific ('WATER QUALITY MANDATES', 'FAIR BRIDGES') and decide the theme whoever
manages the project. Others are generic ('ROUTINE RECONSTRUCTION', 'ESSENTIAL RECONSTRUCTION OF
FACILITIES' spans libraries, DOT and cultural institutions), so the agency the work is for decides:
the sponsor, then an agency prefix in the title ('NYPD - ...'), then the capital budget line that
pays for it ('LQ-0122' is Queens Library, 'SE-0002Q' sewers), then the managing agency. DDC builds
for other agencies and has no theme of its own; DCAS counts only when nothing else does.
"""
import csv
import re
from pathlib import Path

TABLE = Path(__file__).with_name("themes.csv")
BUILDERS = {"DDC"}           # build for others: never decide a theme
FALLBACK_ONLY = {"DCAS"}     # manages energy and office work for many agencies
AGENCY_PREFIX = re.compile(r"\s*([A-Z+]{2,6})\s*[-:]\s")
OTHER = "Other"


def load() -> dict[str, dict]:
    """{'category': {...}, 'agency': {...}, 'budget_line': {...}}: key -> (theme, subtheme or None)."""
    with TABLE.open() as f:
        rows = list(csv.DictReader(f))
    return {kind: {r["key"]: (r["theme"], r["subtheme"] or None) for r in rows if r["kind"] == kind}
            for kind in ("category", "agency", "budget_line")}


def theme(category, sponsor, managing, title, budget_line, rules) -> tuple[str, str | None]:
    """(theme, subtheme). The first matching rule decides the theme; the subtheme comes from the first
    rule that agrees on the theme and names one (a DOT project with an 'HB' budget line is a bridge)."""
    by_agency = rules["agency"]
    m = AGENCY_PREFIX.match((title or "").upper())
    named = [*(s.strip() for s in (sponsor or "").split(",")), m.group(1) if m else None]
    candidates = [rules["category"].get(category)]
    candidates += [by_agency[a] for a in named if a in by_agency and a not in BUILDERS | FALLBACK_ONLY]
    candidates += [rules["budget_line"][c] for c in re.findall(r"\b([A-Z]{1,2})\s*-", budget_line or "")
                   if c in rules["budget_line"]]
    if managing in by_agency and managing not in BUILDERS | FALLBACK_ONLY:
        candidates.append(by_agency[managing])
    candidates = [c for c in candidates if c]
    if not candidates:  # last resort: DCAS as sponsor, title prefix or manager
        return next((by_agency[a] for a in [*named, managing] if a in FALLBACK_ONLY), (OTHER, None))
    decided = candidates[0][0]
    return decided, next((s for t, s in candidates if t == decided and s), None)
