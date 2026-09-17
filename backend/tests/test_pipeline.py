"""End-to-end pipeline tests through the real /v1/analyze route with a scripted
StaticLLMClient. Nothing here touches a network or the real metadata."""

import json

import pytest

from app.llm.client import LLMProviderError, LLMResponse, StaticLLMClient
from app.llm.offline import OfflineLexicalLLMClient
from app.main import REQUEST_ID_HEADER
from tests.conftest import intent_json, selection_json

Q = "Is chronic lung disease associated with feeling depressed?"


def _run(make_client, responses, **settings):
    llm = StaticLLMClient(responses=list(responses))
    client = make_client(llm=llm, **settings)
    r = client.post("/v1/analyze", json={"question": Q}, headers={REQUEST_ID_HEADER: "req-e2e"})
    return r, llm


def test_valid_end_to_end_request(make_client):
    r, llm = _run(make_client, [
        intent_json(exposure="chronic lung disease", outcome="felt depressed past week"),
        selection_json("JC030", "KC030", evidence={"JC030": "LUNG DISEASE", "KC030": "chronic lung disease"}),
        selection_json("LD110", evidence={"LD110": "FELT DEPRESSED"}),
    ])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["contract"] == "v1"
    assert body["status"] == "ok"
    assert body["request_id"] == "req-e2e"
    assert body["question"] == Q
    assert [x["role"] for x in body["intent"]["roles"]] == ["exposure", "outcome"]
    assert [x["status"] for x in body["roles"]] == ["ok", "ok"]
    exposure = body["roles"][0]
    assert exposure["modules"][0]["module_id"].endswith("::C")
    assert exposure["candidates"] == {"retrieved": 6, "family_expanded": 3, "total": 9, "truncated": False}
    codes = [s["code"] for s in exposure["selections"]]
    assert codes == ["JC030", "KC030"]
    sel = exposure["selections"][0]
    assert sel["grounding"] == {"in_context": True, "evidence_grounded": True, "evidence_checked": True}
    assert sel["family_waves"] == ["2004", "2006", "2008"]
    assert sel["candidate_source"] in ("module", "family")
    assert [v["code"] for v in body["variables"]] == ["JC030", "KC030", "LD110"]
    assert body["llm"] == {"provider": "static", "model": "static", "live": False, "calls": 3, "failed_calls": 0, "retries": 0}
    assert set(body["stages"]) == {"intent", "retrieval", "filter", "validation"}
    assert body["index"]["variables"] == 22
    # the "not a real model" limitation is always present for non-live providers
    assert any(l["code"] == "offline_llm" for l in body["limitations"])
    # candidate lines reached the LLM with the compact representation
    assert "JC030 | LUNG DISEASE |" in llm.calls[1]["prompt"]
    assert llm.calls[1]["prompt"].startswith("TASK: select")


def test_no_stub_response_remains(client):
    r = client.post("/v1/analyze", json={"question": Q})
    assert "stub" not in r.text.lower()


def test_empty_retrieval_role_is_reported_not_fatal(make_client):
    r, _ = _run(make_client, [
        intent_json(exposure="quantum chromodynamics lattice", outcome="felt depressed"),
        selection_json("JD110", evidence={"JD110": "FELT DEPRESSED"}),   # only the outcome role calls the LLM
    ])
    body = r.json()
    assert r.status_code == 200 and body["status"] == "ok"
    exposure, outcome = body["roles"]
    assert exposure["status"] == "empty_retrieval" and exposure["modules"] == [] and exposure["selections"] == []
    assert outcome["status"] == "ok"
    assert body["llm"]["calls"] == 2
    assert any(l["code"] == "empty_retrieval" and l["role"] == "exposure" for l in body["limitations"])


def test_malformed_llm_selection_marks_role_failed_and_response_partial(make_client):
    r, _ = _run(make_client, [
        intent_json(exposure="lung disease", outcome="felt depressed"),
        "```json\n{\"selections\": [",                       # truncated output
        selection_json("KD110"),
    ])
    body = r.json()
    assert r.status_code == 200
    assert body["status"] == "partial"
    assert body["roles"][0]["status"] == "failed"
    assert "unparseable" in body["roles"][0]["error"]
    assert body["roles"][0]["rejected"]["parse_errors"]
    assert body["roles"][1]["status"] == "ok"


def test_duplicate_ids_are_collapsed(make_client):
    r, _ = _run(make_client, [
        intent_json(exposure="lung disease"),
        json.dumps({"selections": [{"column_name": "JC030"}, {"column_name": " jc030 "}, {"column_name": "JC030"}]}),
    ])
    body = r.json()
    assert [s["code"] for s in body["roles"][0]["selections"]] == ["JC030"]
    assert len(body["variables"]) == 1


