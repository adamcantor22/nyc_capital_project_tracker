from son import area_class, parse


def test_area_class_both_eras():
    assert area_class("Local - Queens CD 7") == "local"
    assert area_class("Community district") == "local"
    assert area_class("Bronx, CD 12") == "local"
    assert area_class("Regional – Brooklyn CDs 6, 7, 10, 11, 12 and 14") == "regional"
    assert area_class("Borough") == "regional"
    assert area_class("Regional/Brooklyn") == "regional"
    assert area_class("Queens") == "regional"
    assert area_class("Regional - Citywide (mainly Manhattan)") == "citywide"
    assert area_class("Citywide") == "citywide"
    assert area_class("") is None


OLD = """=== page 12
AGENCY  Administration for Children's Services (ACS)

PROPOSAL  Consolidation of Division of Child Protection Offices in the
Bronx

AREA SERVED  Regional – Bronx (boroughwide)

PUBLIC PURPOSE  ACS plans to consolidate
=== page 13
AGENCY
 Department of Health & Mental Hygiene (DOHMH)
PROPOSAL

 Queens Animal Receiving Center
AREA SERVED

 Queens
PUBLIC PURPOSE
"""

NEW = """=== page 40
AREA SERVED: The geography that the facility intends to serve (e.g., Community district,
Borough, Citywide).
PROPOSAL Relocation of Bronx District 2 Garage
=== page 41
DCAS Project ID 24-6191
STATUS New Proposal
AGENCY  Department of Sanitation (DSNY)
AREA SERVED Community District
FACILITY TYPE Operational
FACILITY
DOMAIN
Core Infrastructure and Transportation
PUBLIC FACING
"""


def test_parse_old_layout():
    rows = parse(OLD)
    assert [(r["page"], r["proposal"], r["area_class"]) for r in rows] == [
        (12, "Consolidation of Division of Child Protection Offices in the Bronx", "regional"),
        (13, "Queens Animal Receiving Center", "regional"),
    ]
    assert rows[1]["agency"] == "Department of Health & Mental Hygiene (DOHMH)"


def test_parse_new_layout_skips_definitions():
    (row,) = parse(NEW)
    assert row["proposal"] == "Relocation of Bronx District 2 Garage"
    assert row["agency"] == "Department of Sanitation (DSNY)"
    assert (row["page"], row["area_served"], row["area_class"]) == (41, "Community District", "local")
    assert row["facility_type"] == "Operational"
    assert row["facility_domain"] == "Core Infrastructure and Transportation"
