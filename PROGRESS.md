# FiberDoc AI: Progress Log

Newest entries first. Each entry lists what changed, why, and what is next.

---

## 2026-11-19

### Speed fix: time budget and fallback model for Gemini ✅
**Why:** the 2026-11-15 timing breakdown showed that 127 of the upload's 136 s went into one Gemini call (rule PRM-002). It made 4 attempts at an overloaded model (two 504s, two 503s), with back-off in between, and still ended as *needs review*. So the wait bought nothing. The fix is to stop waiting on a busy model: try a different one, and cap the total time.

- **Fallback model** (`GEMINI_FALLBACK_MODEL`, default `gemini-3.7-flash`). On a 503 (overloaded), a 504 (deadline) or a client-side timeout, the next attempt goes **straight to the other model, with no sleep**. Back-off only starts once both have failed. *Why 3.7:* it is available to this key, and a different model generation runs on separate capacity, so it is often free when 3.8 is busy.
- **Total time budget per call** (`GEMINI_CALL_BUDGET_S`, default 60 s). Each request's timeout is cut to whatever is left of the budget. If less than 5 s remains, the call gives up and the rule becomes *needs review*, as before, so a person checks it.
- **Per-request timeout** lowered from 60 s to 30 s (`GEMINI_TIMEOUT_S`), so a stalled request leaves time for the fallback.
- **Unchanged:** a 429 (rate limit) still backs off on the same model, and a 400 still fails at once. **Embeddings never fall back**, because vectors from a different model wouldn't match the stored ones. They do get the budget.
- **Recorded:** each Gemini call in the timing breakdown now stores the model that answered. Each error is prefixed with its model. The result panel shows "answered by gemini-3.7-flash" when the fallback was used, and labels errors like "503 unavailable (gemini-3.8-flash)". LangSmith gets the model that actually answered.
- **Checked:** the SDK (google-genai 3.0.0) makes only one attempt when no retry options are set, so there are no hidden retries inside our loop.
- **Tests:** `backend/tests/test_llm_fallback.py` (7 tests, on a fake clock), covering:
  - fallback on 503 and on a timeout
  - never running past the budget
  - request timeouts cut to what's left
  - single-model back-off for embeddings
  - no retry for a 400
  - the fallback list ignores an empty or duplicate fallback

  The existing timing and LangSmith tests were updated for the new signatures.

**Status:** 130 tests passing, 4 skipped. TypeScript compiles; the changed files have no lint warnings. Live check, made while both flash models were returning 503: the call alternated 3.8 → 3.7 → 3.8 → 3.7 and gave up after **25.7 s instead of 127 s**. A live embedding call succeeded (0.4 s).

**Re-upload after restarting the backend** (it ran without `--reload`, so the first re-upload still used the old code): **17.3 s in total**, down from 136.5 s. The rule check alternated 3.8 → 3.7 → 3.8 → 3.7, all 503, and gave up in 7.7 s. A probe right after showed 3.8, 3.7 and 3.5 flash all overloaded. 2.5-flash returns 404 (retired, though the model list still shows it), so more fallback models wouldn't have helped.

### Retries use the whole budget ✅
**Why:** the 4-attempt cap ended that run after 7.7 s, with about 52 s of the 60 s budget unused, and the rule went to a person. Gemini's "high demand" spells often pass within 20–30 s. The owner chose a real answer over a faster upload, so a busy upload can now take up to about a minute, still never the old 2+ minutes.

- Back-off grows 1, 2, 4, 8, 16 s (capped at 16 s), and the **budget** decides when to stop. `attempts` is now just a safety cap of 10.
- **Tests:** 2 more in `test_llm_fallback.py`:
  - quick 503s keep being retried until the budget is used (8 attempts, about 47 s)
  - an overload that clears after about 25 s gets a real answer

**Status:** 132 tests passing, 4 skipped. The backend now runs with `--reload`.

**Next:** re-upload on a quieter day to see a rule answered by Gemini. Then speed up PDF reading (7–9 s). Then the classifier fix.

## 2026-11-17

