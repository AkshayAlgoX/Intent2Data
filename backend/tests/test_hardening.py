"""Regression tests for the hardening pass: error sanitisation, request-size
defence, contract-strict request model, CORS configuration, fail-fast index,
atomic cache writes, bounded call retention, coverage-signal correctness."""

import importlib
import json
import re
import threading
from pathlib import Path

import pytest

from app.llm.client import CALL_HISTORY, StaticLLMClient
from app.llm.offline import OfflineLexicalLLMClient
from app.main import REQUEST_ID_HEADER, app
from app.retrieval.index import RuntimeIndex
from app.retrieval.text import concept_terms
from app.runtime import RuntimeNotReady, load_runtime
from tests.conftest import intent_json, make_settings, selection_json

REPO = Path(__file__).resolve().parents[2]
DEFAULT_LIMIT = 64 * 1024


# ---- 3. validation error leakage --------------------------------------------------

def test_validation_errors_do_not_echo_input(client):
    marker = "SECRET-MARKER-" + "x" * 300
    r = client.post("/v1/analyze", json={"question": marker + "y" * 2000})   # too long -> 422
    body = r.json()
    assert r.status_code == 422 and marker not in r.text
    for item in body["detail"]:
        assert set(item) <= {"loc", "msg", "type"}


def test_oversize_value_is_not_echoed(client):
    r = client.post("/v1/analyze", json={"question": "y" * 2001})
    assert r.status_code == 422 and "y" * 100 not in r.text


# ---- 7. request-body abuse + contract strictness --------------------------------------

def test_unknown_fields_rejected_per_contract(client):
    r = client.post("/v1/analyze", json={"question": "Is lung disease related to depression?", "padding": "z" * 100})
    assert r.status_code == 422
    assert any("padding" in str(d.get("loc")) for d in r.json()["detail"])
    assert "zzzz" not in r.text


def test_body_over_limit_rejected_413_with_content_length(make_client):
    client = make_client()
    app.state.max_request_bytes = 4096
    try:
        big = json.dumps({"question": "q" * 10_000})
        r = client.post("/v1/analyze", content=big.encode(),
                        headers={"content-type": "application/json", REQUEST_ID_HEADER: "big-1"})
        assert r.status_code == 413
        assert r.json() == {"error": "Request body too large.", "request_id": "big-1", "max_bytes": 4096}
        assert r.headers[REQUEST_ID_HEADER] == "big-1"
    finally:
        app.state.max_request_bytes = DEFAULT_LIMIT


def test_body_over_limit_rejected_when_chunked_without_content_length(make_client):
    client = make_client()
    app.state.max_request_bytes = 4096
    try:
        def chunks():
            yield b'{"question": "'
            for _ in range(20):
                yield b"q" * 500
            yield b'"}'
        r = client.post("/v1/analyze", content=chunks(),
                        headers={"content-type": "application/json", "transfer-encoding": "chunked"})
        assert r.status_code == 413
    finally:
        app.state.max_request_bytes = DEFAULT_LIMIT


def test_normal_bodies_pass_the_limit(make_client):
    client = make_client(llm=StaticLLMClient([intent_json(exposure="lung disease"), selection_json("JC030")]))
    r = client.post("/v1/analyze", json={"question": "Is chronic lung disease associated with feeling depressed?"})
    assert r.status_code == 200
    assert client.get("/health").status_code == 200          # GET is never limited


# ---- 4. CORS configuration ----------------------------------------------------------------------

def test_cors_can_be_restricted_by_environment(monkeypatch):
    monkeypatch.setenv("INTENT2DATA_CORS_ORIGINS", "https://demo.example.org")
    monkeypatch.setenv("INTENT2DATA_BUILD_INDEX_ON_STARTUP", "0")
    import app.main as main_mod
    reloaded = importlib.reload(main_mod)
    try:
        from fastapi.testclient import TestClient
        with TestClient(reloaded.app) as c:
            allowed = c.options("/v1/analyze", headers={"Origin": "https://demo.example.org",
                                                        "Access-Control-Request-Method": "POST"})
            assert allowed.headers.get("access-control-allow-origin") == "https://demo.example.org"
            denied = c.options("/v1/analyze", headers={"Origin": "https://evil.example.net",
                                                       "Access-Control-Request-Method": "POST"})
            assert denied.headers.get("access-control-allow-origin") is None
    finally:
        monkeypatch.delenv("INTENT2DATA_CORS_ORIGINS")
        importlib.reload(main_mod)


# ---- 2. fail-fast when the index artifact is missing --------------------------------------------

def test_require_index_makes_missing_artifact_fatal(tmp_path):
    settings = make_settings(build_index_on_startup=True, metadata_path=tmp_path / "missing.jsonl",
                             index_cache_path=tmp_path / "missing.json.gz", require_index=True)
    with pytest.raises(RuntimeNotReady) as ei:
        load_runtime(settings)
    assert "INTENT2DATA_REQUIRE_INDEX=1" in str(ei.value) and "build_index.py" in str(ei.value)


def test_without_require_index_runtime_degrades_instead(tmp_path):
    settings = make_settings(build_index_on_startup=True, metadata_path=tmp_path / "missing.jsonl",
                             index_cache_path=tmp_path / "missing.json.gz", require_index=False)
    state = load_runtime(settings)
    assert not state.ready and "metadata not found" in state.index_error


