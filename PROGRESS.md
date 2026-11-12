# FiberDoc AI: Progress Log

Newest entries first. Each entry lists what changed, why, and what is next.

---

## 2026-11-12

### Roadmap step 3: retrieval traceability and richer findings ✅
**Why:** the owner's spec asks that every finding show *why* it exists: which rule (and which version of it) was applied, why that rule was picked for this document, what text was looked at, and what the reviewer should do. Before this, a finding stored only one quote and an explanation. A reviewer couldn't tell whether a rule was checked against the whole document or just a few excerpts, and nothing recorded which rules were retrieved but produced no finding, which the Recall@K eval (step 4) needs.

- **New finding fields** (`backend/app/db/models.py`, added to existing databases at startup in `backend/app/db/session.py`):
  - `status`: `compliant`, `non_compliant` or `unverified`. *Why:* this is the result of the automatic check, kept separate from the human `decision`. Before, "requirement met" could only be read from the title.
  - `evidence`: a list of `{page, quote}`. A consistency check (DSN-003) now cites **both** numbers it compared, not just the first. *Why:* a mismatch can't be judged from one side of it.
  - `source_pages_checked`: every page for deterministic checks; only the excerpt pages for Gemini checks. *Why:* "not found on pages 2, 5" means something different from "not found anywhere".
  - `recommended_action` and `needs_human_review`, both derived from the check result in plain Python (`outcome` in `backend/app/workflow/graph.py`). *Why:* the LLM should not write instructions, and the wording should be the same every time. `needs_human_review` means the automation couldn't settle the rule; every finding still waits for a human decision either way.
  - `retrieval`: the rule exactly as used (ID, version, source, section, text), its rank and score breakdown (0.7 × vector + 0.3 × keyword), and for Gemini rules the chunks it was shown, with page, similarity and a 300-character excerpt. *Why:* rules can change later, so the finding keeps a copy of what was actually applied.
- **Full retrieval list in the audit log.** The `workflow_completed` audit event now holds every retrieved rule with its rank and scores, including rules that produced no finding. *Why:* Recall@K compares the retrieved list with the rules that should apply, so it needs the complete list, not just the rules that fired.
- **Retrieval code** (`backend/app/services/retrieval.py`): new `rank_rules` and `evidence_chunks_for_rule` return the scores. The old `retrieve_rules` and `top_chunks_for_rule` still work unchanged on top of them.
- **API and UI.** `GET /api/findings` returns the new fields (camelCase) plus `evidenceList`; `evidence` stays as the first item for older clients. Findings created before this change return `null` for the new fields, and their single quote is still shown. The finding card shows a status badge, all quotes, the pages checked and the recommended action, plus a collapsible "Why this rule was checked" panel (`frontend/src/FindingCard.tsx`). The HTML report shows the same information.
- **Tests.** New `backend/tests/test_traceability.py` (7 tests). End-to-end check on `samples/demo_small_construction_plan.pdf` against the real database: every finding had all the new fields, and the audit event listed all 7 retrieved rules with scores. The throwaway project was deleted afterwards.

**Found during the check (not fixed yet):** the sample PDF is classified as `design_summary`, not `construction_plan`. Its sections are titled "Design summary" and "Cable schedule", which outscore the single "Construction plan" in the title (3 hits to 1). The construction-only rules (QA-014, utility locate, traffic control, and so on) were therefore never checked. The classifier gives every keyword hit the same weight wherever it appears.

**Status:** 91 tests passing, 4 skipped.

**Next:**
1. Fix classification: give the document title or first lines more weight than section headings. Then add the sample PDF as a classification test.
2. Roadmap step 4: Recall@K eval for rule retrieval, using the `retrieved_rules` list in the audit event.
3. Change the shared database password once development settles.

---

## 2026-11-11

