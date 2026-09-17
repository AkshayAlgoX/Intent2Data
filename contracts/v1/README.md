# Contract v1 — `POST /v1/analyze`

Frozen shape. Changes are **additive only**; a removed or renamed field is v2.
`analyze_response.schema.json` is generated from `backend/app/pipeline/models.py`
(the code is the source of truth); `example_response.json` is a real run of the
pipeline on the synthetic test catalog with a scripted client.

## Request — `analyze.schema.json`
`{"question": string}` — 3..2000 chars, trimmed, non-blank. Anything else → `422`.

## Headers
`X-Request-ID` is echoed if supplied, minted otherwise; it is also in every body (`request_id`).

## Response — `analyze_response.schema.json`

| Field | Meaning |
|---|---|
| `contract` | always `"v1"` |
| `status` | `ok` (every role ran), `partial` (≥1 role failed, ≥1 succeeded), `failed` |
| `intent.roles[]` | `{role, intent}` in canonical order: exposure, outcome, population, covariates, secondary, temporal, proxies. Only roles the question implies. |
| `intent.source` / `intent.errors` | which client produced it; parse warnings (e.g. unknown roles dropped) |
| `roles[]` | one entry per intent role, see below |
| `variables[]` | de-duplicated union of grounded selections across roles, with the roles each serves |
| `limitations[]` | `{code, role?, message}` — what the pipeline could **not** establish (see codes below) |
| `stages` | per-stage wall time in ms + small detail dict (`intent`, `retrieval`, `filter`, `validation`) |
| `llm` | `{provider, model, live, calls, failed_calls, retries}` (`retries` added additively: retry attempts the orchestrator made). **`live=false` means selections came from the offline deterministic stand-in and say nothing about model quality.** |
| `index` | `{variables, modules, families, fingerprint}` of the codebook index used |

### `roles[]`
| Field | Meaning |
|---|---|
| `status` | `ok`, `no_selection` (candidates shown, none chosen), `empty_retrieval` (no module matched), `failed` (provider error or unparseable output; see `error`) |
| `modules[]` | retrieved codebook modules `{module_id, rank, score, product_key, product_title, section, section_title, variable_count}` — `module_id` is `product_key::section`, i.e. one survey wave × one section |
| `candidates` | `{retrieved, family_expanded, total, truncated}` — variables inside the retrieved modules, cross-wave siblings added structurally, what the LLM was shown, whether the per-call cap cut it |
| `selections[]` | grounded variables only (see below) |
| `rejected` | `{out_of_context, hallucinated, parse_errors, over_limit}` — everything the model returned that was **not** forwarded |
| `intent_coverage` | `{terms, unmatched, coverage}` — which of the intent's concept terms occur anywhere in the module vocabulary (titles + labels). Deterministic, model-independent. An unmatched term could not have influenced retrieval. (additive) |
| `retrieval` | `{top_score, max_possible_score, strength}` — best module's BM25 score and its saturation bound for this intent; `strength` = ratio in 0..1. **Descriptive and uncalibrated**: good and bad retrievals overlap around 0.2–0.3 on HRS, so no threshold or limitation is derived from it; compare roles within one response only. (additive) |

### `selections[]`
`code, label, module_id, section, year, family_id, family_waves[], candidate_source, reason, evidence, grounding`

* `candidate_source`: `module` (was in a retrieved module) or `family` (added by cross-wave expansion)
* `family_waves`: years of every sibling of this item, so a UI can render the wave grid
* `grounding.in_context`: always `true` here — anything not in the candidate set is in `rejected`
* `grounding.evidence_grounded`: the model's `evidence` is a verbatim span of that candidate's codebook line
* `grounding.evidence_checked`: `false` when the model gave no evidence

### `limitations[].code`
`no_roles`, `intent_parse_warning`, `empty_retrieval`, `no_grounded_selection`, `role_failed`,
`candidates_truncated`, `hallucinated_ids_dropped`, `ungrounded_ids_dropped`, `evidence_not_verbatim`, `concept_terms_unmatched` (intent term(s) occur in no module document; says whether retrieval fell back to generic words only), `offline_llm`.

## Errors — `error_response.json`
Always `{"error": string, "request_id": string, ...}`.

| Status | When | Extra fields |
|---|---|---|
| 422 | request validation; or the intent stage returned unparseable output | `detail` / `stage`, `retryable=false` |
| 502 | the LLM provider failed on the intent call | `stage`, `retryable=true` |
| 503 | runtime index not loaded | `detail` |
| 500 | anything else (opaque; details are in the server log under the request id) | — |

Provider failures on a *role* call do not fail the request: that role is `failed` and `status` is `partial`.
