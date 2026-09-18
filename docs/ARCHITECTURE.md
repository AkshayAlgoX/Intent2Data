# Architecture (runtime, as implemented)

```
POST /v1/analyze {question}
  │  validation (3..2000 chars, non-blank) · X-Request-ID · CORS
  ▼
1. Intent            LLMClient.generate_json → parse_intent_output
  │                  roles ⊆ {exposure, outcome, population, covariates, secondary, temporal, proxies}
  ▼
2. Retrieval         per role: BM25 over 932 module docs (product_key::section = wave × section) → top-k modules
  │                  (deterministic; no LLM)
  ▼
3. Structural        every variable in the retrieved modules + every cross-wave sibling of those
   expansion         variables (family = same item across biennial waves) → ordered, capped candidate set
  │                  (deterministic; no temporal filter — any wave scope must come from the request's own intent)
  ▼
4. Context filter    per role: LLMClient.generate_json(question, role, intent, "code | label | question_text" lines)
  │                  → parse_selection_output → in-context / out-of-context / hallucinated
  ▼
5. Validation        deterministic: only in-context codes survive; evidence checked as a verbatim codebook span;
  │                  family waves attached; limitations derived (empty retrieval, unmatched concept terms, no selection, truncation, …)
  │                  each role also carries intent_coverage (terms absent from the catalog vocabulary) and an
  │                  uncalibrated retrieval strength (top BM25 score / saturation bound) for display only
  ▼
contract v1 response  (contracts/v1/README.md)
```

**Process model.** The compact index (122,296 variables · 932 modules · 94,221 families; 7 MB cached) and the
LLM client are built once in the FastAPI lifespan. The 261 MB raw metadata is never read in the request path.

**Provider boundary.** `app/pipeline` depends only on `app.llm.client.LLMClient` (`generate_json(system, prompt, schema) -> LLMResponse`).
`offline` (deterministic lexical stand-in, the default), `static` (scripted, for tests) and `gemini`
(`app/llm/gemini.py`, the only module that imports the google-genai SDK, lazily) are the clients in this build.
Adapters make one request per call, map provider failures to `LLMProviderError(kind, retryable)` and never retry;
the orchestrator owns retry/partial-result policy: one retry (configurable) on retryable failures only, then non-retryable intent failure → 422, exhausted retryable → 502, role failure → `partial`.
A live provider is used only when `INTENT2DATA_LLM_PROVIDER` names it; a misconfigured provider degrades the runtime to 503 rather than silently substituting another client.

**Failure semantics.** Provider failure on the intent call → `502 retryable`. Unparseable intent → `422`.
Provider failure or unparseable output on a role call → that role `failed`, response `partial`, other roles intact.
Index not loaded → `503`. Nothing from a provider error body reaches the client.

**What this build does and does not show.** It exercises the offline-validated retrieval design
(module top-5 → wave-family expansion; 343/621 gold reachable on the 20-question population [STRUCTURAL REACHABILITY])
on the real codebook, through every pipeline stage. With `llm.live = false` the selections come from a
lexical stand-in; the pipeline runs end to end as *software*, but **end-to-end selection accuracy is unmeasured**
[LIVE RESULT: none] (see `docs/SCIENTIFIC_CLAIMS.md` §3 and `evaluation/results/EXP24_FINAL_REPORT.md`).

**Retrieval design decisions (verified 2026-09-18).**
* *Module documents are titles + variable labels only; `question_text` is deliberately excluded.* This is the representation the offline reachability numbers were measured on. Adding question text would multiply module-document text 4.4× (4.1 M → 22 M chars; even a distinct-token vocabulary adds +54 %), change BM25 statistics and invalidate every measured retrieval figure. The demonstrated blind spot is not "missing vocabulary" but *intent phrasing*: the same concept ranks 1st or >300th depending on whether the intent uses codebook words. The runtime therefore exposes `intent_coverage` (which intent terms exist in the module vocabulary at all) instead of widening the index.
* *Tokenisation splits on non-alphanumerics* (`PM2.5` → `pm2`, `5`; `COVID-19` → `covid`, `19`), matching the validated experiments. Retrieval still uses every token; the coverage report drops pure numbers and shows scientific compounds in their surface form (`pm2.5`, `covid-19`) so it is readable without changing what is indexed.
* *Wave families are HRS-specific* (`WAVE_PREFIX_YEAR`, `core`/`exit`/`cognition` patterns); other records become singleton families and simply get no expansion.

Evaluation scripts (`evaluation/`) are the conceptual source for stages 2–3 and must stay outside the runtime;
`backend/tests/test_no_benchmark_leakage.py` enforces that.
