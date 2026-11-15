"""Chat history in the database (tables chats / chat_messages, migration 0002).

The backend writes the messages about an upload itself: an `upload` message when the file arrives, and a `result`
(or `error`) message when the background workflow ends. So the outcome is saved even if the browser was closed
while the document was being checked.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Chat, ChatMessage, Document, Finding


def add_message(db: Session, chat: Chat, role: str, text: str, kind: str = "text",
                document_id: str | None = None) -> ChatMessage:
    msg = ChatMessage(chat_id=chat.id, role=role, text=text, kind=kind, document_id=document_id)
    db.add(msg)
    chat.updated_at = datetime.now(timezone.utc)  # moves the chat to the top of "Recent chats"
    db.commit()
    return msg


def _plural(n: int, word: str, plural: str | None = None) -> str:
    return f"{n} {word if n == 1 else (plural or word + 's')}"


def result_text(doc: Document, statuses: list[str | None]) -> str:
    """The assistant's reply once a document has been checked. `statuses` = the status of each finding."""
    if doc.status == "error":
        return f"Processing {doc.name} failed: {doc.error or 'unknown error'}"
    count = statuses.count
    open_ = len(statuses) - count("passed")
    return (
        f"Finished {doc.name} ({_plural(doc.page_count, 'page')}, classified as {doc.doc_type.replace('_', ' ')}). "
        f"Checked {_plural(len(statuses), 'rule')}: {count('failed')} failed, {count('missing_evidence')} missing evidence, "
        f"{count('needs_review')} need review, {count('passed')} passed. "
        + (f"The {_plural(open_, 'open issue')} {'is' if open_ == 1 else 'are'} waiting for a human reviewer. " if open_ else "")
        + "Nothing is approved automatically."
    )


def record_outcome(db: Session, document_id: str) -> int:
    """Write the result (or error) message into every chat the document was uploaded from. Safe to call twice:
    a chat that already has an outcome message for this document is skipped. Returns the number written."""
    doc = db.get(Document, document_id)
    if doc is None or doc.status == "processing":
        return 0
    chat_ids = set(db.scalars(select(ChatMessage.chat_id).where(
        ChatMessage.document_id == document_id, ChatMessage.kind == "upload")))
    done = set(db.scalars(select(ChatMessage.chat_id).where(
        ChatMessage.document_id == document_id, ChatMessage.kind.in_(("result", "error")))))
    todo = chat_ids - done
    if not todo:
        return 0
    statuses = list(db.scalars(select(Finding.status).where(Finding.document_id == document_id)))
    text, kind = result_text(doc, statuses), ("error" if doc.status == "error" else "result")
    for chat_id in sorted(todo):
        add_message(db, db.get(Chat, chat_id), "assistant", text, kind, document_id)
    return len(todo)
