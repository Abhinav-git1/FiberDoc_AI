"""Demo rule catalogue, loaded from reference/demo_rule_catalogue.md. Run: python -m app.workflow.seed_rules

NON-AUTHORITATIVE: these requirements are invented for demonstration. They are not official telecom, utility or
regulatory standards, and the rule IDs and jurisdiction/standard names are placeholders, not real references.

The Markdown file is the source of truth: one `###` heading per rule (the rule-sized unit that is embedded and
retrieved), `- key: value` bullets for its fields, and the paragraph underneath as the requirement text.
"""
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Rule

CATALOGUE_PATH = Path(__file__).resolve().parents[2] / "reference" / "demo_rule_catalogue.md"
DEMO_NOTICE = "Demo rule catalogue - non-authoritative. Not an official telecom or regulatory standard."

SEVERITIES = {"high", "medium", "low"}
DOC_TYPES = {"construction_plan", "design_summary", "as_built", "permit", "test_report"}
CHECK_TYPES = {"required_term", "numeric_min", "numeric_max", "consistency", "semantic"}
CATALOGUE_KEYS = ("source_name", "jurisdiction", "standard_family", "version", "effective_date", "status")
# Fields copied to the database row on every startup, so edits to the catalogue file take effect.
SYNCED = ("title", "text", "severity", "applies_to", "keywords", "check_type", "params", "section", *CATALOGUE_KEYS)

_RULE = re.compile(r"^###\s+([A-Z]{2,4}-\d{3}):\s*(.+?)\s*$")
_SECTION = re.compile(r"^##\s+Section:\s*(.+?)\s*$")
_FIELD = re.compile(r"^-\s+(\w+):\s*(.*?)\s*$")


def _unquote(v: str) -> str:
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] == "`" else v


def _csv(v: str) -> list[str]:
    return [p.strip() for p in v.split(",") if p.strip()]


def _build_rule(rid: str, title: str, section: str, fields: dict[str, list[str]], text_lines: list[str]) -> dict:
    def one(key: str, required: bool = True) -> str | None:
        vals = fields.get(key, [])
        if len(vals) > 1:
            raise ValueError(f"{rid}: '{key}' given more than once")
        if not vals and required:
            raise ValueError(f"{rid}: missing '{key}'")
        return vals[0] if vals else None

    severity, check = one("severity"), one("check")
    if severity not in SEVERITIES:
        raise ValueError(f"{rid}: severity must be one of {sorted(SEVERITIES)}, got '{severity}'")
    if check not in CHECK_TYPES:
        raise ValueError(f"{rid}: check must be one of {sorted(CHECK_TYPES)}, got '{check}'")
    applies = one("applies_to")
    applies_to = [] if applies.strip().lower() == "all" else _csv(applies)
    unknown = set(applies_to) - DOC_TYPES
    if unknown:
        raise ValueError(f"{rid}: unknown document type(s) in applies_to: {sorted(unknown)}")
    text = " ".join(" ".join(text_lines).split())
    if not text:
        raise ValueError(f"{rid}: requirement text is missing")

    what = one("what", required=check != "semantic") or ""
    if check == "required_term":
        params = {"patterns": fields.get("pattern", []), "what": what}
        if not params["patterns"]:
            raise ValueError(f"{rid}: required_term needs at least one 'pattern'")
    elif check in ("numeric_min", "numeric_max"):
        bound = "minimum" if check == "numeric_min" else "maximum"
        params = {"pattern": one("pattern"), bound: float(one("limit")), "unit": one("unit", required=False) or "", "what": what}
    elif check == "consistency":
        params = {"pattern_a": one("pattern_a"), "pattern_b": one("pattern_b"), "what": what}
    else:
        params = {}
    for key in ("pattern", "pattern_a", "pattern_b"):
        for p in fields.get(key, []):
            try:
                re.compile(p)
            except re.error as e:
                raise ValueError(f"{rid}: invalid regex in '{key}': {e}") from e
    if check in ("numeric_min", "numeric_max", "consistency"):
        for p in [params.get("pattern"), params.get("pattern_a"), params.get("pattern_b")]:
            if p is not None and re.compile(p).groups < 1:
                raise ValueError(f"{rid}: pattern must capture the number in a group: {p}")

    return dict(
        id=rid, title=title, section=section, severity=severity, text=text, applies_to=applies_to,
        keywords=_csv(one("keywords")), check_type=check, params=params,
        examples={"pass": one("example_pass"), "fail": one("example_fail")},
    )


def parse_catalogue(markdown: str) -> tuple[dict, list[dict]]:
    """Parse the catalogue Markdown into (catalogue metadata, rules). Raises ValueError on any malformed rule."""
    catalogue: dict[str, str] = {}
    rules: list[dict] = []
    section, block = None, None  # block: the heading currently collecting fields ("catalogue" or a rule)

    def flush():
        if block and block["id"] != "catalogue":
            rules.append(_build_rule(block["id"], block["title"], block["section"], block["fields"], block["text"]))

    for raw in markdown.splitlines():
        line = raw.strip()
        if m := _RULE.match(line):
            flush()
            if section is None:
                raise ValueError(f"{m.group(1)}: rule appears before any '## Section:' heading")
            block = {"id": m.group(1), "title": m.group(2), "section": section, "fields": {}, "text": []}
        elif m := _SECTION.match(line):
            flush()
            section, block = m.group(1), None
        elif line == "## Catalogue":
            flush()
            block = {"id": "catalogue", "fields": {}, "text": []}
        elif line.startswith("#"):
            flush()
            block = None
        elif block and (m := _FIELD.match(line)):
            block["fields"].setdefault(m.group(1), []).append(_unquote(m.group(2)))
            if block["id"] == "catalogue":
                catalogue[m.group(1)] = _unquote(m.group(2))
        elif block and block["id"] != "catalogue" and line and not line.startswith(">"):
            block["text"].append(line)
    flush()

    missing = [k for k in CATALOGUE_KEYS if not catalogue.get(k)]
    if missing:
        raise ValueError(f"catalogue metadata missing: {missing}")
    ids = [r["id"] for r in rules]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"duplicate rule ids: {dupes}")
    return {k: catalogue[k] for k in CATALOGUE_KEYS}, rules


CATALOGUE, RULES = parse_catalogue(CATALOGUE_PATH.read_text(encoding="utf-8"))


def seed(db: Session) -> None:
    """Insert new rules and keep existing ones in sync with the catalogue file. If a rule's title or text changes,
    its embedding is cleared so `embed_rules` re-embeds it. Rules removed from the file are marked 'retired',
    never deleted, so old findings keep their rule."""
    known = set()
    for base in RULES:
        r = {**CATALOGUE, **{k: v for k, v in base.items() if k != "examples"}}
        known.add(r["id"])
        existing = db.get(Rule, r["id"])
        if existing is None:
            db.add(Rule(**r))
            continue
        if (existing.title, existing.text) != (r["title"], r["text"]):
            existing.embedding = None
        for key in SYNCED:
            setattr(existing, key, r[key])
    for orphan in db.query(Rule).filter(Rule.id.notin_(known)).all():
        orphan.status = "retired"
    db.commit()


if __name__ == "__main__":
    from app.db.session import SessionLocal, init_db
    from app.services.retrieval import embed_rules

    init_db()
    with SessionLocal() as s:
        seed(s)
        embed_rules(s)  # needs GEMINI_API_KEY; only rules without an embedding are sent
    print("seeded", len(RULES), "rules")