def test_hallucinated_ids_are_dropped_and_surfaced(make_client):
    r, _ = _run(make_client, [
        intent_json(exposure="lung disease"),
        selection_json("JC030", "ZZ999", "MADEUP"),
    ])
    role = r.json()["roles"][0]
    assert [s["code"] for s in role["selections"]] == ["JC030"]
    assert role["rejected"]["hallucinated"] == ["ZZ999", "MADEUP"]
    assert any(l["code"] == "hallucinated_ids_dropped" for l in r.json()["limitations"])


def test_out_of_context_valid_ids_are_dropped_not_forwarded(make_client):
    # HHID is a real catalog variable but is never in a section-C candidate set.
    r, _ = _run(make_client, [
        intent_json(exposure="lung disease"),
        selection_json("HHID", "KC030"),
    ])
    role = r.json()["roles"][0]
    assert [s["code"] for s in role["selections"]] == ["KC030"]
    assert role["rejected"]["out_of_context"] == ["HHID"]
    assert role["rejected"]["hallucinated"] == []
    assert any(l["code"] == "ungrounded_ids_dropped" for l in r.json()["limitations"])


def test_evidence_not_verbatim_is_flagged_but_kept(make_client):
    r, _ = _run(make_client, [
        intent_json(exposure="lung disease"),
        selection_json("JC030", evidence={"JC030": "this text is not in the codebook"}),
    ])
    body = r.json()
    sel = body["roles"][0]["selections"][0]
    assert sel["grounding"]["in_context"] is True
    assert sel["grounding"]["evidence_grounded"] is False
    assert any(l["code"] == "evidence_not_verbatim" for l in body["limitations"])


def test_empty_role_selection_is_no_selection(make_client):
    r, _ = _run(make_client, [
        intent_json(exposure="lung disease", outcome="   ", covariates=""),   # blank roles dropped
        '{"selections": []}',
    ])
    body = r.json()
    assert [x["role"] for x in body["intent"]["roles"]] == ["exposure"]
    assert body["roles"][0]["status"] == "no_selection"
    assert body["status"] == "ok"
    assert any(l["code"] == "no_grounded_selection" for l in body["limitations"])


def test_unknown_roles_dropped_with_warning(make_client):
    r, _ = _run(make_client, [
        json.dumps({"roles": {"exposure": "lung disease", "mediator": "x", "primary outcome": "felt depressed"}}),
        '{"selections": []}', '{"selections": []}',
    ])
    body = r.json()
    assert [x["role"] for x in body["intent"]["roles"]] == ["exposure", "outcome"]
    assert any("mediator" in e for e in body["intent"]["errors"])


def test_intent_unparseable_returns_422_with_stage(make_client):
    r, _ = _run(make_client, ["totally not json"])
    assert r.status_code == 422
    body = r.json()
    assert body["stage"] == "intent" and body["retryable"] is False and body["request_id"] == "req-e2e"


def test_intent_with_no_roles_fails_cleanly(make_client):
    r, _ = _run(make_client, ['{"roles": {}}'])
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "failed" and body["roles"] == []
    assert any(l["code"] == "no_roles" for l in body["limitations"])


class _Flaky:
    """LLMClient that fails on chosen *attempt* indices (1-based, counting retries)."""

    def __init__(self, responses, fail_at, exc=None):
        self.responses = list(responses)
        self.fail_at = set(fail_at)
        self.exc = exc or ConnectionError("simulated provider outage 429")
        self.n = 0

    def generate_json(self, system, prompt, schema):
        self.n += 1
        if self.n in self.fail_at:
            raise self.exc
        return LLMResponse(text=self.responses.pop(0), model="flaky")


NON_RETRYABLE = LLMProviderError("quota", "provider daily quota exhausted", retryable=False, status_code=429)
RETRYABLE = LLMProviderError("rate_limit", "provider rate limit", retryable=True, status_code=429)


def test_provider_failure_at_intent_returns_502_after_retry_exhausted(make_client):
    llm = _Flaky([], fail_at={1, 2})                      # first attempt + the one retry both fail
    client = make_client(llm=llm)
    r = client.post("/v1/analyze", json={"question": Q}, headers={REQUEST_ID_HEADER: "req-fail"})
    assert r.status_code == 502
    body = r.json()
    assert body["retryable"] is True and body["stage"] == "intent" and body["request_id"] == "req-fail"
    assert "429" not in r.text          # provider error bodies never leak
    assert llm.n == 2                   # exactly one retry


def test_intent_retry_once_then_succeeds(make_client):
    llm = _Flaky([intent_json(exposure="lung disease"), selection_json("JC030")], fail_at={1})
    r = make_client(llm=llm).post("/v1/analyze", json={"question": Q})
    body = r.json()
    assert r.status_code == 200 and body["status"] == "ok"
    assert body["llm"] == {"provider": "static", "model": "flaky", "live": False, "calls": 2, "failed_calls": 1, "retries": 1}


