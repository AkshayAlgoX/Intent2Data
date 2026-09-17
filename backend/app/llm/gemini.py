"""Google Gemini adapter for the LLMClient protocol.

This is the ONLY module in the runtime allowed to import the google-genai SDK,
and it imports it lazily so that the rest of the application never loads it.
It performs exactly one request per call, never retries, never logs or
returns the API key, and maps SDK failures onto LLMProviderError so the
orchestrator can apply its own retry/partial-result policy.

Configuration (environment):
  GEMINI_API_KEY                 required (or pass api_key=)
  INTENT2DATA_LLM_MODEL          model name (default: DEFAULT_MODEL)
  INTENT2DATA_LLM_TIMEOUT_S      per-request timeout in seconds (default 60)
"""

import os
import time
from typing import Any, Callable, Optional

from app.llm.client import LLMConfigError, LLMProviderError, LLMResponse

DEFAULT_MODEL = "gemini-3.6-flash"  # the model the evaluation experiments are configured for
DEFAULT_TIMEOUT_S = 60.0
API_KEY_ENV = "GEMINI_API_KEY"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class GeminiClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_s: Optional[float] = None,
        temperature: float = 0.0,
        client: Any = None,
        client_factory: Optional[Callable[[str, float], Any]] = None,
    ):
        key = api_key if api_key is not None else os.getenv(API_KEY_ENV, "")
        key = key.strip()
        if not key:
            raise LLMConfigError(f"{API_KEY_ENV} is not set")
        self.model = (model or os.getenv("INTENT2DATA_LLM_MODEL") or DEFAULT_MODEL).strip()
        self.timeout_s = float(timeout_s if timeout_s is not None else _env_float("INTENT2DATA_LLM_TIMEOUT_S", DEFAULT_TIMEOUT_S))
        if self.timeout_s <= 0:
            raise LLMConfigError("timeout must be positive")
        self.temperature = temperature
        self.calls = 0
        # The SDK client is created lazily on first use unless one is injected
        # (tests inject a fake; nothing here contacts the network at construction).
        self._client = client
        self._client_factory = client_factory or self._default_client_factory
        self._key = key  # never logged, never included in errors or repr

    def __repr__(self) -> str:
        return f"GeminiClient(model={self.model!r}, timeout_s={self.timeout_s})"

    # ---- SDK boundary ----------------------------------------------------------
    @staticmethod
    def _default_client_factory(api_key: str, timeout_s: float):
        from google import genai  # lazy: only this adapter ever imports the SDK
        from google.genai import types

        # HttpOptions.timeout is in milliseconds.
        return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000)))

    def _sdk(self):
        if self._client is None:
            self._client = self._client_factory(self._key, self.timeout_s)
        return self._client

    def _config(self, system: str, schema: dict):
        try:
            from google.genai import types
        except ImportError:
            # Fake clients in tests may not need real config objects.
            return {"system_instruction": system, "temperature": self.temperature,
                    "response_mime_type": "application/json", "response_schema": schema}
        return types.GenerateContentConfig(
            system_instruction=system,
            temperature=self.temperature,
            response_mime_type="application/json",
            response_json_schema=schema,
        )

    # ---- LLMClient --------------------------------------------------------------
    def generate_json(self, system: str, prompt: str, schema: dict) -> LLMResponse:
        self.calls += 1
        start = time.perf_counter()
        try:
            response = self._sdk().models.generate_content(
                model=self.model, contents=prompt, config=self._config(system, schema),
            )
        except LLMProviderError:
            raise
        except Exception as exc:  # single mapping point; NO retry here
            raise _map_exception(exc) from exc
        latency = time.perf_counter() - start
        return _to_response(response, self.model, latency)


# ---- mapping helpers (SDK-free so they are unit-testable) -----------------------

def _to_response(response: Any, model: str, latency: float) -> LLMResponse:
    """Extract text + token metadata defensively. A payload without text is not
    an exception: it becomes an empty LLMResponse that the parser records as
    'empty response', which the orchestrator turns into a failed role."""
    try:
        text = getattr(response, "text", None)
    except Exception:  # the SDK raises when there are no candidates
        text = None
    if text is None:
        text = _text_from_candidates(response)
    usage = getattr(response, "usage_metadata", None)
    return LLMResponse(
        text=text or "",
        input_tokens=_int_attr(usage, "prompt_token_count"),
        output_tokens=_int_attr(usage, "candidates_token_count"),
        latency_s=latency,
        model=model,
        raw=response,
    )


def _text_from_candidates(response: Any) -> str:
    try:
        for cand in getattr(response, "candidates", None) or []:
            content = getattr(cand, "content", None)
            for part in getattr(content, "parts", None) or []:
                t = getattr(part, "text", None)
                if isinstance(t, str) and t:
                    return t
    except Exception:
        pass
    return ""


def _int_attr(obj: Any, name: str) -> Optional[int]:
    value = getattr(obj, name, None) if obj is not None else None
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _map_exception(exc: Exception) -> LLMProviderError:
    """Translate SDK/transport exceptions into LLMProviderError without
    leaking payloads. Uses duck-typing (code/status/message) so the mapping is
    testable without the SDK's exception classes."""
    code = getattr(exc, "code", None)
    code = code if isinstance(code, int) else None
    status = str(getattr(exc, "status", "") or "")
    name = exc.__class__.__name__
    text = f"{status} {getattr(exc, 'message', '') or ''} {exc}".lower()
    quota_daily = "per day" in text or "perday" in text or "generate_content_free_tier_requests" in text

    if code == 429 or "resource_exhausted" in text or "429" in text:
        if quota_daily:
            return LLMProviderError("quota", "provider daily quota exhausted", retryable=False, status_code=429)
        return LLMProviderError("rate_limit", "provider rate limit", retryable=True, status_code=429)
    if code in (401, 403) or "api key" in text or "permission" in text or "unauthenticated" in text:
        return LLMProviderError("auth", "provider rejected credentials", retryable=False, status_code=code)
    if code == 400 or "invalid_argument" in text or "bad request" in text:
        return LLMProviderError("bad_request", "provider rejected the request", retryable=False, status_code=400)
    if "timeout" in name.lower() or "timed out" in text or "deadline" in text or code == 504:
        return LLMProviderError("timeout", "provider request timed out", retryable=True, status_code=code or 504)
    if (code is not None and code >= 500) or "unavailable" in text or "overloaded" in text or "servererror" in name.lower():
        return LLMProviderError("unavailable", "provider unavailable", retryable=True, status_code=code or 503)
    if "connection" in name.lower() or "connect" in text:
        return LLMProviderError("unavailable", "could not reach provider", retryable=True, status_code=None)
    return LLMProviderError("unknown", f"provider failure ({name})", retryable=False, status_code=code)
