"""Explicit, request-scoped pipeline:

    intent -> retrieval (per role) -> context filter (per role, LLM)
           -> validation (deterministic) -> contract v1 response

Every stage has typed inputs/outputs, is timed, and records its failure on
the response instead of raising, except for the two cases where nothing
useful can be returned (intent call failed, intent unparseable), which raise
PipelineError so the API can map them to an HTTP status.
"""

import logging
import time
from dataclasses import dataclass

from app.llm.client import LLMClient, LLMProviderError
from app.llm.offline import MODEL_NAME as OFFLINE_MODEL
from app.llm.parsing import parse_intent_output, parse_selection_output
from app.pipeline import prompts
from app.pipeline.models import (
    AnalyzeResponse, CandidateStats, IndexInfo, Intent, IntentRole, LLMInfo, ModuleRef, Rejected, RoleResult, StageTiming,
)
from app.pipeline.validation import build_selections, derive_limitations, rejected_from, summarize_variables
from app.retrieval.candidates import RoleCandidates, build_role_candidates
from app.retrieval.index import RuntimeIndex

logger = logging.getLogger("intent2data.pipeline")


class PipelineError(RuntimeError):
    def __init__(self, stage: str, message: str, retryable: bool = False):
        super().__init__(f"{stage}: {message}")
        self.stage = stage
        self.message = message
        self.retryable = retryable


@dataclass
class PipelineConfig:
    module_top_k: int = 5
    max_candidates_per_call: int = 2000
    max_selections_per_role: int = 25
    provider: str = "offline"
    # Retry policy is owned here, never by a provider adapter. Only failures the
    # adapter marks retryable (rate limit, timeout, unavailable) are retried;
    # a daily-quota or auth failure is never retried.
    max_retries: int = 1
    retry_backoff_s: float = 0.5


@dataclass
class _CallStats:
    calls: int = 0          # successful provider calls
    failed_calls: int = 0   # attempts that raised (including ones later retried)
    retries: int = 0        # retry attempts made


