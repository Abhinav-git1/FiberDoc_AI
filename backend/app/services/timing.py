"""Where the processing time goes: per-step durations and every Gemini call, for one document.

`track()` opens a recorder for the current job. `step()` and `llm_call()` add to it and do nothing when no recorder
is open, so code that is timed (the parser, the workflow nodes, the Gemini provider) runs unchanged in tests and
scripts. The recorder lives in a ContextVar, which LangGraph copies into the threads that run workflow nodes.
"""
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class Timings:
    started: float = field(default_factory=time.perf_counter)
    steps: list[dict] = field(default_factory=list)
    llm_calls: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        return {"total_s": round(time.perf_counter() - self.started, 2), "steps": self.steps, "llm_calls": self.llm_calls}


_current: ContextVar[Timings | None] = ContextVar("fiberdoc_timings", default=None)


@contextmanager
def track():
    t = Timings()
    token = _current.set(t)
    try:
        yield t
    finally:
        _current.reset(token)


@contextmanager
def step(name: str):
    t = _current.get()
    start = time.perf_counter()
    try:
        yield
    finally:
        if t is not None:  # recorded even when the step raises, so a failure still shows how long it ran
            t.steps.append({"name": name, "seconds": round(time.perf_counter() - start, 3)})


def llm_call(op: str, seconds: float, attempts: int, errors: list[str], **extra) -> None:
    t = _current.get()
    if t is not None:
        t.llm_calls.append({"op": op, "seconds": round(seconds, 3), "attempts": attempts, "errors": errors, **extra})
