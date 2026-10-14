import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from evalkit.api import create_app
from evalkit.cache import ResponseCache
from evalkit.runner import ClientOptions, RunOverrides, execute
from evalkit.store import Store
from tests.conftest import make_task


@pytest.mark.asyncio
async def test_api_serves_leaderboard(tmp_path):
    db = tmp_path / "results.sqlite"
    task = make_task("http://mock.local/v1")
    store = Store(db)
    cache = ResponseCache(tmp_path / "cache.sqlite")
    body = {
        "choices": [{"message": {"content": json.dumps({"name": "Ada"})}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4},
    }
    async with respx.mock:
        respx.post("http://mock.local/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=body)
        )
        await execute(
            task,
            store=store,
            cache=cache,
            overrides=RunOverrides(label="sample"),
            options=ClientOptions(backoff_s=0, max_backoff_s=0),
        )
    store.close()

    client = TestClient(create_app(db))
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True
    runs = client.get("/api/runs")
    assert runs.status_code == 200
    assert runs.json()[0]["kind"] == "sample"
    run_id = runs.json()[0]["id"]
    detail = client.get(f"/api/runs/{run_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["kind"] == "sample"
    assert "not a benchmark" in payload["disclaimer"]
    assert payload["run"]["targets"][0]["samples"][0]["metrics"]["exactMatch"] == 1.0
    board = client.get("/api/leaderboard")
    assert board.status_code == 200
    assert board.json()["rows"][0]["exactMatch"]["passes"] == 1
    missing = client.get("/api/runs/does-not-exist")
    assert missing.status_code == 404


def test_empty_database_leaderboard(tmp_path):
    client = TestClient(create_app(tmp_path / "empty.sqlite"))
    response = client.get("/api/leaderboard")
    assert response.status_code == 200
    assert response.json()["rows"] == []
