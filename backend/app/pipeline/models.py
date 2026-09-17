"""Contract v1 response model for POST /v1/analyze.

Frozen shape. Additive changes only; anything removed or renamed is v2.
Field semantics are documented in contracts/v1/README.md.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

RoleStatus = Literal["ok", "no_selection", "empty_retrieval", "failed"]
ResponseStatus = Literal["ok", "partial", "failed"]


class IntentRole(BaseModel):
    role: str
    intent: str


class Intent(BaseModel):
    roles: list[IntentRole]
    source: str = "llm"           # which client produced it (model name)
    errors: list[str] = Field(default_factory=list)


class ModuleRef(BaseModel):
    module_id: str
    rank: int
    score: float
    product_key: str
    product_title: str
    section: str
    section_title: str
    variable_count: int


class CandidateStats(BaseModel):
    retrieved: int                 # variables inside the retrieved modules
    family_expanded: int           # cross-wave siblings added structurally
    total: int                     # what the LLM was shown
    truncated: bool


class Grounding(BaseModel):
    in_context: bool               # code was in the candidate set shown to the model
    evidence_grounded: bool        # evidence string is a verbatim span of that candidate
    evidence_checked: bool         # False when the model gave no evidence


class SelectedVariable(BaseModel):
    code: str
    label: str
    module_id: str
    section: str
    year: str
    family_id: str
    family_waves: list[str]        # years of every sibling in the same family
    candidate_source: str          # "module" | "family": how it entered the candidate set
    reason: str
    evidence: str
    grounding: Grounding


class Rejected(BaseModel):
    out_of_context: list[str] = Field(default_factory=list)
    hallucinated: list[str] = Field(default_factory=list)
    parse_errors: list[str] = Field(default_factory=list)
    over_limit: int = 0            # selections dropped by max_selections_per_role


class RoleResult(BaseModel):
    role: str
    intent: str
    status: RoleStatus
    modules: list[ModuleRef]
    candidates: CandidateStats
    selections: list[SelectedVariable]
    rejected: Rejected
    error: Optional[str] = None


class VariableSummary(BaseModel):
    code: str
    label: str
    module_id: str
    year: str
    family_id: str
    roles: list[str]


class Limitation(BaseModel):
    code: str
    role: Optional[str] = None
    message: str


class StageTiming(BaseModel):
    ms: float
    detail: dict = Field(default_factory=dict)


class LLMInfo(BaseModel):
    provider: str
    model: str
    live: bool                     # False for the offline stand-in; never claim model quality when False
    calls: int
    failed_calls: int
    retries: int = 0               # retry attempts the orchestrator made (retryable failures only)


class IndexInfo(BaseModel):
    variables: int
    modules: int
    families: int
    fingerprint: str


class AnalyzeResponse(BaseModel):
    contract: str = "v1"
    request_id: str
    status: ResponseStatus
    question: str
    intent: Intent
    roles: list[RoleResult]
    variables: list[VariableSummary]
    limitations: list[Limitation]
    stages: dict[str, StageTiming]
    llm: LLMInfo
    index: IndexInfo
