"""Documents left 'processing' by a server restart are failed at startup, so the UI stops polling."""
from types import SimpleNamespace

from app.api import projects
from app.api.projects import INTERRUPTED, fail_interrupted


class FakeDB:
    def __init__(self, docs):
        self.docs, self.committed = docs, False

    def scalars(self, stmt):
        assert "processing" in str(stmt.compile(compile_kwargs={"literal_binds": True}))
        return SimpleNamespace(all=lambda: [d for d in self.docs if d.status == "processing"])

    def commit(self):
        self.committed = True


def test_stuck_documents_are_marked_interrupted_and_others_untouched(monkeypatch):
    told = []  # the chats the documents came from get an error message
    monkeypatch.setattr(projects, "record_outcome", lambda db, doc_id: told.append(doc_id))
    stuck = SimpleNamespace(id="d1", status="processing", error=None)
    done = SimpleNamespace(id="d2", status="awaiting_review", error=None)
    db = FakeDB([stuck, done])
    assert fail_interrupted(db) == 1 and db.committed
    assert told == ["d1"]
    assert (stuck.status, stuck.error) == ("error", INTERRUPTED)
    assert (done.status, done.error) == ("awaiting_review", None)