class AnalyzePipeline:
    def __init__(self, index: RuntimeIndex, llm: LLMClient, config: PipelineConfig | None = None, sleep=time.sleep):
        self.index = index
        self.llm = llm
        self.config = config or PipelineConfig()
        self._sleep = sleep

    def _call(self, stats: _CallStats, request_id: str, label: str, system: str, prompt: str, schema: dict):
        """One provider call with the orchestrator's retry policy. Raises the last
        exception when every attempt fails."""
        attempts = 1 + max(0, self.config.max_retries)
        for attempt in range(1, attempts + 1):
            try:
                resp = self.llm.generate_json(system, prompt, schema)
                stats.calls += 1
                return resp
            except Exception as exc:
                stats.failed_calls += 1
                can_retry = attempt < attempts and _retryable(exc)
                logger.warning("%s call failed request_id=%s attempt=%d/%d err=%s retry=%s",
                               label, request_id, attempt, attempts, _err_label(exc), can_retry)
                if not can_retry:
                    raise
                stats.retries += 1
                if self.config.retry_backoff_s > 0:
                    self._sleep(self.config.retry_backoff_s * attempt)

    # ---- public --------------------------------------------------------------
    def run(self, question: str, request_id: str) -> AnalyzeResponse:
        stages: dict[str, StageTiming] = {}
        stats = _CallStats()

        # Stage 1: intent -------------------------------------------------------
        t = time.perf_counter()
        try:
            resp = self._call(stats, request_id, "intent", prompts.INTENT_SYSTEM, prompts.intent_prompt(question), prompts.INTENT_SCHEMA)
        except Exception as exc:
            raise PipelineError("intent", f"LLM provider failure ({_err_label(exc)})", retryable=_retryable(exc)) from exc
        parsed_intent = parse_intent_output(resp.text)
        model_name = resp.model or self.config.provider
        if not parsed_intent.parse_ok:
            raise PipelineError("intent", "intent output could not be parsed: " + "; ".join(parsed_intent.errors))
        intent = Intent(
            roles=[IntentRole(role=r, intent=i) for r, i in parsed_intent.roles.items()],
            source=model_name, errors=parsed_intent.errors,
        )
        stages["intent"] = StageTiming(ms=_ms(t), detail={"roles": len(intent.roles)})

        # Stage 2: retrieval + structural expansion (deterministic) ---------------
        t = time.perf_counter()
        role_cands: list[RoleCandidates] = [
            build_role_candidates(self.index, r.role, r.intent, self.config.module_top_k, self.config.max_candidates_per_call)
            for r in intent.roles
        ]
        stages["retrieval"] = StageTiming(ms=_ms(t), detail={
            "candidates_per_role": {rc.role: len(rc.candidates) for rc in role_cands},
            "modules_per_role": {rc.role: len(rc.modules) for rc in role_cands},
        })

        # Stage 3: context filter (one LLM call per role with candidates) --------
        t = time.perf_counter()
        roles: list[RoleResult] = []
        for rc in role_cands:
            modules = [ModuleRef(rank=h.rank, score=h.score, **self.index.module_summary(h.module_id)) for h in rc.modules]
            cstats = CandidateStats(retrieved=rc.retrieved_count, family_expanded=rc.expanded_count,
                                    total=len(rc.candidates), truncated=rc.truncated)
            if not rc.candidates:
                roles.append(RoleResult(role=rc.role, intent=rc.intent, status="empty_retrieval", modules=modules,
                                        candidates=cstats, selections=[], rejected=Rejected()))
                continue
            try:
                resp = self._call(stats, request_id, f"filter[{rc.role}]", prompts.FILTER_SYSTEM,
                                  prompts.filter_prompt(question, rc.role, rc.intent, rc.lines), prompts.FILTER_SCHEMA)
            except Exception as exc:
                roles.append(RoleResult(role=rc.role, intent=rc.intent, status="failed", modules=modules, candidates=cstats,
                                        selections=[], rejected=Rejected(), error=f"LLM provider failure ({_err_label(exc)})"))
                continue
            parsed = parse_selection_output(resp.text, rc.codes, self.index.variables.keys())
            selections, over = build_selections(self.index, rc, parsed, self.config.max_selections_per_role)
            status = "ok" if selections else ("failed" if not parsed.parse_ok else "no_selection")
            roles.append(RoleResult(
                role=rc.role, intent=rc.intent, status=status, modules=modules, candidates=cstats,
                selections=selections, rejected=rejected_from(parsed, over),
                error=None if parsed.parse_ok else "LLM output unparseable: " + "; ".join(parsed.errors),
            ))
        stages["filter"] = StageTiming(ms=_ms(t), detail={"calls": stats.calls - 1, "failed": stats.failed_calls, "retries": stats.retries})

        # Stage 4: validation (deterministic) --------------------------------------
        t = time.perf_counter()
        live = model_name != OFFLINE_MODEL and self.config.provider not in ("offline", "static")
        limitations = derive_limitations(roles, intent.errors, live, len(intent.roles))
        variables = summarize_variables(roles)
        stages["validation"] = StageTiming(ms=_ms(t), detail={"limitations": len(limitations)})

        if not roles:
            status = "failed"
        elif any(r.status == "failed" for r in roles) and any(r.status == "ok" for r in roles):
            status = "partial"
        elif all(r.status == "failed" for r in roles):
            status = "failed"
        else:
            status = "ok"

        return AnalyzeResponse(
            request_id=request_id, status=status, question=question, intent=intent, roles=roles,
            variables=variables, limitations=limitations, stages=stages,
            llm=LLMInfo(provider=self.config.provider, model=model_name, live=live, calls=stats.calls,
                        failed_calls=stats.failed_calls, retries=stats.retries),
            index=IndexInfo(**self.index.stats()),
        )


def _err_label(exc: Exception) -> str:
    # Typed provider errors carry a stable category; anything else is named by class only,
    # so no provider payload ever reaches a response.
    return exc.kind if isinstance(exc, LLMProviderError) else exc.__class__.__name__


def _retryable(exc: Exception) -> bool:
    return exc.retryable if isinstance(exc, LLMProviderError) else True


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)
