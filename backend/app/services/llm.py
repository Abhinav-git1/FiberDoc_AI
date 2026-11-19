"""LLM provider interface. Gemini first; swap by implementing LLMProvider."""
from typing import Protocol, TypeVar

from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree
from pydantic import BaseModel

from app.config import get_settings
from app.services import timing

T = TypeVar("T", bound=BaseModel)


class QuotaExhausted(RuntimeError):
    """Every model's quota is used up (until the time Gemini gave); no request was made."""


# model -> time.perf_counter() value when its quota resets. Process-wide, so once a daily quota is gone no later
# call waits on that model again until the reset Gemini announced. Cleared on restart.
_quota_reset_at: dict[str, float] = {}


def _retry_after_s(message: str) -> float | None:
    """Seconds Gemini says to wait, from "Please retry in 11h56m7.2s" or "'retryDelay': '42s'"; None if absent."""
    import re

    m = re.search(r"retry in ((?:\d+h)?(?:\d+m)?(?:[\d.]+s)?)", message) or         re.search(r"'retryDelay': '([\d.]+s)'", message)
    if not m or not m.group(1):
        return None
    parts = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", m.group(1))
    if not parts:
        return None
    h, mins, secs = parts.groups()
    return int(h or 0) * 3600 + int(mins or 0) * 60 + float(secs or 0)


def _fmt_wait(s: float) -> str:
    h, rem = divmod(max(0, int(s)), 3600)
    return f"{h}h{rem // 60:02d}m" if h else f"{rem // 60}m{rem % 60:02d}s"


