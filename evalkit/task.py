"""YAML task definitions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from evalkit.errors import ConfigError
from evalkit.pricing import ModelPrice

MetricName = Literal["exact_match", "json_schema", "llm_judge", "latency", "cost"]
ProviderName = Literal["openai", "groq", "ollama", "vllm", "openai-compatible"]

PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "ollama": "http://127.0.0.1:11434/v1",
    "vllm": "http://127.0.0.1:8000/v1",
    "openai-compatible": "https://api.openai.com/v1",
}


class Sample(BaseModel):
    id: str
    input: str
    expected: Any = None


class Dataset(BaseModel):
    samples: list[Sample]

    @field_validator("samples")
    @classmethod
    def unique_ids(cls, samples: list[Sample]) -> list[Sample]:
        ids = [sample.id for sample in samples]
        if len(ids) != len(set(ids)):
            raise ValueError("sample ids must be unique")
        if not samples:
            raise ValueError("dataset.samples must not be empty")
        return samples


class Prompt(BaseModel):
    system: str = ""
    user: str


class OutputSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    format: Literal["json", "text"] = "json"
    json_schema: dict[str, Any] | None = Field(default=None, alias="schema")


class Target(BaseModel):
    id: str
    provider: ProviderName = "openai-compatible"
    model: str
    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    temperature: float = 0
    max_tokens: int = 512
    extra: dict[str, Any] = Field(default_factory=dict)


class JudgeSpec(BaseModel):
    rubric: str
    provider: ProviderName = "openai-compatible"
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    temperature: float = 0
    max_tokens: int = 256


class TaskSpec(BaseModel):
    name: str
    description: str = ""
    version: str = "1"
    dataset: Dataset
    prompt: Prompt
    output: OutputSpec = Field(default_factory=OutputSpec)
    metrics: list[MetricName]
    targets: list[Target]
    judge: JudgeSpec | None = None
    pricing: dict[str, ModelPrice] = Field(default_factory=dict)

    @field_validator("metrics")
    @classmethod
    def metrics_present(cls, metrics: list[MetricName]) -> list[MetricName]:
        if not metrics:
            raise ValueError("metrics must not be empty")
        if len(metrics) != len(set(metrics)):
            raise ValueError("metrics must not repeat")
        return metrics

    @field_validator("targets")
    @classmethod
    def targets_present(cls, targets: list[Target]) -> list[Target]:
        if not targets:
            raise ValueError("targets must not be empty")
        ids = [target.id for target in targets]
        if len(ids) != len(set(ids)):
            raise ValueError("target ids must be unique")
        return targets


def load_task(path: Path) -> TaskSpec:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"Could not read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a YAML mapping")
    try:
        return TaskSpec.model_validate(raw)
    except Exception as exc:
        raise ConfigError(f"Invalid task file {path}: {exc}") from exc


def render_user(template: str, input_text: str) -> str:
    if "{{" not in template:
        return template
    rendered = template.replace("{{ input }}", input_text).replace("{{input}}", input_text)
    return rendered


def default_base_url(provider: str) -> str:
    try:
        return PROVIDER_BASE_URLS[provider]
    except KeyError as exc:
        raise ConfigError(f"Unknown provider {provider}") from exc
