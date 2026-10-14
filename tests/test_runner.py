from __future__ import annotations

import json

import httpx
import pytest
import respx

from evalkit.cache import ResponseCache
from evalkit.errors import ConfigError
from evalkit.report import build_run_payload
from evalkit.runner import ClientOptions, RunOverrides, execute, resolve_targets
from evalkit.store import Store
from evalkit.task import load_task
from tests.conftest import make_task

ROOT_TASK = "tasks/json_extract.yaml"
URL = "http://mock.local/v1/chat/completions"


def _completion(content: str, *, prompt_tokens: int | None = 20, completion_tokens: int | None = 5) -> dict:
    payload: dict = {"choices": [{"message": {"content": content}}]}
    if prompt_tokens is not None and completion_tokens is not None:
        payload["usage"] = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
    return payload


def _options() -> ClientOptions:
    return ClientOptions(timeout_s=5, max_retries=3, backoff_s=0, max_backoff_s=0, concurrency=2)


@pytest.mark.asyncio
async def test_runner_scores_caches_and_redacts_secrets(tmp_path):
    task = make_task("http://mock.local/v1", with_judge=True)
    store = Store(tmp_path / "results.sqlite")
    cache = ResponseCache(tmp_path / "cache.sqlite")

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["model"] == "judge-model":
            return httpx.Response(
                200, json=_completion('{"score": 1, "reason": "exact"}', prompt_tokens=8, completion_tokens=4)
            )
        return httpx.Response(200, json=_completion(json.dumps({"name": "Ada"})))

    async with respx.mock:
        route = respx.post(URL).mock(side_effect=respond)
        run_id = await execute(
            task, store=store, cache=cache, overrides=RunOverrides(), options=_options()
        )
        second = await execute(
            task, store=store, cache=cache, overrides=RunOverrides(), options=_options()
        )
        assert route.call_count == 2

    payload = build_run_payload(store, run_id)
    assert payload is not None
    sample = payload["run"]["targets"][0]["samples"][0]
    assert sample["metrics"]["exactMatch"] == 1.0
    assert sample["metrics"]["jsonSchema"] == 1.0
    assert sample["metrics"]["judge"] == 1.0
    assert sample["costUsd"] == pytest.approx((20 * 0.15 + 5 * 0.60) / 1_000_000)
    assert sample["cached"] is False
    assert sample["latencyMs"] is not None
    cached = build_run_payload(store, second)
    assert cached is not None
    cached_sample = cached["run"]["targets"][0]["samples"][0]
    assert cached_sample["cached"] is True
    assert cached_sample["latencyMs"] is None
    assert cached_sample["metrics"]["exactMatch"] == 1.0
    stored = json.dumps(store.get_run(run_id)["config"])
    assert "secret" not in stored
    assert store.get_run(run_id)["config"]["targets"][0]["apiKeySet"] is True


@pytest.mark.asyncio
async def test_runner_retries_then_succeeds(tmp_path):
    task = make_task("http://mock.local/v1", with_judge=False)
    store = Store(tmp_path / "results.sqlite")
    cache = ResponseCache(tmp_path / "cache.sqlite")
    calls = {"n": 0}

    def respond(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, json={"error": "unavailable"})
        return httpx.Response(200, json=_completion(json.dumps({"name": "Ada"})))

    async with respx.mock:
        respx.post(URL).mock(side_effect=respond)
        run_id = await execute(
            task, store=store, cache=cache, overrides=RunOverrides(), options=_options()
        )
    sample = build_run_payload(store, run_id)["run"]["targets"][0]["samples"][0]
    assert calls["n"] == 2
    assert sample["attempts"] == 2
    assert sample["error"] is None
    assert sample["metrics"]["exactMatch"] == 1.0


@pytest.mark.asyncio
async def test_runner_does_not_retry_client_errors_or_invent_cost(tmp_path):
    task = make_task("http://mock.local/v1", model="not-a-published-model")
    task.pricing = {}
    store = Store(tmp_path / "results.sqlite")
    cache = ResponseCache(tmp_path / "cache.sqlite")

    async with respx.mock:
        route = respx.post(URL).mock(return_value=httpx.Response(400, json={"error": "bad"}))
        run_id = await execute(
            task, store=store, cache=cache, overrides=RunOverrides(), options=_options()
        )
        assert route.call_count == 1
    failed = build_run_payload(store, run_id)["run"]["targets"][0]["samples"][0]
    assert failed["error"]
    assert failed["attempts"] == 1
    assert failed["metrics"]["exactMatch"] is None
    assert failed["costUsd"] is None

    async with respx.mock:
        respx.post(URL).mock(
            return_value=httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
        )
        priced = await execute(
            task, store=store, cache=cache, overrides=RunOverrides(), options=_options()
        )
    sample = build_run_payload(store, priced)["run"]["targets"][0]["samples"][0]
    assert sample["promptTokens"] is None
    assert sample["costUsd"] is None
    assert sample["metrics"]["exactMatch"] == 0.0


def test_remote_target_without_a_key_fails_before_requests():
    task = make_task("https://api.openai.com/v1", api_key=None)
    with pytest.raises(ConfigError):
        resolve_targets(task, RunOverrides())


def test_shipped_task_file_loads():
    task = load_task(__import__("pathlib").Path(ROOT_TASK))
    assert task.name == "json_extract"
    assert len(task.dataset.samples) == 8
    assert task.metrics == ["exact_match", "json_schema", "llm_judge", "latency", "cost"]
    assert task.targets[0].provider == "openai"
    assert task.output.json_schema is not None
    assert "name" in task.output.json_schema["properties"]
