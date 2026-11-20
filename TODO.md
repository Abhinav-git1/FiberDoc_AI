# FiberDoc AI: To-do

What's left, in order, with the reason for each item. Finished work moves to [PROGRESS.md](PROGRESS.md), which logs what changed and why.
The full spec is [docs/blueprint.md](docs/blueprint.md).

Status: ✅ done · 🟡 partly done · ⬜ not started

## Owner requests

| # | Request | Status | Where / what's left |
|---|---|---|---|
| 1 | Show the result of an uploaded document in the UI, broken into categories, with a button to open it from the chat | ✅ | Result panel (`frontend/src/ResultPanel.tsx`), opened by **View details →**. Shows counts by status, severity and **rule category** (Construction, Permits, Design…). Click a category to filter the findings |
| 2 | Schema for the data: where to store it, how many tables | ✅ | [docs/schema.md](docs/schema.md): one Postgres + pgvector database, 14 tables (8 existing, 6 new) plus `geo_features` later. Alembic migrations in `backend/migrations/`; chat tables built (`0002`). The other new tables come with the roadmap steps that use them |
| 3 | MCP server: connect external tools to the app | ⬜ | See [MCP](#mcp-model-context-protocol) below |
| 4 | n8n: automate the workflow around the app | 🟡 | **Email after each upload is built:** outbound webhook, ⚡ Automations page, and an importable n8n workflow ([integrations/n8n/](integrations/n8n/README.md)). **First real run done 2026-11-20:** test email received through local n8n and Gmail SMTP. Intake and reminders are still to do. See [n8n](#n8n-workflow-automation) below |

## Roadmap (blueprint)

| # | Item | Status | Why |
|---|---|---|---|
| 1 | **Classifier fix** | ✅ | Done 2026-11-19: title hits weighted 5×, embedding tie-breaker for close calls, confidence and reason stored and shown. The sample construction plan is now classified correctly. Not yet re-uploaded through the UI |
| 2 | **Recall@3 / Recall@5** on 10–20 labelled documents | ⬜ | Blueprint section 12. Measures whether the right rules are retrieved. Needs `rule_chunks` (schema table 6) and the full retrieved list, which the audit log already stores |
| 3 | **Risk score and confidence** | ⬜ | Blueprint section 7: severity × status weights, scaled to 0–100, with confidence kept separate and its reasons written out. Adds `workflow_runs` |
| 4 | **7-node workflow** with pause and resume for review | ⬜ | Blueprint section 3. LangGraph checkpointer, `workflow_steps` (latency, tokens, model per step), versioned `reports` |
| 5 | **Auth, API completeness, audit timeline** | ⬜ | Demo login with roles (engineer / reviewer / admin); `reviews` replaces `review_comments` and keeps every decision; an audit timeline on screen |
| 6 | **GIS extension** | ⬜ | PostGIS `geo_features`: GeoJSON routes and boundaries checked against the documents |
| 7 | **Deployment** | ⬜ | Docker, Cloud Run, a hosted Postgres (Neon / Supabase / Cloud SQL), Playwright UI tests |

## Smaller items

- 🟡 **Processing speed.** The first real upload (4 pages) took 2 min 25 s, almost all of it in Gemini. Timings are now recorded per step and per Gemini call (result panel: "Where the time went"). The cause was waiting on an overloaded model (4 failed attempts, 127 s). **Fixed 2026-11-19:** a fallback model on 503/504 and a 60 s total budget per Gemini call, with retries using the whole budget. Re-upload: 17 s instead of 136 s. Next: speed up PDF reading (7–9 s, now the biggest step). **Measured 2026-11-19:** text extraction takes 0.004 s; PyMuPDF `find_tables()` takes the rest (about 0.2–1.4 s per page, plus a one-off warm-up). In the owner's 4-page test PDF, 3 pages have no vector lines at all (`page.get_drawings()` is empty) and no tables. Planned fix: skip `find_tables()` on pages without line or rect drawings. Paused for the n8n/MCP work.
- ✅ A real upload through the UI, to check chat saving and the category view end to end (done 2026-11-15: a 4-page construction plan, 14 rules checked).
- ✅ Stop tracking `frontend/tsconfig.tsbuildinfo`, a build cache that changes on every type-check (2026-11-15, now in `.gitignore`).
- ⬜ Check the LangSmith endpoint deprecation notice, which says the old endpoint stops on 2027-01-31.
- ⬜ Serve stored originals back and delete them with their project.
- ⬜ Chat Q&A. The chat says it isn't built. It would be retrieval over the document's chunks, with citations.

## Engineering skills (added 2026-11-20)

The owner's projects were checked against a common job-requirements list (REST APIs, Docker/Kubernetes, CI/CD, task queues, load balancers, observability, auth). REST APIs and auth (in the portfolio) are covered. These four close the biggest gaps with real code in FiberDoc. Times are rough estimates of hands-on work together, not calendar time.

| # | Item | Status | Est. time | Why |
|---|---|---|---|---|
| A | **CI: GitHub Actions** | ⬜ | ~1 hour | Run pytest (with a Postgres + pgvector service container) and the frontend type-check on every push and pull request. Today the 130 tests only run by hand, and none of the projects has CI |
| B | **Docker Compose for the whole app** | ⬜ | 1–2 hours | Backend, frontend and Postgres start with one command. `backend/Dockerfile` exists but has never been used. A first step toward roadmap item 7 (deployment) |
| C | **Task queue: Celery + Redis** | ⬜ | ~half a day | Upload processing currently runs in FastAPI `BackgroundTasks`, inside the web server process. A server restart loses in-progress uploads (it has happened). A queue keeps jobs across restarts, retries them, and lets workers scale separately from the API |
| D | **User auth with roles** | ⬜ | ~1 day | Same as roadmap item 5: demo login with engineer / reviewer / admin roles, replacing the hard-coded "Reviewer". Also unblocks n8n intake, which needs API-key auth |

Suggested order: A → B → C (C needs Redis, which B can run), then D with the roadmap.

---

## MCP (Model Context Protocol)

**What it is:** an open standard for connecting AI assistants to tools and data. An *MCP server* exposes **tools** (functions the AI can call) and **resources** (data it can read) in a standard format. Any *MCP client*, such as Claude Desktop, Claude Code or IDE assistants, can then use them without custom integration code.

**Two ways it fits FiberDoc:**

1. **FiberDoc as an MCP server (recommended first).** Expose the existing API as tools, so an assistant can work with FiberDoc directly:
   - `list_projects`, `upload_document(project_id, file)`, `get_document_status(id)`
   - `get_findings(document_id, status?)`, `get_report(project_id)`

   The assistant can then be asked, for example, "Check this construction plan and summarise the failed rules."

   *Guardrail:* **no tool to approve or reject findings.** Decisions stay with a human in the review UI, as the blueprint requires.

   *How:* the official Python `mcp` SDK (FastMCP), as a thin layer over the current services in `backend/mcp_server.py`, run over stdio for local clients.
2. **FiberDoc as an MCP client (later).** The workflow calls outside MCP servers for extra evidence: a GIS lookup, a permit register, or a document store such as Google Drive or SharePoint to fetch files. *Why later:* each external source needs its own trust rules, and the core checks should work without them.

**Done when:** an MCP client (for example Claude Desktop) can list projects, upload a sample PDF and read its findings; there are tests for each tool; and the README shows the client config.

## n8n (workflow automation)

**What it is:** an open-source tool for automating workflows by connecting nodes on a visual canvas, similar to Zapier or Make but self-hostable (Docker) or cloud-hosted. Triggers (a new file, a webhook, a schedule) start a flow that calls APIs and apps: email, Slack/Teams, Google Drive, Jira and others.

**How it fits:** around FiberDoc, not inside it. The validation logic stays in LangGraph, which is tested and traced, while n8n handles the steps before and after:

1. **Intake:** a new file in a watched Drive/SharePoint folder or email inbox → `POST /api/projects/{id}/documents`.
2. **Notify:** when checking finishes, FiberDoc calls an n8n webhook → n8n posts the summary to Slack/Teams or email, and opens a Jira ticket for each **failed** high-severity finding.
3. **Reminders:** each day, findings still pending review → a reminder to the reviewer.

**Status:**
- ✅ **Outbound webhook** (2026-11-16): the settings and the delivery log are on the ⚡ Automations page; the payload is signed and delivery is retried. The n8n email workflow is in `integrations/n8n/`, with its setup guide.
- ✅ First real run (2026-11-20): n8n 2.48.7 via `npx n8n`, workflow imported and published, Gmail App Password (SMTP 465/SSL), Header Auth token. The **[TEST]** email arrived, and so did the email for a real upload (`demo_small_construction_plan.pdf`). Next: the Think → Act workflow.
- 🟡 **Think → Act agent** (`integrations/n8n/fiberdoc_think_act_workflow.json`): two Gemini agents write suggested next steps for the email. Imported and published 2026-11-20, with its own Gemini project, a fallback model, retry and continue-on-error. Graceful degradation verified (the email still arrives when Gemini fails). **Left:** one run where both agents succeed, after the free-tier daily quota resets. Send **one** test, not several.
- ⬜ **Intake** (n8n → `POST /api/projects/{id}/documents`) needs **API-key auth** on FiberDoc first (roadmap item 5). Until then, n8n could upload to an open local API, so it isn't built.
- ⬜ Reminders and Jira/Slack: extra nodes in n8n, using the same webhook.
