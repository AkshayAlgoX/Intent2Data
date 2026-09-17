"""Fresh runtime validation of the canonical demo candidates against the
ACTUAL RuntimeIndex. Offline only (no provider); nothing here feeds the runtime.

For each candidate question and role it runs the real retrieval path
(intent → module BM25 top-k → family expansion) twice: with the intents the
runtime's offline stand-in derives from the question, and with the concept
phrases the demo documentation states. Each documented expectation (a code or a
label pattern) is then classified:

  FOUND_TOPK       in the runtime candidate set at the default top-k
  REACHABLE_DEEPER matching variable's module ranks 6..SCAN_K for that intent
  NOT_RETRIEVED    variable exists but its module is outside the top SCAN_K
  ABSENT           no variable in the catalog matches the expectation
  DOC_INCONSISTENT documentation names a code/file that is not in the catalog

    python scripts/validate_canonical.py [--json out.json]
"""

import json
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.offline import OfflineLexicalLLMClient  # noqa: E402
from app.llm.parsing import parse_intent_output  # noqa: E402
from app.pipeline import prompts  # noqa: E402
from app.retrieval.candidates import build_role_candidates  # noqa: E402
from app.runtime import load_runtime  # noqa: E402
from app.settings import Settings  # noqa: E402

SCAN_K = 50

# Expectations transcribed from docs/CANONICAL_DEMO_CANDIDATES.md and
# docs/CANONICAL_DEMO_VALIDATION.md. "codes" are codes the docs name
# explicitly; "labels" are regexes over variable_label for concepts the docs
# describe in words. These live only in this offline script.
CANDIDATES = [
    {"id": "1.1", "question": "How does current smoking status relate to self-reported health?",
     "roles": {"exposure": ("current smoking status smoke cigarettes", [r"SMOKE"]),
               "outcome": ("self-reported general health rating", [r"RATE.*HEALTH|HEALTH.*(EXCELLENT|RATING|STATUS)|SELF.?RATED"])}},
    {"id": "1.2", "question": "Does years of education predict household income?",
     "roles": {"exposure": ("years of education highest grade completed", [r"YEARS OF EDUC|HIGHEST GRADE|EDUCATION"]),
               "outcome": ("total household income", [r"HOUSEHOLD INCOME|HH INC|TOTAL INCOME"])},
     "doc_codes": ["RAEDUC"], "doc_labels": ["TOT HH INC"]},
    {"id": "1.3", "question": "Is there a relationship between age and retirement status?",
     "roles": {"exposure": ("respondent age", [r"^AGE\b|R AGE|AGE AT|AGE IN YEARS"]),
               "outcome": ("retirement status retired", [r"RETIRE"])}},
    {"id": "2.1", "question": "How does lifelong religious and spiritual involvement shape physical functioning in later life?",
     "roles": {"exposure": ("lifelong religious spiritual involvement childhood attend services", [r"ATTEND.*SERVICE|RELIG|SPIRITUAL"]),
               "outcome": ("physical functioning walking climbing stairs bathing dressing ADL", [r"WALK|CLIMB|BATH|DRESS|ADL"])},
     "doc_codes": ["PV355"]},
    {"id": "2.2", "question": "Does pre-pandemic functional impairment predict survival outcomes after COVID-19?",
     "roles": {"exposure": ("functional impairment ADL difficulty walking bathing dressing", [r"DIFFICULTY.*(WALK|BATH|DRESS)|ADL"]),
               "outcome": ("survival mortality death year vital status", [r"YEAR OF DEATH|VITAL STATUS|DEATH|DECEASED|ALIVE"]),
               "covariates": ("COVID-19 coronavirus pandemic infection", [r"COVID|CORONAVIRUS"])},
     "doc_codes": ["EXDEATHYR", "QALIVE"]},
    {"id": "2.3", "question": "How do childhood socioeconomic conditions affect late-life cognitive decline?",
     "roles": {"exposure": ("childhood socioeconomic status father mother education family financial situation", [r"FATHER EDUC|MOTHER EDUC|CHILDHOOD|FAMILY.*FINANC|FINANCIAL.*(CHILD|GROW)"]),
               "outcome": ("cognitive decline memory word recall", [r"MEMORY|WORD RECALL|RECALL|COGNIT|TICS"])},
     "doc_labels": ["FATHER EDUCATION- HIGHEST GRADE"]},
    {"id": "2.4", "question": "Is neighborhood social cohesion related to cardiovascular health?",
     "roles": {"exposure": ("neighborhood social cohesion neighbors trust", [r"NEIGHBOR"]),
               "outcome": ("cardiovascular health heart attack stroke hypertension", [r"HEART|STROKE|HIGH BLOOD PRESSURE|HYPERTENS"])}},
    {"id": "2.5", "question": "Does exposure to job stress over generations affect memory?",
     "roles": {"exposure": ("job stress work stress occupational", [r"STRESS"]),
               "outcome": ("memory recall", [r"MEMORY|RECALL"])}},
    {"id": "3.1", "question": "How do epigenetic aging clocks (like GrimAge) correlate with daily smartphone usage in older adults?",
     "roles": {"exposure": ("daily smartphone usage mobile phone", [r"SMARTPHONE|SMART PHONE|CELL ?PHONE|MOBILE"]),
               "outcome": ("epigenetic aging clock GrimAge DNA methylation", [r"GRIMAGE|EPIGENET|METHYLAT"])}},
    {"id": "3.2", "question": "Does localized air pollution (PM2.5) exposure drive early-onset dementia?",
     "roles": {"exposure": ("localized air pollution PM2.5 fine particulate matter", [r"PM ?2\.5|POLLUT|PARTICULATE"]),
               "outcome": ("early onset dementia Alzheimer", [r"DEMENTIA|ALZHEIMER"])}},
    {"id": "3.3", "question": "Is the balance between monocytes and protective cholesterol predicting survival?",
     "roles": {"exposure": ("monocytes HDL protective cholesterol biomarkers", [r"MONOCYTE|HDL"]),
               "outcome": ("survival mortality death", [r"YEAR OF DEATH|VITAL STATUS|DEATH|DECEASED"])}},
]


