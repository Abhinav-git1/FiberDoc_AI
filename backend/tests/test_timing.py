"""Timing breakdown: steps and Gemini calls are recorded per document and served by the API."""
from types import SimpleNamespace as NS

import pytest
from google.genai import errors
from langgraph.graph import END, START, StateGraph

from app.services import llm, timing
from app.workflow.graph import _timed

from .test_chats import client  # noqa: F401  (throwaway-schema API fixture)


def test_nothing_is_recorded_without_a_tracker():
    with timing.step("parse"):
        pass
    timing.llm_call("embed 1 texts", 0.1, 1, [])  # no tracker open: must not raise


def test_steps_are_recorded_even_when_they_fail():
    with timing.track() as t:
        with timing.step("parse"):
            pass
        with pytest.raises(ValueError), timing.step("embed_chunks"):
            raise ValueError("boom")
    assert [s["name"] for s in t.steps] == ["parse", "embed_chunks"]
    assert set(t.summary()) == {"total_s", "steps", "llm_calls"}


def _no_sleep(monkeypatch):
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)


def test_retry_records_attempts_errors_and_tokens(monkeypatch):
    _no_sleep(monkeypatch)
    calls = iter([errors.ServerError(503, {"error": {"message": "overloaded"}}),
                  NS(usage_metadata=NS(prompt_token_count=900, candidates_token_count=30, thoughts_token_count=700))])

    def call():
        r = next(calls)
        if isinstance(r, Exception):
            raise r
        return r

    with timing.track() as t:
        llm.GeminiProvider._retry("generate EvidenceCheck", call)
    (c,) = t.llm_calls
    assert c["op"] == "generate EvidenceCheck" and c["attempts"] == 2 and len(c["errors"]) == 1
    assert (c["input_tokens"], c["output_tokens"], c["thinking_tokens"]) == (900, 30, 700)


def test_retry_records_a_call_that_finally_fails(monkeypatch):
    _no_sleep(monkeypatch)

    def call():
        raise errors.ClientError(400, {"error": {"message": "bad request"}})  # not transient: no retry

    with timing.track() as t, pytest.raises(errors.ClientError):
        llm.GeminiProvider._retry("embed 3 texts", call)
    (c,) = t.llm_calls
    assert c["failed"] and c["attempts"] == 1


def test_process_saves_timings_and_api_serves_them(client, monkeypatch):  # noqa: F811
    """End to end with fakes: steps from _process and from LangGraph nodes (which run in worker threads) land in
    one record, and GET /api/documents/{id}/timings returns it."""
    from app.api import projects
    from app.db.models import Document, Project

    http, Session = client
    with Session() as db:
        p = Project(name="Demo", location="")
        db.add(p)
        db.flush()
        d = Document(project_id=p.id, name="plan.pdf", status="processing")
        db.add(d)
        db.commit()
        doc_id = d.id

    assert http.get(f"/api/documents/{doc_id}/timings").status_code == 404  # nothing recorded yet

    def fake_workflow(db, document_id):
        g = StateGraph(dict)
        g.add_node("classify", _timed("classify", lambda s: {}))
        g.add_edge(START, "classify")
        g.add_edge("classify", END)
        g.compile().invoke({"document_id": document_id})
        doc = db.get(Document, document_id)
        doc.status = "awaiting_review"
        db.commit()

    monkeypatch.setattr(projects, "SessionLocal", Session)
    monkeypatch.setattr(projects, "parse_document", lambda path: NS(page_count=1, chunks=[]))
    monkeypatch.setattr(projects, "embed_document_chunks", lambda db, i: timing.llm_call("embed 0 texts", 0.2, 1, []))
    monkeypatch.setattr(projects, "run_workflow", fake_workflow)
    monkeypatch.setattr(projects, "record_outcome", lambda db, i: 0)
    projects._process(doc_id, None)

    r = http.get(f"/api/documents/{doc_id}/timings")
    assert r.status_code == 200
    js = r.json()
    assert [s["name"] for s in js["steps"]] == ["parse", "embed_chunks", "classify"]
    assert js["llmCalls"][0]["op"] == "embed 0 texts" and js["totalS"] >= 0
