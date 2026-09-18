"""Deterministic, network-free stand-in for an LLM.

It exists so the complete pipeline can run end-to-end (tests, CI, a demo with
no provider quota). It is NOT a model: intent roles come from cue-word
splitting of the question and selections from lexical overlap between the
role intent and each candidate line. Every response is stamped
model="offline-lexical" and the API surfaces `llm.live = false` so nothing it
produces can be mistaken for measured model behaviour.
"""

import json
import re
import time
from collections import deque

from app.llm.client import CALL_HISTORY, LLMResponse
from app.retrieval.text import tokenize

MODEL_NAME = "offline-lexical"
_STOP = {
    "the", "a", "an", "of", "in", "on", "to", "and", "or", "is", "are", "be", "with", "by", "for",
    "does", "do", "how", "could", "might", "can", "there", "between", "relate", "related", "relationship",
    "associated", "association", "affect", "affects", "predict", "predicts", "shape", "shapes", "drive",
    "drives", "later", "life", "among", "older", "adults", "what", "whether", "influence", "impact",
}
# Relational cue phrases: the left side is treated as exposure, the right as outcome.
_CUES = [
    r"\bassociated with\b", r"\brelated to\b", r"\brelate to\b", r"\brelationship between\b",
    r"\baffect(?:s)?\b", r"\bpredict(?:s)?\b", r"\bshape(?:s)?\b", r"\bdrive(?:s)?\b",
    r"\bcontribute to\b", r"\binfluence(?:s)?\b", r"\bimpact(?:s)?\b", r"\bconnected to\b",
    r"\blinked to\b", r"\band\b",
]
_YEAR = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")


def _clean(text: str) -> str:
    text = re.sub(r"^\s*(does|do|is|are|could|might|can|how|what|whether|there)\b\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"^\s*(does|do|is|are|a|an|the)\b\s*", "", text, flags=re.I)
    return text.strip(" ?.,")


class OfflineLexicalLLMClient:
    def __init__(self, max_selections: int = 10, history: int = 0):
        self.max_selections = max_selections
        # Production default keeps no prompt text at all (history=0): only a
        # counter and a bounded ring of small call summaries.
        self.call_count = 0
        self.calls: deque = deque(maxlen=history if history > 0 else CALL_HISTORY)
        self._keep_prompts = history > 0

    # The orchestrator tags every prompt with a task line so the stand-in knows
    # which fake to produce; a real provider ignores the tag.
    def generate_json(self, system: str, prompt: str, schema: dict) -> LLMResponse:
        start = time.perf_counter()
        self.call_count += 1
        if self._keep_prompts:
            self.calls.append({"system": system, "prompt": prompt, "schema": schema})
        else:
            self.calls.append({"task": prompt.split("\n", 1)[0], "prompt_chars": len(prompt)})
        if prompt.startswith("TASK: intent"):
            text = self._intent(prompt)
        else:
            text = self._select(prompt)
        return LLMResponse(text=text, model=MODEL_NAME, latency_s=time.perf_counter() - start)

    # ---- fakes ---------------------------------------------------------------
    def _intent(self, prompt: str) -> str:
        question = prompt.split("QUESTION:", 1)[-1].strip()
        exposure, outcome = question, ""
        for cue in _CUES:
            parts = re.split(cue, question, maxsplit=1, flags=re.I)
            if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                exposure, outcome = parts[0], parts[1]
                break
        roles = {"exposure": _clean(exposure)}
        if _clean(outcome):
            roles["outcome"] = _clean(outcome)
        if re.search(r"\b(older adults?|elderly|retire|respondents?|women|men|veterans?)\b", question, re.I):
            roles["population"] = re.search(r"\b(older adults?|elderly|retirees?|respondents?|women|men|veterans?)\b", question, re.I).group(0)
        years = _YEAR.findall(question)
        if years:
            roles["temporal"] = " ".join(sorted(set(years)))
        return json.dumps({"roles": roles})

    def _select(self, prompt: str) -> str:
        concept = prompt.split("RESEARCH CONCEPT:", 1)[-1].split("CANDIDATES:", 1)[0]
        terms = {t for t in tokenize(concept) if t not in _STOP and len(t) > 2}
        block = prompt.split("CANDIDATES:", 1)[-1]
        scored = []
        for line in block.strip().splitlines():
            parts = line.split(" | ", 2)
            if len(parts) < 2:
                continue
            code = parts[0].strip()
            label_terms = set(tokenize(parts[1]))
            text_terms = set(tokenize(parts[2])) if len(parts) > 2 else set()
            overlap_label = terms & label_terms
            overlap_text = terms & text_terms
            score = 2 * len(overlap_label) + len(overlap_text)
            if score:
                evidence = parts[1].strip() if overlap_label else " ".join(parts[2].split()[:12])
                scored.append((-score, code, evidence, sorted(overlap_label | overlap_text)))
        scored.sort()
        selections = [
            {"column_name": code, "reason": "lexical overlap: " + ", ".join(hits), "evidence": evidence}
            for _, code, evidence, hits in scored[: self.max_selections]
        ]
        return json.dumps({"selections": selections})
