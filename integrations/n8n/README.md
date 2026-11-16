# n8n: email the result of each checked document

When FiberDoc finishes checking a document, it sends a short summary to an n8n workflow, and the workflow emails it.
n8n handles the steps *around* FiberDoc (notifications, and later Slack, Jira or reminders). The checking itself
stays in FiberDoc's LangGraph workflow, which is tested and traced.

```
FiberDoc backend ──POST summary──► n8n Webhook ──► Build email (Code) ──► Send email (SMTP) ──► inbox
     (when a document finishes)      checks the token     subject + HTML table      e.g. smtp.gmail.com
```

**What is sent:** the document's name, type, status and page count, the project name, the finding counts, the open
findings (rule, title, status, severity, explanation shortened to 300 characters) and a link to the app.
**The document's text is never sent.** Every delivery is logged on the **⚡ Automations** page.

## Files

| File | What it is |
|---|---|
| `fiberdoc_email_workflow.json` | The simple workflow to import into n8n: Webhook → Build email → Send email |
| `fiberdoc_think_act_workflow.json` | The same, with a **Think → Act** AI agent (Gemini) that writes suggested next steps for the email ([below](#optional-the-think--act-agent-workflow)) |
| `backend/app/services/notify.py` | Builds, signs and sends the summary (3 attempts), logs each delivery |
| `backend/app/api/automations.py` | Settings, test send and delivery log API (`/api/automations/...`) |
| `frontend/src/AutomationsView.tsx` | The Automations page |

## Setup, step by step

### 1. Start n8n (on this computer)
In a new terminal:
```
npx n8n
```
The first run downloads n8n, which takes a few minutes. When it says it's ready, open **http://localhost:5678**
and create the owner account. This account is local to your computer.

### 2. Create a Gmail App Password
n8n sends mail through your Gmail account over SMTP. Google doesn't accept your normal password for this, so you
make an app-specific one:
1. Go to **myaccount.google.com → Security** and turn on **2-Step Verification** if it isn't on already.
2. Search for **App passwords** in the account settings and create one. Name it `n8n`.
3. Copy the 16-character password. You'll paste it into n8n in step 4.

For another provider, use its SMTP settings instead. Outlook, for example, is `smtp.office365.com`, port 587.

### 3. Import the workflow
In n8n: **Create workflow** → the **⋯** menu (top right) → **Import from File** → choose
`integrations/n8n/fiberdoc_email_workflow.json`.

### 4. Connect the two credentials
**Webhook token.** This makes sure only FiberDoc can trigger the workflow.
1. Open the **FiberDoc webhook** node → **Credential for Header Auth** → **Create new**.
2. Set **Name** to `X-FiberDoc-Token`.
3. For **Value**, open FiberDoc's **⚡ Automations** page and copy the **Shared token**. Paste it here.

**Email (SMTP).**
1. Open the **Send email** node → **Credential** → **Create new** (SMTP).
2. Fill in:
   - **User:** your Gmail address
   - **Password:** the App Password from step 2
   - **Host:** `smtp.gmail.com`
   - **Port:** `465`
   - **SSL/TLS:** on
3. In the same node, change **From Email** from `you@gmail.com` to your Gmail address.

### 5. Activate the workflow and copy its URL
1. **Save** the workflow, then switch it to **Active** (top right).
2. Open the **FiberDoc webhook** node and copy the **Production URL**, for example
   `http://localhost:5678/webhook/fiberdoc-checked`.

   Don't copy the *Test URL* (`/webhook-test/...`). It only works while the editor is listening.

### 6. Connect FiberDoc
On the **⚡ Automations** page:
1. Paste the **n8n webhook URL**.
2. Enter the address to **send the email to**.
3. Tick **Send a summary when a document has been checked**, then click **Save**.
4. Click **Send test**. A `[TEST]` email should arrive within a few seconds, and the delivery log shows **Sent · 200**.

### 7. Try it with a real document
Upload a document in **Chat & upload**. When checking finishes, the summary email arrives and the delivery log lists
the document.

## Optional: the Think → Act agent workflow

`fiberdoc_think_act_workflow.json` does the same job, with an AI agent in the middle that writes suggested next steps:

```
FiberDoc webhook ─► Config ─► Open issues? ──yes──► Think ──► Act ──► Build email ─► Send email
                                     │               │ Gemini   │ Gemini      ▲
                                     │               │ + JSON    │ + JSON     │
                                     └──no──────────────────────────────────┘   (failed document, or nothing open)
```

| Node | What it does |
|---|---|
| **Config** | Context for both agents: what FiberDoc is, who the email is for, owner roles, maximum steps, and the guardrails (never approve findings, use only the given findings, don't invent values). Edit the values here |
| **Open issues?** | Skips the AI when nothing is open or the document failed. Each AI run uses 2 Gemini requests, and the free tier allows about 20 a day in total |
| **Think** + output parser | Analyses the open findings. Output JSON: `assessment`, `risk_level`, `key_issues[]`, `plan[]` |
| **Act** + output parser | Turns the plan into `next_steps[]` (order, action, rule IDs, owner role, priority), plus an `email_intro` and `caveats[]` |
| **Build email** | FiberDoc's summary, the AI assessment, the numbered next steps, the caveats and the findings table |

The output parsers force each agent to answer in a fixed JSON format, as in the n8n template you started from.
The next steps are **suggestions only**: the email says so, and findings are still decided by a human in FiberDoc.

**Setup.** Follow steps 1–6 above, importing this file instead (or as well). Then add one more credential:
- **Gemini (Think)** and **Gemini (Act)** nodes → **Credential** → **Create new** (*Google Gemini (PaLM) API*).
  - **Host:** leave the default.
  - **API Key:** a Gemini API key. You can reuse `GEMINI_API_KEY` from `backend/.env`, or create a separate one in Google AI Studio, so n8n's usage is counted separately.
- The model is `models/gemini-3.8-flash`, the same as the backend. Change it in both Gemini nodes if you like.

Its webhook path is `fiberdoc-think-act`, so its Production URL ends in `/webhook/fiberdoc-think-act`. Paste that URL into the
Automations page to use this workflow. Only one URL is active at a time.

**Where the data goes with this workflow:** the summary (never the document text) goes from n8n to Gemini, twice,
and then through your mail server. The Automations page shows this as step 5.

## When something goes wrong

| What you see | Likely cause |
|---|---|
| Log: `Failed`, `ConnectError` | n8n isn't running, or the URL's host or port is wrong |
| Log: `HTTP 404` | The workflow isn't **Active**, or you used the Test URL (`/webhook-test/`) |
| Log: `HTTP 403` / `401` | The token in n8n's Header Auth doesn't match FiberDoc's (for example after **New token**) |
| Log: `Sent`, but no email | Check **Executions** in n8n: usually the SMTP login (App Password, port 465 with SSL) or the From address. Also check the spam folder |
| Think/Act node fails in Executions | `503`/`429` from Gemini means it's overloaded or the daily quota is used up. Re-run the execution later. A parser error means the model broke the JSON format: run it again, or lower the temperature in the Gemini node |
| Imported node shows "?" or "install" | Your n8n version names that node differently. Re-add it from the node panel with the same settings (the AI nodes are under *Advanced AI*) |

## Payload reference
`POST` with JSON. Headers:
- `X-FiberDoc-Event`: `document.checked` or `test`
- `X-FiberDoc-Token`: the shared token
- `X-FiberDoc-Signature`: `sha256=<HMAC-SHA256 of the body, keyed with the token>`, for receivers that verify signatures

```json
{
  "event": "document.checked", "test": false, "sent_at": "2026-11-16T15:30:00+00:00",
  "recipient": "you@example.com",
  "summary": "Finished plan.pdf (4 pages, classified as construction plan). Checked 14 rules: ...",
  "document": {"id": "…", "name": "plan.pdf", "doc_type": "construction_plan", "status": "awaiting_review", "page_count": 4, "error": null},
  "project": {"id": "…", "name": "Metro Ring North - Segment 4"},
  "counts": {"failed": 1, "missing_evidence": 4, "needs_review": 1, "passed": 8, "total": 14},
  "open_findings": [{"rule_id": "CON-007", "title": "…", "severity": "high", "status": "failed", "section": "Construction", "explanation": "…"}],
  "links": {"app": "http://localhost:5173"}
}
```
A document that failed to process is also sent, with `"status": "error"` and the error message. The email subject
then says so.
