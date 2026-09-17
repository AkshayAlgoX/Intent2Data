"""Provider-agnostic LLM boundary for the Intent2Data runtime.

Nothing in this package imports a provider SDK. Provider adapters live in
their own modules and implement the LLMClient protocol; everything downstream
of the boundary works on parsed, grounded Python objects only.
"""

from app.llm.client import LLMClient, LLMResponse, StaticLLMClient
from app.llm.parsing import (
    ROLES,
    ParsedIntent,
    ParsedSelections,
    Selection,
    normalize_code,
    parse_intent_output,
    parse_selection_output,
)

__all__ = [
    "LLMClient",
    "LLMResponse",
    "StaticLLMClient",
    "ROLES",
    "ParsedIntent",
    "ParsedSelections",
    "parse_intent_output",
    "Selection",
    "normalize_code",
    "parse_selection_output",
]
