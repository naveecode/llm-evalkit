"""Build a Pydantic model from a small JSON Schema subset and validate with it."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, create_model

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


def extract_json_text(text: str) -> str:
    stripped = text.strip()
    fenced = _FENCE.match(stripped)
    if fenced:
        return fenced.group(1).strip()
    return stripped


def parse_json_value(text: str) -> tuple[Any, str | None]:
    """Return (value, error). Scans from the first object or array if needed."""
    candidate = extract_json_text(text)
    try:
        return json.loads(candidate), None
    except json.JSONDecodeError:
        pass
    for index, char in enumerate(candidate):
        if char not in "{[":
            continue
        try:
            value, _end = json.JSONDecoder().raw_decode(candidate[index:])
        except json.JSONDecodeError:
            continue
        return value, None
    return None, "output is not valid JSON"


def _literal(values: list[Any]) -> Any:
    return Literal.__getitem__(tuple(values))


def _python_type(schema: dict[str, Any], name: str) -> Any:
    if "enum" in schema:
        values = schema["enum"]
        if values and all(isinstance(item, (str, int, float, bool)) for item in values):
            non_bool = [item for item in values if not isinstance(item, bool)]
            if non_bool or all(isinstance(item, bool) for item in values):
                return _literal(list(values))
    raw_type = schema.get("type", "string")
    nullable = False
    if isinstance(raw_type, list):
        nullable = "null" in raw_type
        remaining = [item for item in raw_type if item != "null"]
        raw_type = remaining[0] if len(remaining) == 1 else "string"
    py_type = _named_type(raw_type, schema, name)
    if nullable:
        return py_type | None
    return py_type


def _named_type(raw_type: str, schema: dict[str, Any], name: str) -> Any:
    if raw_type == "string":
        return str
    if raw_type == "integer":
        return int
    if raw_type == "number":
        return float
    if raw_type == "boolean":
        return bool
    if raw_type == "array":
        item_schema = schema.get("items") or {"type": "string"}
        if not isinstance(item_schema, dict):
            return list[Any]
        return list[_python_type(item_schema, f"{name}Item")]
    if raw_type == "object":
        return model_from_schema(name, schema)
    return Any


def model_from_schema(name: str, schema: dict[str, Any]) -> type[BaseModel]:
    key = json.dumps({"name": name, "schema": schema}, sort_keys=True)
    return _cached_model(key)


@lru_cache(maxsize=64)
def _cached_model(key: str) -> type[BaseModel]:
    payload = json.loads(key)
    return _build_model(payload["name"], payload["schema"])


def _build_model(name: str, schema: dict[str, Any]) -> type[BaseModel]:
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    fields: dict[str, Any] = {}
    for prop_name, prop_schema in properties.items():
        if not isinstance(prop_schema, dict):
            prop_schema = {"type": "string"}
        annotation = _python_type(prop_schema, f"{name}_{prop_name}")
        if prop_name in required:
            fields[prop_name] = (annotation, ...)
        else:
            fields[prop_name] = (annotation | None, None)
    extra = "forbid" if schema.get("additionalProperties") is False else "ignore"
    safe_name = re.sub(r"\W", "_", name) or "Output"
    return create_model(
        safe_name,
        __config__=ConfigDict(extra=extra),
        **fields,
    )


def validation_errors(text: str, schema: dict[str, Any] | None) -> tuple[Any, list[str]]:
    """Parse JSON and, when a schema is present, validate it with Pydantic.

    The returned value is the raw parsed JSON (not the model dump), so extra
    keys stay visible to exact-match even when the schema ignores them.
    """
    parsed, error = parse_json_value(text)
    if error:
        return None, [error]
    if schema is None:
        return parsed, []
    if schema.get("type", "object") != "object" or not isinstance(parsed, dict):
        if schema.get("type") == "array":
            model = _array_wrapper(schema)
            try:
                model.model_validate({"items": parsed})
            except ValidationError as exc:
                return parsed, _format_errors(exc)
            return parsed, []
        if not isinstance(parsed, dict):
            return parsed, ["JSON value must be an object"]
    try:
        model_from_schema("Output", schema).model_validate(parsed)
    except ValidationError as exc:
        return parsed, _format_errors(exc)
    return parsed, []


def _array_wrapper(schema: dict[str, Any]) -> type[BaseModel]:
    item_type = _python_type(schema.get("items") or {"type": "string"}, "Item")
    return create_model(
        "OutputList",
        __config__=ConfigDict(extra="forbid"),
        items=(list[item_type], ...),
    )


def _format_errors(exc: ValidationError) -> list[str]:
    messages: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", [])) or "(root)"
        messages.append(f"{loc}: {err.get('msg')}")
    return messages or ["schema validation failed"]
