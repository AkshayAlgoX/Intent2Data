# Project Overview: Intent2Data

## 1. Problem
Traditional variable-level retrieval (like BM25 or dense embeddings) suffers from semantic mismatch and term dilution. When searching for broad concepts like "survival", highly specific variables like "year of death" are often buried or missed.

## 2. Technical Hypothesis
Variable-level retrieval is fundamentally flawed for complex datasets. Structural module retrieval combined with LLM context filtering substantially improves variable discovery by relying on dataset structures (modules) rather than individual variable labels.

## 3. Intent2Data Architecture
- **Intent Decomposition:** Extract roles from the research question.
- **Module Retrieval:** Embed and retrieve full dataset sections (modules) instead of single variables.
- **LLM Context Filtering:** Pass the full module codebook to an LLM to surgically extract variables, avoiding term dilution.
- **Operationalization Validator:** Cross-check candidates for proxy errors, population mismatch, etc.

## 4. Current Evidence (Prior Research)
- BM25 Recall@5R: 0.184
- Operationalization-aware retrieval: 0.304
- Module + LLM Context Filter: 0.593
- Full Intent2Data prototype: 0.649 Recall@5R
*(Note: These are our measured results under our evaluation setup, not official leaderboard scores.)*

## 5. Current Limitation
Module retrieval reachability ceilings at roughly 0.698 in our evaluation. If the module is not retrieved, the variable cannot be found.

## 6. Pre-Event Research
The architectural experiments, benchmarks, and prior iterations of the OADD pipeline were completed before this hackathon began. They serve as the design foundation.

## 7. Hackathon Implementation
This repository represents the clean, production-ready backend built exclusively during the hackathon build window, implementing the verified architecture.