def test_non_retryable_provider_failure_is_not_retried(make_client):
    llm = _Flaky([intent_json(exposure="lung disease", outcome="felt depressed"), selection_json("KD110")],
                 fail_at={2}, exc=NON_RETRYABLE)
    client = make_client(llm=llm)
    r = client.post("/v1/analyze", json={"question": Q})
    body = r.json()
    assert r.status_code == 200 and body["status"] == "partial"
    assert body["roles"][0]["status"] == "failed" and body["roles"][0]["error"] == "LLM provider failure (quota)"
    assert body["roles"][1]["status"] == "ok"
    assert body["llm"]["failed_calls"] == 1 and body["llm"]["calls"] == 2 and body["llm"]["retries"] == 0
    assert llm.n == 3                   # no extra attempt was made


def test_role_retry_once_then_succeeds(make_client):
    llm = _Flaky([intent_json(exposure="lung disease"), selection_json("JC030")], fail_at={2}, exc=RETRYABLE)
    r = make_client(llm=llm).post("/v1/analyze", json={"question": Q})
    body = r.json()
    assert body["status"] == "ok" and [s["code"] for s in body["roles"][0]["selections"]] == ["JC030"]
    assert body["llm"]["retries"] == 1 and body["llm"]["failed_calls"] == 1 and body["llm"]["calls"] == 2
    assert body["stages"]["filter"]["detail"]["retries"] == 1


def test_role_retry_exhausted_yields_partial(make_client):
    llm = _Flaky([intent_json(exposure="lung disease", outcome="felt depressed"), selection_json("KD110")],
                 fail_at={2, 3}, exc=RETRYABLE)
    body = make_client(llm=llm).post("/v1/analyze", json={"question": Q}).json()
    assert body["status"] == "partial"
    assert body["roles"][0]["status"] == "failed" and body["roles"][0]["error"] == "LLM provider failure (rate_limit)"
    assert body["roles"][1]["status"] == "ok"
    assert body["llm"] == {"provider": "static", "model": "flaky", "live": False, "calls": 2, "failed_calls": 2, "retries": 1}


def test_retries_can_be_disabled(make_client):
    llm = _Flaky([], fail_at={1}, exc=RETRYABLE)
    r = make_client(llm=llm, llm_max_retries=0).post("/v1/analyze", json={"question": Q})
    assert r.status_code == 502 and llm.n == 1


def test_retry_backoff_uses_configured_delay_via_injected_sleep(index):
    from app.pipeline.orchestrator import AnalyzePipeline, PipelineConfig
    slept = []
    llm = _Flaky([intent_json(exposure="lung disease"), selection_json("JC030")], fail_at={1, 3}, exc=RETRYABLE)
    pipe = AnalyzePipeline(index, llm, PipelineConfig(module_top_k=2, provider="static", max_retries=1, retry_backoff_s=0.25),
                           sleep=slept.append)
    resp = pipe.run(Q, "rid")
    assert resp.status == "ok" and resp.llm.retries == 2 and slept == [0.25, 0.25]


def test_request_id_propagates_header_and_body(make_client):
    r, _ = _run(make_client, [intent_json(exposure="lung disease"), '{"selections": []}'])
    assert r.headers[REQUEST_ID_HEADER] == "req-e2e" and r.json()["request_id"] == "req-e2e"
    client = make_client(llm=StaticLLMClient([intent_json(exposure="lung disease"), '{"selections": []}']))
    minted = client.post("/v1/analyze", json={"question": Q})
    assert minted.headers[REQUEST_ID_HEADER] == minted.json()["request_id"] and len(minted.json()["request_id"]) == 32


def test_max_selections_per_role_is_enforced(make_client):
    r, _ = _run(make_client, [intent_json(exposure="lung disease"), selection_json("JC030", "KC030", "LC030")],
                max_selections_per_role=2)
    role = r.json()["roles"][0]
    assert len(role["selections"]) == 2 and role["rejected"]["over_limit"] == 1


def test_runtime_not_ready_returns_503(make_client):
    client = make_client(ready=False)
    r = client.post("/v1/analyze", json={"question": Q})
    assert r.status_code == 503 and r.json()["error"] == "Runtime index not available."
    assert client.get("/health").json()["status"] == "degraded"


def test_complete_pipeline_with_offline_client_is_deterministic(make_client):
    client = make_client(llm=OfflineLexicalLLMClient(), llm_provider="offline")
    a = client.post("/v1/analyze", json={"question": Q}).json()
    b = client.post("/v1/analyze", json={"question": Q}).json()
    for body in (a, b):
        assert body["status"] == "ok"
        assert body["llm"]["provider"] == "offline" and body["llm"]["live"] is False
    roles = {r["role"]: r for r in a["roles"]}
    assert set(roles) == {"exposure", "outcome"}
    assert {s["code"] for s in roles["exposure"]["selections"]} >= {"JC030", "KC030", "LC030"}
    assert {s["code"] for s in roles["outcome"]["selections"]} >= {"JD110", "KD110", "LD110"}
    assert all(s["grounding"]["evidence_grounded"] for r in a["roles"] for s in r["selections"])
    strip = lambda body: {k: v for k, v in body.items() if k not in ("stages", "request_id")}
    assert strip(a) == strip(b)
