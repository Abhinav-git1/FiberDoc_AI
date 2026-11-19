"""Gemini calls switch to the fallback model on 503/504 and never run past their total time budget.

Why: one upload spent 127 s on four failed attempts at an overloaded model (2026-11-15 timing breakdown)."""
import httpx
import pytest
from google.genai import errors

from app.services import llm, timing

PRIMARY, FALLBACK = "gemini-main", "gemini-backup"


class Clock:
    """Fake time: requests and sleeps advance it, so budgets are tested without waiting."""

    def __init__(self, monkeypatch):
        import time

        self.now, self.sleeps = 0.0, []
        monkeypatch.setattr(time, "perf_counter", lambda: self.now)
        monkeypatch.setattr(time, "sleep", self._sleep)

    def _sleep(self, s):
        self.sleeps.append(s)
        self.now += s


def _overloaded():
    return errors.ServerError(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}})


def _deadline():
    return errors.ServerError(504, {"error": {"code": 504, "message": "deadline", "status": "DEADLINE_EXCEEDED"}})


def test_overloaded_model_falls_back_at_once(monkeypatch):
    clock, asked = Clock(monkeypatch), []

    def call(model, timeout_s):
        asked.append(model)
        clock.now += 3
        if model == PRIMARY:
            raise _overloaded()
        return "ok"

    with timing.track() as t:
        resp, model = llm.GeminiProvider._retry("generate EvidenceCheck", call, [PRIMARY, FALLBACK], 60, 30)
    assert (resp, model, asked) == ("ok", FALLBACK, [PRIMARY, FALLBACK])
    assert clock.sleeps == []  # no back-off before trying a model that hasn't failed yet
    (c,) = t.llm_calls
    assert c["model"] == FALLBACK and c["attempts"] == 2
    assert c["errors"][0].startswith(f"{PRIMARY}: ServerError: 503")


def test_client_timeout_also_falls_back(monkeypatch):
    clock = Clock(monkeypatch)

    def call(model, timeout_s):
        clock.now += timeout_s
        if model == PRIMARY:
            raise httpx.ReadTimeout("timed out")
        return "ok"

    assert llm.GeminiProvider._retry("generate X", call, [PRIMARY, FALLBACK], 60, 30)[1] == FALLBACK


def test_never_runs_past_the_budget(monkeypatch):
    """Both models keep timing out: the call gives up within the budget instead of after minutes."""
    clock, timeouts = Clock(monkeypatch), []

    def call(model, timeout_s):
        timeouts.append(timeout_s)
        clock.now += timeout_s  # each request uses its whole timeout, then the server gives up
        raise _deadline()

    with timing.track() as t, pytest.raises(errors.ServerError):
        llm.GeminiProvider._retry("generate EvidenceCheck", call, [PRIMARY, FALLBACK], 60, 30)
    assert clock.now <= 60
    assert timeouts == [30, 30]  # the second request gets only what was left
    (c,) = t.llm_calls
    assert c["failed"] and c["attempts"] == 2


def test_request_timeout_is_cut_to_what_is_left(monkeypatch):
    clock, timeouts = Clock(monkeypatch), []

    def call(model, timeout_s):
        timeouts.append(timeout_s)
        clock.now += 20
        if len(timeouts) < 3:
            raise _overloaded()
        return "ok"

    llm.GeminiProvider._retry("generate X", call, [PRIMARY, FALLBACK], 60, 30)
    # 1st: 30 (cap). 2nd: 30 (40 left). Both models failed, so 1 s back-off; 3rd: 60 - 41 = 19 left.
    assert timeouts == [30, 30, 19] and clock.sleeps == [1.0]


def test_single_model_backs_off_and_retries(monkeypatch):
    """Embeddings have one model (vectors from another model would not match the stored ones): plain back-off."""
    clock, asked = Clock(monkeypatch), []

    def call(model, timeout_s):
        asked.append(model)
        if len(asked) == 1:
            raise _overloaded()
        return "ok"

    assert llm.GeminiProvider._retry("embed 3 texts", call, [PRIMARY], 60, 30) == ("ok", PRIMARY)
    assert asked == [PRIMARY, PRIMARY] and clock.sleeps == [1.0]


def test_bad_request_is_not_retried_on_the_fallback(monkeypatch):
    Clock(monkeypatch)
    asked = []

    def call(model, timeout_s):
        asked.append(model)
        raise errors.ClientError(400, {"error": {"message": "bad request"}})

    with pytest.raises(errors.ClientError):
        llm.GeminiProvider._retry("generate X", call, [PRIMARY, FALLBACK], 60, 30)
    assert asked == [PRIMARY]


def test_models_list_skips_an_empty_or_duplicate_fallback():
    p = object.__new__(llm.GeminiProvider)
    p._model = PRIMARY
    for fb, want in [(FALLBACK, [PRIMARY, FALLBACK]), ("", [PRIMARY]), (PRIMARY, [PRIMARY])]:
        p._fallback = fb
        assert p._models() == want


def test_quick_503s_keep_trying_until_the_budget_is_used(monkeypatch):
    """2026-11-19: both models answered 503 within a second, and the old 4-attempt cap gave up after 7.7 s with
    most of the budget unused. Now the back-off grows (capped at 16 s) and the budget decides when to stop."""
    clock = Clock(monkeypatch)

    def call(model, timeout_s):
        clock.now += 0.5
        raise _overloaded()

    with timing.track() as t, pytest.raises(errors.ServerError):
        llm.GeminiProvider._retry("generate EvidenceCheck", call, [PRIMARY, FALLBACK], 60, 30)
    assert clock.sleeps == [1, 2, 4, 8, 16, 16]
    assert 45 < clock.now <= 60
    assert t.llm_calls[0]["attempts"] == 8


def test_overload_that_clears_gets_a_real_answer(monkeypatch):
    clock = Clock(monkeypatch)

    def call(model, timeout_s):
        clock.now += 0.5
        if clock.now < 25:  # busy for the first ~25 s
            raise _overloaded()
        return "ok"

    resp, _ = llm.GeminiProvider._retry("generate EvidenceCheck", call, [PRIMARY, FALLBACK], 60, 30)
    assert resp == "ok" and clock.now < 60
