from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_analyze_valid():
    response = client.post("/v1/analyze", json={"question": "Test question?"})
    assert response.status_code == 200
    assert response.json() == {
        "status": "stub",
        "message": "Intent2Data backend skeleton is running"
    }

def test_analyze_invalid():
    response = client.post("/v1/analyze", json={})
    assert response.status_code == 422
