import logging

from sqlalchemy.orm import Session

from app.db.models import AuditEvent

log = logging.getLogger("fiberdoc.audit")


def record(db: Session, actor: str, action: str, entity: str, entity_id: str, **detail) -> None:
    """Persist an audit event (also emitted as a structured log line)."""
    db.add(AuditEvent(actor=actor, action=action, entity=entity, entity_id=entity_id, detail=detail))
    db.commit()
    log.info("audit", extra={"actor": actor, "action": action, "entity": entity, "entity_id": entity_id, **detail})
