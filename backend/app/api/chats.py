"""Saved chats. Upload and result messages are written by the backend (see app/services/chat_log.py);
the client adds its own text messages through POST /chats/{id}/messages."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Chat, Document, Project
from app.db.session import get_db
from app.schemas import ChatIn, ChatOut, ChatSummaryOut, DocumentOut, MessageIn, MessageOut
from app.services.chat_log import add_message

router = APIRouter(prefix="/api")


def get_chat(db: Session, chat_id: str) -> Chat:
    chat = db.get(Chat, chat_id)
    if chat is None:
        raise HTTPException(404, "Chat not found")
    return chat


@router.get("/chats", response_model=list[ChatSummaryOut], response_model_by_alias=True)
def list_chats(limit: int = 50, db: Session = Depends(get_db)):
    return list(db.scalars(select(Chat).order_by(Chat.updated_at.desc()).limit(min(max(limit, 1), 200))))


@router.post("/chats", response_model=ChatSummaryOut, response_model_by_alias=True, status_code=201)
def create_chat(body: ChatIn, db: Session = Depends(get_db)):
    if body.project_id and db.get(Project, body.project_id) is None:
        raise HTTPException(404, "Project not found")
    chat = Chat(title=body.title.strip()[:120] or "New chat", project_id=body.project_id)
    db.add(chat)
    db.commit()
    return chat


@router.get("/chats/{chat_id}", response_model=ChatOut, response_model_by_alias=True)
def read_chat(chat_id: str, db: Session = Depends(get_db)):
    chat = get_chat(db, chat_id)
    doc_ids = {m.document_id for m in chat.messages if m.document_id}
    docs = list(db.scalars(select(Document).where(Document.id.in_(doc_ids)))) if doc_ids else []
    return ChatOut(**ChatSummaryOut.model_validate(chat).model_dump(),
                   messages=[MessageOut.model_validate(m) for m in chat.messages],
                   documents=[DocumentOut.model_validate(d) for d in docs])


@router.post("/chats/{chat_id}/messages", response_model=MessageOut, response_model_by_alias=True, status_code=201)
def post_message(chat_id: str, body: MessageIn, db: Session = Depends(get_db)):
    return add_message(db, get_chat(db, chat_id), body.role, body.text, body.kind)