### Bigger diagrams on GitHub ✅
**Why:** GitHub scales each Mermaid diagram down to the page width, so the wide left-to-right flowcharts came out with tiny text. The owner prefers the horizontal layout.

- The flowcharts are kept horizontal, as they were, with `%%{init: {"flowchart": {"useMaxWidth": false}}}%%` added. They now render at their natural size, and you scroll sideways if a diagram is wider than the page.
- **Architecture diagrams** (overview and README): the flow stays left to right (browser → server → database and services), but the boxes inside each group stack top to bottom (`direction TB`), so the diagram is narrower and taller and GitHub shows it bigger, with an 18 px font. Arrows connect the groups rather than the boxes inside them, because Mermaid ignores a group's direction when arrows reach into it.
- Tried and reverted the same day: a top-to-bottom layout with an 18 px font, which came out too big, then a toned-down version.

## 2026-11-16

### README rewritten: technologies and techniques ✅
**Why:** the root `README.md` was empty, and it is the first page anyone sees on GitHub. The owner asked for it to describe every technology and technique used so far.

- **New `README.md`:** what the app does, an architecture diagram, and the tech stack grouped into backend, data, frontend, automation and tooling. It then describes 13 techniques: deterministic-first checks, hybrid retrieval, grounded structured LLM output, the LangGraph state graph, human-in-the-loop with audit, the rule catalogue as data, resilience, observability and timing, safe migrations, signed outbound webhooks, the n8n Think → Act agent, API and frontend patterns, and evaluation.
- It also covers where the data goes, the project layout, how to run it, the test suites and the status and roadmap. It links to the detailed docs.
- **Other docs brought up to date:**
  - `backend/README.md`: it no longer mentions Docker Compose or mock functions, and it lists every router and service.
  - `backend/migrations/README.md`: adds the `0003` row.
  - `PROJECT_OVERVIEW.md`: adds Alembic, httpx, the timing recorder and n8n to the stack; adds n8n to the diagram; adds the chats and automations data rows, processing step 6 and all the endpoints; changes four views to five; updates the test counts.
- **Honest status:** it says that the n8n workflows haven't been run in a real n8n yet, that the last eval run is out of date, and that the classifier and speed are known issues.

### Think → Act agent workflow in n8n ✅ (not yet run in n8n)
**Why:** the owner wanted a workflow like n8n's "Think → Act" agent template: one agent plans, a second carries out the plan, and each is forced into JSON by an output parser. The goal is to turn a list of findings into suggested next steps in the email. It lives in **n8n**, not in FiberDoc, by the owner's choice. *Why that fits:* the steps are a suggestion for people, not part of the auditable check, so they don't need the backend's tests and traces, and the agent's prompts can be changed in n8n without a code change.

- **`integrations/n8n/fiberdoc_think_act_workflow.json`:**
  - The chain: Webhook (Header Auth) → **Config** (context and guardrails) → **Open issues?** → **Think** (Gemini + structured output parser: assessment, risk level, key issues, plan) → **Act** (Gemini + parser: ordered next steps with rule IDs, owner role and priority, plus an email intro and caveats) → Build email → Send email.
  - Sticky notes explain each part, as in the template.
  - Generated from a script, so the long prompts and code don't need hand-escaping.
- **Guardrails** in the agents' context: never approve or close findings, use only the findings given, don't invent values, and name what a human should check. The email labels the steps as AI suggestions.
- **The AI is skipped** when nothing is open or the document failed. *Why:* there's nothing to plan, and each run costs 2 Gemini requests on a free tier of about 20 a day.
- **Gemini instead of the template's OpenRouter.** *Why:* the project already has a Gemini key, and one provider is easier to reason about for where data goes.
- **The Automations page's data-flow diagram** gained a step: with this workflow, the summary (never the document text) goes from n8n to Gemini.
- **The guide** (`integrations/n8n/README.md`) gained a section covering the Gemini credential, the separate webhook path `fiberdoc-think-act` and troubleshooting.

**Status:** the JSON is valid, and the 15 nodes are all connected. Both schemas are valid JSON Schema. Both Code nodes were run in Node.js against FiberDoc's real test message, with and without agent output: the steps sort by `order`, and the email without AI works. **Not yet imported or run in n8n:** the AI node settings (agent, Gemini model, output parser) can only be confirmed there.

