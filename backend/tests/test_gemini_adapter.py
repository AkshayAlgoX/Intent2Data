"""Unit tests for the Gemini adapter. Every test injects a fake SDK client;
no test constructs a real google-genai client and nothing touches the network.
"""

import json
import sys
from types import SimpleNamespace

import pytest

from app.llm.client import LLMConfigError, LLMProviderError, LLMResponse
from app.llm.factory import ProviderNotAvailable, build_llm_client
from app.llm.gemini import API_KEY_ENV, DEFAULT_MODEL, DEFAULT_TIMEOUT_S, GeminiClient, _map_exception, _to_response

SCHEMA = {"type": "object"}


class FakeModels:
    def __init__(self, result=None, exc=None):
        self.result, self.exc, self.calls = result, exc, []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return self.result


class FakeSDK:
    def __init__(self, result=None, exc=None):
        self.models = FakeModels(result, exc)


def fake_response(text='{"selections": []}', prompt_tokens=123, out_tokens=7):
    usage = SimpleNamespace(prompt_token_count=prompt_tokens, candidates_token_count=out_tokens)
    return SimpleNamespace(text=text, usage_metadata=usage, candidates=[])


def make(sdk, **kw):
    kw.setdefault("api_key", "test-key-not-real")
    return GeminiClient(client=sdk, **kw)


# ---- construction / configuration -------------------------------------------

def test_missing_api_key_is_config_error(monkeypatch):
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    with pytest.raises(LLMConfigError):
        GeminiClient(client=FakeSDK())
    with pytest.raises(LLMConfigError):
        GeminiClient(api_key="   ", client=FakeSDK())


def test_api_key_is_never_exposed():
    c = make(FakeSDK())
    assert "test-key" not in repr(c)
    assert "test-key" not in str(vars(c).keys())
    with pytest.raises(LLMProviderError) as ei:
        make(FakeSDK(exc=RuntimeError("boom test-key-not-real"))).generate_json("s", "p", SCHEMA)
    assert "test-key" not in str(ei.value)


def test_model_configuration(monkeypatch):
    assert make(FakeSDK()).model == DEFAULT_MODEL
    assert make(FakeSDK(), model="gemini-custom").model == "gemini-custom"
    monkeypatch.setenv("INTENT2DATA_LLM_MODEL", "gemini-from-env")
    assert make(FakeSDK()).model == "gemini-from-env"
    sdk = FakeSDK(fake_response())
    make(sdk, model="gemini-x").generate_json("s", "p", SCHEMA)
    assert sdk.models.calls[0]["model"] == "gemini-x"


def test_timeout_configuration(monkeypatch):
    assert make(FakeSDK()).timeout_s == DEFAULT_TIMEOUT_S
    assert make(FakeSDK(), timeout_s=12.5).timeout_s == 12.5
    monkeypatch.setenv("INTENT2DATA_LLM_TIMEOUT_S", "7")
    assert make(FakeSDK()).timeout_s == 7.0
    monkeypatch.setenv("INTENT2DATA_LLM_TIMEOUT_S", "not-a-number")
    assert make(FakeSDK()).timeout_s == DEFAULT_TIMEOUT_S
    with pytest.raises(LLMConfigError):
        make(FakeSDK(), timeout_s=0)


def test_timeout_is_passed_to_client_factory_in_ms_and_construction_is_lazy():
    seen = {}

    def factory(api_key, timeout_s):
        seen["timeout_s"] = timeout_s
        seen["key_len"] = len(api_key)
        return FakeSDK(fake_response())

    c = GeminiClient(api_key="k1", timeout_s=3, client_factory=factory)
    assert seen == {}                       # nothing built at construction
    c.generate_json("s", "p", SCHEMA)
    assert seen == {"timeout_s": 3.0, "key_len": 2}


# ---- successful structured response --------------------------------------------