def test_cache_alone_is_sufficient_no_metadata_needed(tmp_path, index):
    cache = tmp_path / "idx.json.gz"
    index.save(cache)
    settings = make_settings(build_index_on_startup=True, metadata_path=tmp_path / "missing.jsonl",
                             index_cache_path=cache, require_index=True)
    state = load_runtime(settings)
    assert state.ready and state.index.stats() == index.stats() and "load_cache_s" in state.index_timings


# ---- 5. atomic cache write, unique temp names -------------------------------------------------------

def test_concurrent_saves_do_not_collide_and_leave_no_temp_files(tmp_path, index):
    path = tmp_path / "shared.json.gz"
    errors = []

    def worker():
        try:
            index.save(path)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert RuntimeIndex.load(path).stats() == index.stats()
    assert [p.name for p in tmp_path.iterdir()] == ["shared.json.gz"]      # no *.tmp leftovers


def test_stray_temp_file_is_never_read(tmp_path, index):
    path = tmp_path / "idx.json.gz"
    index.save(path)
    (tmp_path / "idx.json.gz.999.deadbeef.tmp").write_bytes(b"garbage")   # interrupted writer
    assert RuntimeIndex.load(path).stats() == index.stats()


# ---- 6. bounded call retention ---------------------------------------------------------------------------

def test_offline_client_keeps_no_prompt_text_and_bounded_history():
    c = OfflineLexicalLLMClient()
    prompt = ("TASK: select\nQUESTION:\nq\n\nROLE:\nexposure\n\nRESEARCH CONCEPT:\nlung\n\nCANDIDATES:\n"
              + "\n".join(f"C{i} | LUNG {i} | text" for i in range(2000)))
    for _ in range(CALL_HISTORY * 3):
        c.generate_json("s", prompt, {})
    assert c.call_count == CALL_HISTORY * 3
    assert len(c.calls) == CALL_HISTORY
    assert all("prompt" not in entry for entry in c.calls)
    assert c.calls[-1] == {"task": "TASK: select", "prompt_chars": len(prompt)}
    verbose = OfflineLexicalLLMClient(history=2)
    for _ in range(3):
        verbose.generate_json("s", prompt, {})
    assert len(verbose.calls) == 2 and "prompt" in verbose.calls[-1]


def test_static_client_history_is_bounded():
    c = StaticLLMClient(history=3)
    for i in range(10):
        c.generate_json("s", f"p{i}", {})
    assert c.call_count == 10 and [x["prompt"] for x in c.calls] == ["p7", "p8", "p9"]


# ---- 8/9. coverage signal: numeric/scientific tokens and empty denominators ------------------------

@pytest.mark.parametrize("text, expected", [
    ("PM2.5 exposure", [("pm2.5", ["pm2"]), ("exposure", ["exposure"])]),
    ("COVID-19 infection", [("covid-19", ["covid"]), ("infection", ["infection"])]),
    ("Type 2 diabetes", [("type", ["type"]), ("diabetes", ["diabetes"])]),
    ("retirement in 2020", [("retirement", ["retirement"])]),
    ("HbA1c levels", [("hba1c", ["hba1c"]), ("levels", ["levels"])]),
    ("to of in for that", []),
])
def test_concept_terms_surface_forms(text, expected):
    assert concept_terms(text) == expected


def test_coverage_reports_surface_form_and_zero_for_no_terms(make_client):
    client = make_client(llm=StaticLLMClient([
        intent_json(exposure="PM2.5 lung disease", outcome="to of in for that"),
        '{"selections": []}', '{"selections": []}',
    ]))
    body = client.post("/v1/analyze", json={"question": "Does PM2.5 drive lung disease?"}).json()
    exp, out = body["roles"]
    assert exp["intent_coverage"] == {"terms": ["pm2.5", "lung", "disease"], "unmatched": ["pm2.5"], "coverage": 0.6667}
    assert out["intent_coverage"] == {"terms": [], "unmatched": [], "coverage": 0.0}
    codes = {(l["code"], l["role"]) for l in body["limitations"]}
    assert ("concept_terms_unmatched", "exposure") in codes and ("no_concept_terms", "outcome") in codes


# ---- 1. deployment audit (static; Docker may be unavailable in CI) -------------------------------------

def test_runtime_requirements_declare_pinned_gemini_sdk():
    req = (REPO / "backend" / "requirements.txt").read_text()
    pins = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s#]+)", req, re.M))
    assert {"fastapi", "uvicorn", "pydantic", "google-genai"} <= set(pins), pins
    assert "pytest" not in pins                                          # test deps are not shipped
    dev = (REPO / "backend" / "requirements-dev.txt").read_text()
    assert "-r requirements.txt" in dev and "pytest==" in dev and "httpx==" in dev


def test_dockerfile_bakes_index_and_fails_fast():
    df = (REPO / "Dockerfile").read_text()
    assert "COPY backend/.cache/runtime_index.json.gz /app/.cache/runtime_index.json.gz" in df
    assert "INTENT2DATA_REQUIRE_INDEX=1" in df and "INTENT2DATA_INDEX_CACHE=/app/.cache/runtime_index.json.gz" in df
    assert not any("metadata.jsonl" in l for l in df.splitlines() if l.startswith("COPY"))   # raw metadata never baked
    assert "HEALTHCHECK" in df
    ignore = (REPO / ".dockerignore").read_text()
    assert "backend/tests/" in ignore and "backend/.cache/*.tmp*" in ignore