**Next:** import it into n8n and run **Send test**. That's 2 Gemini requests.

### Email after each upload, through n8n ✅
**Why:** the owner asked for the result of each upload to arrive by email, set up through n8n, with a sidebar tab that shows where the data goes. Email comes from n8n rather than from FiberDoc itself because n8n can then send it anywhere (email now; Slack, Teams, Jira or reminders later) by adding nodes, with no new code in FiberDoc. The checking logic stays in LangGraph, which is tested and traced. The only thing FiberDoc needs is one well-defined outbound event.

- **Outbound webhook** (`backend/app/services/notify.py`). When a document's workflow ends (checked or failed), `_process` calls `notify_document_checked`, right after the chat result message.
  - **What is sent:** a summary: name, type, status, project, counts, the open findings with explanations shortened to 300 characters, and a link to the app. *Why:* the document text has no reason to leave the machine for an email. Gemini already sees it, n8n doesn't need to.
  - **Headers:** `X-FiberDoc-Token` (the shared secret) and `X-FiberDoc-Signature` (HMAC-SHA256 of the body). *Why both:* n8n's Webhook node can check a header token with no code, while the signature serves receivers that verify bodies properly.
  - **Retries:** 3 attempts on connection errors, 5xx and 429, but not on other 4xx. *Why:* a wrong URL or token won't fix itself, so retrying only delays the error.
  - **It never raises.** *Why:* a broken webhook must not change a document's result.
- **Tables** `automation_settings` (one row) and `webhook_deliveries` (Alembic `0003`). *Why a delivery log:* "did the email go?" should be answerable from the app. The log stores exactly what was sent. The real DB was backed up first (`backend/data/backups/fiberdoc_pre_0003_2026-11-16.dump`). The migration was applied, `alembic check` is clean, and a downgrade then upgrade round trip was tested.
- **API** (`backend/app/api/automations.py`):
  - `GET`/`PUT /api/automations/settings`, which validates the URL and email and refuses "on" without a URL.
  - `POST /api/automations/settings/secret` creates a new token.
  - `POST /api/automations/test` sends a labelled sample, even while switched off.
  - `GET /api/automations/deliveries`.
  - Settings changes go to the audit log.
- **⚡ Automations tab**, below Projects (`frontend/src/AutomationsView.tsx`):
  - A "Where the data goes" diagram that marks each point where data leaves the computer (Gemini, n8n, the mail server).
  - The settings form, with the token (show / copy / new).
  - **Send test**, and the delivery log, which refreshes every 10 s.
- **n8n workflow** `integrations/n8n/fiberdoc_email_workflow.json`: Webhook (Header Auth) → Build email (Code: subject plus an HTML table of open findings) → Send email (SMTP). It comes with a step-by-step guide covering Gmail App Password, import, credentials and troubleshooting (`integrations/n8n/README.md`). The Code node was run against a real FiberDoc test message to check its output.
- **Tidy-up:** the sidebar `NavBtn` moved out of `App`, because a component defined inside another is re-created on every render. Lint warnings dropped from 9 to 5.
- **Tests:** `backend/tests/test_notify.py` (5 tests):
  - Settings defaults and validation.
  - The token and signature headers on a test send.
  - Retries: a connection error and a 503 succeed on attempt 3; a 404 isn't retried.
  - The real-event payload: counts, failed first, explanation shortened, no document text, and the on/off switch.
  - A broken webhook never raises.

**Status:** 123 tests passing, 4 skipped. TypeScript compiles cleanly. The endpoints were checked against the running server. **Not yet run end to end with a real n8n and inbox**: that needs the owner's Gmail App Password (guide step 2).

**Next:** the owner runs the setup guide; then the speed fix (Gemini time budget and fallback model).

## 2026-11-15

