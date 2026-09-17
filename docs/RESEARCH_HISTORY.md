# Research History

The benchmark experiments and architectural exploration (BM25 and role-aware baselines, hierarchical module + BM25 retrieval, and the pre-hackathon **projection** of a module + LLM pipeline) were conducted **before** the hackathon build period, in the workspace root outside this repository (`eval_ablation.py`, `eval_operationalization.py`, `eval_hierarchical.py`, `intent2data_eval/evaluate.py`).

Two points about that history matter for how results are read:

* The retrieval baselines (0.184, 0.304, 0.221) and the 0.698 reachability figure were **measured offline** [MEASURED OFFLINE] / [STRUCTURAL REACHABILITY], on 20 questions, with the benchmark's temporal window applied to candidate lists.
* The 0.593 and 0.649 figures were **projections**: `0.698 × 0.85` and `0.698 × 0.93`, where 0.85 and 0.93 are assumed extraction efficiencies for the LLM stages [SIMULATION / PROJECTION]. No language model was run to obtain them.

The hackathon-period experiments (`evaluation/exp1`–`exp24`) re-measured the structural properties deterministically and attempted, unsuccessfully so far, to obtain live LLM measurements. The findings from both periods guide the architecture implemented in this repository; the authoritative statement of every claim is `docs/SCIENTIFIC_CLAIMS.md`.
