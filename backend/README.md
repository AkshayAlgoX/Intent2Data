# Intent2Data Backend

FastAPI implementation of the Intent2Data service.

## Local Execution

```bash
# Setup virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# Run pytest suite
PYTHONPATH=backend pytest backend/tests

# Run local development server
PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Docker Containerization

### Build Image
```bash
docker build -t intent2data-backend:latest .
```

### Run Container
```bash
docker run -d --name intent2data-api -p 8000:8000 intent2data-backend:latest
```

## Verification & API Testing

### Health Check (`/health`)
```bash
curl -s http://localhost:8000/health
# Expected: {"status":"ok"}
```

### Analysis Endpoint (`/v1/analyze`)
```bash
# Valid request
curl -s -X POST http://localhost:8000/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"question": "How does smoking affect survival in later life?"}'
# Expected: {"status":"stub","message":"Intent2Data backend skeleton is running"}

# Invalid request (missing required field)
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{}'
# Expected: 422
```
