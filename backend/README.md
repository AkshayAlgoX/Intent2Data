# Intent2Data Backend

FastAPI runtime for `POST /v1/analyze`: research question → intent roles → module-first retrieval → cross-wave family expansion → per-role LLM selection → deterministic grounding validation → contract v1 response.

## Run

```bash
cd intent2data
python -m venv venv && venv/bin/pip install -r backend/requirements.txt
venv/bin/python backend/scripts/build_index.py        # optional: pre-build the 7 MB index cache (≈2 s)
cd backend && ../venv/bin/uvicorn app.main:app --port 8000
curl -s localhost:8000/health
curl -s -X POST localhost:8000/v1/analyze -H 'content-type: application/json' \
     -d '{"question":"How does lifelong religious involvement shape physical functioning in later life?"}'
```

Without any configuration the server uses the **offline deterministic stand-in** (`llm.live = false` in every response). It exercises the pipeline as software; it says nothing about model quality [LIVE RESULT: none].

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
| `INTENT2DATA_CORS_ORIGINS` | `*` | comma-separated allowed origins |

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