### Timing breakdown for every document ✅
**Why:** the first real upload, a 4-page construction plan, took 2 min 25 s. Reading the PDF takes about 3 s, and only two Gemini calls are made for that document (one embedding batch and one semantic rule). So the time is going into Gemini, but nothing recorded where: the database had only the upload and finish times. Measuring first means the speed fix will target the real cause (model "thinking", timeouts, retries or slow responses) instead of a guess. The blueprint also asks for latency per workflow step.

- **`app/services/timing.py`:** a small per-document recorder.
  - `step()` times a stage, and `llm_call()` records a Gemini call.
  - Both do nothing when no recorder is open, so tests and scripts are unaffected.
  - *Why a ContextVar:* LangGraph runs workflow nodes in worker threads and copies the context into them, so steps recorded there reach the same recorder without passing it through every function.
- **What is timed:**
  - In `_process`: `parse` and `embed_chunks`.
  - Each workflow node (`classify`, `retrieve_rules`, `validate_evidence`, `risk_assessment`, `human_review`), wrapped by `_timed()` in `graph.py`.
- **Every Gemini call** (`GeminiProvider._retry` in `llm.py`) records:
  - Total seconds, including retries and back-off.
  - The number of attempts and the errors seen, including calls that finally fail.
  - Input, output and **thinking** token counts. *Why thinking tokens:* newer Flash models reason before answering by default, which is a likely cause of slow yes/no rule checks.
- **Stored** as a `processing_timed` audit event, saved for failed runs too. *Why the audit log:* no migration needed, and timings belong with the document's history. A `workflow_steps` table can replace it with the 7-node workflow (roadmap 4).
- **API:** `GET /api/documents/{id}/timings`. It returns 404 while processing and for documents processed before this change.
- **Result panel:** a "Where the time went" section with a bar per step, then each Gemini call with its time, attempts, thinking and output tokens, and any errors.
- **Tests:** `backend/tests/test_timing.py` (5 tests):
  - No-op without a recorder; steps recorded even when they raise.
  - Retries recorded with tokens; failed calls recorded.
  - End to end: `_process` with fakes, a real LangGraph node in a worker thread, and the API returning the record.

**Status:** 118 tests passing, 4 skipped. TypeScript compiles cleanly, with no new lint warnings. The endpoint was checked live (404 for the earlier upload, as expected). The breakdown for a real document needs one re-upload.

**First measurement** (the same 4-page construction plan, re-uploaded): 136.5 s in total.
- Reading the PDF: 7.1 s. Embedding: 2.4 s, of which the Gemini call was 0.7 s.
- The other workflow steps: under 0.1 s combined.
- **Checking the rules: 126.8 s, all of it one Gemini call** for the permit rule (PRM-002). It made 4 attempts and all failed: two "504 deadline exceeded" and two "503 model experiencing high demand".
- The rule correctly became *needs review*, as it did in the first upload, so the 2-minute wait bought nothing.

The cause is waiting on an overloaded Gemini model, not thinking tokens or our code. The panel now shows error codes ("503 unavailable") instead of only "ServerError".

**Next:** cap each Gemini rule check at a total time budget and fall back to a second model on 503/504. Then speed up PDF table detection.

### Recent chats stay in the sidebar on every page ✅
**Why:** the first real upload through the UI worked end to end: a 4-page construction plan, classified correctly, with 14 rules checked, a saved result message, and the result panel with categories. During that test the owner noticed that "Recent chats" disappeared on the Projects, Findings and Review queue pages. Saved chats are how you get back to a result, so they should always be one click away.

- `frontend/src/App.tsx`: the chat list is no longer limited to the chat page. Clicking a chat from any page opens it and switches back to the chat view. A chat is highlighted only while the chat view is open, so it doesn't look selected on other pages.

**Status:** TypeScript compiles cleanly. The fix itself hasn't been tried in the browser yet; the owner will.

- **Housekeeping:** `frontend/tsconfig.tsbuildinfo` is no longer tracked (added to `.gitignore`). *Why:* it's a TypeScript build cache that changes on every type-check, which added noise to every commit.

**Next:** classifier fix.

## 2026-11-14

