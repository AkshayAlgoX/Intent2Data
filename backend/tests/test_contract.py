"""The contract files are generated from the response model; this keeps them
from drifting apart silently."""

import json
from pathlib import Path

from app.pipeline.models import AnalyzeResponse

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts" / "v1"


def test_example_response_validates_against_model():
    example = json.loads((CONTRACTS / "example_response.json").read_text())
    parsed = AnalyzeResponse.model_validate(example)
    assert parsed.contract == "v1" and parsed.status == "ok"
    assert parsed.llm.live is False


def test_response_schema_file_matches_model():
    on_disk = json.loads((CONTRACTS / "analyze_response.schema.json").read_text())
    generated = AnalyzeResponse.model_json_schema()
    for key in ("$schema", "title"):
        on_disk.pop(key, None)
        generated.pop(key, None)
    assert on_disk == generated, "regenerate contracts/v1/analyze_response.schema.json from the model"


def test_request_schema_matches_api_bounds():
    from app.main import QUESTION_MAX_CHARS, QUESTION_MIN_CHARS
    schema = json.loads((CONTRACTS / "analyze.schema.json").read_text())
    q = schema["properties"]["question"]
    assert (q["minLength"], q["maxLength"]) == (QUESTION_MIN_CHARS, QUESTION_MAX_CHARS)
    assert schema["required"] == ["question"]
