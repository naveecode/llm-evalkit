"""Write web/data/measured-results.json from local Ollama models.

The scores are whatever evalkit computes. Quantization and parameter size come
from Ollama's show API. Hardware comes from /proc and the llama-server process
maps. Do not hand-edit the file; re-run this script.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urlparse

import httpx

from evalkit.cache import ResponseCache
from evalkit.pricing import ModelPrice
from evalkit.report import build_run_payload
from evalkit.runner import ClientOptions, RunOverrides, execute
from evalkit.store import Store
from evalkit.task import Target, load_task

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TASKS = (
    ROOT / "tasks" / "json_extract.yaml",
    ROOT / "tasks" / "classification.yaml",
)
DEFAULT_OUTPUT = ROOT / "web" / "data" / "measured-results.json"

DISCLAIMER = (
    "Measured by evalkit against local Ollama on this machine. "
    "Each score is the harness metric on every row of the task file. "
    "The judge was not called: the task files point it at gpt-4o-mini, and this run "
    "did not use a paid API or a substitute grader. "
    "Cost is zero because these calls had no provider bill. "
    "Quantization and parameter size come from the Ollama show API for the tag that was requested. "
    "The CPU line comes from /proc. The inference library is the ggml shared object mapped "
    "into the llama-server process that served the calls."
)

PROCEDURE = (
    "Each model was stopped before the task. "
    "Samples ran one at a time, all rows of one model before the next model. "
    "The first sample of a model can include weight load in its latency. "
    "A fresh response cache was used, so none of these rows are cache hits."
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--api-key", default="ollama")
    parser.add_argument("--model", action="append", required=True, dest="models")
    parser.add_argument("--task", action="append", type=Path, dest="tasks")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--concurrency", type=int, default=1)
    args = parser.parse_args()
    if args.concurrency < 1:
        raise SystemExit("--concurrency must be at least 1")
    tasks = args.tasks or list(DEFAULT_TASKS)
    origin = _origin(args.base_url)
    collected_at = datetime.now(UTC).isoformat()
    version = _ollama_version(origin)
    hardware = _hardware(version, collected_at)
    shown = [_show(origin, model) for model in args.models]
    listed = {item["name"]: item for item in _get(origin, "/api/tags").get("models") or []}
    for model in shown:
        tag = listed.get(model["model"])
        if tag is None:
            raise SystemExit(f"{model['model']} is not in /api/tags")
        model["digest"] = tag.get("digest")
        model["sizeBytes"] = tag.get("size")
        if not model["digest"]:
            raise SystemExit(f"{model['model']} has no digest in /api/tags")
    _ensure_loaded(origin, args.base_url, args.api_key, [model["model"] for model in shown])
    running = {item["name"]: item for item in (_get(origin, "/api/ps").get("models") or [])}
    for model in shown:
        live = running.get(model["model"])
        if live is None:
            raise SystemExit(f"{model['model']} did not appear in /api/ps")
        context = live.get("context_length")
        if not isinstance(context, int):
            raise SystemExit(f"{model['model']} has no context_length in /api/ps")
        model["contextLength"] = context
        model["ps"] = {
            "size": live.get("size"),
            "sizeVram": live.get("size_vram"),
            "contextLength": context,
            "runner": live.get("runner"),
        }
    _stop_models([model["model"] for model in shown])
    runs = asyncio.run(
        _run_tasks(
            tasks=tasks,
            models=shown,
            base_url=args.base_url,
            api_key=args.api_key,
            timeout_s=args.timeout,
            concurrency=args.concurrency,
            hardware=hardware,
        )
    )
    if not hardware["ggmlLibraries"]:
        raise SystemExit("llama-server did not map a ggml library during the timed run")
    if not any("libggml-cpu" in name for name in hardware["ggmlLibraries"]):
        raise SystemExit(f"expected a CPU ggml library, found {hardware['ggmlLibraries']}")
    payload = {
        "kind": "measured",
        "disclaimer": DISCLAIMER,
        "generator": "scripts/export_measured_results.py",
        "judgeRan": False,
        "procedure": PROCEDURE,
        "hardware": hardware,
        "models": shown,
        "runs": runs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    for run in runs:
        print(f"\n{run['taskName']}  n={run['targets'][0]['summary']['n']}  {run['createdAt']}")
        for target in run["targets"]:
            summary = target["summary"]
            exact = summary["exactMatch"]
            schema = summary["jsonSchema"]
            print(
                f"  {target['model']}  {target['quantization']}  "
                f"exact {exact['passes']}/{exact['scored']}  "
                f"schema {schema['passes']}/{schema['scored']}  "
                f"p50 {summary['latencyMsP50']}  errors {summary['errors']}"
            )


async def _run_tasks(
    *,
    tasks: list[Path],
    models: list[dict[str, Any]],
    base_url: str,
    api_key: str,
    timeout_s: float,
    concurrency: int,
    hardware: dict[str, Any],
) -> list[dict[str, Any]]:
    model_names = [model["model"] for model in models]
    by_model = {model["model"]: model for model in models}
    as_of = datetime.now(UTC).date().isoformat()
    price = ModelPrice(
        input_per_million=0,
        output_per_million=0,
        source="local Ollama; no provider bill",
        as_of=as_of,
    )
    runs: list[dict[str, Any]] = []
    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        store = Store(tmp_path / "results.sqlite")
        for task_path in tasks:
            _stop_models(model_names)
            task = load_task(task_path)
            task.targets = [
                Target(
                    id=_target_id(model_name),
                    provider="ollama",
                    model=model_name,
                    base_url=base_url,
                    api_key=api_key,
                    temperature=0,
                    max_tokens=task.targets[0].max_tokens,
                )
                for model_name in model_names
            ]
            task.pricing = {model_name: price for model_name in model_names}
            cache = ResponseCache(tmp_path / f"cache-{task.name}.sqlite")
            run_id = await execute(
                task,
                store=store,
                cache=cache,
                overrides=RunOverrides(label="measured", skip_judge=True, api_key=api_key),
                options=ClientOptions(
                    timeout_s=timeout_s,
                    max_retries=2,
                    backoff_s=0.5,
                    concurrency=concurrency,
                ),
            )
            libraries = _mapped_libraries()
            hardware["ggmlLibraries"] = sorted(set(hardware["ggmlLibraries"]) | set(libraries["ggml"]))
            hardware["acceleratorLibraries"] = sorted(
                set(hardware["acceleratorLibraries"]) | set(libraries["accelerator"])
            )
            payload = build_run_payload(store, run_id)
            if payload is None:
                raise SystemExit(f"{task_path} did not store a run")
            run = payload["run"]
            if run["label"] != "measured":
                raise SystemExit("run label was not measured")
            for target in run["targets"]:
                meta = by_model[target["model"]]
                summary = target["summary"]
                if summary["errors"]:
                    raise SystemExit(f"{target['model']} on {run['taskName']} has {summary['errors']} errors")
                expected_n = len(task.dataset.samples)
                if summary["n"] != expected_n:
                    raise SystemExit(f"{target['model']} scored {summary['n']} rows, task has {expected_n}")
                target["quantization"] = meta["quantization"]
                target["parameterSize"] = meta["parameterSize"]
                target["family"] = meta["family"]
                target["digest"] = meta["digest"]
                target["contextLength"] = meta["contextLength"]
            runs.append(run)
    return runs


def _ensure_loaded(origin: str, base_url: str, api_key: str, models: list[str]) -> None:
    running = {item["name"] for item in (_get(origin, "/api/ps").get("models") or [])}
    missing = [model for model in models if model not in running]
    if not missing:
        return
    with httpx.Client(timeout=180) as client:
        for model in missing:
            response = client.post(
                base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Reply with the word ok."}],
                    "temperature": 0,
                    "max_tokens": 1,
                },
            )
            response.raise_for_status()


def _show(origin: str, model: str) -> dict[str, Any]:
    payload = _post(origin, "/api/show", {"name": model})
    details = payload.get("details") or {}
    quant = details.get("quantization_level")
    if not isinstance(quant, str) or not quant.strip():
        raise SystemExit(f"{model} is missing details.quantization_level")
    parameter_size = details.get("parameter_size")
    if not isinstance(parameter_size, str) or not parameter_size.strip():
        raise SystemExit(f"{model} is missing details.parameter_size")
    info = payload.get("model_info") or {}
    return {
        "model": model,
        "format": details.get("format"),
        "family": details.get("family"),
        "parameterSize": parameter_size,
        "parameterCount": info.get("general.parameter_count"),
        "quantization": quant,
        "ollamaDetails": details,
    }


def _hardware(version: str, collected_at: str) -> dict[str, Any]:
    cpuinfo = Path("/proc/cpuinfo").read_text(encoding="utf-8")
    block: dict[str, str] = {}
    for line in cpuinfo.splitlines():
        if not line.strip():
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        block[key.strip()] = value.strip()
    logical = sum(1 for line in cpuinfo.splitlines() if line.startswith("processor"))
    meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
    total_kib = _meminfo_kib(meminfo, "MemTotal")
    available_kib = _meminfo_kib(meminfo, "MemAvailable")
    uname = platform.uname()
    return {
        "cpuModel": block["model name"],
        "cpuFamily": int(block["cpu family"]),
        "cpuModelId": int(block["model"]),
        "cpuStepping": int(block["stepping"]),
        "logicalCpus": logical,
        "memoryTotalBytes": total_kib * 1024,
        "memoryAvailableBytes": available_kib * 1024,
        "platform": platform.platform(),
        "kernel": f"{uname.system} {uname.release} {uname.machine}",
        "backend": "ollama",
        "backendVersion": version,
        "runner": "llamacpp",
        "ggmlLibraries": [],
        "acceleratorLibraries": [],
        "collectedAt": collected_at,
    }


def _mapped_libraries() -> dict[str, list[str]]:
    ggml: set[str] = set()
    accelerator: set[str] = set()
    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="ignore")
            maps = (entry / "maps").read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "llama-server" not in command:
            continue
        for line in maps.splitlines():
            path = line.split()[-1] if line.split() else ""
            name = Path(path).name
            if "libggml" in name or "libllama" in name:
                ggml.add(name)
            lowered = name.lower()
            if any(token in lowered for token in ("cuda", "cublas", "hip", "vulkan", "metal")):
                accelerator.add(name)
    return {"ggml": sorted(ggml), "accelerator": sorted(accelerator)}


def _stop_models(models: list[str]) -> None:
    for model in models:
        subprocess.run(["ollama", "stop", model], check=False, capture_output=True, text=True)


def _ollama_version(origin: str) -> str:
    payload = _get(origin, "/api/version")
    version = payload.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit(f"unexpected /api/version payload: {payload}")
    return version


def _origin(base_url: str) -> str:
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise SystemExit(f"invalid base URL {base_url}")
    return f"{parsed.scheme}://{parsed.netloc}"


def _get(origin: str, path: str) -> dict[str, Any]:
    with httpx.Client(timeout=60) as client:
        response = client.get(origin + path)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} did not return an object")
    return payload


def _post(origin: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=60) as client:
        response = client.post(origin + path, json=body)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} did not return an object")
    return payload


def _meminfo_kib(text: str, key: str) -> int:
    for line in text.splitlines():
        if line.startswith(key + ":"):
            return int(line.split()[1])
    raise SystemExit(f"/proc/meminfo has no {key}")


def _target_id(model: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", model)
    if not cleaned:
        raise SystemExit(f"cannot make a target id from {model}")
    return cleaned


if __name__ == "__main__":
    main()
