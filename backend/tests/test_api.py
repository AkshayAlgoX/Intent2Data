from app.main import QUESTION_MAX_CHARS, REQUEST_ID_HEADER, app
from tests.conftest import intent_json
from app.llm.client import StaticLLMClient


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok" and body["ready"] is True
    assert body["index"]["variables"] == 22


def test_version(client):
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {"version": app.version, "contract": "v1"}


def test_analyze_valid_uses_real_pipeline(make_client):
    client = make_client(llm=StaticLLMClient([intent_json(exposure="lung disease"), '{"selections": []}']))
    response = client.post("/v1/analyze", json={"question": "Test question?"})
    assert response.status_code == 200
    body = response.json()
    assert body["contract"] == "v1" and body["roles"][0]["role"] == "exposure"
    assert "stub" not in response.text


def test_analyze_invalid(client):
    response = client.post("/v1/analyze", json={})
    assert response.status_code == 422


def test_validation_error_matches_contract_shape(client):
    # contracts/v1/error_response.json promises a top-level "error" string.
    response = client.post("/v1/analyze", json={})
    body = response.json()
    assert body["error"] == "Invalid request parameters."
    assert isinstance(body["detail"], list)
    assert body["request_id"]


def test_blank_question_rejected(client):
    assert client.post("/v1/analyze", json={"question": "   "}).status_code == 422


def test_oversize_question_rejected(client):
    assert client.post("/v1/analyze", json={"question": "x" * (QUESTION_MAX_CHARS + 1)}).status_code == 422


def test_wrong_type_rejected(client):
    assert client.post("/v1/analyze", json={"question": ["not", "a", "string"]}).status_code == 422


def test_malformed_json_body_rejected(client):
    response = client.post("/v1/analyze", content=b"{not json", headers={"content-type": "application/json"})
    assert response.status_code == 422
    assert response.json()["error"]


def test_request_id_is_minted_and_echoed(client):
    minted = client.get("/health")
    assert minted.headers.get(REQUEST_ID_HEADER)
    echoed = client.get("/health", headers={REQUEST_ID_HEADER: "demo-123"})
    assert echoed.headers[REQUEST_ID_HEADER] == "demo-123"


def test_unhandled_exception_returns_opaque_500(client):
    @app.get("/__boom")
    def boom():
        raise RuntimeError("provider secret 429 body should never leak")

    response = client.get("/__boom", headers={REQUEST_ID_HEADER: "boom-1"})
    assert response.status_code == 500
    assert response.json() == {"error": "Internal server error.", "request_id": "boom-1"}
    assert "secret" not in response.text


def test_cors_preflight_allows_demo_frontend(client):
    response = client.options(
        "/v1/analyze",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin")