def test_successful_structured_response_and_token_metadata():
    sdk = FakeSDK(fake_response('{"selections": [{"column_name": "JC030"}]}', 4321, 55))
    resp = make(sdk, model="gemini-t").generate_json("SYS", "PROMPT", SCHEMA)
    assert isinstance(resp, LLMResponse)
    assert json.loads(resp.text)["selections"][0]["column_name"] == "JC030"
    assert (resp.input_tokens, resp.output_tokens, resp.model) == (4321, 55, "gemini-t")
    assert resp.latency_s is not None and resp.latency_s >= 0
    call = sdk.models.calls[0]
    assert call["contents"] == "PROMPT"
    cfg = call["config"]
    # real SDK config object or dict fallback; both must carry the JSON-mode settings
    get = (lambda k: getattr(cfg, k, None)) if not isinstance(cfg, dict) else cfg.get
    assert get("system_instruction") == "SYS"
    assert get("temperature") == 0.0
    assert get("response_mime_type") == "application/json"
    assert (get("response_json_schema") or get("response_schema")) == SCHEMA


def test_one_request_per_call_no_retry():
    sdk = FakeSDK(exc=RuntimeError("503 UNAVAILABLE overloaded"))
    c = make(sdk)
    with pytest.raises(LLMProviderError):
        c.generate_json("s", "p", SCHEMA)
    assert len(sdk.models.calls) == 1 and c.calls == 1


# ---- malformed provider payloads -------------------------------------------------

def test_payload_without_text_becomes_empty_response_not_exception():
    class NoText:
        usage_metadata = SimpleNamespace(prompt_token_count=10, candidates_token_count=0)
        candidates = []

        @property
        def text(self):
            raise ValueError("no candidates")   # the SDK raises on blocked responses

    resp = make(FakeSDK(NoText())).generate_json("s", "p", SCHEMA)
    assert resp.text == "" and resp.input_tokens == 10 and resp.output_tokens == 0


def test_text_recovered_from_candidate_parts_when_text_is_none():
    part = SimpleNamespace(text='{"roles": {"exposure": "x"}}')
    cand = SimpleNamespace(content=SimpleNamespace(parts=[part]))
    resp = _to_response(SimpleNamespace(text=None, usage_metadata=None, candidates=[cand]), "m", 0.1)
    assert json.loads(resp.text)["roles"]["exposure"] == "x"
    assert resp.input_tokens is None and resp.output_tokens is None


@pytest.mark.parametrize("payload", [None, 42, "just a string", object()])
def test_completely_foreign_payloads_do_not_crash(payload):
    resp = _to_response(payload, "m", 0.0)
    assert resp.text == "" and resp.input_tokens is None


def test_bogus_usage_metadata_is_ignored():
    usage = SimpleNamespace(prompt_token_count="lots", candidates_token_count=True)
    resp = _to_response(SimpleNamespace(text="{}", usage_metadata=usage), "m", 0.0)
    assert resp.input_tokens is None and resp.output_tokens is None


# ---- provider exception mapping ------------------------------------------------------

class FakeAPIError(Exception):
    def __init__(self, code, status="", message=""):
        super().__init__(f"{code} {status}. {message}")
        self.code, self.status, self.message = code, status, message


@pytest.mark.parametrize("exc, kind, retryable, status", [
    (FakeAPIError(429, "RESOURCE_EXHAUSTED", "Quota exceeded for metric: generate_content_free_tier_requests, limit: 20 per day"), "quota", False, 429),
    (FakeAPIError(429, "RESOURCE_EXHAUSTED", "Please retry in 9s"), "rate_limit", True, 429),
    (FakeAPIError(403, "PERMISSION_DENIED", "API key not valid"), "auth", False, 403),
    (FakeAPIError(400, "INVALID_ARGUMENT", "schema invalid"), "bad_request", False, 400),
    (FakeAPIError(503, "UNAVAILABLE", "The model is overloaded"), "unavailable", True, 503),
    (FakeAPIError(500, "INTERNAL", ""), "unavailable", True, 500),
    (TimeoutError("read timed out"), "timeout", True, 504),
    (ConnectionError("connection refused"), "unavailable", True, None),
    (ValueError("something odd"), "unknown", False, None),
])
def test_exception_mapping(exc, kind, retryable, status):
    mapped = _map_exception(exc)
    assert (mapped.kind, mapped.retryable, mapped.status_code) == (kind, retryable, status)


