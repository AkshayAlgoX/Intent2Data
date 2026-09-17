# Canonical Demo Validation Report (runtime-validated, 2026-09-17)

> **Provenance.** This report was produced by `backend/scripts/validate_canonical.py` against the **actual `RuntimeIndex`** (122,296 variables · 932 modules · 94,221 families, fingerprint `ad858fde4e28f02e`). It exercises the real runtime retrieval path (intent → module BM25 top-5 → wave-family expansion) and, separately, the full `/v1/analyze` pipeline with the offline deterministic stand-in. **No language model was run** [LIVE RESULT: none]. Everything below is [MEASURED OFFLINE] / [STRUCTURAL REACHABILITY] at the retrieval stage; whether an LLM *selects* the right variable from the retrieved context is unmeasured. Machine-readable results: `docs/canonical_runtime_validation.json`. Labels are defined in `docs/SCIENTIFIC_CLAIMS.md`.

## Method

For every candidate in `CANONICAL_DEMO_CANDIDATES.md`, each documented expectation (an explicit code such as `PV355`, or a label pattern for a concept described in words) was classified under **two intent sources**:

* **doc-intent** — the concept phrase the documentation states (what a competent intent compiler is expected to produce);
* **runtime-intent** — what the offline stand-in actually derives from the question today.

| Class | Meaning |
|---|---|
| **a) FOUND_TOPK** | a matching variable is in the runtime candidate set at the default top-5 modules |
| **b) REACHABLE_DEEPER (rank n)** | matching variables exist; their best module ranks 6–50 for that intent |
| **c) ABSENT** | no variable in the catalog matches the expectation |
| **d) DOC_INCONSISTENT** | the documentation names a code/file/label that is not in the catalog, or its premise does not hold |

No variable code is hardcoded in the runtime; the expectations live only in the offline validation script.

## Results

| Cand. | Question | Role · expectation | doc-intent | runtime-intent | Notes |
|---|---|---|---|---|---|
| 1.1 | current smoking status ↔ self-reported health | exposure · `SMOKE` | a) FOUND_TOPK | a) FOUND_TOPK | |
| | | outcome · self-rated health | a) FOUND_TOPK | b) rank 9 | stand-in intent "self-reported health" ranks the internet-survey `RATE HEALTH` module 9th |
| **1.2** | years of education → household income | exposure · education | **a) FOUND_TOPK** (`HB014 R HIGHEST LEVEL OF EDUCATION`, core `B`) | **a) FOUND_TOPK** | |
| | | outcome · household income | **a) FOUND_TOPK** (`HHHINC HOUSEHOLD INCOME`, imputation modules) | **a) FOUND_TOPK** | |
| | | doc names `RAEDUC` | **d) DOC_INCONSISTENT** — not in catalog | | RAND files are not part of this catalog |
| | | doc names `TOT HH INC` | **d) DOC_INCONSISTENT** — no such label | | |
| 1.3 | age ↔ retirement status | exposure · age | a) FOUND_TOPK | a) FOUND_TOPK | stand-in splits the question badly ("there a"); real intent compiler needed |
| | | outcome · retirement | a) FOUND_TOPK (`HJ564 USUAL RETIREMENT AGE`, core `J`) | a) FOUND_TOPK | |
| **2.1** | religious involvement → physical functioning | exposure · **`PV355`** | **a) FOUND_TOPK** — `2016_core::V` at rank 1 | **a) FOUND_TOPK** — rank 1 | hero case holds at the retrieval stage |
| | | outcome · ADL/mobility | a) FOUND_TOPK | a) FOUND_TOPK | |
| 2.2 | functional impairment → survival after COVID | exposure · ADL difficulty | a) FOUND_TOPK | b) rank 23 | |
| | | outcome · **`EXDEATHYR`, `QALIVE`** | **a) FOUND_TOPK** — `tracker::TR` at rank 1 for "survival mortality death year vital status" | **NOT retrieved** (outside top-50) for "survival outcomes after COVID-19" | **intent-dependent**: the intent must expand "survival" to mortality/vital-status vocabulary |
| | | covariates · COVID | a) FOUND_TOPK (2021 pandemic mail survey) | no runtime intent | |
| 2.3 | childhood SES → cognitive decline | exposure · parental education / childhood finances | a) FOUND_TOPK (`FATHER EDUCATION- HIGHEST GRADE` = `xB026`, core `B`) | a) FOUND_TOPK | doc label confirmed present |
| | | outcome · memory / recall | a) FOUND_TOPK (core `D`) | a) FOUND_TOPK | |
| 2.4 | neighborhood cohesion ↔ cardiovascular health | exposure · neighborhood | a) FOUND_TOPK (`LB` psychosocial) | a) FOUND_TOPK | |
| | | outcome · heart/stroke/BP | a) FOUND_TOPK (core `C`) | a) FOUND_TOPK | |
| 2.5 | job stress → memory | exposure · stress | a) FOUND_TOPK | a) FOUND_TOPK | |
| | | outcome · memory | a) FOUND_TOPK | a) FOUND_TOPK | |
| 3.1 | epigenetic clocks ↔ smartphone usage | exposure · smartphone | a) FOUND_TOPK — **`NV108 USE SMARTPHONE`, `xLB038_4 OWN SMARTPHONE` exist** | a) FOUND_TOPK | **d) DOC_INCONSISTENT**: the doc's premise that smartphone usage "might be completely absent" is false |
| | | outcome · GrimAge | a) FOUND_TOPK — **`DNAMGRIMAGE` exists** (`hrs_epigenetic_clocks_codebook::A`) | no runtime intent (stand-in failed to split) | **d) DOC_INCONSISTENT**: not a missing-data case |
| **3.2** | PM2.5 → early-onset dementia | exposure · PM2.5 / pollution | **c) ABSENT** — 0 matching variables | **c) ABSENT** | genuine limitation confirmed |
| | | outcome · dementia | a) FOUND_TOPK (ADAMS modules at ranks 1–5) | a) FOUND_TOPK | |
| 3.3 | monocytes / HDL → survival | exposure · monocytes, HDL | a) FOUND_TOPK (`PMONO` VBS 2016; `KHDLBIOS` biomarker 2006) | a) FOUND_TOPK | **d) DOC_INCONSISTENT**: the doc expected the biomarker module to *miss* the top-10; it ranks in the top-5 |
| | | outcome · death / vital status | a) FOUND_TOPK | b) rank 9 | |