### Results broken into rule categories; to-do list ✅
**Why:** the owner asked for the upload result to be broken into categories. The result panel only counted by status and severity, which shows how much is wrong but not where. Rules already have a catalogue section (Construction, Permits, Design, Quality assurance…), which matches how engineering teams divide the work.

- **`ruleSection` on every finding** (`backend/app/schemas.py`, `backend/app/api/findings.py`), read from the rule's `section`. *Why:* taken from the rule record rather than the retrieval trace, so findings created before traces existed are grouped too.
- **"By category" in the result panel** (`frontend/src/ResultPanel.tsx`):
  - One row per category, with a bar split by status and an "N open · total" count.
  - Sorted with the most open issues first.
  - Clicking a row filters the findings list to that category.
- **One rule for findings without a status.** Findings from before 2026-11-12 count as *needs review* in the tiles, the category bars and the sort order. *Why:* they were never settled automatically. Before, the tiles skipped them while the sort treated them as needs review, so the counts didn't add up.
- **`TODO.md`** at the repo root:
  - The owner's four requests with their status.
  - The blueprint roadmap, each item with its reason.
  - A plan for **MCP** (expose FiberDoc as an MCP server first; no approve tool, so decisions stay with humans) and for **n8n** (automation around the app: intake, notifications, reminders, with an outbound webhook needed first).

  *Why:* one place to see what's left and why, next to the log of what's done.

**Status:** 113 tests passing, 4 skipped (`test_traceability.py` now checks `ruleSection`). TypeScript compiles cleanly, with no new lint warnings. Grouping was checked against the live API: the 15 existing findings fall into 4 categories. The panel itself hasn't been viewed with a fresh upload yet (see TODO.md).

**Next:** classifier fix.

### Chats are saved in the database ✅
**Why:** chats lived only in React state, so a page refresh lost every conversation and its results. The result panel could not be rebuilt either. Also, if the browser was closed while a document was being checked, its result reached no chat at all, because only the open tab was polling for it. The blueprint asks for a full, auditable record of what was checked and what was reported.

- **API** (`backend/app/api/chats.py`):
  - `GET /api/chats`: the most recently used first.
  - `POST /api/chats`: create a chat.
  - `GET /api/chats/{id}`: its messages, plus the documents they refer to.
  - `POST /api/chats/{id}/messages`: add a message.
- **The backend writes the messages about uploads** (`backend/app/services/chat_log.py`):
  - When a file arrives with `chat_id`, an `upload` message.
  - When the workflow ends, a `result` message (or `error`), written by `record_outcome`. It is also written for documents failed by `fail_interrupted` at startup.

  *Why:* the result is then saved even if no browser is open. Clients can post only `text` and `error` messages (a 422 for anything else), so a client can't fake a check result.
- **One wording for results.** The summary ("Checked N rules: … failed, … missing evidence …") is now built in Python (`result_text`). The chat shows the saved text, so a live chat and a reopened one say exactly the same thing. The old browser-side text remains only as a fallback when the chat couldn't be saved.
- **Frontend:**
  - A chat is saved on its first message, not when "New chat" is clicked. *Why:* no empty chats in the database.
  - The sidebar lists saved chats at startup, and opening one loads its messages (`frontend/src/savedChat.ts`).
  - The backend stores one row per file. A user's text plus the files sent with it are merged back into one bubble, as they were sent.
  - A reopened chat whose document is still being checked polls every 5 s and picks up the result when it's saved.
  - If saving fails (backend down), the chat still works in that tab, as before.
- **`sizeBytes` on documents**, read from the stored original, because a reopened chat has no local file to measure. It is `null` for uploads made before originals were stored.
- **Extracted text tab:** the browser preview exists only in the session the file was uploaded in, and a reopened chat says so.
- **Tests:** `backend/tests/test_chats.py` (6 tests):
  - Result wording, without a database.
  - The full API against a throwaway Postgres schema that is dropped afterwards: create, post, read, reject fake results, and 404s.
  - An upload with `chat_id` writing its `upload` message.
  - `record_outcome` waiting while processing and running only once.

  The `fail_interrupted` test now also checks that interrupted documents report back to their chat.
