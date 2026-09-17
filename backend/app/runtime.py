"""Process-wide runtime state: the compact index and the LLM client.

Loaded once (lifespan), read by every request. Tests replace it through
FastAPI dependency overrides with a tiny in-memory index and a scripted client,
so no test ever touches the 261 MB metadata file or a network.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from app.llm.client import LLMClient
from app.llm.factory import build_llm_client
from app.pipeline.orchestrator import AnalyzePipeline, PipelineConfig
from app.retrieval.index import RuntimeIndex
from app.settings import Settings

logger = logging.getLogger("intent2data.runtime")


@dataclass
class RuntimeState:
    settings: Settings
    index: Optional[RuntimeIndex] = None
    llm: Optional[LLMClient] = None
    index_timings: dict = field(default_factory=dict)
    index_error: Optional[str] = None

    @property
    def ready(self) -> bool:
        return self.index is not None and self.llm is not None

    def pipeline(self) -> AnalyzePipeline:
        if not self.ready:
            raise RuntimeError("runtime not ready")
        cfg = PipelineConfig(
            module_top_k=self.settings.module_top_k,
            max_candidates_per_call=self.settings.max_candidates_per_call,
            max_selections_per_role=self.settings.max_selections_per_role,
            provider=self.settings.llm_provider,
            max_retries=self.settings.llm_max_retries,
            retry_backoff_s=self.settings.llm_retry_backoff_s,
        )
        return AnalyzePipeline(self.index, self.llm, cfg)


def load_runtime(settings: Settings) -> RuntimeState:
    state = RuntimeState(settings=settings)
    try:
        state.llm = build_llm_client(settings.llm_provider, settings.llm_model)
    except Exception as exc:
        state.index_error = f"llm: {exc}"
        logger.error("LLM client unavailable: %s", exc)
        return state
    if not settings.build_index_on_startup:
        state.index_error = "index build disabled (INTENT2DATA_BUILD_INDEX_ON_STARTUP=0)"
        return state
    if not settings.metadata_path.exists() and not settings.index_cache_path.exists():
        state.index_error = f"metadata not found: {settings.metadata_path}"
        logger.error(state.index_error)
        return state
    t = time.perf_counter()
    try:
        state.index, state.index_timings = RuntimeIndex.load_or_build(settings.metadata_path, settings.index_cache_path)
        state.index_timings["total_s"] = round(time.perf_counter() - t, 3)
        logger.info("runtime index ready %s timings=%s", state.index.stats(), state.index_timings)
    except Exception as exc:
        state.index_error = f"index: {exc.__class__.__name__}: {exc}"
        logger.exception("index load failed")
    return state
