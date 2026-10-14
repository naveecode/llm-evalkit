"""Read-only HTTP API over a results database."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from evalkit import __version__
from evalkit.report import build_run_payload
from evalkit.store import Store


def create_app(db_path: Path) -> FastAPI:
    store = Store(db_path)
    app = FastAPI(title="evalkit", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/runs")
    def runs() -> list[dict[str, object]]:
        listed = []
        for run in store.list_runs():
            listed.append(
                {
                    "id": run["id"],
                    "taskName": run["task_name"],
                    "taskVersion": run["task_version"],
                    "createdAt": run["created_at"],
                    "label": run["label"],
                    "kind": "sample" if run["label"] == "sample" else "measured",
                }
            )
        return listed

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str) -> dict[str, object]:
        payload = build_run_payload(store, run_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="run not found")
        return payload

    @app.get("/api/leaderboard")
    def leaderboard(run_id: str | None = None) -> dict[str, object]:
        chosen = run_id
        if chosen is None:
            existing = store.list_runs()
            if not existing:
                return {"runId": None, "kind": None, "disclaimer": None, "rows": []}
            chosen = existing[0]["id"]
        payload = build_run_payload(store, str(chosen))
        if payload is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {
            "runId": payload["run"]["id"],
            "kind": payload["kind"],
            "disclaimer": payload["disclaimer"],
            "taskName": payload["run"]["taskName"],
            "rows": [target["summary"] for target in payload["run"]["targets"]],
        }

    return app
