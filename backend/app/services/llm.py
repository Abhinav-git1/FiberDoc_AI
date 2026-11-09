"""LLM provider interface. Gemini first; swap by implementing LLMProvider."""
from typing import Protocol, TypeVar

from langsmith import traceable
from pydantic import BaseModel

from app.config import get_settings

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    def generate_structured(self, prompt: str, schema: type[T]) -> T: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class GeminiProvider:
    def __init__(self) -> None:
        from google import genai

        s = get_settings()
        if not s.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self._client = genai.Client(api_key=s.gemini_api_key)
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
        return schema.model_validate_json(resp.text)  # raises if the model broke the schema

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
