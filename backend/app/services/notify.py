"""Outbound webhook: tell an outside workflow (for example n8n, which emails it) that a document has been checked.

What is sent is a summary only: the document's name, type and status, the finding counts and the open findings
(rule, severity, a shortened explanation) plus a link back to the app. The document's text is never sent.

Each request carries two headers so the receiver can check it came from FiberDoc:
  X-FiberDoc-Token      the shared secret itself (n8n's Webhook node checks it with "Header Auth")
  X-FiberDoc-Signature  sha256=<HMAC-SHA256 of the body with the secret>, for receivers that verify signatures
Delivery is retried, and every outcome is logged in webhook_deliveries (shown on the Automations page).
"""
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import AutomationSettings, Document, Finding, Project, WebhookDelivery
from app.services.chat_log import result_text

STATUS_ORDER = ["failed", "missing_evidence", "needs_review", "passed"]
SEVERITY_ORDER = ["high", "medium", "low"]
EXPLANATION_CHARS = 300
RETRY_DELAYS_S = (1, 3)  # waits between the 3 attempts


def get_settings_row(db: Session) -> AutomationSettings:
    """The single settings row, created (disabled, with a fresh secret) on first use."""
    row = db.get(AutomationSettings, "default")
    if row is None:
        row = AutomationSettings(id="default", enabled=False, secret=new_secret())
        db.add(row)
        db.commit()
    return row


def new_secret() -> str:
    return secrets.token_urlsafe(24)


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def document_payload(db: Session, doc: Document, recipient: str | None) -> dict:
    findings = list(db.scalars(select(Finding).where(Finding.document_id == doc.id)))
    status = lambda f: f.status or "needs_review"  # noqa: E731  (findings from before statuses existed)
    open_ = sorted((f for f in findings if status(f) != "passed"),
                   key=lambda f: (STATUS_ORDER.index(status(f)), SEVERITY_ORDER.index(f.severity)))
    project = db.get(Project, doc.project_id)
    return {
        "event": "document.checked",
        "test": False,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "recipient": recipient,
        "summary": result_text(doc, [f.status for f in findings]),
        "document": {"id": doc.id, "name": doc.name, "doc_type": doc.doc_type, "status": doc.status,
                     "page_count": doc.page_count, "error": doc.error},
        "project": {"id": project.id, "name": project.name} if project else None,
        "counts": {s: sum(status(f) == s for f in findings) for s in STATUS_ORDER} | {"total": len(findings)},
        "open_findings": [{"rule_id": f.rule_id, "title": f.title, "severity": f.severity, "status": status(f),
                           "section": f.rule.section if f.rule else None,
                           "explanation": (f.explanation or "")[:EXPLANATION_CHARS]} for f in open_],
        "links": {"app": get_settings().app_url},
    }


def test_payload(recipient: str | None) -> dict:
    """A clearly labelled sample, in the same shape as a real event, for the "Send test" button."""
    return {
        "event": "test",
        "test": True,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "recipient": recipient,
        "summary": "Test message from FiberDoc AI. If you can read this, the webhook and email are set up correctly.",
        "document": {"id": "test", "name": "example_construction_plan.pdf", "doc_type": "construction_plan",
                     "status": "awaiting_review", "page_count": 4, "error": None},
        "project": {"id": "test", "name": "Example project"},
        "counts": {"failed": 1, "missing_evidence": 1, "needs_review": 0, "passed": 2, "total": 4},
        "open_findings": [
            {"rule_id": "CON-007", "title": "Conduit burial depth may be below requirement", "severity": "high",
             "status": "failed", "section": "Construction", "explanation": "Example only: 24 in stated, 36 in required."},
            {"rule_id": "SAF-002", "title": "Site safety plan not referenced", "severity": "medium",
             "status": "missing_evidence", "section": "Safety", "explanation": "Example only."},
        ],
        "links": {"app": get_settings().app_url},
    }


def _post(url: str, body: bytes, headers: dict) -> httpx.Response:
    return httpx.post(url, content=body, headers=headers, timeout=get_settings().webhook_timeout_s)


def deliver(db: Session, settings: AutomationSettings, event: str, payload: dict,
            document_id: str | None = None) -> WebhookDelivery:
    """POST the payload (3 attempts on network errors and 5xx/429), then log the outcome."""
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "FiberDoc-Webhook/1",
               "X-FiberDoc-Event": event, "X-FiberDoc-Token": settings.secret,
               "X-FiberDoc-Signature": sign(settings.secret, body)}
    status, code, error, attempts = "failed", None, None, 0
    for attempt in range(len(RETRY_DELAYS_S) + 1):
        attempts = attempt + 1
        try:
            r = _post(settings.webhook_url, body, headers)
            code = r.status_code
            if r.is_success:
                status, error = "sent", None
                break
            error = f"HTTP {code}: {r.text[:200]}"
            if code < 500 and code != 429:
                break  # a 4xx (wrong URL, wrong token) will not fix itself: don't retry
        except httpx.HTTPError as e:
            code, error = None, f"{type(e).__name__}: {str(e)[:200]}"
        if attempt < len(RETRY_DELAYS_S):
            time.sleep(RETRY_DELAYS_S[attempt])
    d = WebhookDelivery(document_id=document_id, event=event, url=settings.webhook_url, status=status,
                        http_status=code, attempts=attempts, error=error, payload=payload)
    db.add(d)
    db.commit()
    return d


def notify_document_checked(db: Session, document_id: str) -> WebhookDelivery | None:
    """Called when a document's workflow ends (checked or failed). Does nothing unless automations are enabled.
    Never raises: a broken webhook must not affect the document's result."""
    try:
        s = get_settings_row(db)
        if not (s.enabled and s.webhook_url):
            return None
        doc = db.get(Document, document_id)
        if doc is None or doc.status == "processing":
            return None
        return deliver(db, s, "document.checked", document_payload(db, doc, s.recipient_email), document_id)
    except Exception:
        db.rollback()
        return None
