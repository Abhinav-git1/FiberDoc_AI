"""Automations: the outbound webhook that sends a summary of each checked document to an outside workflow
(an n8n workflow that emails it; see integrations/n8n/). Settings, a test send, and the delivery log."""
import re
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, WebhookDelivery
from app.db.session import get_db
from app.schemas import AutomationSettingsIn, AutomationSettingsOut, DeliveryOut
from app.services import audit
from app.services.notify import deliver, get_settings_row, new_secret, test_payload

router = APIRouter(prefix="/api/automations")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _clean(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


@router.get("/settings", response_model=AutomationSettingsOut, response_model_by_alias=True)
def read_settings(db: Session = Depends(get_db)):
    return get_settings_row(db)


@router.put("/settings", response_model=AutomationSettingsOut, response_model_by_alias=True)
def update_settings(body: AutomationSettingsIn, db: Session = Depends(get_db)):
    url, email = _clean(body.webhook_url), _clean(body.recipient_email)
    if url and (urlparse(url).scheme not in ("http", "https") or not urlparse(url).netloc):
        raise HTTPException(422, "The webhook URL must start with http:// or https://")
    if email and not EMAIL.match(email):
        raise HTTPException(422, "That doesn't look like an email address")
    if body.enabled and not url:
        raise HTTPException(422, "Set the webhook URL before turning automations on")
    s = get_settings_row(db)
    s.enabled, s.webhook_url, s.recipient_email = body.enabled, url, email
    db.commit()
    audit.record(db, "user", "automation_settings_updated", "automation_settings", s.id,
                 enabled=s.enabled, webhook_url=url, recipient_email=email)
    return s


@router.post("/settings/secret", response_model=AutomationSettingsOut, response_model_by_alias=True)
def rotate_secret(db: Session = Depends(get_db)):
    """New shared secret. The n8n Header Auth credential must be updated to match."""
    s = get_settings_row(db)
    s.secret = new_secret()
    db.commit()
    audit.record(db, "user", "automation_secret_rotated", "automation_settings", s.id)
    return s


def _out(d: WebhookDelivery, names: dict[str, str]) -> DeliveryOut:
    return DeliveryOut.model_validate(d).model_copy(update={"document_name": names.get(d.document_id)})


@router.post("/test", response_model=DeliveryOut, response_model_by_alias=True)
def send_test(db: Session = Depends(get_db)):
    """Send a labelled sample event now (works even while automations are switched off)."""
    s = get_settings_row(db)
    if not s.webhook_url:
        raise HTTPException(422, "Set the webhook URL first")
    return _out(deliver(db, s, "test", test_payload(s.recipient_email)), {})


@router.get("/deliveries", response_model=list[DeliveryOut], response_model_by_alias=True)
def list_deliveries(limit: int = 50, db: Session = Depends(get_db)):
    rows = list(db.scalars(select(WebhookDelivery).order_by(WebhookDelivery.created_at.desc()).limit(min(limit, 200))))
    ids = {d.document_id for d in rows if d.document_id}
    names = dict(db.execute(select(Document.id, Document.name).where(Document.id.in_(ids))).all()) if ids else {}
    return [_out(d, names) for d in rows]
