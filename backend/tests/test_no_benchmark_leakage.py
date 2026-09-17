"""Guardrail: evaluation-only artifacts must never enter the runtime package.

The benchmark CSV carries gold labels (`hrs_column_ids`) and gold-derived
temporal windows (`allowed_years`); `expanded_intents.json` carries hand-
expanded intents; the canonical demo variable codes must be *discovered* by
the pipeline, not hardcoded. Any of these in backend/app is benchmark leakage.
"""

import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"

FORBIDDEN_TOKENS = [
    "OADD_Bench",
    "hrs_column_ids",
    "allowed_years",
    "expanded_intents",
    "metadata_fixes",  # benchmark-side patch file, not a runtime input
    "mod_ceiling",     # evaluation simulation constant (see MIGRATION_MAP.txt)
    "expand_and_filter",  # evaluation helper that takes gold-derived allowed_years
]
FORBIDDEN_IMPORTS = [
    re.compile(r"^\s*(from|import)\s+evaluation\b", re.M),
    re.compile(r"^\s*(from|import)\s+Methods\b", re.M),
]
# Provider SDK imports are allowed in exactly one adapter module each.
PROVIDER_IMPORT = re.compile(r"^\s*(from|import)\s+google\b", re.M)
PROVIDER_ADAPTERS = {"app/llm/gemini.py"}
# Canonical demo targets named in docs/CANONICAL_DEMO_*.md. They may appear in
# tests as sample data, never in runtime code.
CANONICAL_DEMO_CODES = ["PV355", "EXDEATHYR", "QALIVE", "RAEDUC"]


def _runtime_sources():
    files = sorted(APP_DIR.rglob("*.py"))
    assert files, f"no runtime sources found under {APP_DIR}"
    return files


def test_no_benchmark_artifacts_in_runtime():
    offenders = []
    for path in _runtime_sources():
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_TOKENS:
            if token in text:
                offenders.append(f"{path.relative_to(APP_DIR.parent)}: {token}")
    assert not offenders, "benchmark/evaluation artifact referenced in runtime:\n" + "\n".join(offenders)


def test_no_evaluation_or_provider_imports_in_runtime():
    offenders = []
    for path in _runtime_sources():
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_IMPORTS:
            if pattern.search(text):
                offenders.append(f"{path.relative_to(APP_DIR.parent)}: {pattern.pattern}")
    assert not offenders, "forbidden import in runtime:\n" + "\n".join(offenders)


def test_provider_sdk_imported_only_in_its_adapter():
    offenders = []
    for path in _runtime_sources():
        rel = path.relative_to(APP_DIR.parent).as_posix()
        if PROVIDER_IMPORT.search(path.read_text(encoding="utf-8")) and rel not in PROVIDER_ADAPTERS:
            offenders.append(rel)
    assert not offenders, "provider SDK imported outside its adapter:\n" + "\n".join(offenders)
    # and the adapter imports it lazily (inside a function), never at module top level
    adapter = (APP_DIR / "llm" / "gemini.py").read_text(encoding="utf-8")
    top_level = [l for l in adapter.splitlines() if re.match(r"^(from|import)\s+google\b", l)]  # column 0 only
    assert not top_level, "google-genai must be imported inside functions in the adapter"


def test_canonical_demo_variables_not_hardcoded():
    offenders = []
    for path in _runtime_sources():
        text = path.read_text(encoding="utf-8")
        for code in CANONICAL_DEMO_CODES:
            if re.search(rf"\b{code}\b", text):
                offenders.append(f"{path.relative_to(APP_DIR.parent)}: {code}")
    assert not offenders, "canonical demo variable hardcoded in runtime:\n" + "\n".join(offenders)