- **Dev server reload hang: cause found.** On Windows, uvicorn restarts by sending the worker a Ctrl+C event (`CTRL_C_EVENT`), then waits with no time limit. That signal only reaches processes attached to a console. Servers started from a background shell have none, so every reload hung. LangSmith, suspected earlier, was not the cause. `--reload` works in a normal terminal; servers started by an agent should run without it and be restarted after changes.

**Status:** 113 tests passing, 4 skipped. TypeScript compiles cleanly, with no new lint warnings. Chat endpoints were checked against the running server; the test chat was deleted afterwards. A real upload through the UI hasn't been run, to save Gemini quota.

**Next:** classifier fix (roadmap step), then Recall@3/@5.

### Alembic migrations; chat tables added ✅
**Why:** until now, `init_db` ran `create_all()`, which only creates missing tables, followed by hand-written `ALTER TABLE ... IF NOT EXISTS` statements, all on every startup. That approach keeps no history, has no undo, and can't safely rename columns, add foreign keys to existing tables or move data. The next schema steps need all three (for example, `review_comments` becomes `reviews`). It would also let the local database and Neon slowly drift apart.

- **Alembic set up** (`backend/alembic.ini`, `backend/migrations/`, how-to in `backend/migrations/README.md`). `env.py` uses the app's own engine, so the URL and password stay in `.env` only.
- **`0001` baseline:** the 8 existing tables, written out by hand. *Why:* the baseline must stay fixed even as the models change. Running `create_all` inside a migration would silently follow later model edits.
- **`0002`:** `chats` and `chat_messages` (docs/schema.md tables 10 and 11), with indexes on every foreign key and on `(chat_id, created_at)` to load a chat's messages in order. Deleting a chat deletes its messages. Deleting a document keeps the message but clears its link.
- **Startup now runs `alembic upgrade head`** (`backend/app/db/session.py`). A database created before Alembic gets a one-time handover: the old ALTERs add any missing columns, `rules.status` is made NOT NULL to match the model (it was the one difference found), and the database is recorded as `0001` before `0002` runs. *Why:* the existing data is kept rather than recreated.
- The "is this an old database?" check looks only at the current schema. *Why:* Postgres reflection with no schema named also sees tables further down the search path, which made a fresh test schema look like an old database.
- **Verified on throwaway schemas inside `fiberdoc`** (the app user can't create databases):
  - Fresh database: upgrade, no differences from the models, downgrade to empty, upgrade again.
  - Simulated pre-Alembic database: missing columns restored, an empty rule status filled, recorded as `0001`, chat tables added, no differences from the models, and `init_db` safe to run twice.
- **Real database:** backed up first with `pg_dump` to `backend/data/backups/` (git-ignored), then migrated. It is at `0002` with no differences from the models; all rows are unchanged (1 project, 5 documents, 63 chunks, 15 findings, 20 rules).
- **Dev server** now runs with `--reload-dir app`. *Why:* uvicorn was watching `.venv` too, so installing a package triggered a reload. (Why reloads then hung is explained in the chat entry above.) The old `--reload-exclude "data/*"` pattern was also expanded by the shell into file names.

**Status:** 107 tests passing, 4 skipped. The chat tables exist but nothing writes to them yet.

**Next:** chat API endpoints (create, list, get chats and messages), the backend writing the result message when the workflow finishes, and the frontend loading saved chats instead of keeping them only in browser memory.

### Result sidebar, LangSmith token usage, schema plan ✅
**Why:** the upload result was only a chat message, LangSmith showed Gemini calls without token counts, and there was no written plan for which tables the blueprint needs.

- **Result panel** (`frontend/src/ResultPanel.tsx`), opened automatically on upload or from "View details →":
  - Live progress while the document uploads and is checked.
  - The response message and document details (type, pages, size, processing time, SHA-256, ID).
  - A summary count for each status, and links to the review queue and the report.
  - The document's findings, sorted by status and then severity, with a "Hide passed" toggle.
  - An "Extracted text" tab.

  Findings are matched to their document by the new `documentId` field in the API.
- **Token usage in LangSmith** (`_record_usage` in `backend/app/services/llm.py`). Gemini's input, output and thinking token counts and the model name are attached to each traced call, so LangSmith's Tokens and Cost columns are filled in. Tests are in `backend/tests/test_llm_usage.py`.
- **Schema plan** (`docs/schema.md`): 14 tables in total (8 existing, 6 new), plus `geo_features` later. Each table is added in the roadmap step that first uses it.

## 2026-11-12

### Full blueprint saved; findings use the blueprint's four statuses ✅
**Why:** until today only sections 5 and 6 of the owner's blueprint were known. With all 12 sections available, two things in this morning's work didn't match it: the blueprint's statuses are *Passed, Failed, Missing evidence* and *Needs review*, and its risk formula weights "failed" (1.0) and "missing evidence" (0.7) differently. A single "non-compliant" status couldn't tell them apart, and the risk score will be built on top of these values.

- **Blueprint in the repo.** [`docs/blueprint.md`](docs/blueprint.md) holds the full spec (sections 1–12), transcribed from the PDF. *Why:* it's the acceptance criteria. It should be versioned with the code, not kept only in a chat history.
- **Four statuses** (`outcome` in `backend/app/workflow/graph.py`):
  - `passed`: the requirement is met, with evidence.
  - `failed`: evidence was found and it breaks the requirement (e.g. a 30 in. depth against a 36 in. minimum).
  - `missing_evidence`: the check looked and found nothing to judge (no OTDR results, no depth stated, only one side of a comparison).
  - `needs_review`: something was found but the automation couldn't decide.

  Checks now set a `missing` flag when they find nothing (`backend/app/services/validators.py`). *Why:* "the cable is too shallow" and "the document doesn't say how deep the cable is" need different fixes from the engineer, and the blueprint scores them differently.
- **Missing values handled the same way.** A missing minimum value (e.g. no burial depth) and a missing maximum value (e.g. no splice loss) are now both `missing_evidence`. Before, the first counted as a violation and the second as "could not verify".
- **Stricter rule for Gemini answers** (`backend/app/services/semantic.py`). A "violates" answer counts as `failed` only when its quote appears in the document. Without a quote it becomes `needs_review`. A "complies" answer with an invented quote also becomes `needs_review`; before, it was reported as a violation. If Gemini says it found nothing relevant, the result is `missing_evidence`. *Why:* blueprint guardrail: "fail the result if citations are absent or invalid". An uncited claim, for or against, shouldn't count as a result.
- **Recommended actions** follow the status. For missing evidence: "Add the evidence … or mark the rule not applicable", following the blueprint's example finding.
- **Renamed in the database at startup** (`backend/app/db/session.py`), in case any findings already had the earlier values. None did: the 14 existing findings predate status.
- **UI and report** show the new labels.
- **Tests.** `backend/tests/test_traceability.py` covers the four statuses, the `missing` flag on each check type, and each kind of Gemini answer, using a fake LLM so no quota is used. End-to-end on the sample PDF: CON-007 is `failed`, DSN-018 is `missing_evidence`, PRM-002 is `needs_review`.

**Status:** 104 tests passing, 4 skipped.

**Next:** follows the new roadmap in `PROJECT_OVERVIEW.md` (Target design): classifier fix, Recall@3/@5, risk score and confidence, the 7-node workflow, then auth, API, GIS and deployment.

### Roadmap step 3: retrieval traceability and richer findings ✅
**Why:** the owner's spec asks that every finding show *why* it exists: which rule (and which version of it) was applied, why that rule was picked for this document, what text was looked at, and what the reviewer should do. Before this, a finding stored only one quote and an explanation. A reviewer couldn't tell whether a rule was checked against the whole document or just a few excerpts, and nothing recorded which rules were retrieved but produced no finding, which the Recall@K eval (step 4) needs.

- **New finding fields** (`backend/app/db/models.py`, added to existing databases at startup in `backend/app/db/session.py`):
  - `status`: `compliant`, `non_compliant` or `unverified` (replaced later the same day by the blueprint's four statuses, see above). *Why:* this is the result of the automatic check, kept separate from the human `decision`. Before, "requirement met" could only be read from the title.
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
