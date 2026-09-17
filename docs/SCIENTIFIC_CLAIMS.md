# Intent2Data — Scientific Claims (single source of truth)

This document is the only authoritative statement of what Intent2Data has and has not shown.
Every number anywhere else in this repository must carry one of the labels below and must agree with this page.
If another document disagrees with this one, this one wins.

## Labels

| Label | Meaning |
|---|---|
| **[MEASURED OFFLINE]** | Computed deterministically from codebook metadata and benchmark labels. No language model involved. |
| **[STRUCTURAL REACHABILITY]** | A [MEASURED OFFLINE] quantity of a specific kind: the fraction of gold variables *present in a candidate set*. It is a ceiling on what any downstream selector could recover; it is not a recall of anything selected. |
| **[SIMULATION / PROJECTION]** | A number produced by multiplying a measured ceiling by an *assumed* factor. It is not a measurement of anything. |
| **[LIVE RESULT]** | Output of an actual language-model call scored against gold. **None exist yet.** |

Benchmark used throughout: **OADD-Bench, HRS subset** — 160 research questions with gold HRS variable codes (`hrs_column_ids`) and a per-question `allowed_years` window.
Unless stated otherwise the population is the **20 intent-annotated questions** (`sample_20.json` / `expanded_intents.json`), **621 gold variable labels**.

---

## 1. MEASURED OFFLINE RESULTS

### 1a. Pre-hackathon retrieval baselines
Scripts: `../eval_ablation.py`, `../eval_operationalization.py`, `../eval_hierarchical.py` (workspace root, outside this repository).
Metric: **macro-averaged Recall@5R** — for each question, the fraction of its R gold variables found in the top 5·R retrieved variables, averaged over the 20 questions.
Important caveat for all four numbers: retrieved family rankings were expanded to variable codes **filtered by the benchmark's `allowed_years`**, i.e. these runs used benchmark-side temporal information that a runtime does not have. They are valid for comparing retrieval methods with each other; they are optimistic as absolute values.

| Value | Label | What it is |
|---|---|---|
| **0.184** | [MEASURED OFFLINE] | Single-query BM25 over variable families, Recall@5R. No persisted result file in this repository; reproducible by re-running the script. |
| **0.304** | [MEASURED OFFLINE] | Role-aware ("operationalization-aware") BM25: one query per intent role, fused by reciprocal-rank fusion, Recall@5R. Same caveat about persistence. |
| **0.221** | [MEASURED OFFLINE] | Module top-k per role, then within-module BM25, Recall@5R (`../metrics.json`, key `A_module_retrieval_only`). |
| **0.698** | [STRUCTURAL REACHABILITY] | Fraction of gold variables present in the *candidate pool* after module retrieval + within-module BM25 + wave-family expansion + `allowed_years` filter, macro-averaged (`../metrics.json`, key `reachability`). The module top-k that produced it was **not persisted**. It is **not comparable** to the 0.330 figure in 1b (different metric, different candidate construction). |

### 1b. Hackathon-period structural analysis (`evaluation/exp1`–`exp17`)
Metric unless stated: **micro recall = gold labels surfaced ÷ 621**, where "surfaced" means *present in the candidate set*. These are all [STRUCTURAL REACHABILITY] numbers; nothing selects anything.

| Value | Label | What it is | Source |
|---|---|---|---|
| 932 modules; median 86, max 1,899 variables/module; largest raw module 2.35 MB | [MEASURED OFFLINE] | Codebook structure (`module = product_key::section` = one survey wave × one section) | `exp1_module_size.json` |
| 99.8 % / 74.4 % / 97.3 % | [MEASURED OFFLINE] | **Lexical** presence of gold evidence in three context representations (raw block / code+label / code+label+question_text) over 2,011 gold variables. Says nothing about whether a model can use the text. | `exp2_info_preservation.json` |
| **205/621 = 0.330** | [STRUCTURAL REACHABILITY] | Module BM25, top-5 modules per role, union of the 7 roles' module variables | `exp3_retrieval.json` |
| 222/621 = 0.358 (+17) | [STRUCTURAL REACHABILITY] | Above ∪ global flat BM25 top-200 on the question | `exp3_retrieval.json` |
| 537/621 gold labels belong to a multi-wave series; 367 of 417 misses have their module at rank 6–44 | [MEASURED OFFLINE] | Why module top-5 misses: wave-series fragmentation, not absent modules | `exp11_wave_series.json` |
| **343/621 = 0.552** (170,668 candidates) | [STRUCTURAL REACHABILITY] | Module top-5 + cross-wave family expansion, **no temporal filter** — the candidate construction the runtime implements | `exp12`, `exp17_temporal_corrected_v2.json` |
| 342/621 = 0.551 (77,348 candidates) | [STRUCTURAL REACHABILITY] | Same, filtered by benchmark `allowed_years`. **Uses gold-derived temporal information; not available at runtime; reported for comparison only.** | `exp17_temporal_corrected_v2.json` |
| 341/621 (top-10), 445/621 (top-20), 470/621 (whole section) | [STRUCTURAL REACHABILITY] | Deeper module retrieval, at 205k–373k candidates | `exp12_wave_completion.json` |
| 0.330 → 0.130 / 0.121 / 0.108 / 0.079 | [STRUCTURAL REACHABILITY] | Within-module **lexical** pruning to top-500/300/200/100 per role destroys reachability; there is no cheap lexical substitute for reading the module | `exp15_within_module_pruning.json` |
| 7 roles in every one of the 20 questions | [MEASURED OFFLINE] | | `exp6_roles.json` |

