# Project Overview: Intent2Data

> All numbers below carry a label defined in `docs/SCIENTIFIC_CLAIMS.md`, which is the single source of truth for what has and has not been shown. **No live LLM result exists yet.**

## 1. Problem
Traditional variable-level retrieval (BM25 or dense embeddings) suffers from semantic mismatch and, in longitudinal codebooks, from series fragmentation: the same item recurs in every survey wave under a different code, so a flat retriever must find each copy independently. When searching for broad concepts like "survival", specific variables like "year of death" are often buried or missed.

## 2. Technical Hypothesis
Variable-level retrieval is a weak fit for structured longitudinal codebooks. We hypothesise that structural module retrieval, cross-wave family expansion, and LLM context filtering together improve variable discovery by relying on dataset structure (modules, wave families) rather than individual variable labels. The retrieval part of this hypothesis has offline support (§4); the LLM part is untested (§5).

## 3. Intent2Data Architecture
- **Intent Decomposition:** Extract search roles (exposure, outcome, population, covariates, secondary, temporal, proxies) from the research question.
- **Module Retrieval:** Retrieve whole codebook sections (modules = one survey wave × one section) instead of single variables.
- **Wave-Family Expansion:** Add every cross-wave sibling of the retrieved variables (deterministic, metadata-only).
- **LLM Context Filtering:** Show the module's variables to an LLM and ask it to select those that operationalize the role's concept.
- **Grounding Validation:** Keep only selections that were in the shown candidate set; check that cited evidence is a verbatim codebook span; report gaps.

## 4. Current Evidence (offline, no language model involved)
Population: 20 intent-annotated OADD-Bench questions (HRS), 621 gold variable labels, unless stated.

| Result | Label |
|---|---|
| Single-query BM25 Recall@5R 0.184 → role-aware BM25 0.304 (pre-hackathon, macro-averaged, benchmark temporal filter applied) | [MEASURED OFFLINE] |
| Module top-5 per role: 205/621 gold present in candidates (0.330) | [STRUCTURAL REACHABILITY] |
| + cross-wave family expansion (the runtime's configuration): 343/621 (0.552) | [STRUCTURAL REACHABILITY] |
| Role sharding: 0 reachable gold lost, −81 % candidates per call (reachability only; says nothing about live selection quality) | [STRUCTURAL REACHABILITY] |

**Not evidence — listed only so nobody mistakes them for it.** Pre-hackathon *projections* of 0.593 and 0.649 exist in old material. They are `0.698 reachability × an assumed 0.85 / 0.93 extraction efficiency` [SIMULATION / PROJECTION]: no language model was run to obtain them, and they must not be read, quoted or plotted as recall.

## 5. Current Limitations
- Module reachability is a hard ceiling: if the module is not retrieved, the variable cannot be found. Pre-hackathon macro reachability was about 0.698 [STRUCTURAL REACHABILITY]; the runtime's configuration reaches 0.552 micro on the same questions (different metric; see `SCIENTIFIC_CLAIMS.md` §1).
- **Live LLM selection has not been measured.** Six live attempts: five blocked by provider quota/outages; Exp25 completed **one** generation call (1 of 7) before a `503` abort — a feasibility observation, not an accuracy result [LIVE RESULT: n = 1 call]. Exp24 and the rest of Exp25 are staged.
- Wave-family expansion is demonstrated on HRS only; it is a blueprint for other longitudinal datasets, not a demonstrated general method.
- Intent2Data maps concepts to variables; it does not perform or validate causal inference.

## 6. Pre-Event Research
The retrieval experiments, benchmarks, and the pre-hackathon simulation were completed before this hackathon began. They serve as the design foundation; see `docs/RESEARCH_HISTORY.md`.

## 7. Hackathon Implementation
This repository contains the backend built during the hackathon build window. It implements the offline-validated retrieval design end to end (pipeline functionality, exercised on the real codebook index with a deterministic offline stand-in); its LLM stages are implemented behind a provider-agnostic boundary and remain unvalidated.
