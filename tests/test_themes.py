import csv
from pathlib import Path

import pytest

import phase_groups
import themes

RULES = themes.load()


@pytest.mark.parametrize("category, sponsor, managing, title, budget_line, expected", [
    ("WATER QUALITY MANDATES", None, "EDC", "", "", ("Water and sewer", "Treatment and water quality")),
    ("ESSENTIAL RECONSTRUCTION OF FACILITIES", "NYPL", "DDC", "", "LN-0001", ("Libraries and culture", "Libraries")),
    ("ESSENTIAL RECONSTRUCTION OF FACILITIES", None, "DDC", "", "PV-0022", ("Libraries and culture", "Culture")),
    ("MISCELLANEOUS ENERGY EFFICIENCY AND SUSTAINABILITY", None, "DCAS", "NYPD - 10th Precinct", "PU-0025",
     ("Public safety and justice", "Police")),                                   # title prefix beats DCAS
    ("REPLACEMENT OF CHRONICALLY FAILING COMPONENTS", None, "DDC", "", "SE-0002Q",
     ("Water and sewer", "Water mains and sewers")),                             # budget line when DDC builds
    ("BRIDGE LIFE EXTENSION AND MISCELLANEOUS WORK", None, "DOT", "", "HB-1047", ("Transportation", "Bridges")),
    ("GARAGES AND FACILITIES", None, "DDC", "", "S -0195", ("Sanitation", None)),  # 'S -0195' spacing
    ("New Jail Facilities", None, "DDC", "", "", ("Public safety and justice", "Jails and corrections")),
    ("ROUTINE RECONSTRUCTION", None, "DCAS", "", "", ("Government buildings and operations", None)),
    (None, None, "DDC", "", "", ("Other", None)),
])
def test_theme(category, sponsor, managing, title, budget_line, expected):
    assert themes.theme(category, sponsor, managing, title, budget_line, RULES) == expected


def test_themes_csv_is_well_formed():
    with (Path(__file__).parents[1] / "pipeline" / "themes.csv").open() as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["kind", "key", "theme", "subtheme"]
    assert [i for i, r in enumerate(rows, 1) if len(r) != 4] == []
    assert {r[0] for r in rows[1:]} == {"category", "agency", "budget_line"}
    assert len({(r[0], r[1]) for r in rows[1:]}) == len(rows) - 1


@pytest.mark.parametrize("raw, expected", [
    ("(On-Hold)", "Stalled"), ("(On-hold)", "Stalled"), ("(On Hold)", "Stalled"),
    ("Construction procurement", "Active"), ("CONSTRUCTION", "Active"), ("(Pre-Design)", "Active"),
    ("(cancelled)", "Ended early"), ("(Completed)", "Done"), ("(Partner-managed)", "Partner-managed"),
    ("Something new", "Unknown"),
])
def test_phase_group(raw, expected):
    assert phase_groups.group(raw, phase_groups.load()) == expected
