"""The demo rule catalogue (reference/demo_rule_catalogue.md): parsing, labelling, and every rule's own examples."""
import pytest

from app.services.validators import Chunk, check_numeric_max, run_rule_check
from app.workflow.seed_rules import CATALOGUE, CATALOGUE_PATH, DOC_TYPES, RULES, parse_catalogue

DETERMINISTIC = [r for r in RULES if r["check_type"] != "semantic"]
ORIGINAL = {"QA-014", "DSN-003", "DSN-011", "CON-007", "PRM-002", "LBL-001"}


def test_catalogue_has_about_twenty_rules_including_the_originals():
    ids = [r["id"] for r in RULES]
    assert 15 <= len(ids) <= 30 and len(ids) == len(set(ids))
    assert ORIGINAL <= set(ids)


def test_every_rule_has_section_text_examples_and_valid_fields():
    for r in RULES:
        assert r["section"] and r["title"] and r["text"] and r["keywords"], r["id"]
        assert r["examples"]["pass"] and r["examples"]["fail"], r["id"]
        assert set(r["applies_to"]) <= DOC_TYPES, r["id"]


def test_semantic_rules_stay_few_to_protect_llm_quota():
    assert sum(r["check_type"] == "semantic" for r in RULES) <= 3


def test_catalogue_is_labelled_non_authoritative_with_placeholder_values():
    for key in ("source_name", "jurisdiction", "standard_family", "version", "effective_date", "status"):
        assert CATALOGUE[key]
    assert "non-authoritative" in CATALOGUE["source_name"].lower()
    assert CATALOGUE["jurisdiction"].startswith("DEMO-") and CATALOGUE["standard_family"].startswith("DEMO-")
    assert "NON-AUTHORITATIVE" in CATALOGUE_PATH.read_text(encoding="utf-8")


@pytest.mark.parametrize("rule", DETERMINISTIC, ids=lambda r: r["id"])
def test_rule_passes_its_compliant_example(rule):
    res = run_rule_check(rule["check_type"], rule["params"], [Chunk(1, rule["examples"]["pass"])])
    assert res.passed is True, res.explanation


@pytest.mark.parametrize("rule", DETERMINISTIC, ids=lambda r: r["id"])
def test_rule_flags_its_violating_example(rule):
    res = run_rule_check(rule["check_type"], rule["params"], [Chunk(1, rule["examples"]["fail"])])
    assert res.passed is False, res.explanation
    assert res.explanation


def test_numeric_max_missing_value_is_undeterminable_not_a_breach():
    res = check_numeric_max([Chunk(1, "OTDR traces recorded.")], r"splice loss\D{0,40}?(\d+(?:\.\d+)?)\s*dB", 0.15, "dB", "splice loss")
    assert res.passed is None and "could not be checked" in res.explanation


def test_numeric_max_uses_the_highest_value():
    text = "Splice loss 0.05 dB at SP-01. Splice loss 0.21 dB at SP-02."
    res = check_numeric_max([Chunk(3, text)], r"splice loss\D{0,40}?(\d+(?:\.\d+)?)\s*dB", 0.15, "dB", "splice loss")
    assert res.passed is False and "0.21" in res.explanation and res.page == 3


HEADER = """## Catalogue
- source_name: Test (non-authoritative)
- jurisdiction: DEMO-X
- standard_family: DEMO-Y
- version: 1
- effective_date: 2026-01-01
- status: approved

## Section: Test
"""
RULE = """### TST-001: A rule
- severity: {severity}
- applies_to: all
- keywords: a
- check: required_term
- pattern: `{pattern}`
- what: thing
- example_pass: `a`
- example_fail: `b`

Requirement text.
"""


def test_parser_reads_a_minimal_rule():
    cat, rules = parse_catalogue(HEADER + RULE.format(severity="low", pattern="a"))
    assert cat["jurisdiction"] == "DEMO-X"
    assert rules[0]["params"] == {"patterns": ["a"], "what": "thing"} and rules[0]["applies_to"] == []


@pytest.mark.parametrize("doc,error", [
    (HEADER + RULE.format(severity="urgent", pattern="a"), "severity"),
    (HEADER + RULE.format(severity="low", pattern="(unclosed"), "invalid regex"),
    (HEADER + RULE.format(severity="low", pattern="a") * 2, "duplicate"),
    (HEADER.replace("- jurisdiction: DEMO-X\n", "") + RULE.format(severity="low", pattern="a"), "metadata missing"),
])
def test_parser_rejects_malformed_catalogues(doc, error):
    with pytest.raises(ValueError, match=error):
        parse_catalogue(doc)
