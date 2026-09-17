"""Defensive parsing and grounding of LLM selection output.

The LLM is asked for {"selections": [{"column_name", "reason", "evidence"}]}.
Anything it returns is untrusted: it may be non-JSON, the wrong shape, contain
duplicates, codes with stray whitespace/case, or codes that were never in the
candidate set. This module never raises on model output; it classifies it.

Classification mirrors evaluation/results/EXP24_SCORING_SPEC.md so the runtime
and the evaluation agree on what "grounded" means:
  in_context    -> code was in the candidate set shown to the model (usable)
  out_of_context-> real variable, but not shown to the model (NOT usable at
                   runtime: it is ungrounded even if it happens to be right)
  hallucinated  -> not a known variable at all
"""

import json
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

_WS = re.compile(r"\s+")
MAX_REASON_CHARS = 500
MAX_EVIDENCE_CHARS = 1000


def normalize_code(code: object) -> str:
    """Canonical variable code: no whitespace, upper-case. Matches the
    benchmark's normalization so runtime and evaluation compare like with like."""
    return _WS.sub("", str(code)).upper()


@dataclass(frozen=True)
class Selection:
    code: str
    reason: str = ""
    evidence: str = ""


@dataclass
class ParsedSelections:
    parse_ok: bool
    in_context: list[Selection] = field(default_factory=list)
    out_of_context: list[str] = field(default_factory=list)
    hallucinated: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def usable(self) -> list[Selection]:
        """What the pipeline may forward. Only grounded selections."""
        return list(self.in_context)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text


def _clip(value: object, limit: int) -> str:
    return str(value)[:limit] if value is not None else ""


def parse_selection_output(
    raw_text: Optional[str],
    candidate_ids: Iterable[str],
    known_ids: Optional[Iterable[str]] = None,
) -> ParsedSelections:
    """Parse and ground one LLM selection response.

    candidate_ids: exactly the codes shown to the model in this call.
    known_ids: every code in the catalog (optional). Used only to distinguish
      out_of_context from hallucinated; both are dropped from `usable`.
    """
    result = ParsedSelections(parse_ok=False)
    cand = {normalize_code(c) for c in candidate_ids}
    known = {normalize_code(c) for c in known_ids} if known_ids is not None else None

    if not raw_text or not str(raw_text).strip():
        result.errors.append("empty response")
        return result

    try:
        data = json.loads(_strip_code_fence(str(raw_text)))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        result.errors.append(f"invalid json: {exc.__class__.__name__}")
        return result

    # Accept either the documented envelope or a bare list.
    if isinstance(data, dict):
        selections = data.get("selections", [])
    elif isinstance(data, list):
        selections = data
    else:
        result.errors.append(f"unexpected top-level type: {type(data).__name__}")
        return result

    if not isinstance(selections, list):
        result.errors.append("'selections' is not a list")
        return result

    result.parse_ok = True
    seen: set[str] = set()
    for item in selections:
        if isinstance(item, str):
            item = {"column_name": item}
        if not isinstance(item, dict):
            result.errors.append(f"selection item is {type(item).__name__}, not object")
            continue
        raw_code = item.get("column_name", item.get("code"))
        if raw_code is None or not str(raw_code).strip():
            result.errors.append("selection missing column_name")
            continue
        code = normalize_code(raw_code)
        if code in seen:
            continue
        seen.add(code)

        if code in cand:
            result.in_context.append(
                Selection(
                    code=code,
                    reason=_clip(item.get("reason"), MAX_REASON_CHARS),
                    evidence=_clip(item.get("evidence"), MAX_EVIDENCE_CHARS),
                )
            )
        elif known is not None and code in known:
            result.out_of_context.append(code)
        else:
            result.hallucinated.append(code)
    return result


# ---------------------------------------------------------------------------
# Intent output
# ---------------------------------------------------------------------------

ROLES = ("exposure", "outcome", "population", "covariates", "secondary", "temporal", "proxies")
_ROLE_ALIASES = {
    "primary outcome": "outcome",
    "primary_outcome": "outcome",
    "secondary outcomes": "secondary",
    "secondary_outcomes": "secondary",
    "confounders": "covariates",
    "covariate": "covariates",
    "temporal constraints": "temporal",
    "temporal_constraints": "temporal",
    "proxy": "proxies",
}
MAX_INTENT_CHARS = 600


@dataclass
class ParsedIntent:
    parse_ok: bool
    roles: dict[str, str] = field(default_factory=dict)   # role -> intent text (ordered as ROLES)
    errors: list[str] = field(default_factory=list)


def parse_intent_output(raw_text: Optional[str]) -> ParsedIntent:
    """Parse {"roles": {"exposure": "...", ...}} or {"roles": [{"role","intent"}]}.

    Unknown roles are dropped (with an error note), blank intents are dropped,
    output order is canonical, and nothing here ever raises on model output.
    """
    result = ParsedIntent(parse_ok=False)
    if not raw_text or not str(raw_text).strip():
        result.errors.append("empty response")
        return result
    try:
        data = json.loads(_strip_code_fence(str(raw_text)))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        result.errors.append(f"invalid json: {exc.__class__.__name__}")
        return result

    roles_obj = data.get("roles", data) if isinstance(data, dict) else data
    pairs: list[tuple[object, object]] = []
    if isinstance(roles_obj, dict):
        pairs = list(roles_obj.items())
    elif isinstance(roles_obj, list):
        for item in roles_obj:
            if isinstance(item, dict):
                pairs.append((item.get("role"), item.get("intent", item.get("query"))))
            else:
                result.errors.append(f"role item is {type(item).__name__}, not object")
    else:
        result.errors.append(f"unexpected roles type: {type(roles_obj).__name__}")
        return result

    result.parse_ok = True
    found: dict[str, str] = {}
    for role, intent in pairs:
        key = str(role or "").strip().lower()
        key = _ROLE_ALIASES.get(key, key)
        if key not in ROLES:
            result.errors.append(f"unknown role dropped: {role!r}")
            continue
        if isinstance(intent, list):
            intent = " ".join(str(x) for x in intent)
        text = _WS.sub(" ", str(intent or "")).strip()[:MAX_INTENT_CHARS]
        if not text:
            continue
        found.setdefault(key, text)
    result.roles = {r: found[r] for r in ROLES if r in found}
    return result
