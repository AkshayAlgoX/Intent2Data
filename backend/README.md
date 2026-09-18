# Intent2Data Backend

FastAPI runtime for `POST /v1/analyze`: research question → intent roles → module-first retrieval → cross-wave family expansion → per-role LLM selection → deterministic grounding validation → contract v1 response.

## Local Execution

```bash
# Setup virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# Pre-build index cache (optional: pre-build the 7 MB index cache in ≈2 s)
PYTHONPATH=backend python backend/scripts/build_index.py

# Run pytest suite
PYTHONPATH=backend pytest backend/tests

# Run local development server
PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Without any configuration the server uses the **offline deterministic stand-in** (`llm.live = false` in every response). It exercises the pipeline as software; it says nothing about model quality [LIVE RESULT: none].

## Docker Containerization

The image contains the application code, pinned runtime dependencies (including the Gemini SDK) and the **7 MB runtime index artifact**. The raw 261 MB metadata is never baked in, so **the index must be built before the image**; the build fails at the `COPY` step if it is missing.

### Build Image
```bash
venv/bin/python backend/scripts/build_index.py        # produces backend/.cache/runtime_index.json.gz (≈2 s)
docker build -t intent2data-backend:latest .
```

### Run Container
```bash
docker run -d --name intent2data-api -p 8000:8000 intent2data-backend:latest                     # offline stand-in
docker run -d -p 8000:8000 -e INTENT2DATA_LLM_PROVIDER=gemini -e GEMINI_API_KEY=... \
           -e INTENT2DATA_CORS_ORIGINS=https://your-frontend.example intent2data-backend:latest   # live provider, restricted CORS
```

The container sets `INTENT2DATA_REQUIRE_INDEX=1`: if the artifact is missing or corrupt the process logs a `CRITICAL` line naming the expected path and exits non-zero instead of serving 503s. To provision the artifact externally (volume / object store) instead of baking it, mount it and point `INTENT2DATA_INDEX_CACHE` at it, and drop the `COPY backend/.cache/...` line. `HEALTHCHECK` polls `/health` and reports unhealthy unless `ready` is true.

Dependencies: `requirements.txt` = pinned runtime deps (shipped); `requirements-dev.txt` = `pytest`/`httpx` for the test suite.

## Verification & API Testing

### Health Check (`/health`)
```bash
curl -s http://localhost:8000/health
# Expected: {"status":"ok", ...}
```

### Analysis Endpoint (`/v1/analyze`)
```bash
# Valid request
curl -s -X POST http://localhost:8000/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"question": "How does lifelong religious involvement shape physical functioning in later life?"}'

# Invalid request (missing required field)
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{}'
# Expected: 422
```

## Configuration (environment)

| Variable | Default | Purpose |
|---|---|---|
| `INTENT2DATA_METADATA_PATH` | `../benchmark/HRS_metadata/metadata.jsonl` (relative to the workspace) | raw codebook JSONL, read once at startup |
| `INTENT2DATA_INDEX_CACHE` | `backend/.cache/runtime_index.json.gz` | compact index cache; rebuilt automatically if missing/corrupt |
| `INTENT2DATA_BUILD_INDEX_ON_STARTUP` | `1` | `0` starts the API without an index (`/v1/analyze` → 503) |
| `INTENT2DATA_LLM_PROVIDER` | `offline` | `offline` (deterministic stand-in), `static` (scripted, tests), `gemini` (live adapter `app/llm/gemini.py`; used **only** when named explicitly). |
| `INTENT2DATA_LLM_MODEL` | adapter default (`gemini-3.6-flash` for Gemini) | model name passed to the provider adapter |
| `INTENT2DATA_LLM_TIMEOUT_S` | `60` | per-request provider timeout (seconds); the adapter makes exactly one request per call and never retries |
| `INTENT2DATA_LLM_MAX_RETRIES` | `1` | orchestrator-owned retry budget per call; only failures the adapter marks retryable (rate limit, timeout, unavailable) are retried — daily-quota and auth failures never are |
| `INTENT2DATA_LLM_RETRY_BACKOFF_S` | `0.5` | base delay before a retry (× attempt number); `0` disables the wait |
| `GEMINI_API_KEY` | — | required when `INTENT2DATA_LLM_PROVIDER=gemini`; read from the environment only, never logged. If missing, the runtime starts **degraded** (`/health` reports it, `/v1/analyze` → 503) rather than falling back to another provider. |
| `INTENT2DATA_MODULE_TOP_K` | `5` | modules retrieved per role (the offline-validated setting) |
| `INTENT2DATA_MAX_CANDIDATES_PER_CALL` | `2000` | hard cap on candidate lines per LLM call; overflow is reported as `candidates_truncated` |
| `INTENT2DATA_MAX_SELECTIONS_PER_ROLE` | `25` | overflow reported in `rejected.over_limit` |
| `INTENT2DATA_CORS_ORIGINS` | `*` | comma-separated allowed origins. `*` is for the demo (no cookies/credentials are used) and logs a warning at startup; set an explicit list in production. |
| `INTENT2DATA_REQUIRE_INDEX` | `0` (`1` in the container) | `1` makes a missing/corrupt index a fatal startup error instead of a degraded server |
| `INTENT2DATA_MAX_REQUEST_BYTES` | `65536` | request bodies above this (declared or streamed) are rejected with `413` before parsing; unknown JSON fields are rejected with `422` |

## Layout

```
app/main.py            HTTP surface: validation, request ids, CORS, error envelope, lifespan
app/settings.py        env → Settings
app/runtime.py         process state (index + LLM client), built once in lifespan
app/retrieval/         compact index (index.py), BM25 (bm25.py), cross-wave families (families.py),
                       role-aware candidate construction (candidates.py)
app/llm/               LLMClient protocol, StaticLLMClient, offline stand-in, Gemini adapter (only SDK import), factory, defensive parsing
app/pipeline/          contract models, prompts, deterministic validation, orchestrator
scripts/build_index.py offline cache build;  scripts/bench_runtime.py  timings/memory/candidate volumes
tests/                 run `pytest -q backend` from the repo root or `pytest -q` here; network is disabled for every test
```

## Guardrails (enforced by tests)
* `backend/app` never references the benchmark CSV, gold labels, `allowed_years`, `expanded_intents`, evaluation scripts, `Methods/`, provider SDKs, or the canonical demo variable codes (`tests/test_no_benchmark_leakage.py`).
* Model output is untrusted: only codes that were in the candidate set shown to the model are forwarded; everything else is listed under `rejected`.
* No test reads the real metadata or the network; fixtures use a 22-variable synthetic catalog.

## Measured on the real catalog (offline stand-in, this machine) — [MEASURED OFFLINE], engineering timings only, no quality metric
* index build from 261 MB JSONL: 1.74 s → 7.1 MB gzip cache; warm load 0.83 s; RSS after load ≈300 MB
* request wall time ≈100 ms (retrieval ≈10 ms; the rest is the stand-in's lexical scoring)
* candidates per role at top-5 modules: 350–2,000+ (cap hit on 3 of 6 roles across the 3 canonical questions)
