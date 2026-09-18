from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Protocol

# How many recent calls the test/offline clients remember. Bounded so a
# long-running process never accumulates prompts (a single request can carry
# several hundred KB of candidate text per role).
CALL_HISTORY = 32


@dataclass(frozen=True)
class LLMResponse:
    text: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    latency_s: Optional[float] = None
    model: str = ""
    raw: object = field(default=None, repr=False, compare=False)


class LLMClient(Protocol):
    """The only surface the pipeline is allowed to depend on.

    Implementations must raise on transport/provider failure rather than
    return partial text, and must never retry silently: retry policy is owned
    by the orchestrator so that request budgets stay observable.
    """

    def generate_json(self, system: str, prompt: str, schema: dict) -> LLMResponse: ...


class StaticLLMClient:
    """Deterministic client for tests and offline demos.

    Responses are served in order; when they run out, `fallback` is returned
    (default: an empty selection, which the parser treats as a valid "nothing
    applies" answer rather than a failure).
    """

    def __init__(self, responses: Optional[list] = None, fallback: str = '{"selections": []}', history: int = CALL_HISTORY):
        self._responses = list(responses or [])
        self._fallback = fallback
        self.calls: deque = deque(maxlen=history)   # most recent calls only (test observability)
        self.call_count = 0

    def generate_json(self, system: str, prompt: str, schema: dict) -> LLMResponse:
        self.call_count += 1
        self.calls.append({"system": system, "prompt": prompt, "schema": schema})
        text = self._responses.pop(0) if self._responses else self._fallback
        return LLMResponse(text=text, model="static")


class LLMProviderError(RuntimeError):
    """Provider failure translated into runtime semantics.

    kind: short stable category — "auth", "quota", "rate_limit", "timeout",
          "unavailable", "bad_request", "empty_response", "unknown".
    retryable: whether the orchestrator may reasonably retry (it decides; the
          adapter never retries).
    The message must never contain credentials or raw provider payloads.
    """

    def __init__(self, kind: str, message: str, *, retryable: bool = False, status_code: Optional[int] = None):
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message
        self.retryable = retryable
        self.status_code = status_code


class LLMConfigError(RuntimeError):
    """The provider cannot be constructed (e.g. missing credentials)."""