class LLMProvider(Protocol):
    def generate_structured(self, prompt: str, schema: type[T]) -> T: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class GeminiProvider:
    def __init__(self) -> None:
        from google import genai
        from google.genai import types

        s = get_settings()
        if not s.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        # The SDK has no default timeout: a stalled request would block the workflow indefinitely.
        self._client = genai.Client(api_key=s.gemini_api_key,
                                    http_options=types.HttpOptions(timeout=s.gemini_timeout_s * 1000))  # ms
        self._model = s.gemini_model
        self._fallback = s.gemini_fallback_model
        self._timeout_s = s.gemini_timeout_s
        self._budget_s = s.gemini_call_budget_s
        self._embed_model = s.gemini_embed_model
        self._dim = s.embed_dim

    @staticmethod
    def _retry(op: str, call, models: list[str], budget_s: float, timeout_s: float, attempts: int = 10):
        """Call Gemini with retries, a model fallback and a total time budget. Returns (response, model used).

        `call(model, timeout_s)` makes one request. Errors are handled like this:
        - 503 overloaded / 504 deadline / a client-side timeout: try the next model in `models` right away (no
          sleep the first time each model is tried), since waiting on a busy model is what made uploads take minutes.
        - 429 with a long wait (a daily quota: "retry in 11h56m"): that model is skipped until its quota resets,
          for every later call too, and the next model is tried at once. Quotas are per model, so the fallback
          usually still has some. (2026-11-19: five back-offs on a model whose daily quota was gone used the whole
          budget for nothing.)
        - 429 with a short wait (a per-minute limit): the next model if there is an untried one, else back off.
        - Anything else (400, a bad key): raise at once.
        No request may run past `budget_s` in total; when too little is left for a useful attempt, the last error is
        raised and the caller marks the rule 'needs review'. The budget, not `attempts`, is what normally ends a run
        of failures: Gemini's "high demand" spells often pass within 20-30 s, so using the whole budget (back-off
        1, 2, 4, 8, 16 s) more often gets a real answer than stopping after a few quick tries (2026-11-19: four 503s
        in 7.7 s, then 'needs review'). `attempts` is only a safety cap.

        Every call is recorded for the timing breakdown (app/services/timing.py): total seconds, attempts, the errors
        seen (each prefixed with its model), the model that answered, and token counts (thinking tokens separately)."""
        import time

        import httpx
        from google.genai import errors

        min_attempt_s = 5.0  # less time than this left: not worth another request
        max_delay_s = 16
        start, seen, tried, m = time.perf_counter(), [], set(), 0
        live = [x for x in models if _quota_reset_at.get(x, 0) <= start]
        if not live:
            waits = ", ".join(f"{x} in {_fmt_wait(_quota_reset_at[x] - start)}" for x in models)
            seen.append(f"QuotaExhausted: daily quota used up; resets: {waits}")
            timing.llm_call(op, 0.0, 0, seen, failed=True, model=models[0])
            raise QuotaExhausted(seen[-1])
        for i in range(attempts):
            model = live[m]
            tried.add(model)
            remaining = budget_s - (time.perf_counter() - start)
            try:
                resp = call(model, min(timeout_s, remaining))
            except Exception as e:
                seen.append(f"{model}: {type(e).__name__}: {str(e)[:120]}")
                overloaded = isinstance(e, (errors.ServerError, httpx.TimeoutException))
                rate_limited = isinstance(e, errors.ClientError) and getattr(e, "code", None) == 429
                hint = _retry_after_s(str(e)) if rate_limited else None
                delay = 0.0
                if rate_limited and hint is not None and hint > budget_s:  # quota gone for hours: skip this model
                    _quota_reset_at[model] = time.perf_counter() + hint
                    live.remove(model)
                    m = m % len(live) if live else 0
                elif (overloaded or rate_limited) and len(live) > 1:
                    m = (m + 1) % len(live)
                    if live[m] in tried:  # every model has failed once: back off before going round again
                        delay = float(min(hint or 2 ** (i - 1), max_delay_s))
                elif overloaded or rate_limited:
                    delay = float(min(hint or 2**i, max_delay_s))  # 1, 2, 4, 8, 16 s
                left = budget_s - (time.perf_counter() - start) - delay
                if not (overloaded or rate_limited) or not live or i == attempts - 1 or left < min_attempt_s:
                    timing.llm_call(op, time.perf_counter() - start, i + 1, seen, failed=True, model=model)
                    raise
                if delay:
                    time.sleep(delay)
                continue
            u = getattr(resp, "usage_metadata", None)
            tokens = {} if u is None else {"input_tokens": getattr(u, "prompt_token_count", None) or 0,
                                           "output_tokens": getattr(u, "candidates_token_count", None) or 0,
                                           "thinking_tokens": getattr(u, "thoughts_token_count", None) or 0}
            timing.llm_call(op, time.perf_counter() - start, i + 1, seen, model=model, **tokens)
            return resp, model

    def _models(self) -> list[str]:
        """The main model, then each backup once (blank and repeated names dropped)."""
        out = [self._model]
        for name in (x.strip() for x in self._fallback.split(",")):
            if name and name not in out:
                out.append(name)
        return out

    # Records prompt + answer in LangSmith when LANGSMITH_TRACING=true; a no-op otherwise.
    # embed() is deliberately not traced, so bulk chunk text is not sent to LangSmith.
    @traceable(run_type="llm", name="gemini.generate_structured",
               process_inputs=lambda i: {"prompt": i["prompt"], "schema": i["schema"].__name__})
    def generate_structured(self, prompt: str, schema: type[T]) -> T:
        from google.genai import types

        resp, model = self._retry(f"generate {schema.__name__}", lambda model, timeout_s: self._client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.0,
                http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),  # ms; never past the call's budget
            ),
        ), self._models(), self._budget_s, self._timeout_s)
        self._record_usage(resp, model)
        return schema.model_validate_json(resp.text)  # raises if the model broke the schema

    def _record_usage(self, resp, model: str) -> None:
        """Attach Gemini's token counts and the model name to the current LangSmith run, so the project's
        Tokens / Cost columns and Monitor charts are filled in. No-op when tracing is off."""
        rt = get_current_run_tree()
        if rt is None:
            return
        u = resp.usage_metadata
        meta = {"ls_provider": "google_genai", "ls_model_name": model}
        if u is None:
            rt.set(metadata=meta)
            return
        inp = u.prompt_token_count or 0
        out = (u.candidates_token_count or 0) + (u.thoughts_token_count or 0)  # thinking tokens are billed as output
        rt.set(metadata=meta, usage_metadata={
            "input_tokens": inp,
            "output_tokens": out,
            "total_tokens": u.total_token_count or inp + out,
            "input_token_details": {"cache_read": u.cached_content_token_count or 0},
            "output_token_details": {"reasoning": u.thoughts_token_count or 0},
        })

    def embed(self, texts: list[str]) -> list[list[float]]:
        from google.genai import types

        out: list[list[float]] = []
        for i in range(0, len(texts), 50):
            batch = texts[i : i + 50]
            # One model only: vectors from a different embedding model would not be comparable with the stored ones.
            resp, _ = self._retry(f"embed {len(batch)} texts", lambda model, timeout_s: self._client.models.embed_content(
                model=model,
                contents=batch,
                config=types.EmbedContentConfig(output_dimensionality=self._dim,
                                                http_options=types.HttpOptions(timeout=int(timeout_s * 1000))),
            ), [self._embed_model], self._budget_s, self._timeout_s)
            out += [e.values for e in resp.embeddings]
        return out


_provider: LLMProvider | None = None


def get_llm() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = GeminiProvider()
    return _provider


def set_llm(provider: LLMProvider | None) -> None:
    """Override the provider (tests, alternative models)."""
    global _provider
    _provider = provider
