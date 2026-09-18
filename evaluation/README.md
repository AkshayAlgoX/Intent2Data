# Evaluation

All labels are defined in `docs/SCIENTIFIC_CLAIMS.md` (the single source of truth).

Known prior results (pre-event research, 20-question population, macro Recall@5R with benchmark temporal filter):
- BM25 = 0.184 [MEASURED OFFLINE]
- Operationalization-aware (role-aware BM25 + RRF) = 0.304 [MEASURED OFFLINE]
- Module + LLM = 0.593 [SIMULATION / PROJECTION] — `0.698 reachability × assumed 0.85 extraction efficiency`; no model was run
- Intent2Data = 0.649 [SIMULATION / PROJECTION] — `0.698 × assumed 0.93`; no model was run

**Explicitly:** these are prior research figures under our own evaluation setup, not official leaderboard results, and the two projections must never be presented as measured recall.

Hackathon-period experiments live in `exp*.py` with outputs in `results/`. `exp1`–`exp17`, `exp19`, `exp20` are deterministic offline analyses [MEASURED OFFLINE] / [STRUCTURAL REACHABILITY]. `exp18`, `exp21`–`exp25` are live-LLM attempts; across all of them exactly **one** generation call has completed (`exp25` call 1/7, then `503`) — a feasibility observation, not a result [LIVE RESULT: n = 1]. `exp25` must not be described as a completed or successful 7-call validation. `exp13` is superseded by `exp17_temporal_corrected_v2` (see `SCIENTIFIC_CLAIMS.md` §1b). `exp24` and `exp25` are frozen and must not be modified.
