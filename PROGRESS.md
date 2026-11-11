# FiberDoc AI: Progress Log

Newest entries first. Each entry lists what changed, why, and what is next.

---

## 2026-11-11

### Roadmap step 1: rule catalogue metadata and non-authoritative labelling ✅
**Why:** the owner's target spec requires every finding to be traceable to a specific rule source and version, with retrieval limited to rules that are approved and in scope. Previously the rules were bare text with no provenance, so a reviewer couldn't tell where a requirement came from or whether it was still valid. The rules are invented for the demo, so they also have to be clearly labelled as not being official telecom or regulatory standards. Otherwise a report could be mistaken for a real compliance check.

- **Rule metadata.** Every rule now has `source_name`, `section`, `jurisdiction`, `standard_family`, `version`, `effective_date` and `status` (`backend/app/db/models.py`). Existing databases get the new columns on startup (`backend/app/db/session.py`).
- **Demo catalogue.** `backend/app/workflow/seed_rules.py` defines shared `CATALOGUE` metadata with clearly fake values (`DEMO-REGION-A`, `DEMO-STD-1`, v0.1) and a section for each of the 6 rules.
- **Retrieval filters.** `retrieve_rules` keeps only `approved` rules and can also filter by jurisdiction or standard family. All filters run *before* similarity ranking, so a retired or out-of-scope rule can never be retrieved (`backend/app/services/retrieval.py`).
- **Labelling.** The HTML report cites each rule's version and source and calls the catalogue non-authoritative (`backend/app/services/report.py`). The UI shows a demo-catalogue banner (`frontend/src/App.tsx`, `App.css`).
- **Eval fix.** If a document errored, the eval now records "could not evaluate" instead of treating the empty result as "no findings" (`backend/evals/run_eval.py`). *Why:* a failed run (for example, Gemini out of quota) was being scored as a pass on every "should be OK" check, which made the accuracy numbers look better than they were.
- **Tests.** New `backend/tests/test_catalogue.py`, plus extra report checks in `test_report.py`.

### Reliability: Gemini request timeout
**Why:** during testing a 1-page upload never finished. The chat polled the server every 3 seconds for minutes, and the document was never reviewed. A review tool has to always reach a result, even if that result is "a human needs to check this".

- **Problem.** The Gemini SDK has no timeout by default. A stalled request left documents stuck in `processing` for minutes, while the chat kept polling.
- **Fix.** Added `gemini_timeout_s = 60` (`backend/app/config.py`, `backend/app/services/llm.py`). If a call times out, the rule is recorded as "manual review needed" and the document still finishes.

### Dev environment: Docker removed
**Why:** the project isn't being deployed yet, so Docker only added overhead for local development. Docker Desktop had to be started by hand, and when it wasn't running the database was silently unavailable and every request failed. Port 5432 was also already taken by a PostgreSQL 18 service on this machine that another project uses. Running FiberDoc on that same server, in its own database, removes the extra moving parts and the port conflict.

- **New database.** FiberDoc now runs on the local Windows **PostgreSQL 18** service (port 5432, database `fiberdoc`). pgvector 0.8.7 was built from source with the VS 2022 Build Tools.
- **Data moved.** All existing data was copied over from the old Docker database: 6 documents, 99 chunks with embeddings, 6 rules, 14 findings.
- **Config and docs.** Removed `backend/docker-compose.yml`, switched the default `DATABASE_URL` to 5432, and rewrote the setup section in `PROJECT_OVERVIEW.md`. The same server also hosts another project's database; each project has its own database and user.
- **Server restarts.** Start the backend with `--reload-exclude "data/*"`, so saving an uploaded file doesn't restart the server and kill in-progress uploads. *Why:* three uploads were lost this way today and stayed stuck in `processing`.
- **Security fix.** A real Gemini API key had been put into `backend/.env.example`. It was removed before committing (the key lives only in the git-ignored `.env`). *Why:* `.env.example` is committed, so the key would have been stored in git history and usable by anyone with access to the repo.

### Testing aid
- Added `samples/demo_small_construction_plan.pdf`: 1 page, fictional data. It should trigger CON-007 (30 in. burial depth) and QA-014 (no OTDR results), and pass DSN-003 and DSN-011. *Why:* the earlier test PDFs were 5 to 12 pages and slow to process. A small file with known expected results makes it quick to check the full upload flow by hand, and it uses at most one Gemini call.

**Status:** 27 tests passing, 4 skipped (the live Gemini eval runs only with `RUN_LIVE_EVAL=1`).

**Next:**
1. Roadmap step 2: grow the catalogue to about 20 demo rules, loaded from a reference document.
2. On startup, mark documents left in `processing` by a restart as "interrupted, please re-upload".
3. Store the rule IDs and excerpts retrieved for each finding, plus the new finding fields; then the Recall@K eval, weighted risk scoring, and pause/resume review.

---

## 2026-11-09: baseline

- Backend workflow (FastAPI + LangGraph + Postgres/pgvector + Gemini). Projects, findings, review and upload are connected to the React frontend.
- Downloadable HTML report (`GET /api/projects/{id}/report`).
- Checksums for uploads, with original files stored. Rule eval set. 23 tests passing.
- "Could not verify" handling: deterministic checks that can't decide now create a pending finding for manual review instead of staying silent.
- LangSmith tracing for Gemini generate calls.
