"""Saved chats: the API, and the messages the backend writes about an upload.

The API tests run against a throwaway Postgres schema (dropped afterwards) and are skipped when the database
can't be reached. The wording tests need no database.
"""
import uuid
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.services.chat_log import record_outcome, result_text


# --- wording (no database) -------------------------------------------------

def _doc(**kw):
    return NS(**{"name": "plan.pdf", "status": "awaiting_review", "error": None, "page_count": 3,
                 "doc_type": "construction_plan", **kw})


def test_result_text_counts_each_status():
    t = result_text(_doc(), ["failed", "missing_evidence", "passed", "passed", "needs_review"])
    assert t.startswith("Finished plan.pdf (3 pages, classified as construction plan).")
    assert "Checked 5 rules: 1 failed, 1 missing evidence, 1 need review, 2 passed." in t
    assert "The 3 open issues are waiting for a human reviewer." in t
    assert t.endswith("Nothing is approved automatically.")


def test_result_text_singular_and_all_passed():
    t = result_text(_doc(page_count=1), ["passed"])
    assert "(1 page," in t and "Checked 1 rule:" in t and "waiting for a human reviewer" not in t


def test_result_text_for_a_failed_document():
    assert result_text(_doc(status="error", error="bad PDF"), []) == "Processing plan.pdf failed: bad PDF"


# --- API against a throwaway schema ----------------------------------------

@pytest.fixture()
def client():
    from app.config import get_settings
    from app.db import models  # noqa: F401
    from app.db.session import Base, get_db
    from app.main import app
    from sqlalchemy.engine import make_url

    schema = f"test_chats_{uuid.uuid4().hex[:8]}"
    base = make_url(get_settings().database_url)
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as c:
            c.execute(text(f'CREATE SCHEMA "{schema}"'))
    except Exception as e:  # no database here: skip rather than fail
        pytest.skip(f"Postgres not reachable: {type(e).__name__}")
    engine = create_engine(base.update_query_dict({"options": f"-csearch_path={schema},public"}))
    # checkfirst=False: the real tables in public are visible on the search path and would be taken as existing
    Base.metadata.create_all(engine, checkfirst=False)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def db_override():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = db_override
    try:
        # no `with`: skips the app's startup (migrations and seeding run against the real database)
        yield TestClient(app), Session
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        with admin.connect() as c:
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def _seed(Session):
    from app.db.models import Document, Finding, Project, Rule

    with Session() as db:
        p = Project(name="Demo", location="")
        db.add(p)
        db.flush()
        d = Document(project_id=p.id, name="plan.pdf", status="processing", page_count=2, doc_type="construction_plan")
        db.add(d)
        db.add(Rule(id="R1", title="t", text="t", severity="high", applies_to=[], keywords=[], check_type="semantic",
                    params={}, status="approved"))
        db.commit()
        return p.id, d.id


def test_chat_lifecycle(client):
    api, Session = client
    project_id, doc_id = _seed(Session)

    r = api.post("/api/chats", json={"title": "  Segment 4 check  ", "projectId": project_id})
    assert r.status_code == 201
    chat = r.json()
    assert (chat["title"], chat["projectId"]) == ("Segment 4 check", project_id)

    assert api.post(f"/api/chats/{chat['id']}/messages", json={"role": "user", "text": "please check"}).status_code == 201
    # clients may not write upload/result messages: only the backend does
    assert api.post(f"/api/chats/{chat['id']}/messages", json={"role": "assistant", "text": "x", "kind": "result"}).status_code == 422

    # what the upload endpoint does when given chat_id, then the workflow finishing
    from app.db.models import Chat, Document, Finding
    from app.services.chat_log import add_message
    with Session() as db:
        add_message(db, db.get(Chat, chat["id"]), "user", "plan.pdf", "upload", doc_id)
        assert record_outcome(db, doc_id) == 0  # still processing: nothing to report yet
        db.get(Document, doc_id).status = "awaiting_review"
        db.add_all([Finding(project_id=project_id, document_id=doc_id, rule_id="R1", title="t", severity="high",
                            source="ai", explanation="e", status=s) for s in ("failed", "passed")])
        db.commit()
        assert record_outcome(db, doc_id) == 1
        assert record_outcome(db, doc_id) == 0  # idempotent

    full = api.get(f"/api/chats/{chat['id']}").json()
    assert [(m["role"], m["kind"]) for m in full["messages"]] == [("user", "text"), ("user", "upload"), ("assistant", "result")]
    assert full["messages"][2]["documentId"] == doc_id
    assert "1 failed" in full["messages"][2]["text"] and "1 passed" in full["messages"][2]["text"]
    assert [d["id"] for d in full["documents"]] == [doc_id]

    listed = api.get("/api/chats").json()
    assert [c["id"] for c in listed] == [chat["id"]]


def test_unknown_chat_and_project(client):
    api, _ = client
    assert api.get("/api/chats/nope").status_code == 404
    assert api.post("/api/chats/nope/messages", json={"role": "user", "text": "x"}).status_code == 404
    assert api.post("/api/chats", json={"title": "x", "projectId": "nope"}).status_code == 404


def test_upload_with_chat_id_writes_upload_message(client, monkeypatch, tmp_path):
    api, Session = client
    project_id, _ = _seed(Session)
    from app.api import projects

    monkeypatch.setattr(projects, "_process", lambda *a: None)  # don't run the real pipeline
    monkeypatch.setattr(projects, "get_settings", lambda: NS(upload_dir=str(tmp_path), max_upload_mb=5))
    chat_id = api.post("/api/chats", json={"title": "c"}).json()["id"]

    r = api.post(f"/api/projects/{project_id}/documents", data={"chat_id": chat_id},
                 files={"file": ("route.pdf", b"%PDF-1.4 fake", "application/pdf")})
    assert r.status_code == 202, r.text
    assert r.json()["sizeBytes"] == len(b"%PDF-1.4 fake")
    msgs = api.get(f"/api/chats/{chat_id}").json()["messages"]
    assert [(m["kind"], m["text"], m["documentId"]) for m in msgs] == [("upload", "route.pdf", r.json()["id"])]

    bad = api.post(f"/api/projects/{project_id}/documents", data={"chat_id": "nope"},
                   files={"file": ("route.pdf", b"%PDF-1.4", "application/pdf")})
    assert bad.status_code == 404
