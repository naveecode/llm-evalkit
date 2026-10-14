"""SQLite storage for eval runs. API keys are never written."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                task_name TEXT NOT NULL,
                task_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                label TEXT,
                config_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(id),
                target_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                base_url TEXT NOT NULL,
                sample_id TEXT NOT NULL,
                input_text TEXT NOT NULL,
                expected_json TEXT,
                prediction_text TEXT,
                parsed_json TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                latency_ms REAL,
                cost_usd REAL,
                cached INTEGER NOT NULL,
                attempts INTEGER NOT NULL,
                error TEXT,
                metrics_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS samples_run ON samples(run_id);
            """
        )
        self._conn.commit()

    def create_run(
        self,
        *,
        task_name: str,
        task_version: str,
        label: str | None,
        config: dict[str, Any],
    ) -> str:
        run_id = uuid.uuid4().hex
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO runs (id, task_name, task_version, created_at, label, config_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, task_name, task_version, utc_now(), label, json.dumps(config)),
            )
            self._conn.commit()
        return run_id

    def add_sample(self, run_id: str, row: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO samples (
                    run_id, target_id, provider, model, base_url, sample_id, input_text,
                    expected_json, prediction_text, parsed_json, prompt_tokens,
                    completion_tokens, latency_ms, cost_usd, cached, attempts, error,
                    metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    row["target_id"],
                    row["provider"],
                    row["model"],
                    row["base_url"],
                    row["sample_id"],
                    row["input_text"],
                    _dump(row.get("expected")),
                    row.get("prediction_text"),
                    _dump(row.get("parsed")),
                    row.get("prompt_tokens"),
                    row.get("completion_tokens"),
                    row.get("latency_ms"),
                    row.get("cost_usd"),
                    1 if row.get("cached") else 0,
                    int(row.get("attempts") or 0),
                    row.get("error"),
                    json.dumps(row.get("metrics") or {}),
                ),
            )
            self._conn.commit()

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, task_name, task_version, created_at, label, config_json FROM runs ORDER BY created_at DESC"
            ).fetchall()
        return [_run_row(row) for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, task_name, task_version, created_at, label, config_json FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return _run_row(row)

    def samples(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT target_id, provider, model, base_url, sample_id, input_text,
                       expected_json, prediction_text, parsed_json, prompt_tokens,
                       completion_tokens, latency_ms, cost_usd, cached, attempts, error,
                       metrics_json
                FROM samples WHERE run_id = ? ORDER BY id
                """,
                (run_id,),
            ).fetchall()
        return [_sample_row(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _dump(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _load(value: str | None) -> Any:
    if value is None:
        return None
    return json.loads(value)


def _run_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "task_name": row["task_name"],
        "task_version": row["task_version"],
        "created_at": row["created_at"],
        "label": row["label"],
        "config": json.loads(row["config_json"]),
    }


def _sample_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "target_id": row["target_id"],
        "provider": row["provider"],
        "model": row["model"],
        "base_url": row["base_url"],
        "sample_id": row["sample_id"],
        "input_text": row["input_text"],
        "expected": _load(row["expected_json"]),
        "prediction_text": row["prediction_text"],
        "parsed": _load(row["parsed_json"]),
        "prompt_tokens": row["prompt_tokens"],
        "completion_tokens": row["completion_tokens"],
        "latency_ms": row["latency_ms"],
        "cost_usd": row["cost_usd"],
        "cached": bool(row["cached"]),
        "attempts": row["attempts"],
        "error": row["error"],
        "metrics": json.loads(row["metrics_json"]),
    }
