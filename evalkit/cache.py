"""SQLite cache of successful chat completions, keyed by the request body."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


def cache_key(
    *,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    extra: dict[str, Any] | None,
) -> str:
    payload = {
        "base_url": base_url.rstrip("/"),
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "extra": extra or {},
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ResponseCache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                response_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        self._conn.commit()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT response_json FROM cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        loaded = json.loads(row[0])
        if not isinstance(loaded, dict):
            return None
        return loaded

    def put(self, key: str, response: dict[str, Any]) -> None:
        raw = json.dumps(response, ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (key, response_json) VALUES (?, ?)",
                (key, raw),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