### Full-pipeline run (offline stand-in) — behaviour, not quality
All 11 questions return `status = ok` through `/v1/analyze` (2 roles each; 1.3 exposure and 3.1 population `no_selection`). Selections in this mode are lexical-overlap picks stamped `llm.live = false` with an `offline_llm` limitation; they are **not** evidence of model quality. Note that for 3.2 the stand-in still selects weakly-matching variables for the absent PM2.5 concept — the "honest limitation" behaviour must come from the real LLM returning an empty selection (allowed by the prompt) and from module scores, and has **not** been demonstrated.

## Decision

* **Q1 — keep candidate 1.2 ("Does years of education predict household income?")**, with corrected expectations: education via core `B` (`xB014 R HIGHEST LEVEL OF EDUCATION`) and `core::PR` (`xZ216 R YEARS OF EDUCATION`); income via the core imputation modules (`xHHINC HOUSEHOLD INCOME`). The earlier expectation of `RAEDUC` / `TOT HH INC` is withdrawn: those variables belong to RAND products that are **not in this catalog**. The question itself is suitable; the documentation was wrong.
* **Q2 — keep candidate 2.1.** `PV355` is discovered by the runtime at module rank 1 under both intent sources.
* **Q3 — keep candidate 3.2.** PM2.5 is genuinely absent (0 catalog matches); dementia is well covered. Candidates 3.1 and 3.3 are **not** valid limitation demos: their "missing" concepts are present in the catalog.
* Candidate 2.2 is usable only if the intent compiler expands "survival" to mortality vocabulary; do not use it with the offline stand-in.

## Hardcoding audit
`backend/tests/test_no_benchmark_leakage.py` fails if `PV355`, `EXDEATHYR`, `QALIVE` or `RAEDUC` appear in `backend/app`; the expectations above exist only in `backend/scripts/validate_canonical.py` and this document. **Result: PASSED** (see test run in the session log).