Superseded: `exp13_temporal_wave.json` reports 621/621 under temporal filtering; that run seeded the candidate set from gold (see `evaluation/exp13_temporal.py`, `cand_temp = set(golds)`) and is **invalid**. `exp17_temporal_corrected_v2` replaces it (603/621 gold lie inside their own `allowed_years` window).

### 1c. Role-sharding candidate-volume results (`exp19`, `exp20`)
Metric: candidate counts and offline `count_tokens` sizes of the prompts that *would* be sent. No generation.

| Value | Label | What it is |
|---|---|---|
| 541,436 → 103,131 candidates (−81.0 %) | [MEASURED OFFLINE] | Sum over 140 role-calls of candidates shown, union-of-all-roles vs. each role's own modules |
| 32.3 M → 6.25 M input tokens (compact); 9.06 M → 1.68 M (code+label) | [MEASURED OFFLINE] | Same, in tokens |
| Union per-call: p50 169,106 / p90 383,647 / max 930,377 tokens; Sharded: p50 29,863 / p90 90,588 / max 565,772 | [MEASURED OFFLINE] | Compact representation |
| **342 reachable gold under union, 342 under sharding — 0 lost** | [STRUCTURAL REACHABILITY] | See §4 for the exact permitted phrasing |
| 623 of 700 top-5 module retrievals unique across roles (11 % overlap) | [MEASURED OFFLINE] | |

### 1d. Runtime engineering measurements (`backend/scripts/bench_runtime.py`, this machine)
[MEASURED OFFLINE] — timings only, no quality content: index build 1.74 s from the 261 MB JSONL, 7.1 MB cache, warm load 0.83 s, ≈300 MB RSS, ≈100 ms per request with the offline stand-in.

---

## 2. SIMULATION / PROJECTION RESULTS

Source: `../intent2data_eval/evaluate.py` and `../metrics.json` (workspace root).

| Value | Label | Exact derivation |
|---|---|---|
| **0.593** | [SIMULATION / PROJECTION] | `0.698 × 0.85`. The 0.85 is an **assumed extraction efficiency** for an LLM context filter. No model was run. |
| **0.649** | [SIMULATION / PROJECTION] | `0.698 × 0.93`. The 0.93 is an **assumed extraction efficiency** for filter + validator. No model was run. |
| 0.389 (Recall@R), 0.519 (Recall@2R) | [SIMULATION / PROJECTION] | `0.649 × 0.6` and `0.649 × 0.8`. Assumed rank-concentration factors. |

These numbers are **mathematical projections from an assumed efficiency applied to a reachability ceiling**. They are:
* **not** live LLM measurements,
* **not** benchmark results, wins, or leaderboard scores,
* **not** "verified accuracy",
* **not** theoretical upper bounds (the ceiling is 0.698; these are the ceiling times a guess).

They may be described only as "projected recall under an assumed 85 %/93 % extraction efficiency, pre-hackathon". Their only legitimate use is to motivate why the LLM stage was worth building; they must not appear in a results table.

---

## 3. LIVE RESULTS

**Status: not yet measured. No live LLM extraction accuracy of any kind may be claimed.**

| Attempt | Outcome |
|---|---|
| `exp18` (280 planned calls, 2 representations) | 0 calls executed — no API key in the environment |
| `exp21` (28-call union-vs-sharded A/B) | aborted on call 1 — `429/503`, 8 retries exhausted |
| `exp22` (14-call micro-paired A/B) | aborted on call 1 — `429/503` |
| `exp23` (payload feasibility ladder from 25k tokens) | aborted at the first rung — `429/503` |
| `exp24` (14-call staged, controlled single-question pilot; frozen) | aborted on call 1 — `429 RESOURCE_EXHAUSTED`, free-tier limit of 20 requests/day already spent |

Total successful live generation calls across all experiments: **0**.
Exp24 is a *staged controlled pilot*: n = 14 calls on one question. Even when it runs, it can only indicate whether selection behaviour differs between the union and sharded contexts on that question; it cannot establish benchmark-level extraction quality.
The runtime's default client is a deterministic lexical stand-in; every response it produces carries `llm.live = false` and an `offline_llm` limitation so that it cannot be mistaken for model output.

---

## 4. ROLE SHARDING

Permitted statement:

