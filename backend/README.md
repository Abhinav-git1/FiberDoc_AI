# FiberDoc AI – backend

FastAPI + LangGraph + Gemini + PostgreSQL/pgvector. Principle: **deterministic Python where possible; the LLM interprets
unstructured evidence and explains, but never invents values or approves anything.**

```
app/
  main.py                 FastAPI app, CORS, startup (create tables, seed rules)
  config.py               env settings
  schemas.py              Pydantic models (camelCase JSON, matches frontend/src/types.ts) + LLM output schemas
  api/projects.py         GET/POST /api/projects, upload POST /api/projects/{id}/documents (validated, async)
  api/findings.py         GET /api/findings, POST /api/findings/{id}/review  (human decisions only)
  db/                     SQLAlchemy models: users, projects, documents, chunks(vector), rules(vector),
                          findings, review_comments, audit_events
  services/
    document_parser.py    PyMuPDF / python-docx / openpyxl -> text + tables + page metadata
    validators.py         deterministic checks: required terms, numeric limits, consistency, quote grounding
    llm.py                LLMProvider interface + GeminiProvider (swap models here)
    retrieval.py          hybrid retrieval: pgvector + keyword + doc-type metadata filter
    audit.py              audit events
  workflow/
    graph.py              LangGraph: classify -> retrieve_rules -> validate_evidence -> risk_assessment -> human_review
    seed_rules.py         demo rule set
tests/                    pytest (validators, parser)
```

## Run

```bash
docker compose up -d db
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # add GEMINI_API_KEY
python -m app.workflow.seed_rules   # seeds + embeds rules
uvicorn app.main:app --reload       # http://localhost:8000/docs
pytest
```

Then in `frontend/src/api.ts` replace the mock functions with `fetch` calls to `http://localhost:8000/api/...`.

## Safety guards
- Semantic LLM answers must quote the document; quotes are checked verbatim (`quote_is_grounded`) or dropped.
- LLM failure produces a "manual review needed" finding, never a fabricated result.
- Findings are always created `pending`; only `/review` changes a decision, and it is audited.

## Not yet built
Auth (users table exists, no login), PostGIS/GeoJSON extension, LangSmith tracing/eval dataset, Cloud Run deploy config,
Alembic migrations (tables are created at startup), React/Playwright tests.
