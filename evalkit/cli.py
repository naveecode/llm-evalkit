"""Command line: evalkit run, evalkit leaderboard, evalkit serve."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import typer

from evalkit.api import create_app
from evalkit.cache import ResponseCache
from evalkit.errors import ConfigError
from evalkit.report import build_run_payload, generation_failed
from evalkit.runner import ClientOptions, RunOverrides, execute
from evalkit.store import Store
from evalkit.task import load_task

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Evaluate chat models on YAML tasks.")


@app.command()
def run(
    task: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    db: Path = typer.Option(Path("evalkit.sqlite"), "--db", help="SQLite file for results."),
    cache: Path = typer.Option(Path(".evalkit/cache.sqlite"), "--cache", help="SQLite file for response cache."),
    base_url: str | None = typer.Option(None, "--base-url", help="Override every target base URL."),
    model: str | None = typer.Option(None, "--model", help="Override every target model name."),
    api_key: str | None = typer.Option(None, "--api-key", help="Override API keys. Prefer an env var."),
    target: str | None = typer.Option(None, "--target", help="Run a single target id from the task file."),
    skip_judge: bool = typer.Option(False, "--skip-judge", help="Do not call the judge model."),
    judge_base_url: str | None = typer.Option(None, "--judge-base-url"),
    judge_model: str | None = typer.Option(None, "--judge-model"),
    concurrency: int = typer.Option(4, "--concurrency", min=1),
    label: str | None = typer.Option(None, "--label", help="Optional run label, for example sample."),
    json_output: bool = typer.Option(False, "--json", help="Print the run payload as JSON."),
) -> None:
    """Run a YAML task against its OpenAI-compatible targets."""
    overrides = RunOverrides(
        base_url=_flag_or_env(base_url, "EVALKIT_BASE_URL"),
        model=_flag_or_env(model, "EVALKIT_MODEL"),
        api_key=_flag_or_env(api_key, "EVALKIT_API_KEY"),
        target_id=target,
        skip_judge=skip_judge or _truthy(os.environ.get("EVALKIT_SKIP_JUDGE")),
        judge_base_url=_flag_or_env(judge_base_url, "EVALKIT_JUDGE_BASE_URL"),
        judge_model=_flag_or_env(judge_model, "EVALKIT_JUDGE_MODEL"),
        label=label,
    )
    try:
        spec = load_task(task)
        store = Store(db)
        response_cache = ResponseCache(cache)
        run_id = asyncio.run(
            execute(
                spec,
                store=store,
                cache=response_cache,
                overrides=overrides,
                options=ClientOptions(concurrency=concurrency),
            )
        )
        payload = build_run_payload(store, run_id)
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    if payload is None:
        typer.echo("run was not stored", err=True)
        raise typer.Exit(code=2)
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(format_report(payload, db))
    if generation_failed(payload):
        raise typer.Exit(code=1)


@app.command()
def leaderboard(
    db: Path = typer.Option(Path("evalkit.sqlite"), "--db"),
    run_id: str | None = typer.Option(None, "--run"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Print the leaderboard for one run. Defaults to the latest run."""
    store = Store(db)
    chosen = run_id
    if chosen is None:
        runs = store.list_runs()
        if not runs:
            typer.echo("no runs in the database", err=True)
            raise typer.Exit(code=2)
        chosen = runs[0]["id"]
    payload = build_run_payload(store, chosen)
    if payload is None:
        typer.echo(f"run {chosen} was not found", err=True)
        raise typer.Exit(code=2)
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(format_report(payload, db))


@app.command()
def serve(
    db: Path = typer.Option(Path("evalkit.sqlite"), "--db"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    """Serve stored results over HTTP."""
    import uvicorn

    uvicorn.run(create_app(db), host=host, port=port)


def format_report(payload: dict, db: Path) -> str:
    run = payload["run"]
    lines = [
        f"run {run['id']}  task {run['taskName']}  kind {payload['kind']}",
        _rule(),
        f"{'target':<22} {'n':>3} {'err':>4} {'exact':>8} {'schema':>8} {'judge':>8} {'p50 ms':>8} {'$/1k':>12}",
    ]
    for target in run["targets"]:
        summary = target["summary"]
        lines.append(
            f"{target['targetId']:<22} "
            f"{summary['n']:>3} "
            f"{summary['errors']:>4} "
            f"{_ratio(summary['exactMatch']):>8} "
            f"{_ratio(summary['jsonSchema']):>8} "
            f"{_judge(summary):>8} "
            f"{_latency(summary):>8} "
            f"{_cost(summary):>12}"
        )
    lines.append(_rule())
    lines.append(f"db {db}")
    if payload["kind"] == "sample":
        lines.append(payload["disclaimer"])
    return "\n".join(lines)


def _ratio(block: dict) -> str:
    if not block["scored"]:
        return "—"
    return f"{block['passes']}/{block['scored']}"


def _judge(summary: dict) -> str:
    if summary["judgeMean"] is None:
        return "—"
    return f"{summary['judgeMean']:.3f}"


def _latency(summary: dict) -> str:
    if summary["latencyMsP50"] is None:
        return "—"
    return f"{summary['latencyMsP50']:.0f}"


def _cost(summary: dict) -> str:
    if summary["costPer1kUsd"] is None:
        return "—"
    return f"{summary['costPer1kUsd']:.6f}"


def _rule() -> str:
    return "-" * 78


def _flag_or_env(flag: str | None, env_name: str) -> str | None:
    if flag is not None and flag.strip() != "":
        return flag
    value = os.environ.get(env_name)
    if value is None or value.strip() == "":
        return None
    return value


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


def main() -> None:
    app()
