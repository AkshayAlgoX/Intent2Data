import json

import pytest

from app.llm import StaticLLMClient, normalize_code, parse_selection_output

CANDS = ["NC030", "MC030", "QJ547"]
KNOWN = CANDS + ["RAEDUC", "XX999"]


def _ok(payload):
    return json.dumps(payload)


def test_happy_path_grounded_selection():
    raw = _ok({"selections": [{"column_name": "NC030", "reason": "lung disease", "evidence": "LUNG DISEASE"}]})
    parsed = parse_selection_output(raw, CANDS, KNOWN)
    assert parsed.parse_ok
    assert [s.code for s in parsed.usable] == ["NC030"]
    assert parsed.in_context[0].evidence == "LUNG DISEASE"
    assert not parsed.errors


def test_empty_selection_is_valid_not_error():
    parsed = parse_selection_output('{"selections": []}', CANDS, KNOWN)
    assert parsed.parse_ok and parsed.usable == [] and not parsed.errors


@pytest.mark.parametrize("raw", [None, "", "   ", "not json at all", "{'single': 'quotes'}", "{\"selections\": "])
def test_garbage_never_raises(raw):
    parsed = parse_selection_output(raw, CANDS, KNOWN)
    assert parsed.parse_ok is False
    assert parsed.usable == []
    assert parsed.errors


def test_code_fenced_json_is_accepted():
    raw = "```json\n" + _ok({"selections": [{"column_name": "QJ547"}]}) + "\n```"
    parsed = parse_selection_output(raw, CANDS, KNOWN)
    assert [s.code for s in parsed.usable] == ["QJ547"]


def test_bare_list_and_bare_strings_accepted():
    parsed = parse_selection_output(_ok(["NC030", {"code": "MC030"}]), CANDS, KNOWN)
    assert [s.code for s in parsed.usable] == ["NC030", "MC030"]


@pytest.mark.parametrize("payload", [42, "just a string", {"selections": "NC030"}, {"selections": {"a": 1}}])
def test_wrong_shapes_are_rejected_cleanly(payload):
    parsed = parse_selection_output(_ok(payload), CANDS, KNOWN)
    assert parsed.usable == []
    assert parsed.errors


def test_out_of_context_is_not_usable_even_if_real():
    # A real variable the model was never shown is ungrounded at runtime.
    parsed = parse_selection_output(_ok({"selections": [{"column_name": "RAEDUC"}]}), CANDS, KNOWN)
    assert parsed.usable == []
    assert parsed.out_of_context == ["RAEDUC"]
    assert parsed.hallucinated == []


def test_unknown_code_is_hallucinated():
    parsed = parse_selection_output(_ok({"selections": [{"column_name": "MADEUP1"}]}), CANDS, KNOWN)
    assert parsed.hallucinated == ["MADEUP1"] and parsed.usable == []


def test_without_known_ids_everything_off_context_is_hallucinated():
    parsed = parse_selection_output(_ok({"selections": [{"column_name": "RAEDUC"}]}), CANDS)
    assert parsed.hallucinated == ["RAEDUC"]


def test_duplicates_and_whitespace_case_are_normalized():
    raw = _ok({"selections": [{"column_name": " nc030 "}, {"column_name": "NC030"}, {"column_name": "N C030"}]})
    parsed = parse_selection_output(raw, CANDS, KNOWN)
    assert [s.code for s in parsed.usable] == ["NC030"]
    assert normalize_code(" n c 030 ") == "NC030"


def test_bad_items_are_skipped_not_fatal():
    raw = _ok({"selections": [None, 7, {"reason": "no code"}, {"column_name": ""}, {"column_name": "MC030"}]})
    parsed = parse_selection_output(raw, CANDS, KNOWN)
    assert [s.code for s in parsed.usable] == ["MC030"]
    assert len(parsed.errors) == 4


def test_reason_and_evidence_are_clipped():
    raw = _ok({"selections": [{"column_name": "NC030", "reason": "r" * 5000, "evidence": "e" * 5000}]})
    parsed = parse_selection_output(raw, CANDS, KNOWN)
    assert len(parsed.in_context[0].reason) == 500
    assert len(parsed.in_context[0].evidence) == 1000


def test_static_client_serves_then_falls_back():
    client = StaticLLMClient(responses=['{"selections": [{"column_name": "NC030"}]}'])
    first = client.generate_json("sys", "p1", {})
    second = client.generate_json("sys", "p2", {})
    assert "NC030" in first.text
    assert json.loads(second.text) == {"selections": []}
    assert [c["prompt"] for c in client.calls] == ["p1", "p2"]


# ---------------------------------------------------------------------------
# Intent parsing
# ---------------------------------------------------------------------------
from app.llm import parse_intent_output  # noqa: E402


def test_intent_dict_form_canonical_order():
    parsed = parse_intent_output(json.dumps({"roles": {"outcome": "b", "exposure": "a", "temporal": "2010 2012"}}))
    assert parsed.parse_ok and list(parsed.roles) == ["exposure", "outcome", "temporal"]


def test_intent_list_form_and_aliases():
    raw = json.dumps({"roles": [{"role": "Primary Outcome", "intent": "x"}, {"role": "confounders", "intent": ["age", "sex"]}]})
    parsed = parse_intent_output(raw)
    assert parsed.roles == {"outcome": "x", "covariates": "age sex"}


def test_intent_unknown_and_blank_roles_dropped():
    parsed = parse_intent_output(json.dumps({"roles": {"mediator": "m", "exposure": "  ", "outcome": "y"}}))
    assert parsed.roles == {"outcome": "y"}
    assert any("mediator" in e for e in parsed.errors)


@pytest.mark.parametrize("raw", [None, "", "nope", "[1, 2]", json.dumps({"roles": 5}), json.dumps(42)])
def test_intent_garbage_never_raises(raw):
    parsed = parse_intent_output(raw)
    assert parsed.roles == {}
    assert parsed.errors or not parsed.parse_ok


def test_intent_fenced_and_bare_dict_accepted():
    parsed = parse_intent_output("```json\n{\"exposure\": \"lung\"}\n```")
    assert parsed.roles == {"exposure": "lung"}
    assert len(parse_intent_output(json.dumps({"roles": {"exposure": "x" * 5000}})).roles["exposure"]) == 600
