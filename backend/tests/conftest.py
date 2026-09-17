import json
import os
import sys
from pathlib import Path

import pytest

# Make `import app` work whether pytest is run from backend/ or the repo root,
# and never build the real index during tests.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("INTENT2DATA_BUILD_INDEX_ON_STARTUP", "0")

from fastapi.testclient import TestClient  # noqa: E402

from app.llm.client import StaticLLMClient  # noqa: E402
from app.main import app, get_runtime  # noqa: E402
from app.retrieval.index import RuntimeIndex  # noqa: E402
from app.runtime import RuntimeState  # noqa: E402
from app.settings import Settings  # noqa: E402


def _rec(code, label, section, year, product="core", qtext="", product_key=None, section_title=None):
    return {
        "variable_code": code,
        "variable_label": label,
        "question_text": qtext or f"Question text for {label.lower()}.",
        "section": section,
        "section_title": section_title or f"Section {section}",
        "year": year,
        "product_family": product,
        "product_key": product_key or (f"{year}_core" if product == "core" else product),
        "product_title": "HRS Core" if product == "core" else product.title(),
    }


# Synthetic HRS-like catalog: three biennial waves (J=2004, K=2006, L=2008) of
# three sections, plus a tracker file. Codes are invented; no canonical demo
# variable appears here.
WAVES = [("J", "2004"), ("K", "2006"), ("L", "2008")]
SECTIONS = {
    "C": [("030", "LUNG DISEASE", "Has a doctor ever told you that you have chronic lung disease"),
          ("010", "HIGH BLOOD PRESSURE", "Has a doctor ever told you that you have high blood pressure"),
          ("110", "EVER SMOKED", "Have you ever smoked cigarettes")],
    "D": [("110", "FELT DEPRESSED", "Much of the time during the past week you felt depressed"),
          ("115", "FELT LONELY", "Much of the time during the past week you felt lonely")],
    "B": [("014", "HIGHEST GRADE COMPLETED", "What is the highest grade of school completed"),
          ("063", "RELIGIOUS SERVICES", "How often do you attend religious services")],
}


def synthetic_records():
    records = []
    for prefix, year in WAVES:
        for section, items in SECTIONS.items():
            for suffix, label, qtext in items:
                records.append(_rec(f"{prefix}{section}{suffix}", label, section, year, qtext=qtext))
    records.append(_rec("HHID", "HOUSEHOLD IDENTIFIER", "TR", "", product="tracker", qtext="Household identifier"))
    return records


@pytest.fixture(scope="session")
def index():
    return RuntimeIndex.from_records(synthetic_records(), source="synthetic")


def make_settings(**overrides) -> Settings:
    base = dict(
        metadata_path=Path("/nonexistent/metadata.jsonl"),
        index_cache_path=Path("/nonexistent/cache.json.gz"),
        llm_provider="static",
        llm_model="",
        module_top_k=2,
        max_candidates_per_call=2000,
        max_selections_per_role=25,
        build_index_on_startup=False,
        llm_max_retries=1,
        llm_retry_backoff_s=0.0,     # never sleep in tests
    )
    base.update(overrides)
    return Settings(**base)


def intent_json(**roles) -> str:
    return json.dumps({"roles": roles})


def selection_json(*codes, evidence=None, reason="because") -> str:
    return json.dumps({"selections": [
        {"column_name": c, "reason": reason, "evidence": evidence.get(c, "") if isinstance(evidence, dict) else (evidence or "")}
        for c in codes
    ]})


@pytest.fixture
def make_client(index):
    """Return a factory: make_client(llm=<LLMClient>, **settings) -> TestClient."""
    created = []

    def _factory(llm=None, ready=True, **settings):
        state = RuntimeState(settings=make_settings(**settings))
        if ready:
            state.index = index
            state.llm = llm if llm is not None else StaticLLMClient()
        else:
            state.index_error = "index build disabled for test"
        app.dependency_overrides[get_runtime] = lambda: state
        client = TestClient(app, raise_server_exceptions=False)
        created.append(client)
        return client

    yield _factory
    app.dependency_overrides.clear()


@pytest.fixture
def client(make_client):
    return make_client()


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Hard guarantee: no test may open a network connection. The in-process
    TestClient does not use sockets, so this only bites accidental provider calls."""
    import socket

    def _blocked(*args, **kwargs):
        raise RuntimeError("network access is disabled in tests (attempted socket connection)")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
