"""Evaluation cases: synthetic documents with KNOWN expected outcomes (demo data only).

Each case lists, per rule, whether the app should FLAG it (a real defect was planted) or find it OK.
Rules not listed in a case are ignored for that case.
Build documents from a clean base and change one thing at a time, so a failure points at one rule.
"""
from dataclasses import dataclass, field

ALL_RULES = ["QA-014", "DSN-011", "DSN-003", "CON-007", "PRM-002"]

CLEAN_PAGES = [
    "METRO RING EAST - SEGMENT 2 (SYNTHETIC DEMO DOCUMENT)\n\nConstruction Plan\n\nScope of work: install underground conduit and fiber "
    "cable along Route B, including trenching, handhole placement and a splice plan for 12 splice points.\n\nRoute length: 3.1 km.",
    "Design summary: 144-count single-mode cable along Route B.\n\nCable type: G.652.D loose-tube armored.\n\n"
    "Minimum bend radius: 15x cable diameter (installed), 20x during pulling.",
    "Trenching notes\n\nTrench to be excavated to 42 in. below grade along the east shoulder.\n\nHandholes every 300 m.",
    "Permits\n\nRight-of-way approved under city permit no. ROW-2026-0142 (attached as Appendix B).",
    "Cable schedule\n\nRoute B uses 144-count single-mode cable between handholes HH-01 and HH-14.\n\n"
    "Test results\n\nOTDR traces recorded for all 12 splices; maximum splice loss 0.06 dB.",
]

# (old, new) text substitutions that plant one defect each
DEFECTS = {
    "QA-014": ("\n\nTest results\n\nOTDR traces recorded for all 12 splices; maximum splice loss 0.06 dB.", ""),
    "DSN-011": ("\n\nMinimum bend radius: 15x cable diameter (installed), 20x during pulling.", ""),
    "DSN-003": ("Route B uses 144-count", "Route B uses 96-count"),
    "CON-007": ("42 in. below grade", "30 inches deep"),
    "PRM-002": ("city permit no. ROW-2026-0142 (attached as Appendix B)", "city permit (copy on file)"),
}


def pages_with(*rule_ids: str, replace: dict[str, str] | None = None) -> list[str]:
    text = "\u0001".join(CLEAN_PAGES)
    for rid in rule_ids:
        old, new = DEFECTS[rid]
        assert old in text, f"defect text for {rid} not found in base document"
        text = text.replace(old, new)
    for old, new in (replace or {}).items():
        assert old in text
        text = text.replace(old, new)
    return text.split("\u0001")


@dataclass
class Case:
    id: str
    kind: str  # pdf | docx | xlsx
    pages: list[str]
    flag: list[str] = field(default_factory=list)  # rules that must produce a finding
    ok: list[str] = field(default_factory=list)  # rules that must NOT produce a finding
    doc_type: str = "construction_plan"
    note: str = ""


def _only(rule: str, kind: str = "pdf", **kw) -> Case:
    return Case(f"only_{rule.lower().replace('-', '_')}_{kind}", kind, pages_with(rule),
                flag=[rule], ok=[r for r in ALL_RULES if r != rule], **kw)


CASES: list[Case] = [
    Case("clean_pdf", "pdf", pages_with(), ok=ALL_RULES, note="No defects: nothing should be flagged"),
    _only("QA-014", note="Missing OTDR / splice-loss results"),
    _only("DSN-011", note="Bend radius not stated"),
    _only("DSN-003", note="144-count vs 96-count; number sits on the line after a heading"),
    _only("CON-007", note="'30 inches deep' wording variant, below the 36 in minimum"),
    _only("PRM-002", note="Permit cited without a number (LLM-interpreted rule)"),
    Case("depth_exactly_36_pdf", "pdf", pages_with(replace={"42 in. below grade": "36 in. below grade"}),
         ok=["CON-007"], note="Boundary: exactly the minimum is compliant"),
    Case("all_defects_pdf", "pdf", pages_with(*ALL_RULES), flag=ALL_RULES, note="Every defect planted"),
    Case("all_defects_docx", "docx", pages_with(*ALL_RULES), flag=ALL_RULES, note="Same defects, DOCX parser path"),
    Case("all_defects_xlsx", "xlsx", pages_with(*ALL_RULES), flag=ALL_RULES, note="Same defects, XLSX parser path"),
]
