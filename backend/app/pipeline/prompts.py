"""Prompt text for the two LLM stages. Kept identical in structure to the
prompts used by the validated offline experiments (QUESTION / ROLE / RESEARCH
CONCEPT / CANDIDATES) so a live provider sees the same shape they measured."""

INTENT_SYSTEM = (
    "You decompose a research question into independent search intents. "
    "Return JSON: {\"roles\": {role: intent}} using only these roles: "
    "exposure, outcome, population, covariates, secondary, temporal, proxies. "
    "Each intent is a short keyword-rich phrase describing what a dataset variable "
    "would have to measure. Omit roles the question does not imply."
)
INTENT_SCHEMA = {
    "type": "object",
    "properties": {"roles": {"type": "object", "additionalProperties": {"type": "string"}}},
    "required": ["roles"],
}

FILTER_SYSTEM = (
    "You select dataset variables that operationalize a research concept.\n"
    "Only return variables that appear in the supplied candidate set.\n"
    "Do not invent variable codes.\n"
    "If no candidate adequately measures the concept, return an empty selection."
)
FILTER_SCHEMA = {
    "type": "object",
    "properties": {
        "selections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "column_name": {"type": "string"},
                    "reason": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["column_name"],
            },
        }
    },
    "required": ["selections"],
}


def intent_prompt(question: str) -> str:
    return f"TASK: intent\nQUESTION:\n{question}"


def filter_prompt(question: str, role: str, intent: str, candidate_lines: list[str]) -> str:
    return (
        f"TASK: select\nQUESTION:\n{question}\n\nROLE:\n{role}\n\n"
        f"RESEARCH CONCEPT:\n{intent}\n\nCANDIDATES:\n" + "\n".join(candidate_lines)
    )