### Loose ends: interrupted uploads, eval coverage for the new rules, backup ✅
- **Interrupted uploads are failed at startup.** On startup the backend now marks any document still in `processing` as an error that says "Interrupted: the server restarted while this document was being processed. Please re-upload it." (`fail_interrupted` in `backend/app/api/projects.py`, called from `backend/app/main.py`; test in `backend/tests/test_interrupted.py`). *Why:* processing runs as a background task inside the server process, so a restart kills it. The document then stayed `processing` forever and the chat kept polling for up to 6 minutes. This happened 3 times today.
- **Cleanup.** Deleted the 2 documents left in `error` by earlier restarts, along with their chunks and stored files. Neither had any findings.
- **The live eval now covers the new rules.** `backend/evals/cases.py` has a 6th page in the clean document (utility locate, warning tape, traffic control, safety plan, slack loops), so it satisfies all 13 deterministic construction-plan rules. It also plants a defect for 8 of the new rules, and adds one new case, `new_rule_defects_pdf`, that plants all 8 at once. Every case now also checks that the rules without a planted defect stay OK. *Why:* the 15 new rules were only tested with one-line examples. Nothing showed whether they fire correctly in a whole document, or fire when they shouldn't. One combined case (not 8 separate ones) keeps the Gemini cost to about one extra document per eval run.
- **Offline check of the eval cases.** `backend/tests/test_eval_rules.py` now runs every eval case's deterministic expectations without Gemini. *Why:* a mistake in a case is caught for free in the normal test run, instead of spending scarce Gemini quota (about 20 calls a day) to find it.
- **Backup and Docker cleanup.** Backed up the `fiberdoc` database to `C:\Users\abhin\backups\fiberdoc_2026-11-11.dump` (`pg_dump -Fc`; verified to contain all 8 tables). Then removed the old Docker container `backend-db-1` and its volume `backend_pgdata`. *Why:* the container was kept only as a fallback after the move to PostgreSQL 18. A dump file is a better fallback: it's one small file and needs no Docker. Docker Desktop itself stays installed, because another project's container (`cms_postgres`) uses it.
  - Restore if ever needed: `pg_restore -h localhost -U fiberdoc -d fiberdoc --clean --if-exists --no-owner "C:\Users\abhin\backups\fiberdoc_2026-11-11.dump"`

**Status:** 84 tests passing, 4 skipped.

### Roadmap step 2: 20-rule demo catalogue loaded from a reference document ✅
**Why:** the owner's spec asks for a 15–30 rule demo knowledge base *ingested from a reference document*, with rule-sized chunks. Six rules hard-coded in Python were too few to show retrieval doing real work, so every rule was retrieved for every document. Code was also the wrong place for content that a domain expert should be able to read and edit. Keeping the rules in one readable document also makes the "non-authoritative" label sit right next to the content it describes.

- **Reference document.** `backend/reference/demo_rule_catalogue.md` has 20 rules in 8 sections: Quality assurance, Design, Construction, Permits, Labelling, Safety, As-built records and Splicing. It carries a NON-AUTHORITATIVE banner, and every value is invented. Each `###` heading is one rule, which is the rule-sized unit that gets embedded and retrieved. Regex patterns are written raw, so the file stays readable.
- **Parser.** `backend/app/workflow/seed_rules.py` now loads the rules from that document instead of a Python list. It rejects mistakes with a clear message: unknown severity or document type, an invalid regex, a numeric pattern without a capture group, duplicate IDs, or missing metadata. *Why:* a typo in the catalogue should stop startup loudly rather than silently turn a rule off.
- **Database sync.** On startup the database is synced with the file. If a rule's wording changes, its embedding is cleared so it gets re-embedded. Rules removed from the file are marked `retired` rather than deleted. *Why:* old findings still point at their rule, and retired rules are already excluded from retrieval.
- **New check type `numeric_max`.** Used for "must not exceed" limits such as QA-021 splice loss ≤ 0.15 dB and CON-012 handhole spacing ≤ 300 m (`backend/app/services/validators.py`). The highest stated value is checked. If no value is found, the result is "could not verify" instead of a violation. *Why:* a document that doesn't report a measurement hasn't broken the limit; a human should check it.
- **Few Gemini rules.** 18 of the 20 rules are deterministic; only PRM-002 and LBL-001 use Gemini. *Why:* the free tier allows about 20 generate calls a day, so each semantic rule costs one call per document.
- **The six original rules are unchanged**: same IDs, text, patterns and limits. Catalogue version bumped from 0.1 to 0.2.
- **Tests.** `backend/tests/test_catalogue.py` now runs every rule's own passing and failing example (36 checks), covers `numeric_max` edge cases, and checks that the parser rejects malformed entries. Two older "compliant document passes every rule" tests in `test_eval_rules.py` were narrowed to the four original deterministic rules, because their sample files predate the new rules.
- **Database.** All 20 rules are seeded, approved and embedded (one Gemini embedding call).
- **Effect on the sample PDF.** `samples/demo_small_construction_plan.pdf` now produces 8 automatic findings instead of 2. The new ones are no slack loops, utility locate, traffic control plan, safety plan, splice plan, or warning tape/tracer wire. These are real gaps in that sample, not false positives.

**Status:** 72 tests passing, 4 skipped.

**Next:**
1. Roadmap step 3: store the rule IDs and excerpts retrieved for each finding, plus the new finding fields (status, evidence list, source pages checked, recommended action, needs human review).
2. Roadmap step 4: Recall@K eval for rule retrieval.
3. Change the shared database password (used by the `postgres` and `fiberdoc` users) once development settles.

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
