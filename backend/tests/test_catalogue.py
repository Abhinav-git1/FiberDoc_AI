from app.workflow.seed_rules import CATALOGUE, RULES, SECTIONS


def test_every_demo_rule_has_a_section_and_catalogue_metadata():
    assert {r["id"] for r in RULES} == set(SECTIONS)
    for key in ("source_name", "jurisdiction", "standard_family", "version", "effective_date", "status"):
        assert CATALOGUE[key]


def test_catalogue_is_labelled_non_authoritative_with_placeholder_values():
    assert "non-authoritative" in CATALOGUE["source_name"].lower()
    assert CATALOGUE["jurisdiction"].startswith("DEMO-") and CATALOGUE["standard_family"].startswith("DEMO-")
