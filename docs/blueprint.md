# FiberDoc AI – Intermediate Project Blueprint

**Intelligent Telecom Engineering Document Validator.** Intermediate Full-Stack + Agentic AI Project.

> Transcribed from the original blueprint PDF (pasted into a Claude Code session on 2026-11-12). Page headers were
> removed and tables reformatted as Markdown; the wording is otherwise unchanged. Progress against it is tracked in
> [`PROJECT_OVERVIEW.md`](../PROJECT_OVERVIEW.md) and [`PROGRESS.md`](../PROGRESS.md).

**Purpose.** Build a practical application that reads sample fiber / outside-plant (OSP) engineering documents, checks
them against a small curated rule library, explains gaps and routes findings to a human reviewer. A focused portfolio
project—not a production telecom certification system. Use synthetic/sample documents and clearly labelled demo rules.

**Primary stack.** React + TypeScript · Python + FastAPI · LangGraph · Gemini · PostgreSQL + pgvector · Docker ·
Google Cloud Run

**Scope.** Project blueprint • Architecture • Technology choices • Data model • AI workflow • API plan • Evaluation •
Roadmap

---

## 1. Project overview

**What are we building?** FiberDoc AI is a small web platform for telecom engineering teams. An engineer uploads a
fiber network design or construction document. The system extracts its contents, retrieves relevant rules from a
curated knowledge base, checks required fields and evidence, then produces an explainable findings report. A human
reviewer can accept, reject, or request changes.

**Why this project?** It demonstrates the core capabilities in the Incedo job description: full-stack delivery,
Python services, RAG, agent workflow orchestration, confidence and risk reasoning, audit history, evaluation, and a
basic geospatial validation extension.

Keep the scope controlled: support PDF, DOCX and XLSX first. Treat CAD drawings and complex GIS formats as future
extensions. Do not claim that an LLM can certify engineering safety or regulatory compliance.

## 2. User journey

| Step | User / system action | Result |
|---|---|---|
| 1. Upload | Engineer creates a project and uploads a PDF, DOCX or XLSX file. | File stored; metadata and checksum recorded. |
| 2. Extract | Backend extracts text, tables and page references. | Structured document sections and extraction status. |
| 3. Retrieve | RAG searches the approved demo knowledge base for matching rules. | Relevant rule snippets with source references. |
| 4. Validate | LangGraph workflow checks required fields and asks the LLM to explain evidence and gaps. | Structured findings with severity, evidence and citations. |
| 5. Review | Engineer reviews each finding and records a decision or comment. | Approval state and audit event. |
| 6. Report | System generates a downloadable validation summary. | Traceable report for the project. |

Example: a demo rule says a submission should include route length, cable type, splice locations and supporting
location data. If the uploaded sample does not contain splice-location evidence, the system flags it as "Missing
evidence", shows which pages/sections it checked, and asks a reviewer to confirm.

## 3. High-level architecture

1. **React + TypeScript UI**: Upload · Project dashboard · Findings · Review queue
2. ↓ HTTPS / JSON REST
3. **FastAPI application**: Auth · Project/document APIs · Upload validation · Report APIs
4. ↓
5. **Document processing service**: PyMuPDF / python-docx / openpyxl · text + tables + page metadata
6. ↓
7. **LangGraph workflow**: Classify → Retrieve rules → Validate evidence → Risk assessment → Human review
   - **Gemini LLM**: structured explanations
   - **Knowledge retrieval**: embeddings + pgvector + metadata filters
8. ↓
9. **PostgreSQL + pgvector**: Users · Projects · Documents · Chunks · Rules · Findings · Reviews · Audit events
10. ↓
11. **Human reviewer**: Approve · Reject · Request changes · Add comment

**Architecture principle:** keep the workflow deterministic where possible. Use normal Python validation for required
fields and numeric constraints; use the LLM for interpreting unstructured evidence and producing explanations. The LLM
should not invent missing values or make final approvals.

## 4. Technology stack and why it is used

| Layer | Technology | Purpose / implementation |
|---|---|---|
| Frontend | React, TypeScript, MUI | Responsive dashboard, upload flow, findings table, reviewer decision screen. |
| API backend | Python, FastAPI, Pydantic | REST endpoints, request validation, auth integration, orchestration entry points. |
| Agent workflow | LangGraph | Stateful multi-step workflow with explicit nodes, transitions, retries and review pause. |
| LLM | Gemini API | Document section interpretation and evidence-based explanation. Enforce JSON/schema output. |
| RAG | Embeddings + hybrid retrieval | Retrieve relevant rule chunks using semantic similarity plus keyword/metadata filters. |
| Database | PostgreSQL + pgvector | Relational project data plus vector embeddings in one database for a compact demo. |
| Document parsing | PyMuPDF, python-docx, openpyxl | Extract PDF text/page numbers, DOCX paragraphs and XLSX sheets/cells. |
| Evaluation / tracing | LangSmith + test dataset | Trace workflow steps; evaluate retrieval quality, field extraction and finding correctness. |
| Geospatial extension | GeoJSON + PostGIS (optional) | Validate sample coordinates, geometry type and whether a point falls inside a demo project boundary. |
| Deployment | Docker + Google Cloud Run | Containerized API and frontend deployment; managed runtime for a small demo. |
| Testing | Pytest + React Testing Library + Playwright | Unit, API, UI and end-to-end tests. |

