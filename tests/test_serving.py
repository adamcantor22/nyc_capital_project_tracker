import re

from serving import CLASSES, classify, load_rules, match


def rule(**kw):
    r = {"kind": "program", "program": "nyc_capital", "scope": "", "key": "", "area_class": "local",
         "basis": "rule: x", "rule_no": 1, **kw}
    if r["kind"] == "title":
        r["regex"] = re.compile(r["key"], re.I)
    return r


def test_scope_and_kinds():
    p = {"program": "nyc_capital", "id": "X1", "theme": "Sanitation", "subtheme": None,
         "title": "DSNY QUEENS 7 GARAGE", "category": "GARAGES AND FACILITIES", "location_source": "dsny_unit"}
    assert match(rule(kind="title", key=r"\bGARAGE\b", scope="Sanitation"), p)
    assert match(rule(kind="title", key=r"\bGARAGE\b", scope="Parks"), p) is None
    assert match(rule(kind="location_source", key="dsny_unit"), p)
    assert match(rule(kind="category", key="garages and facilities"), p)
    assert match(rule(kind="program", program="sca"), p) is None


def test_first_match_wins_and_building_kinds():
    rules = [rule(kind="sca_school", program="sca", key="CITYWIDE SPECIAL EDUCATION", area_class="citywide",
                  rule_no=1),
             rule(kind="sca_school", program="sca", key="Elementary|K-8", area_class="local", rule_no=2),
             rule(kind="program", program="sca", area_class="local", rule_no=3)]
    shared = {"program": "sca", "id": "k1", "building": "K001",
              "school_kinds": {"Elementary", "CITYWIDE SPECIAL EDUCATION"}, "doe_list": "wg9x-4ke6"}
    assert classify(shared, rules)[0]["rule_no"] == 1
    assert classify({**shared, "school_kinds": {"K-8"}}, rules)[0]["rule_no"] == 2
    assert classify({**shared, "school_kinds": set()}, rules)[0]["rule_no"] == 3


def test_mta_category_key():
    p = {"program": "mta", "id": "T1", "agency": "MTA Bus Company", "category": "Bus Company Projects"}
    assert match(rule(kind="mta_category", program="mta", key="MTA Bus Company|"), p)
    assert match(rule(kind="mta_category", program="mta", key="MTA Bus Company|Depots"), p) is None


def test_rule_table_is_well_formed():
    rules = load_rules()
    assert all(r["area_class"] in CLASSES and r["basis"].startswith(("rule:", "review:")) for r in rules)
    assert all(r["evidence"] for r in rules if r["basis"].startswith("rule:"))
    for prog in ("nyc_capital", "sca", "mta"):  # every program ends in a default
        assert [r for r in rules if r["program"] == prog][-1]["kind"] == "program"
