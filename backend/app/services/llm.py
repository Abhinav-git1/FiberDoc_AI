"""LLM provider interface. Gemini first; swap by implementing LLMProvider."""
from typing import Protocol, TypeVar

from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree
from pydantic import BaseModel

from app.config import get_settings

T = TypeVar("T", bound=BaseModel)


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
        self._embed_model = s.gemini_embed_model
        self._dim = s.embed_dim

    @staticmethod
    def _retry(call, attempts: int = 4):
        """Retry transient Gemini errors (503 overloaded, 429 rate limit) with exponential backoff."""
        import time

        from google.genai import errors

        for i in range(attempts):
            try:
                return call()
            except (errors.ServerError, errors.ClientError) as e:
                transient = isinstance(e, errors.ServerError) or getattr(e, "code", None) == 429
                if not transient or i == attempts - 1:
                    raise
                time.sleep(2**i)  # 1s, 2s, 4s

    # Records prompt + answer in LangSmith when LANGSMITH_TRACING=true; a no-op otherwise.
    # embed() is deliberately not traced, so bulk chunk text is not sent to LangSmith.
    @traceable(run_type="llm", name="gemini.generate_structured",
               process_inputs=lambda i: {"prompt": i["prompt"], "schema": i["schema"].__name__})
    def generate_structured(self, prompt: str, schema: type[T]) -> T:
        from google.genai import types

        resp = self._retry(lambda: self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.0,
            ),
        ))
        self._record_usage(resp)
        return schema.model_validate_json(resp.text)  # raises if the model broke the schema

    def _record_usage(self, resp) -> None:
        """Attach Gemini's token counts and the model name to the current LangSmith run, so the project's
        Tokens / Cost columns and Monitor charts are filled in. No-op when tracing is off."""
        rt = get_current_run_tree()
        if rt is None:
            return
        u = resp.usage_metadata
        meta = {"ls_provider": "google_genai", "ls_model_name": self._model}
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
            resp = self._retry(lambda: self._client.models.embed_content(
                model=self._embed_model,
                contents=batch,
                config=types.EmbedContentConfig(output_dimensionality=self._dim),
            ))
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
