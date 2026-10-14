import json

import pytest

from evalkit.metrics import exact_match, json_schema_metric, llm_judge_metric
from evalkit.pricing import ModelPrice, catalog_price, cost_usd, resolve_price
from evalkit.schema_model import validation_errors


def test_exact_match_ignores_key_order():
    expected = {"name": "Ada", "order_id": "A-1"}
    prediction = json.dumps({"order_id": "A-1", "name": "Ada"})
    result = exact_match(expected, prediction)
    assert result["score"] == 1.0
    assert result["matched"] is True


def test_exact_match_reports_fields_and_rejects_prose():
    expected = {"name": "Ada", "email": "a@example.com"}
    result = exact_match(expected, json.dumps({"name": "Ada", "email": "other@example.com"}))
    assert result["score"] == 0.0
    assert result["mismatchedFields"] == ["email"]
    prose = exact_match(expected, "name is Ada")
    assert prose["score"] == 0.0


def test_exact_match_without_prediction_is_unscored():
    assert exact_match({"name": "Ada"}, None)["score"] is None


def test_json_schema_accepts_fenced_json_and_rejects_extra_keys():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["name", "count"],
        "properties": {
            "name": {"type": "string"},
            "count": {"type": "integer"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
    }
    valid = json_schema_metric('```json\n{"name": "Ada", "count": 2, "tags": ["a"]}\n```', schema)
    assert valid["score"] == 1.0
    assert valid["valid"] is True
    extra = json_schema_metric('{"name": "Ada", "count": 2, "note": "no"}', schema)
    assert extra["score"] == 0.0
    assert extra["errors"]
    missing = json_schema_metric('{"name": "Ada"}', schema)
    assert missing["score"] == 0.0


def test_nested_schema_uses_pydantic():
    schema = {
        "type": "object",
        "required": ["customer"],
        "properties": {
            "customer": {
                "type": "object",
                "required": ["email"],
                "properties": {"email": {"type": "string"}},
            }
        },
    }
    parsed, errors = validation_errors('{"customer": {"email": "a@example.com"}}', schema)
    assert errors == []
    assert parsed["customer"]["email"] == "a@example.com"
    _parsed, bad = validation_errors('{"customer": {"email": 3}}', schema)
    assert bad


def test_judge_rejects_out_of_range_scores():
    good = llm_judge_metric('{"score": 0.25, "reason": "one field"}')
    assert good["score"] == 0.25
    bad = llm_judge_metric('{"score": 5, "reason": "too high"}')
    assert bad["score"] is None
    assert bad["error"]
    prose = llm_judge_metric("looks fine")
    assert prose["score"] is None


def test_catalog_price_is_explicit_and_unknown_models_have_none():
    price = catalog_price("gpt-4o-mini")
    assert price is not None
    assert price.input_per_million == 0.15
    assert price.output_per_million == 0.60
    assert price.as_of == "2026-10-14"
    assert catalog_price("not-a-published-model") is None
    assert cost_usd(1_000_000, 2_000_000, price) == pytest.approx(0.15 + 1.20)
    assert cost_usd(10, 10, None) is None
    assert cost_usd(None, 10, price) is None


def test_task_price_overrides_catalog():
    override = ModelPrice(input_per_million=1, output_per_million=2, source="task file")
    resolved = resolve_price("gpt-4o-mini", {"gpt-4o-mini": override})
    assert resolved is not None
    assert resolved.input_per_million == 1
    assert cost_usd(1_000_000, 0, resolved) == pytest.approx(1)
