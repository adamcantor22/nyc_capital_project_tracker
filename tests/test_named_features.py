import pytest

from named_features import load_gazetteer

FEATURES = load_gazetteer()


def first_match(title):
    return next((f["feature_id"] for f in FEATURES if f["regex"].search(title)), None)


def test_gazetteer_ids_are_unique_and_lookups_present():
    ids = [f["feature_id"] for f in FEATURES]
    assert len(ids) == len(set(ids))
    assert all(f["lookup"] for f in FEATURES)
    assert {f["extent"] for f in FEATURES} <= {"point", "area", "linear"}
    assert all(len(f["lookup"]) == 14 and f["lookup"][4:].isdigit()
               for f in FEATURES if f["lookup"].startswith("bbl:"))   # bbl: + 10 digits


@pytest.mark.parametrize("title, expected", [
    ("BROOKLYN BRIDGE - HAZARD MITIGATION", "brooklyn_bridge"),
    ("BROOKLYN BRIDGE PARK SOLE SOURCE MASTER AGREEMENT", None),
    ("WASHINGTON BRIDGE OVER HARLEM RIVER BIN 2066919", "washington_bridge"),
    ("GEORGE WASHINGTON BRIDGE BUS STATION", None),
    ("OB-135-L - OAKWOOD BEACH WWTP HEADWORKS IMPROVEMENTS", "oakwood_beach_wrrf"),
    ("MIDLAND BEACH AND OAKWOOD BEACH EMERGENCY BERM INSTALLATION", None),
    ("BB06, QUEENS, GREEN INFRASTRUCTURE ROW INFILL FOR BOWERY BAY", None),
    ("OH-92 INSTALLATION OF DECHLORINATION SYSTEMS AT OWL'S HEAD WWTP", "owls_head_wrrf"),
    ("CSO-NC-TUN - NEWTOWN CREEK CSO STORAGE TUNNEL", "newtown_creek_tunnel"),
    ("KEC-1 - TUNNEL, SHAFTS & KENSICO ROCK EXCAVATION", "kensico_reservoir"),
    ("CAT-477 CATSKILL AQUEDUCT PRESSURE TUNNELS", "catskill_aqueduct"),
    ("BT-2 - BYPASS TUNNEL CONSTRUCTION - CDA-BT2/TUNNEL DELAWARE-RONDOUT AQUEDUCT", "delaware_bypass"),
    ("CROTON FILTRATION PLANT", "croton_filtration"),
    ("DISMANTAL OF QUEENS DETENTION FACILITY BORO BASED JAILS NEW QUEENS DETENTION FACILITY", "queens_bbj"),
    ("BORO BASED JAIL NEW MANHATTAN DETENTION FACILITY", "manhattan_bbj"),
    ("HORIZON JUVENILE DETENTION CENTER HVAC", None),
    ("QUEENS DETENTION FACILITY", "queens_bbj"),
])
def test_patterns(title, expected):
    assert first_match(title) == expected