def test_provider_exception_is_raised_as_runtime_error_without_payload():
    sdk = FakeSDK(exc=FakeAPIError(429, "RESOURCE_EXHAUSTED", "limit: 20 per day; secret-payload-details"))
    with pytest.raises(LLMProviderError) as ei:
        make(sdk).generate_json("s", "p", SCHEMA)
    assert ei.value.kind == "quota" and ei.value.retryable is False
    assert "secret-payload-details" not in str(ei.value)
    assert isinstance(ei.value.__cause__, FakeAPIError)


# ---- factory + orchestration semantics -----------------------------------------------

def test_factory_wiring(monkeypatch):
    from app.llm.client import StaticLLMClient
    from app.llm.offline import OfflineLexicalLLMClient
    assert isinstance(build_llm_client("offline"), OfflineLexicalLLMClient)
    assert isinstance(build_llm_client(""), OfflineLexicalLLMClient)       # default is offline
    assert isinstance(build_llm_client("static"), StaticLLMClient)
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    with pytest.raises(LLMConfigError):
        build_llm_client("gemini")                                         # no key -> config error, no network
    monkeypatch.setenv(API_KEY_ENV, "fake-key")
    c = build_llm_client("gemini", model="gemini-cfg")
    assert isinstance(c, GeminiClient) and c.model == "gemini-cfg" and c._client is None   # still lazy, no SDK client built
    with pytest.raises(ProviderNotAvailable):
        build_llm_client("openai")


def test_runtime_degrades_safely_when_gemini_misconfigured(monkeypatch):
    from app.runtime import load_runtime
    from tests.conftest import make_settings
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    state = load_runtime(make_settings(llm_provider="gemini"))
    assert not state.ready and "GEMINI_API_KEY" in state.index_error


def test_orchestrator_maps_provider_error_semantics(make_client):
    from app.main import REQUEST_ID_HEADER
    from tests.conftest import intent_json

    class QuotaThenOK:
        def __init__(self):
            self.n = 0

        def generate_json(self, system, prompt, schema):
            self.n += 1
            if self.n == 1:
                raise LLMProviderError("quota", "provider daily quota exhausted", retryable=False, status_code=429)
            return LLMResponse(text=intent_json(exposure="lung disease"), model="fake")

    client = make_client(llm=QuotaThenOK())
    r = client.post("/v1/analyze", json={"question": "Is lung disease related to depression?"}, headers={REQUEST_ID_HEADER: "q-1"})
    assert r.status_code == 422                       # non-retryable provider failure at intent
    assert r.json()["error"] == "LLM provider failure (quota)" and r.json()["retryable"] is False

    class RateLimited:
        def generate_json(self, system, prompt, schema):
            raise LLMProviderError("rate_limit", "provider rate limit", retryable=True, status_code=429)

    r = make_client(llm=RateLimited()).post("/v1/analyze", json={"question": "Is lung disease related to depression?"})
    assert r.status_code == 502 and r.json()["retryable"] is True and r.json()["error"] == "LLM provider failure (rate_limit)"


def test_sdk_not_imported_by_runtime_import():
    for mod in list(sys.modules):
        if mod.startswith("google.genai"):
            del sys.modules[mod]
    import importlib
    import app.main, app.llm.gemini, app.llm.factory  # noqa: F401
    importlib.reload(app.llm.gemini)
    assert not any(m.startswith("google.genai") for m in sys.modules)
