from app.retrieval.bm25 import BM25Index
from app.retrieval.candidates import build_role_candidates
from app.retrieval.families import family_key
from app.retrieval.index import RuntimeIndex
from tests.conftest import synthetic_records


def test_index_stats_and_module_ids(index):
    stats = index.stats()
    assert stats["variables"] == 3 * 7 + 1
    assert stats["modules"] == 3 * 3 + 1          # 3 waves x 3 sections + tracker
    assert stats["families"] == 7 + 1             # each item is one cross-wave family
    assert index.module_codes("2004_core::C") == ["JC030", "JC010", "JC110"]


def test_family_key_groups_waves_and_ignores_wave_prefix():
    recs = {r["variable_code"]: r for r in synthetic_records()}
    assert family_key(recs["JC030"]) == family_key(recs["KC030"]) == family_key(recs["LC030"])
    assert family_key(recs["JC030"]) != family_key(recs["JD110"])


def test_family_codes_are_wave_ordered(index):
    assert index.family_codes("KC030") == ["JC030", "KC030", "LC030"]
    assert index.family_codes("NOPE") == []


def test_bm25_is_deterministic_and_ties_break_by_id():
    idx = BM25Index(["b", "a", "c"], ["lung disease", "lung disease", "blood pressure"])
    first = idx.search("lung", 10)
    second = idx.search("lung", 10)
    assert first == second
    assert [d for d, _ in first] == ["a", "b"]     # equal scores -> id order
    assert idx.search("zzz-unknown", 10) == []       # no scored docs, no arbitrary docs
    assert idx.search("lung", 0) == []


def test_module_search_ranks_matching_section_first(index):
    hits = index.search_modules("chronic lung disease doctor", 3)
    assert hits and all(h.module_id.endswith("::C") for h in hits)
    assert [h.rank for h in hits] == [1, 2, 3]


def test_candidates_module_first_then_family_deterministic(index):
    a = build_role_candidates(index, "outcome", "lung disease", top_k=1, max_candidates=100)
    b = build_role_candidates(index, "outcome", "lung disease", top_k=1, max_candidates=100)
    assert [c.code for c in a.candidates] == [c.code for c in b.candidates]
    assert len(a.modules) == 1
    assert a.retrieved_count == 3                    # one wave of section C
    assert a.expanded_count == 6                     # the other two waves of those 3 items
    sources = [c.source for c in a.candidates]
    assert sources == ["module"] * 3 + ["family"] * 6
    assert [c.code for c in a.candidates][:3] == sorted(c.code for c in a.candidates[:3])
    assert not a.truncated
    assert all(" | " in line for line in a.lines)


def test_candidates_truncate_lowest_provenance_first(index):
    rc = build_role_candidates(index, "outcome", "lung disease", top_k=1, max_candidates=4)
    assert rc.truncated
    assert len(rc.candidates) == 4
    assert [c.source for c in rc.candidates] == ["module", "module", "module", "family"]


def test_candidates_empty_for_blank_or_unmatched_intent(index):
    assert build_role_candidates(index, "x", "   ", 5, 100).candidates == []
    rc = build_role_candidates(index, "x", "quantum chromodynamics", 5, 100)
    assert rc.modules == [] and rc.candidates == []


def test_index_cache_roundtrip(tmp_path, index):
    path = tmp_path / "idx.json.gz"
    index.save(path)
    loaded = RuntimeIndex.load(path)
    assert loaded.stats() == index.stats()
    assert loaded.family_codes("KC030") == index.family_codes("KC030")
    assert loaded.search_modules("lung disease", 2) == index.search_modules("lung disease", 2)


def test_load_or_build_rebuilds_on_corrupt_cache(tmp_path):
    meta = tmp_path / "meta.jsonl"
    import json
    meta.write_text("\n".join(json.dumps(r) for r in synthetic_records()))
    cache = tmp_path / "cache.json.gz"
    cache.write_bytes(b"not gzip")
    idx, timings = RuntimeIndex.load_or_build(meta, cache)
    assert idx.stats()["variables"] == 22
    assert "cache_error" in timings and "build_s" in timings and cache.exists()
    idx2, timings2 = RuntimeIndex.load_or_build(meta, cache)
    assert "load_cache_s" in timings2 and idx2.fingerprint == idx.fingerprint
