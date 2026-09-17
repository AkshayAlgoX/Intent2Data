"""Deterministic retrieval-stage signals: intent-term coverage (a limitation)
and the descriptive, uncalibrated retrieval strength (never a limitation)."""

from app.llm.client import StaticLLMClient
from app.retrieval.candidates import build_role_candidates
from app.retrieval.text import content_tokens
from tests.conftest import intent_json, selection_json

Q = "Does localized air pollution drive chronic lung disease?"


def test_content_tokens_drop_function_words_numbers_and_duplicates():
    assert content_tokens("Is there a relationship between age and retirement status in 2010?") == ["age", "retirement", "status"]
    assert content_tokens("lung disease lung DISEASE 5") == ["lung", "disease"]
    assert content_tokens("") == []


def test_intent_coverage_and_max_score_on_index(index):
    matched, unmatched = index.intent_coverage("localized air pollution lung disease")
    assert matched == ["lung", "disease"] and unmatched == ["localized", "air", "pollution"]
    assert index.max_possible_score("lung disease") > index.search_modules("lung disease", 1)[0].score > 0
    assert index.max_possible_score("zzz qqq") == 0.0


def test_role_candidates_carry_signals(index):
    rc = build_role_candidates(index, "x", "localized pollution lung disease", 2, 100)
    assert rc.unmatched_terms == ["localized", "pollution"] and rc.matched_terms == ["lung", "disease"]
    assert 0 < rc.top_score <= rc.max_possible_score
    blank = build_role_candidates(index, "x", "   ", 2, 100)
    assert blank.matched_terms == blank.unmatched_terms == [] and blank.top_score == 0.0


def _run(make_client, intent, sel='{"selections": []}'):
    client = make_client(llm=StaticLLMClient([intent_json(exposure=intent), sel]))
    return client.post("/v1/analyze", json={"question": Q}).json()


def test_unmatched_concept_terms_become_a_limitation_with_partial_coverage(make_client):
    body = _run(make_client, "localized air pollution lung disease")
    role = body["roles"][0]
    assert role["intent_coverage"] == {"terms": ["localized", "air", "pollution", "lung", "disease"],
                                       "unmatched": ["localized", "air", "pollution"], "coverage": 0.4}
    lims = [l for l in body["limitations"] if l["code"] == "concept_terms_unmatched"]
    assert len(lims) == 1 and lims[0]["role"] == "exposure"
    assert "'pollution'" in lims[0]["message"] and "relied on the remaining term(s) 'lung', 'disease'" in lims[0]["message"]


def test_fully_covered_intent_has_no_coverage_limitation(make_client):
    # coverage is measured over module documents (titles + labels), which is the
    # vocabulary module retrieval uses; "chronic" exists only in question_text here
    body = _run(make_client, "lung disease", selection_json("JC030"))
    role = body["roles"][0]
    assert role["intent_coverage"]["unmatched"] == [] and role["intent_coverage"]["coverage"] == 1.0
    assert not any(l["code"] == "concept_terms_unmatched" for l in body["limitations"])


def test_all_terms_unmatched_is_reported_as_generic_only_or_empty_retrieval(make_client):
    # every concept term absent -> BM25 has nothing -> empty_retrieval; coverage 0 is reported on the role
    body = _run(make_client, "quantum chromodynamics")
    role = body["roles"][0]
    assert role["status"] == "empty_retrieval"
    assert role["intent_coverage"]["coverage"] == 0.0 and role["retrieval"]["top_score"] == 0.0
    codes = {l["code"] for l in body["limitations"]}
    assert {"empty_retrieval", "concept_terms_unmatched"} <= codes
    msg = next(l["message"] for l in body["limitations"] if l["code"] == "concept_terms_unmatched")
    assert "generic words only" in msg


def test_retrieval_strength_is_descriptive_and_bounded(make_client):
    body = _run(make_client, "chronic lung disease", selection_json("JC030"))
    sig = body["roles"][0]["retrieval"]
    assert 0 < sig["strength"] <= 1.0
    assert abs(sig["strength"] - sig["top_score"] / sig["max_possible_score"]) < 1e-3
    # no limitation is ever derived from strength alone
    assert not any("strength" in l["code"] or "weak_retrieval" in l["code"] for l in body["limitations"])