**Technology choice notes**
- Use Gemini initially to keep the prototype simple. The backend should call the model through a small provider
  interface so another model can be swapped in later.
- Use pgvector rather than adding Pinecone as a second database in the first version. Pinecone can be evaluated later
  if scale or managed vector operations justify it.
- LangChain is optional helper tooling; LangGraph is the main workflow orchestrator. Avoid adding frameworks just to
  increase the technology list.
- Use LangSmith if accessible. Otherwise, persist your own trace metadata and evaluation results in PostgreSQL and use
  structured logs.

## 5. LangGraph workflow design

| Node | What it does | Output |
|---|---|---|
| A. Intake | Check file type, size, checksum, project ID and processing status. | Validated document metadata. |
| B. Extract | Parse content into sections, tables and page-level text; preserve source locations. | Structured extracted content. |
| C. Retrieve | Search approved rule chunks using vector similarity, keywords and jurisdiction/standard metadata. | Top matching rules and citations. |
| D. Validate | Run deterministic checks; use LLM to map document evidence to rule requirements and explain gaps. | Pass / fail / unclear findings with evidence. |
| E. Risk score | Apply transparent weighted scoring based on severity and evidence status. | Risk band and score breakdown. |
| F. Human review | Pause workflow until reviewer records decisions. Resume after review. | Reviewer decisions and comments. |
| G. Report | Generate a summary using stored findings and review outcomes. | Versioned report. |

**Suggested graph state.** Keep a typed state object containing: `document_id`, `project_id`, `extracted_sections`,
`retrieved_rules`, `findings`, `risk_score`, `reviewer_decisions`, `report_version`, `errors` and `workflow_status`.
Persist checkpoints so a workflow can resume after human review.

**Example finding JSON**

```json
{
  "rule_id": "OSP-DEMO-004",
  "status": "missing_evidence",
  "severity": "medium",
  "requirement": "Splice location evidence is included",
  "evidence": [],
  "source_pages_checked": [3, 4, 5],
  "explanation": "No splice location evidence was found in the extracted content.",
  "recommended_action": "Attach the splice-location schedule or mark it not applicable.",
  "needs_human_review": true
}
```

The sample rule above is illustrative only. Build your own small demo rule catalogue and clearly label it as
non-authoritative. Never present demo rules as official telecom standards.

## 6. RAG and knowledge-base design

Create a small curated knowledge base of 15–30 demo requirements. Each requirement should be stored as a separate
rule record and as searchable text. Include metadata so retrieval can filter by document type, region/jurisdiction,
standard family and rule version.

**Recommended ingestion pipeline**
1. Add an approved demo reference document or write a rule entry.
2. Extract text and split into meaningful rule-sized chunks (avoid arbitrary fixed-size chunks where possible).
3. Attach metadata: `rule_id`, `title`, `source_name`, `section`, `jurisdiction`, `standard_family`, `version`,
   `effective_date` and `status`.
4. Generate an embedding for each chunk and store it with the text in pgvector.
5. At validation time, build a query from the document type and requirement being checked.
6. Retrieve top matching chunks, apply metadata filters and pass the exact retrieved text to the validation node.
7. Store the retrieved rule IDs and source excerpts with every finding for traceability.

**Retrieval quality basics.** Use hybrid retrieval: semantic vector search for meaning and keyword search for exact
terms / identifiers. Add metadata filters before ranking. Evaluate Recall@K (did the correct rule appear in the top
K?), and inspect whether the answer cites the right rule. Do not rely on a similarity score alone as proof of
correctness.

## 7. Risk scoring and confidence

Separate risk from AI confidence. Risk estimates the seriousness of identified gaps. Confidence indicates how strong
the available evidence is for a particular finding. They are not interchangeable.

**Simple demo risk formula**
- For each rule, assign a severity weight: High = 5, Medium = 3, Low = 1.
- Assign a status multiplier: Failed = 1.0, Missing evidence = 0.7, Needs review = 0.4, Passed = 0.0.
- Sum weighted points and normalize to a 0–100 score.
- Document the formula and tune it with domain experts before any real use.