def matching_codes(index, pattern):
    rx = re.compile(pattern, re.I)
    return [c for c, v in index.variables.items() if rx.search(v.label)]


def module_rank_for(index, intent, codes, k):
    ranks = {h.module_id: h.rank for h in index.search_modules(intent, k)}
    best = None
    for c in codes:
        r = ranks.get(index.get(c).module_id)
        if r and (best is None or r < best):
            best = r
    return best


def classify(index, intent, codes, top_k, max_cands):
    if not codes:
        return "ABSENT", {"matching_in_catalog": 0}
    rc = build_role_candidates(index, "x", intent, top_k, max_cands)
    hit = sorted(set(codes) & rc.codes)
    if hit:
        return "FOUND_TOPK", {"matching_in_catalog": len(codes), "in_candidates": len(hit), "examples": hit[:5],
                              "modules": [h.module_id for h in rc.modules], "truncated": rc.truncated}
    r = module_rank_for(index, intent, codes, SCAN_K)
    if r:
        return "REACHABLE_DEEPER", {"matching_in_catalog": len(codes), "best_module_rank": r, "examples": codes[:5]}
    return "NOT_RETRIEVED", {"matching_in_catalog": len(codes), "examples": codes[:5]}


def main():
    out_path = None
    if "--json" in sys.argv:
        out_path = Path(sys.argv[sys.argv.index("--json") + 1])
    state = load_runtime(Settings.from_env())
    if not state.ready:
        print("runtime not ready:", state.index_error, file=sys.stderr)
        return 1
    idx, s = state.index, state.settings
    stand_in = OfflineLexicalLLMClient()
    report = {"index": idx.stats(), "top_k": s.module_top_k, "scan_k": SCAN_K, "candidates": []}
    for cand in CANDIDATES:
        q = cand["question"]
        runtime_intents = parse_intent_output(stand_in.generate_json("", prompts.intent_prompt(q), {}).text).roles
        entry = {"id": cand["id"], "question": q, "runtime_intents": runtime_intents, "roles": {}, "doc_checks": []}
        for role, (doc_intent, patterns) in cand["roles"].items():
            role_entry = {"doc_intent": doc_intent, "expectations": []}
            for pat in patterns:
                codes = matching_codes(idx, pat)
                res = {"pattern": pat}
                res["via_doc_intent"] = classify(idx, doc_intent, codes, s.module_top_k, s.max_candidates_per_call)
                ri = runtime_intents.get(role)
                res["via_runtime_intent"] = classify(idx, ri, codes, s.module_top_k, s.max_candidates_per_call) if ri else ("NO_RUNTIME_INTENT", {})
                role_entry["expectations"].append(res)
            entry["roles"][role] = role_entry
        for code in cand.get("doc_codes", []):
            rec = idx.get(code)
            if rec is None:
                entry["doc_checks"].append({"code": code, "status": "DOC_INCONSISTENT", "reason": "code not in catalog"})
            else:
                role = next(iter(cand["roles"]))  # doc codes belong to the first (exposure) role unless it is an outcome code
                if code in ("EXDEATHYR", "QALIVE"):
                    role = "outcome"
                di = cand["roles"][role][0]
                status, detail = classify(idx, di, [code], s.module_top_k, s.max_candidates_per_call)
                ri = runtime_intents.get(role)
                rstatus, rdetail = classify(idx, ri, [code], s.module_top_k, s.max_candidates_per_call) if ri else ("NO_RUNTIME_INTENT", {})
                entry["doc_checks"].append({"code": code, "module": rec.module_id, "label": rec.label,
                                            "via_doc_intent": [status, detail], "via_runtime_intent": [rstatus, rdetail]})
        for label in cand.get("doc_labels", []):
            codes = [c for c, v in idx.variables.items() if v.label.strip().upper() == label.upper()]
            entry["doc_checks"].append({"label": label, "status": "OK" if codes else "DOC_INCONSISTENT",
                                        "codes": codes[:5], "reason": "" if codes else "no variable with this label in catalog"})
        # the path the demo actually runs today
        resp = state.pipeline().run(q, uuid.uuid4().hex)
        entry["runtime_run"] = {"status": resp.status, "roles": {r.role: {"status": r.status, "modules": [m.module_id for m in r.modules],
                                "candidates": r.candidates.total, "selected": [x.code for x in r.selections][:8]} for r in resp.roles},
                                "limitations": [l.code for l in resp.limitations]}
        report["candidates"].append(entry)
        # console summary
        print(f"\n=== {cand['id']}  {q}\n    runtime intents: {runtime_intents}")
        for role, re_ in entry["roles"].items():
            for e in re_["expectations"]:
                d, r = e["via_doc_intent"], e["via_runtime_intent"]
                print(f"    [{role}] /{e['pattern']}/  doc-intent: {d[0]} {d[1].get('best_module_rank','')}{d[1].get('examples','')}  | runtime-intent: {r[0]} {r[1].get('best_module_rank','') if r[1] else ''}")
        for c in entry["doc_checks"]:
            print(f"    doc-check: {c}")
        print(f"    runtime_run: {entry['runtime_run']['status']} " + "; ".join(f"{k}={v['status']} sel={v['selected'][:4]}" for k, v in entry['runtime_run']['roles'].items()))
    if out_path:
        out_path.write_text(json.dumps(report, indent=2))
        print(f"\nwritten {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
