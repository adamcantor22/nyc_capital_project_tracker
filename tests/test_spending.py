from spending import city_draft, sca_draft


def test_city_delivery_from_the_raw_phase_and_crews():
    assert city_draft("JOB ORDER CONTRACTING WORK IN REGIONS NORTH", "(Job Order Contract)")[:3] == \
        ("physical", "", "job_order_contract")
    assert city_draft("IN-HOUSE RESURFACING - CREWS&OTHER NON-ASPHALT OTPS", "(Funding Agreement)")[2] == "in_house"
    assert city_draft("BNYDC Infrastructure Waterfront", "(Pass-Through Fund)")[2] == "pass_through"


def test_city_enterprise_it_is_overhead_but_not_paint_application():
    assert city_draft("DCAS Civil Service Exams - Mainframe Replacement", "(IT Project)")[0] == "overhead"
    assert city_draft("CW IT Cabling Upgrade", "Construction")[0] == "overhead"
    assert city_draft("Citywide Inspection/Monitoring of Bridge Paint Removal & App", "(Lump Sum)")[0] == "physical"


def test_city_money_set_aside_is_flagged_for_review():
    kind, flag, _, basis = city_draft("Agency Proposed Outyear Projects", "(Holding Code)")
    assert (kind, flag) == ("overhead", "yes") and basis.startswith("review:")
    assert city_draft("RECONS OF WPCPS AND PUMPING STATIONS DUE TO HURRICANE SANDY", "(Holding Code)")[:2] == \
        ("physical", "")


def test_city_study_institute_is_not_a_study():
    assert city_draft("Haitian Studies Institute Initial Outfitting", "Construction")[3] == "rule: physical work"
    assert city_draft("Citywide - Comfort Stations Standards Study", "Design")[3].startswith("review: a study")


def test_sca_screened_types_are_physical_for_review():
    assert sca_draft("SCA CIP", "LEASE")[3].startswith("review: a lease")
    assert sca_draft("SCA IEH", "IEH TESTING")[3].startswith("review: environmental hygiene")
    assert sca_draft("SCA Furniture & Equipment", "F&E")[0] == "physical"
