"""Gemini token counts are attached to the LangSmith run, so LangSmith can show tokens and cost per call."""
from types import SimpleNamespace as NS

from app.services import llm


class FakeRun:
    def __init__(self):
        self.calls = []

    def set(self, **kw):
        self.calls.append(kw)


def _provider():
    p = object.__new__(llm.GeminiProvider)  # skip __init__: no API key or network needed
    p._model = "gemini-test"
    return p


def test_usage_and_model_are_recorded(monkeypatch):
    run = FakeRun()
    monkeypatch.setattr(llm, "get_current_run_tree", lambda: run)
    usage = NS(prompt_token_count=1200, candidates_token_count=80, thoughts_token_count=40,
               total_token_count=1320, cached_content_token_count=None)
    _provider()._record_usage(NS(usage_metadata=usage), "gemini-test")
    (kw,) = run.calls
    assert kw["metadata"] == {"ls_provider": "google_genai", "ls_model_name": "gemini-test"}
    u = kw["usage_metadata"]
    assert (u["input_tokens"], u["output_tokens"], u["total_tokens"]) == (1200, 120, 1320)
    assert u["output_token_details"] == {"reasoning": 40}


def test_no_usage_still_records_model(monkeypatch):
    run = FakeRun()
    monkeypatch.setattr(llm, "get_current_run_tree", lambda: run)
    _provider()._record_usage(NS(usage_metadata=None), "gemini-test")
    assert run.calls == [{"metadata": {"ls_provider": "google_genai", "ls_model_name": "gemini-test"}}]


def test_noop_when_tracing_is_off(monkeypatch):
    monkeypatch.setattr(llm, "get_current_run_tree", lambda: None)
    _provider()._record_usage(NS(usage_metadata=None), "gemini-test")  # must not raise
