"""Async evaluation loop: one task, many targets, cached and retried completions."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from evalkit.cache import ResponseCache
from evalkit.client import ChatError, OpenAICompatibleClient
from evalkit.errors import ConfigError
from evalkit.metrics import (
    build_judge_messages,
    cost_metric,
    exact_match,
    json_schema_metric,
    latency_metric,
    llm_judge_metric,
)
from evalkit.pricing import resolve_price
from evalkit.store import Store
from evalkit.task import JudgeSpec, Target, TaskSpec, default_base_url, render_user

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal"}


@dataclass
class RunOverrides:
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    target_id: str | None = None
    skip_judge: bool = False
    judge_base_url: str | None = None
    judge_model: str | None = None
    label: str | None = None


@dataclass
class ClientOptions:
    timeout_s: float = 60
    max_retries: int = 3
    backoff_s: float = 0.25
    max_backoff_s: float = 8.0
    concurrency: int = 4


def resolve_targets(task: TaskSpec, overrides: RunOverrides) -> list[Target]:
    selected = list(task.targets)
    if overrides.target_id:
        selected = [target for target in selected if target.id == overrides.target_id]
        if not selected:
            known = ", ".join(target.id for target in task.targets)
            raise ConfigError(f"Unknown target {overrides.target_id!r}. Known targets: {known}")
    resolved: list[Target] = []
    for target in selected:
        data = target.model_copy(deep=True)
        if overrides.base_url:
            data.base_url = overrides.base_url
        if overrides.model:
            data.model = overrides.model
        if not data.base_url:
            data.base_url = default_base_url(data.provider)
        data.api_key = _resolve_api_key(data.api_key, data.api_key_env, overrides.api_key)
        _require_api_key(data.id, data.base_url, data.api_key, data.api_key_env)
        resolved.append(data)
    return resolved


def resolve_judge(task: TaskSpec, target: Target, overrides: RunOverrides) -> Target | None:
    if overrides.skip_judge or "llm_judge" not in task.metrics:
        return None
    if task.judge is None:
        raise ConfigError("metrics includes llm_judge, but the task has no judge: block")
    spec: JudgeSpec = task.judge
    model = overrides.judge_model or spec.model or target.model
    base_url = overrides.judge_base_url or spec.base_url or target.base_url
    if spec.api_key:
        api_key = spec.api_key
    elif overrides.api_key:
        api_key = overrides.api_key
    elif spec.api_key_env and os.environ.get(spec.api_key_env):
        api_key = os.environ[spec.api_key_env]
    else:
        api_key = target.api_key
    _require_api_key("judge", base_url or "", api_key, spec.api_key_env)
    return Target(
        id="judge",
        provider=spec.provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=spec.temperature,
        max_tokens=spec.max_tokens,
    )


def public_config(task: TaskSpec, targets: list[Target], overrides: RunOverrides) -> dict[str, Any]:
    return {
        "taskName": task.name,
        "version": task.version,
        "description": task.description,
        "metrics": list(task.metrics),
        "sampleOrder": [sample.id for sample in task.dataset.samples],
        "label": overrides.label,
        "targets": [_public_target(target) for target in targets],
        "pricing": {
            model: {
                "inputPerMillion": price.input_per_million,
                "outputPerMillion": price.output_per_million,
                "source": price.source,
                "asOf": price.as_of,
            }
            for model, price in task.pricing.items()
        },
    }


async def execute(
    task: TaskSpec,
    *,
    store: Store,
    cache: ResponseCache,
    overrides: RunOverrides | None = None,
    options: ClientOptions | None = None,
) -> str:
    overrides = overrides or RunOverrides()
    options = options or ClientOptions()
    targets = resolve_targets(task, overrides)
    for target in targets:
        resolve_judge(task, target, overrides)
    run_id = store.create_run(
        task_name=task.name,
        task_version=task.version,
        label=overrides.label,
        config=public_config(task, targets, overrides),
    )
    semaphore = asyncio.Semaphore(max(1, options.concurrency))
    async with httpx.AsyncClient(timeout=options.timeout_s) as http:
        client = OpenAICompatibleClient(
            http,
            cache,
            max_retries=options.max_retries,
            backoff_s=options.backoff_s,
            max_backoff_s=options.max_backoff_s,
        )
        jobs = [
            _run_sample(
                task=task,
                target=target,
                sample_id=sample.id,
                input_text=sample.input,
                expected=sample.expected,
                client=client,
                store=store,
                run_id=run_id,
                overrides=overrides,
                semaphore=semaphore,
            )
            for target in targets
            for sample in task.dataset.samples
        ]
        await asyncio.gather(*jobs)
    return run_id


async def _run_sample(
    *,
    task: TaskSpec,
    target: Target,
    sample_id: str,
    input_text: str,
    expected: Any,
    client: OpenAICompatibleClient,
    store: Store,
    run_id: str,
    overrides: RunOverrides,
    semaphore: asyncio.Semaphore,
) -> None:
    messages = [
        {"role": "system", "content": task.prompt.system},
        {"role": "user", "content": render_user(task.prompt.user, input_text)},
    ]
    try:
        async with semaphore:
            chat = await client.chat(
                base_url=target.base_url or "",
                api_key=target.api_key,
                model=target.model,
                messages=messages,
                temperature=target.temperature,
                max_tokens=target.max_tokens,
                extra=target.extra,
            )
    except (ChatError, httpx.HTTPError) as exc:
        attempts = exc.attempts if isinstance(exc, ChatError) else 1
        store.add_sample(
            run_id,
            _row(
                target=target,
                sample_id=sample_id,
                input_text=input_text,
                expected=expected,
                prediction_text=None,
                parsed=None,
                prompt_tokens=None,
                completion_tokens=None,
                latency_ms=None,
                cost_usd=None,
                cached=False,
                attempts=attempts,
                error=str(exc),
                metrics=_empty_metrics(task),
            ),
        )
        return

    metrics: dict[str, Any] = {}
    parsed = None
    if "exact_match" in task.metrics:
        metrics["exact_match"] = exact_match(expected, chat.content)
    if "json_schema" in task.metrics and task.output.format == "json":
        schema_result = json_schema_metric(chat.content, task.output.json_schema)
        parsed = schema_result.pop("parsed")
        metrics["json_schema"] = schema_result
    elif task.output.format == "json":
        schema_result = json_schema_metric(chat.content, None)
        parsed = schema_result["parsed"]
    if "latency" in task.metrics:
        metrics["latency"] = latency_metric(
            latency_ms=chat.latency_ms,
            cached=chat.cached,
            original_ms=chat.original_latency_ms,
            attempts=chat.attempts,
        )
    price = resolve_price(target.model, task.pricing)
    amount = None
    if "cost" in task.metrics:
        cost = cost_metric(chat.prompt_tokens, chat.completion_tokens, price)
        amount = cost["costUsd"]
        metrics["cost"] = cost
    if "llm_judge" in task.metrics and not overrides.skip_judge:
        metrics["llm_judge"] = await _judge_sample(
            task=task,
            target=target,
            client=client,
            overrides=overrides,
            input_text=input_text,
            expected=expected,
            prediction=chat.content,
            semaphore=semaphore,
        )
    store.add_sample(
        run_id,
        _row(
            target=target,
            sample_id=sample_id,
            input_text=input_text,
            expected=expected,
            prediction_text=chat.content,
            parsed=parsed,
            prompt_tokens=chat.prompt_tokens,
            completion_tokens=chat.completion_tokens,
            latency_ms=chat.latency_ms,
            cost_usd=amount,
            cached=chat.cached,
            attempts=chat.attempts,
            error=None,
            metrics=metrics,
        ),
    )


async def _judge_sample(
    *,
    task: TaskSpec,
    target: Target,
    client: OpenAICompatibleClient,
    overrides: RunOverrides,
    input_text: str,
    expected: Any,
    prediction: str,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    judge = resolve_judge(task, target, overrides)
    if judge is None or task.judge is None:
        return llm_judge_metric(None, error="judge is not configured")
    messages = build_judge_messages(
        rubric=task.judge.rubric,
        input_text=input_text,
        expected=expected,
        prediction=prediction,
    )
    async with semaphore:
        try:
            chat = await client.chat(
                base_url=judge.base_url or "",
                api_key=judge.api_key,
                model=judge.model,
                messages=messages,
                temperature=judge.temperature,
                max_tokens=judge.max_tokens,
            )
        except (ChatError, httpx.HTTPError) as exc:
            return llm_judge_metric(None, error=str(exc))
    verdict = llm_judge_metric(chat.content)
    verdict["model"] = judge.model
    verdict["cached"] = chat.cached
    verdict["latencyMs"] = chat.latency_ms
    return verdict


def _empty_metrics(task: TaskSpec) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    if "exact_match" in task.metrics:
        metrics["exact_match"] = exact_match(None, None)
        metrics["exact_match"]["score"] = None
    if "json_schema" in task.metrics:
        metrics["json_schema"] = {
            "score": None,
            "valid": False,
            "errors": ["no prediction"],
        }
    if "latency" in task.metrics:
        metrics["latency"] = latency_metric(
            latency_ms=None, cached=False, original_ms=None, attempts=0
        )
    if "cost" in task.metrics:
        metrics["cost"] = cost_metric(None, None, None)
    if "llm_judge" in task.metrics:
        metrics["llm_judge"] = llm_judge_metric(None, error="generation failed")
    return metrics


def _row(
    *,
    target: Target,
    sample_id: str,
    input_text: str,
    expected: Any,
    prediction_text: str | None,
    parsed: Any,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    latency_ms: float | None,
    cost_usd: float | None,
    cached: bool,
    attempts: int,
    error: str | None,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "target_id": target.id,
        "provider": target.provider,
        "model": target.model,
        "base_url": target.base_url or "",
        "sample_id": sample_id,
        "input_text": input_text,
        "expected": expected,
        "prediction_text": prediction_text,
        "parsed": parsed,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "latency_ms": latency_ms,
        "cost_usd": cost_usd,
        "cached": cached,
        "attempts": attempts,
        "error": error,
        "metrics": metrics,
    }


def _resolve_api_key(yaml_key: str | None, env_name: str | None, override: str | None) -> str | None:
    if override:
        return override
    if env_name:
        from_env = os.environ.get(env_name)
        if from_env:
            return from_env
    return yaml_key


def _require_api_key(name: str, base_url: str, api_key: str | None, env_name: str | None) -> None:
    if api_key or _is_local(base_url):
        return
    hint = f" Set {env_name} or pass --api-key." if env_name else " Pass --api-key."
    raise ConfigError(f"Target {name} at {base_url} needs an API key.{hint}")


def _is_local(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").lower()
    return host in _LOCAL_HOSTS


def _public_target(target: Target) -> dict[str, Any]:
    return {
        "id": target.id,
        "provider": target.provider,
        "model": target.model,
        "baseUrl": target.base_url,
        "apiKeySet": bool(target.api_key),
        "temperature": target.temperature,
        "maxTokens": target.max_tokens,
    }
