"""Deterministic operationalization / grounding validation.

No LLM call. It turns parsed selections into contract objects, checks that the
model's evidence is a verbatim span of the candidate it cites, and derives
limitations from what the pipeline could NOT do (empty retrieval, no grounded
selection for a role, truncated context, offline provider). It never adds or
removes variables on its own.
"""

import re

from app.llm.parsing import ParsedSelections
from app.pipeline.models import Grounding, Limitation, Rejected, RoleResult, SelectedVariable, VariableSummary
from app.retrieval.candidates import RoleCandidates
from app.retrieval.index import RuntimeIndex

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", text or "").strip().lower()


def build_selections(index: RuntimeIndex, cands: RoleCandidates, parsed: ParsedSelections, max_selections: int) -> tuple[list[SelectedVariable], int]:
    by_code = {c.code: c for c in cands.candidates}
    out: list[SelectedVariable] = []
    usable = parsed.usable
    for sel in usable[:max_selections]:
        cand = by_code.get(sel.code)
        rec = index.get(sel.code)
        if cand is None or rec is None:      # cannot happen after grounding, but never trust
            continue
        evidence = sel.evidence.strip()
        grounded = bool(evidence) and _norm(evidence) in _norm(cand.line)
        family = index.family_codes(rec.code)
        out.append(
            SelectedVariable(
                code=rec.code,
                label=rec.label,
                module_id=rec.module_id,
                section=rec.section,
                year=rec.year,
                family_id=rec.family_id,
                family_waves=[index.get(c).year for c in family if index.get(c) and index.get(c).year],
                candidate_source=cand.source,
                reason=sel.reason,
                evidence=evidence,
                grounding=Grounding(in_context=True, evidence_grounded=grounded, evidence_checked=bool(evidence)),
            )
        )
    return out, max(0, len(usable) - max_selections)


def rejected_from(parsed: ParsedSelections, over_limit: int) -> Rejected:
    return Rejected(
        out_of_context=list(parsed.out_of_context),
        hallucinated=list(parsed.hallucinated),
        parse_errors=list(parsed.errors),
        over_limit=over_limit,
    )


def summarize_variables(roles: list[RoleResult]) -> list[VariableSummary]:
    merged: dict[str, VariableSummary] = {}
    for role in roles:
        for sel in role.selections:
            if sel.code not in merged:
                merged[sel.code] = VariableSummary(
                    code=sel.code, label=sel.label, module_id=sel.module_id, year=sel.year,
                    family_id=sel.family_id, roles=[],
                )
            if role.role not in merged[sel.code].roles:
                merged[sel.code].roles.append(role.role)
    return [merged[c] for c in sorted(merged)]


def derive_limitations(roles: list[RoleResult], intent_errors: list[str], llm_live: bool, intent_role_count: int) -> list[Limitation]:
    lims: list[Limitation] = []
    if intent_role_count == 0:
        lims.append(Limitation(code="no_roles", message="The question could not be decomposed into any measurable role."))
    for err in intent_errors:
        lims.append(Limitation(code="intent_parse_warning", message=err))
    for r in roles:
        if r.status == "empty_retrieval":
            lims.append(Limitation(code="empty_retrieval", role=r.role,
                                   message=f"No codebook module matched the '{r.role}' intent; this concept may not be measurable in this dataset."))
        elif r.status == "no_selection":
            lims.append(Limitation(code="no_grounded_selection", role=r.role,
                                   message=f"Modules were retrieved for '{r.role}' but no candidate variable was selected."))
        elif r.status == "failed":
            lims.append(Limitation(code="role_failed", role=r.role, message=r.error or "role stage failed"))
        cov = r.intent_coverage
        if cov and not cov.terms:
            lims.append(Limitation(code="no_concept_terms", role=r.role,
                                   message=f"The '{r.role}' intent contains no concept term (only function words or numbers); any retrieved modules were ranked on generic words."))
        if cov and cov.unmatched:
            all_gone = cov.coverage == 0.0
            lims.append(Limitation(
                code="concept_terms_unmatched", role=r.role,
                message=(f"Intent term(s) {', '.join(repr(t) for t in cov.unmatched)} occur in no module document of this catalog; "
                         + ("no concept term matched, so the retrieved modules were ranked on generic words only."
                            if all_gone else "retrieval relied on the remaining term(s) " + ", ".join(repr(t) for t in cov.terms if t not in cov.unmatched) + ".")),
            ))
        if r.candidates.truncated:
            lims.append(Limitation(code="candidates_truncated", role=r.role,
                                   message="Candidate set exceeded the per-call cap; lowest-provenance candidates were not shown."))
        if r.rejected.hallucinated:
            lims.append(Limitation(code="hallucinated_ids_dropped", role=r.role,
                                   message=f"{len(r.rejected.hallucinated)} returned code(s) were not in the catalog and were dropped."))
        if r.rejected.out_of_context:
            lims.append(Limitation(code="ungrounded_ids_dropped", role=r.role,
                                   message=f"{len(r.rejected.out_of_context)} returned code(s) were real variables not shown to the model and were dropped."))
        ungrounded = [s.code for s in r.selections if s.grounding.evidence_checked and not s.grounding.evidence_grounded]
        if ungrounded:
            lims.append(Limitation(code="evidence_not_verbatim", role=r.role,
                                   message=f"Evidence for {len(ungrounded)} selection(s) is not a verbatim codebook span; treat their rationale with caution."))
    if not llm_live:
        lims.append(Limitation(code="offline_llm",
                               message="Selections were produced by a deterministic offline stand-in, not a language model. This run demonstrates pipeline behaviour, not model quality."))
    return lims