> **Offline structural analysis showed no reachable gold variables lost under role sharding in the tested benchmark configuration** (20 questions, 621 gold labels, module top-5 per role with cross-wave family expansion: 342 reachable under union, 342 under sharding), while reducing candidates shown per call by 81 %.

Mandatory companion statement:

> **This does not establish equal live LLM extraction quality.** Whether a model selects the same variables from a 30k-token context as from a 170k-token one is exactly the untested question of Exp24.

---

## 5. WAVE-FAMILY EXPANSION

What it is: HRS asks the same item in every biennial wave under a wave-prefixed code (`JD112`, `KD112`, `LD112`, …). A *family* groups those copies using only codebook fields (product family, section, normalised label, wave prefix). After module retrieval, every wave-sibling of a retrieved variable is added to the candidate set.

What was shown [STRUCTURAL REACHABILITY]: on the 20-question population, expansion raises reachable gold from 205 to 343 of 621 at a 1.5× candidate cost, whereas retrieving twice as many modules reaches 341 at a 1.8× cost (`exp12`, `exp17`). 537 of the 621 gold labels are members of a multi-wave series, which is why the effect is large **on this benchmark**.

Scope of the claim: this leverages the **longitudinal harmonisation structure of HRS metadata** and is **demonstrated on HRS only**. It is offered as a **blueprint for structured longitudinal datasets** whose codebooks carry repeated-item structure (panel surveys with wave-coded variables). No claim is made that it transfers to arbitrary datasets, to cross-sectional data, or to codebooks without harmonised item labels, and no such transfer has been measured.

---

## 6. CAUSAL CLAIMS

Intent2Data performs **variable discovery and operationalization mapping**: given a research question it proposes which dataset variables could measure the concepts the question names (exposure, outcome, covariates, …) and reports evidence and gaps.

It **does not perform, test, or validate causal inference**. The roles "exposure" and "outcome" are search intents, not causal assertions; a returned variable set is not a study design, not an identification strategy, and not evidence that any relationship in the question holds. Language such as "X drives Y" in a demo question describes the user's question, not a system finding.

---

## 7. CURRENT SYSTEM STATUS

| Dimension | Status |
|---|---|
| **Runtime pipeline functionality** | Implemented and tested offline: `POST /v1/analyze` runs intent → module BM25 retrieval → wave-family expansion → per-role selection call → deterministic grounding validation → contract v1 response. 77 tests pass with a synthetic catalog and scripted/offline clients. Exercised on the real 122,296-variable index. |
| **Offline retrieval evidence** | The candidate construction the runtime implements reaches 343/621 gold on the 20-question population [STRUCTURAL REACHABILITY]. The three canonical demo questions retrieve the modules the demo docs predicted for Q2 and Q3; for Q1 the demo doc names RAND variables (`RAEDUC`) that are **not in this catalog** — see the correction note in `docs/CANONICAL_DEMO_VALIDATION.md`. |
| **Live LLM evaluation** | Not started successfully: 0 live generation calls have completed (§3). No live selection accuracy exists. Exp24 is staged for the next quota window. |
| **Infrastructure / demo readiness** | API hardened (validation, request ids, CORS, error envelope, 503/502 semantics); provider-agnostic `LLMClient` boundary; no live provider adapter is wired; the free-tier quota (20 requests/day) is smaller than one full demo run of three questions (≈ 9 calls each). A demo today runs on the offline stand-in and must be presented as such. |

## Internal claim table (quick reference)

| Claim as it might be spoken | Allowed? | Correct form |
|---|---|---|
| "Intent2Data achieves 0.649 recall" | **No** | "Pre-hackathon projection: 0.698 reachability × an assumed 0.93 extraction efficiency = 0.649 [SIMULATION / PROJECTION]. Not measured." |
| "Module retrieval beats BM25 (0.593 vs 0.184)" | **No** | "Role-aware BM25 improved Recall@5R from 0.184 to 0.304 offline [MEASURED OFFLINE]; the LLM stage is unmeasured." |
| "70 % of gold variables are reachable" | Qualified | "0.698 macro reachability in the pre-hackathon configuration (with benchmark temporal filter) [STRUCTURAL REACHABILITY]; 0.552 micro reachability in the runtime's configuration." |
| "Wave-family expansion improves recall by 67 %" | Qualified | "…improves *reachability* from 205 to 343 of 621 gold labels on HRS [STRUCTURAL REACHABILITY]." |
| "Role sharding loses nothing" | Qualified | §4 wording, with its companion sentence. |
| "The LLM surgically extracts the right variables" | **No** | Hypothesis; no live result. |
| "End-to-end system works" | Qualified | "The pipeline runs end-to-end offline with a deterministic stand-in; end-to-end *accuracy* is unmeasured." |
| "Verified / proven architecture" | **No** | "Offline-validated retrieval design; LLM stages unvalidated." |
| "Generalises to any dataset" | **No** | §5 wording. |
| "Finds the causes of …" | **No** | §6 wording. |