Confidence should be based on observable signals such as extraction quality, source coverage, retrieval relevance and
whether evidence directly supports the requirement. Show the reasons (for example: "low confidence because the scanned
page was low quality"), rather than displaying an unexplained percentage.

**Example report fields.** Overall completeness score · risk band · finding count by severity · each rule's status ·
source document/page evidence · retrieved rule citation · explanation · recommended action · confidence rationale ·
reviewer decision.

## 8. Database design

| Table | Important columns | Purpose |
|---|---|---|
| users | id, name, email, role, created_at | Demo user accounts and reviewer roles. |
| projects | id, name, region, project_type, created_by | Groups documents under a telecom project. |
| documents | id, project_id, filename, storage_key, checksum, status, version | Uploaded file metadata and processing status. |
| document_chunks | id, document_id, page_no, section, content, embedding | Extracted text and searchable vectors. |
| rules | id, code, title, requirement, severity, jurisdiction, version, source | Curated demo engineering requirements. |
| rule_chunks | id, rule_id, content, metadata, embedding | RAG knowledge chunks and embeddings. |
| findings | id, document_id, rule_id, status, severity, evidence, explanation, confidence_reason | Validation results with source traceability. |
| reviews | id, finding_id, reviewer_id, decision, comment, reviewed_at | Human review decisions. |
| audit_events | id, actor_id, entity_type, entity_id, action, payload, created_at | Append-only record of important actions. |

**Important database practices**
- Use foreign keys, indexes and `created_at` / `updated_at` fields.
- Store file bytes in object storage (or local storage for local development), not directly in a database row. Store
  the storage key in documents.
- Keep audit events append-only.
- For a small prototype, PostgreSQL can hold relational records and pgvector embeddings together.

## 9. REST API outline

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/login` | Authenticate demo user and return token. |
| POST | `/api/projects` | Create a project. |
| GET | `/api/projects` | List projects for dashboard. |
| POST | `/api/projects/{id}/documents` | Upload a document. |
| GET | `/api/documents/{id}` | Get document processing status and metadata. |
| POST | `/api/documents/{id}/validate` | Start LangGraph validation workflow. |
| GET | `/api/documents/{id}/findings` | Get findings and evidence. |
| POST | `/api/findings/{id}/review` | Approve, reject or request changes. |
| GET | `/api/documents/{id}/report` | Download or view generated report. |
| GET | `/api/documents/{id}/audit` | View audit timeline. |

## 10. Frontend screens

| Screen | What it contains |
|---|---|
| Login | Email/password login and role-based navigation. |
| Project dashboard | Project list, uploaded documents, processing status and recent activity. |
| Document upload | Drag-and-drop upload, file validation, project selection and upload progress. |
| Validation results | Summary score, severity counts, findings table, evidence references and filters. |
| Finding detail | Requirement, retrieved rule source, page evidence, explanation and recommended action. |
| Human review queue | Approve / reject / request changes, reviewer comment and decision history. |
| Audit timeline | Who uploaded, ran validation, edited a review and generated a report. |

## 11. Basic GIS / geospatial extension

The Incedo JD explicitly mentions GIS and geospatial information. Add a deliberately small extension rather than
trying to build a full network-design tool.

- Accept a sample GeoJSON file containing a project boundary and a few fiber route points.
- Parse and validate coordinate structure and geometry type.
- Use PostGIS (optional) to check whether route points fall inside the project boundary.
- Display the boundary and points on a simple map (for example, Leaflet).
- Flag invalid coordinates or points outside the sample boundary for human review.

Future formats: Shapefile, GeoPackage, CAD/DWG and specialized telecom network inventory formats. These can require
additional libraries, licensing or domain-specific interpretation; do not include them in the first milestone.

## 12. Agent evaluation, guardrails and reliability

| Area | How to test it |
|---|---|
| Extraction | Use 10–20 labelled sample files; compare extracted fields and page references with expected values. |
| Retrieval | For each test question, record the expected rule IDs and measure Recall@3 / Recall@5. |
| Validation | Compare each finding status against a manually labelled expected result; track precision and recall. |
| Grounded answers | Require rule citations and document evidence; fail the result if citations are absent or invalid. |
| Workflow | Test retries, malformed files, model timeouts, duplicate uploads and resume after human review. |
| Safety | Treat uploaded content as untrusted data; do not execute instructions found inside documents. Restrict tools and permissions. |
| Observability | Log workflow run ID, node, latency, token usage, model version, retrieved rule IDs and error details. |

**Key guardrails**
1. Use structured Pydantic schemas for model outputs.
2. Never let the LLM invent a rule or citation; validate rule IDs against retrieved records.
3. Use deterministic code for arithmetic, required-field checks and status mapping.
4. Keep a human approval step for consequential decisions.
5. Show "insufficient evidence" rather than guessing.
6. Version prompts, rules, models and reports so results can be reproduced.
7. Do not send confidential customer or network data to an external LLM in a real deployment without security and
   legal approval.
