"""Role-aware candidate construction: module-first retrieval, then structural
family expansion, with deterministic ordering and a hard size cap.

The temporal scope is deliberately NOT applied here. The validated design
(Exp24) expands every wave of a retrieved family and lets selection/validation
reason about time; any wave filter must come from the request's own intent,
never from an external answer key.
"""

from dataclasses import dataclass, field

from app.retrieval.index import ModuleHit, RuntimeIndex
from app.retrieval.text import content_tokens


@dataclass(frozen=True)
class Candidate:
    code: str
    origin_rank: int          # rank of the module that brought it in (1 = best)
    source: str               # "module" | "family"
    line: str                 # compact representation shown to the LLM


@dataclass
class RoleCandidates:
    role: str
    intent: str
    modules: list[ModuleHit] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    retrieved_count: int = 0      # variables from the retrieved modules
    expanded_count: int = 0       # additional cross-wave siblings
    truncated: bool = False
    terms: list[str] = field(default_factory=list)            # intent concept terms, in intent order
    matched_terms: list[str] = field(default_factory=list)    # intent concept terms present in the catalog vocabulary
    unmatched_terms: list[str] = field(default_factory=list)  # intent concept terms absent from every module document
    top_score: float = 0.0                                    # BM25 score of the best module
    max_possible_score: float = 0.0                           # saturation bound for this intent (see BM25Index)

    @property
    def codes(self) -> set[str]:
        return {c.code for c in self.candidates}

    @property
    def lines(self) -> list[str]:
        return [c.line for c in self.candidates]


def build_role_candidates(index: RuntimeIndex, role: str, intent: str, top_k: int, max_candidates: int) -> RoleCandidates:
    result = RoleCandidates(role=role, intent=intent)
    if not intent or not intent.strip():
        return result
    result.matched_terms, result.unmatched_terms = index.intent_coverage(intent)
    result.terms = [t for t in content_tokens(intent)]
    result.max_possible_score = round(index.max_possible_score(intent), 6)
    result.modules = index.search_modules(intent, top_k)
    if not result.modules:
        return result
    result.top_score = result.modules[0].score

    origin: dict[str, tuple[int, str]] = {}   # code -> (best origin rank, source)
    for hit in result.modules:
        for code in index.module_codes(hit.module_id):
            if code not in origin or hit.rank < origin[code][0]:
                origin[code] = (hit.rank, "module")
    result.retrieved_count = len(origin)

    for code, (rank, _) in list(origin.items()):
        for sibling in index.family_codes(code):
            if sibling not in origin:
                origin[sibling] = (rank, "family")
    result.expanded_count = len(origin) - result.retrieved_count

    # Deterministic: best module rank first, retrieved before family-expanded,
    # then code. Truncation therefore drops the weakest-provenance items first.
    ordered = sorted(origin.items(), key=lambda kv: (kv[1][0], kv[1][1] != "module", kv[0]))
    if len(ordered) > max_candidates:
        ordered = ordered[:max_candidates]
        result.truncated = True
    for code, (rank, source) in ordered:
        rec = index.get(code)
        if rec is None:
            continue
        result.candidates.append(Candidate(code=code, origin_rank=rank, source=source, line=rec.compact_line()))
    return result
