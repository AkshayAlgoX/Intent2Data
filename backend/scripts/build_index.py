"""Build (or refresh) the compact runtime index cache offline.

    python scripts/build_index.py            # uses INTENT2DATA_* env defaults
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.retrieval.index import RuntimeIndex  # noqa: E402
from app.settings import Settings  # noqa: E402


def main() -> int:
    s = Settings.from_env()
    if not s.metadata_path.exists():
        print(f"metadata not found: {s.metadata_path}", file=sys.stderr)
        return 1
    t = time.perf_counter()
    index = RuntimeIndex.from_metadata(s.metadata_path)
    build = time.perf_counter() - t
    t = time.perf_counter()
    index.save(s.index_cache_path)
    print(f"built {index.stats()} in {build:.2f}s; cached to {s.index_cache_path} "
          f"({s.index_cache_path.stat().st_size / 1e6:.1f} MB) in {time.perf_counter() - t:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
