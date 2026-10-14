"""Scoring functions. Each one returns only what it could measure."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from evalkit.pricing import ModelPrice, cost_usd
from evalkit.schema_model import parse_json_value, validation_errors


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def exact_match(expected: Any, prediction_text: str | None) -> dict[str, Any]:
    if prediction_text is None:
        return {"score": None, "matched": False, "mismatchedFields": [], "reason": "no prediction"}
    if isinstance(expected, (dict, list)):
        parsed, error = parse_json_value(prediction_text)
        if error or parsed is None:
            return {
                "score": 0.0,
                "matched": False,
                "mismatchedFields": [],
                "reason": error or "prediction was not JSON",
            }
        mismatched: list[str] = []
        if isinstance(expected, dict) and isinstance(parsed, dict):
            keys = list(dict.fromkeys([*expected.keys(), *parsed.keys()]))
            mismatched = [key for key in keys if expected.get(key) != parsed.get(key)]
        matched = _canonical(expected) == _canonical(parsed)
        return {
            "score": 1.0 if matched else 0.0,
            "matched": matched,
            "mismatchedFields": mismatched,
            "reason": None if matched else "JSON values differ",
        }
    expected_text = expected if isinstance(expected, str) else str(expected)
    matched = prediction_text.strip() == expected_text.strip()
    return {
        "score": 1.0 if matched else 0.0,
        "matched": matched,
        "mismatchedFields": [],
        "reason": None if matched else "text differs",
    }


def json_schema_metric(prediction_text: str | None, schema: dict[str, Any] | None) -> dict[str, Any]:
    if prediction_text is None:
        return {"score": None, "valid": False, "errors": ["no prediction"], "parsed": None}
    parsed, errors = validation_errors(prediction_text, schema)
    valid = not errors
    return {
        "score": 1.0 if valid else 0.0,
        "valid": valid,
        "errors": errors,
        "parsed": parsed,
    }


class JudgeVerdict(BaseModel):
    score: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)


def llm_judge_metric(judge_text: str | None, *, error: str | None = None) -> dict[str, Any]:
    """Parse a judge completion. Out-of-range or non-JSON scores stay unset."""
    if error:
        return {"score": None, "reason": None, "error": error}
    if judge_text is None:
        return {"score": None, "reason": None, "error": "no judge response"}
    parsed, parse_error = parse_json_value(judge_text)
    if parse_error or not isinstance(parsed, dict):
        return {"score": None, "reason": None, "error": parse_error or "judge output was not an object"}
    try:
        verdict = JudgeVerdict.model_validate(parsed)
    except ValidationError as exc:
        message = "; ".join(
            f"{'.'.join(str(part) for part in err.get('loc', ()))}: {err.get('msg')}"
            for err in exc.errors()
        )
        return {"score": None, "reason": None, "error": message or "invalid judge payload"}
    return {"score": verdict.score, "reason": verdict.reason, "error": None}


def latency_metric(
    *,
    latency_ms: float | None,
    cached: bool,
    original_ms: float | None,
    attempts: int,
) -> dict[str, Any]:
    return {
        "latencyMs": latency_ms,
        "cached": cached,
        "originalMs": original_ms,
        "attempts": attempts,
    }


def cost_metric(
    prompt_tokens: int | None,
    completion_tokens: int | None,
    price: ModelPrice | None,
) -> dict[str, Any]:
    amount = cost_usd(prompt_tokens, completion_tokens, price)
    return {
        "costUsd": amount,
        "priceKnown": price is not None,
        "source": price.source if price else None,
        "asOf": price.as_of if price else None,
        "inputPerMillion": price.input_per_million if price else None,
        "outputPerMillion": price.output_per_million if price else None,
    }


def build_judge_messages(
    *,
    rubric: str,
    input_text: str,
    expected: Any,
    prediction: str,
) -> list[dict[str, str]]:
    expected_text = (
        expected
        if isinstance(expected, str)
        else json.dumps(expected, indent=2, ensure_ascii=False)
    )
    system = (
        'You grade one model output. Reply with JSON only: '
        '{"score": <number from 0 to 1>, "reason": "<short explanation>"}.'
    )
    user = (
        f"RUBRIC:\n{rubric.strip()}\n\n"
        f"INPUT:\n{input_text}\n\n"
        f"EXPECTED:\n{expected_text}\n\n"
        f"PREDICTION:\n{prediction}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
