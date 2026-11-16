"""Outbound webhook (n8n -> email): settings API, payload, signing, retries and the delivery log."""
import hashlib
import hmac
import json

import httpx

from app.services import notify

from .test_chats import client  # noqa: F401  (throwaway-schema API fixture)


class FakePost:
    """Stands in for httpx.post: returns (or raises) the queued responses and records each request."""

    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, url, body, headers):
        self.calls.append((url, body, headers))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return httpx.Response(r, text="ok" if r < 400 else "nope")


def _setup(monkeypatch, *responses):
    fake = FakePost(*responses)
    monkeypatch.setattr(notify, "_post", fake)
    monkeypatch.setattr(notify.time, "sleep", lambda s: None)
    return fake


def _seed_checked(Session):
    from app.db.models import Document, Finding, Project, Rule

    with Session() as db:
        p = Project(name="Metro Demo", location="")
        db.add(p)
        db.flush()
        d = Document(project_id=p.id, name="plan.pdf", status="awaiting_review", page_count=4, doc_type="construction_plan")
        db.add(d)
        db.add_all([Rule(id=rid, title=rid, text="t", severity=sev, applies_to=[], keywords=[], check_type="required_term",
                         params={}, status="approved", section="Construction") for rid, sev in [("R1", "low"), ("R2", "high"), ("R3", "high")]])
        db.flush()
        for rid, status, sev in [("R1", "passed", "low"), ("R2", "failed", "high"), ("R3", None, "high")]:
            db.add(Finding(project_id=p.id, document_id=d.id, rule_id=rid, title=f"Rule {rid}", severity=sev, source="rule",
                           explanation="x" * 400, status=status))
        db.commit()
        return d.id


def test_settings_start_disabled_and_validate_input(client):  # noqa: F811
    http, _ = client
    s = http.get("/api/automations/settings").json()
    assert s["enabled"] is False and s["webhookUrl"] is None and len(s["secret"]) >= 20

    assert http.put("/api/automations/settings", json={"enabled": True}).status_code == 422  # no URL yet
    assert http.put("/api/automations/settings", json={"enabled": False, "webhookUrl": "ftp://x"}).status_code == 422
    assert http.put("/api/automations/settings", json={"enabled": False, "recipientEmail": "not-an-email"}).status_code == 422

    r = http.put("/api/automations/settings", json={"enabled": True, "webhookUrl": " http://localhost:5678/webhook/fiberdoc ",
                                                    "recipientEmail": "reviewer@example.com"})
    assert r.status_code == 200 and r.json()["webhookUrl"] == "http://localhost:5678/webhook/fiberdoc"

    old = r.json()["secret"]
    assert http.post("/api/automations/settings/secret").json()["secret"] != old


def test_send_test_is_signed_and_logged(client, monkeypatch):  # noqa: F811
    http, _ = client
    fake = _setup(monkeypatch, 200)
    assert http.post("/api/automations/test").status_code == 422  # no URL yet
    s = http.put("/api/automations/settings", json={"enabled": False, "webhookUrl": "http://n8n.local/webhook/x",
                                                    "recipientEmail": "reviewer@example.com"}).json()

    d = http.post("/api/automations/test").json()  # works while switched off
    assert d["status"] == "sent" and d["event"] == "test" and d["attempts"] == 1

    (url, body, headers), = fake.calls
    assert url == "http://n8n.local/webhook/x"
    assert headers["X-FiberDoc-Token"] == s["secret"]
    expected = "sha256=" + hmac.new(s["secret"].encode(), body, hashlib.sha256).hexdigest()
    assert headers["X-FiberDoc-Signature"] == expected
    payload = json.loads(body)
    assert payload["test"] is True and payload["recipient"] == "reviewer@example.com"

    log = http.get("/api/automations/deliveries").json()
    assert [x["status"] for x in log] == ["sent"]


def test_retries_server_errors_but_not_client_errors(client, monkeypatch):  # noqa: F811
    http, _ = client
    http.put("/api/automations/settings", json={"enabled": False, "webhookUrl": "http://n8n.local/webhook/x"})

    fake = _setup(monkeypatch, httpx.ConnectError("refused"), 503, 200)
    d = http.post("/api/automations/test").json()
    assert d["status"] == "sent" and d["attempts"] == 3 and len(fake.calls) == 3

    fake = _setup(monkeypatch, 404)  # wrong URL: retrying won't help
    d = http.post("/api/automations/test").json()
    assert d["status"] == "failed" and d["attempts"] == 1 and d["httpStatus"] == 404 and "HTTP 404" in d["error"]

    _setup(monkeypatch, httpx.ConnectError("refused"), httpx.ConnectError("refused"), httpx.ConnectError("refused"))
    d = http.post("/api/automations/test").json()
    assert d["status"] == "failed" and d["attempts"] == 3 and d["httpStatus"] is None and "ConnectError" in d["error"]


def test_document_checked_payload_and_switch(client, monkeypatch):  # noqa: F811
    http, Session = client
    doc_id = _seed_checked(Session)

    fake = _setup(monkeypatch, 200)
    with Session() as db:
        assert notify.notify_document_checked(db, doc_id) is None  # switched off: nothing sent
    assert fake.calls == []

    http.put("/api/automations/settings", json={"enabled": True, "webhookUrl": "http://n8n.local/webhook/x",
                                                "recipientEmail": "reviewer@example.com"})
    with Session() as db:
        d = notify.notify_document_checked(db, doc_id)
        assert d.status == "sent" and d.document_id == doc_id

    p = json.loads(fake.calls[0][1])
    assert p["event"] == "document.checked" and p["document"]["name"] == "plan.pdf"
    assert p["project"]["name"] == "Metro Demo"
    assert p["counts"] == {"failed": 1, "missing_evidence": 0, "needs_review": 1, "passed": 1, "total": 3}  # null -> needs review
    assert [f["rule_id"] for f in p["open_findings"]] == ["R2", "R3"]  # passed left out; failed first
    assert len(p["open_findings"][0]["explanation"]) == notify.EXPLANATION_CHARS
    assert "Checked 3 rules" in p["summary"]
    assert "chunks" not in json.dumps(p)  # summary only, no document text

    log = http.get("/api/automations/deliveries").json()
    assert log[0]["documentName"] == "plan.pdf"


def test_a_broken_webhook_never_raises(client, monkeypatch):  # noqa: F811
    http, Session = client
    doc_id = _seed_checked(Session)
    http.put("/api/automations/settings", json={"enabled": True, "webhookUrl": "http://n8n.local/webhook/x"})

    def boom(*a):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(notify, "deliver", boom)
    with Session() as db:
        assert notify.notify_document_checked(db, doc_id) is None
