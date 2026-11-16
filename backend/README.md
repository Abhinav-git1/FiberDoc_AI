# FiberDoc AI – backend

FastAPI + LangGraph + Gemini + PostgreSQL/pgvector. **Principle:** use deterministic Python where possible. The LLM
interprets unstructured evidence and explains, but never invents values or approves anything.

The project overview, the full tech stack and the techniques are in the [root README](../README.md). The detailed
workflow and endpoints are in [PROJECT_OVERVIEW.md](../PROJECT_OVERVIEW.md).

```
app/
  main.py                 FastAPI app, CORS. Startup runs migrations, syncs the rule catalogue and fails interrupted uploads
  config.py               typed settings from .env (pydantic-settings)
  schemas.py              Pydantic models (camelCase JSON, matches frontend/src/types.ts) + LLM output schemas
  api/projects.py         projects; upload POST /api/projects/{id}/documents (202, background task); document timings
  api/findings.py         GET /api/findings, POST /api/findings/{id}/review (human decisions only)
  api/reports.py          GET /api/projects/{id}/report (self-contained HTML)
  api/chats.py            saved chats and their messages
  api/automations.py      webhook settings, new token, test send, delivery log
  db/                     SQLAlchemy models + session; init_db runs Alembic
  services/
    document_parser.py    PyMuPDF / python-docx / openpyxl -> text + tables + page numbers -> chunks
    validators.py         deterministic checks: required terms, numeric min/max, consistency, quote grounding
    retrieval.py          embeddings, metadata filters, hybrid ranking (0.7 vector + 0.3 keyword), evidence chunks
    semantic.py           grounded Gemini rule check
    llm.py                LLMProvider protocol + GeminiProvider (timeout, retries, token usage, LangSmith)
    timing.py             per-step and per-Gemini-call timing (ContextVar, works across threads)
    notify.py             outbound webhook: summary payload, token + HMAC signature, 3 attempts, delivery log
    chat_log.py           upload / result messages written into the chat
    report.py · storage.py · audit.py
  workflow/
    graph.py              LangGraph: classify -> retrieve_rules -> validate_evidence -> risk_assessment -> human_review
    seed_rules.py         parses, validates and syncs reference/demo_rule_catalogue.md (NON-AUTHORITATIVE demo rules)
migrations/               Alembic: 0001 baseline, 0002 chats, 0003 automations (see migrations/README.md)
evals/                    end-to-end evaluation harness (python -m evals.run_eval)
sample_docs/              generated sample PDFs and their generators
tests/                    pytest
```

## Run

You need a local PostgreSQL with the `vector` extension and a `fiberdoc` database. Setup is in the
[root README](../README.md#running-it-locally).

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env               # set DATABASE_URL and GEMINI_API_KEY
uvicorn app.main:app --port 8000     # http://localhost:8000/docs
pytest                               # 123 passed, 4 skipped (live Gemini evals need RUN_LIVE_EVAL=1)
```

At startup the server applies migrations, seeds or syncs the rules (it embeds them when the Gemini key is set), and
marks any upload left *processing* by a previous run as failed. `--reload --reload-dir app` works in a normal
terminal. Started from a background shell on Windows, reload can hang, so leave it off there.

The `Dockerfile` builds the API image for a later Cloud Run deployment. Locally, Postgres runs as a Windows service,
not in Docker.

## Safety guards
- Semantic LLM answers must quote the document. Quotes are checked verbatim (`quote_is_grounded`); a claim without a
  grounded quote becomes *needs review*.
- An LLM failure produces a "manual review needed" finding, never a fabricated result.
- Findings are always created `pending`. Only `/review` changes a decision, and the change is audited.
- Webhook delivery never raises, and it sends a summary only, never the document text.

## Not yet built
- Auth: the `users` table exists, but there's no login.
- PostGIS/GeoJSON checks.
- A LangSmith eval dataset.
- Cloud Run deployment.
- React/Playwright tests.

The roadmap is in [TODO.md](../TODO.md).
