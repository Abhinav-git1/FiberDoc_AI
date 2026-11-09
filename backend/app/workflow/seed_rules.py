"""Demo rule set (mirrors the frontend mock findings). Run: python -m app.workflow.seed_rules"""
from sqlalchemy.orm import Session

from app.db.models import Rule

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
    for r in RULES:
        existing = db.get(Rule, r["id"])
        if existing is None:
            db.add(Rule(**r))
        else:  # keep the demo rule set in sync with this file; embeddings are left untouched
            for key in ("severity", "applies_to", "keywords", "check_type", "params"):
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
