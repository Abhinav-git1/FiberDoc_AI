"""Demo rule catalogue. Run: python -m app.workflow.seed_rules

NON-AUTHORITATIVE: these requirements are invented for demonstration. They are not official telecom, utility or
regulatory standards, and the rule IDs and jurisdiction/standard names below are placeholders, not real references.
"""
from sqlalchemy.orm import Session

from app.db.models import Rule

DEMO_NOTICE = "Demo rule catalogue - non-authoritative. Not an official telecom or regulatory standard."

# Metadata shared by every demo rule. Placeholder values on purpose, so nothing resembles a real standard.
CATALOGUE = dict(
    source_name="FiberDoc Demo Rule Catalogue (non-authoritative)",
    jurisdiction="DEMO-REGION-A",
    standard_family="DEMO-STD-1",
    version="0.1",
    effective_date="2026-01-01",
    status="approved",
)

SECTIONS = {  # rule id -> section label inside the demo catalogue
    "QA-014": "Quality assurance", "DSN-003": "Design", "DSN-011": "Design",
    "CON-007": "Construction", "PRM-002": "Permits", "LBL-001": "Labelling",
}

RULES = [
    dict(id="QA-014", title="Splice loss test results missing", severity="high",
         text="Every spliced segment must include OTDR test results with measured loss per splice.",
         applies_to=["construction_plan", "test_report", "as_built"], keywords=["otdr", "splice", "loss"],
         check_type="required_term", params={"patterns": [r"otdr", r"splice loss"], "what": "OTDR / splice-loss results"}),
    dict(id="DSN-003", title="Fiber count inconsistent between sections", severity="high",
         text="Fiber count stated in the design summary must match the cable schedule.",
         applies_to=["construction_plan", "design_summary"], keywords=["fiber", "count", "schedule"],
         check_type="consistency",
         # [\s\S]{0,200}? lets the number sit on the line after a heading, but stops at the first "N-count"
         params={"pattern_a": r"design summary[\s\S]{0,200}?(\d+)-count", "pattern_b": r"cable schedule[\s\S]{0,200}?(\d+)-count", "what": "fiber count"}),
    dict(id="DSN-011", title="Minimum bend radius not stated", severity="medium",
         text="Design must state the minimum bend radius for installed cable (>= 15x cable diameter).",
         applies_to=["design_summary", "construction_plan"], keywords=["bend", "radius"],
         check_type="required_term", params={"patterns": [r"bend radius"], "what": "minimum bend radius"}),
    dict(id="CON-007", title="Conduit burial depth may be below requirement", severity="medium",
         text="Underground conduit must be buried at least 36 inches below grade unless a waiver is attached.",
         applies_to=["construction_plan", "design_summary", "as_built"], keywords=["conduit", "depth", "trench", "burial"],
         check_type="numeric_min",
         params={"pattern": r"(\d+(?:\.\d+)?)\s*(?:in\.|inch(?:es)?|\")\s*(?:deep|depth|below grade)?", "minimum": 36, "unit": "in", "what": "burial depth"}),
    dict(id="PRM-002", title="Permit referenced but not attached", severity="low",
         text="Permits cited in the document must be attached or referenced by permit number.",
         applies_to=[], keywords=["permit"], check_type="semantic", params={}),
    dict(id="LBL-001", title="Cable labelling convention", severity="low",
         text="Cable tags must follow the site-ID/route/fiber-count format.",
         applies_to=["as_built"], keywords=["tag", "label"], check_type="semantic", params={}),
]


def seed(db: Session) -> None:
    for base in RULES:
        r = {**CATALOGUE, "section": SECTIONS[base["id"]], **base}
        existing = db.get(Rule, r["id"])
        if existing is None:
            db.add(Rule(**r))
        else:  # keep the demo rule set in sync with this file; embeddings are left untouched
            for key in ("severity", "applies_to", "keywords", "check_type", "params",
                        "source_name", "section", "jurisdiction", "standard_family", "version", "effective_date", "status"):
                setattr(existing, key, r[key])
    db.commit()


if __name__ == "__main__":
    from app.db.session import SessionLocal, init_db
    from app.services.retrieval import embed_rules

    init_db()
    with SessionLocal() as s:
        seed(s)
        embed_rules(s)  # needs GEMINI_API_KEY
    print("seeded", len(RULES), "rules")
