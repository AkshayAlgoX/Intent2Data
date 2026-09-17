"""Runtime configuration. Everything is an environment variable with a safe
default so demo-day switches (provider, model, top-k) are config, not code."""

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent          # intent2data/
WORKSPACE_DIR = REPO_DIR.parent        # OADD-Bench/ (holds benchmark/HRS_metadata)

ROLE_ORDER = ("exposure", "outcome", "population", "covariates", "secondary", "temporal", "proxies")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    metadata_path: Path
    index_cache_path: Path
    llm_provider: str
    llm_model: str
    module_top_k: int
    max_candidates_per_call: int
    max_selections_per_role: int
    build_index_on_startup: bool
    llm_max_retries: int = 1
    llm_retry_backoff_s: float = 0.5

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            metadata_path=Path(
                os.getenv("INTENT2DATA_METADATA_PATH", WORKSPACE_DIR / "benchmark" / "HRS_metadata" / "metadata.jsonl")
            ),
            index_cache_path=Path(
                os.getenv("INTENT2DATA_INDEX_CACHE", BACKEND_DIR / ".cache" / "runtime_index.json.gz")
            ),
            # "offline" = deterministic lexical stand-in (no network). Live providers
            # register in app.llm.factory and must implement LLMClient only.
            llm_provider=os.getenv("INTENT2DATA_LLM_PROVIDER", "offline"),
            llm_model=os.getenv("INTENT2DATA_LLM_MODEL", ""),
            module_top_k=_int("INTENT2DATA_MODULE_TOP_K", 5),
            max_candidates_per_call=_int("INTENT2DATA_MAX_CANDIDATES_PER_CALL", 2000),
            max_selections_per_role=_int("INTENT2DATA_MAX_SELECTIONS_PER_ROLE", 25),
            build_index_on_startup=os.getenv("INTENT2DATA_BUILD_INDEX_ON_STARTUP", "1") not in ("0", "false", "no"),
            llm_max_retries=max(0, _int("INTENT2DATA_LLM_MAX_RETRIES", 1)),
            llm_retry_backoff_s=max(0.0, _float("INTENT2DATA_LLM_RETRY_BACKOFF_S", 0.5)),
        )
