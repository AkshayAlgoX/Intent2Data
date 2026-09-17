"""Offline runtime benchmark: startup cost, per-request timings, memory, and
candidate volumes, using the deterministic offline LLM stand-in (no network).

    python scripts/bench_runtime.py [question ...]

Selections printed here come from the offline stand-in and say nothing about
model quality; the point is to exercise the real retrieval/orchestration path
on the real codebook.
"""

import json
import resource
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.runtime import load_runtime  # noqa: E402
from app.settings import Settings  # noqa: E402

DEFAULT_QUESTIONS = [
    "Is years of education associated with total household income?",
    "How does lifelong religious and spiritual involvement shape physical functioning in later life?",
    "Does localized air pollution (PM2.5) exposure drive early-onset dementia?",
]


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def main() -> int:
    questions = sys.argv[1:] or DEFAULT_QUESTIONS
    print(f"rss_before_load={rss_mb():.0f}MB")
    state = load_runtime(Settings.from_env())
    if not state.ready:
        print("runtime not ready:", state.index_error, file=sys.stderr)
        return 1
    print(f"index={state.index.stats()} timings={state.index_timings} rss_after_load={rss_mb():.0f}MB")
    pipeline = state.pipeline()
    for q in questions:
        t = time.perf_counter()
        resp = pipeline.run(q, uuid.uuid4().hex)
        wall = (time.perf_counter() - t) * 1000
        print(f"\nQ: {q}\n  status={resp.status} wall={wall:.0f}ms stages={{{', '.join(f'{k}:{v.ms}ms' for k, v in resp.stages.items())}}} rss={rss_mb():.0f}MB")
        for r in resp.roles:
            mods = [f"{m.module_id}#{m.rank}" for m in r.modules]
            print(f"  [{r.role}] {r.status} intent={r.intent!r}\n     modules={mods}\n     candidates={r.candidates.model_dump()} selected={[s.code for s in r.selections]}")
        print("  limitations=" + json.dumps([l.code for l in resp.limitations]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
