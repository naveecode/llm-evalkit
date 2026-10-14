"""Turn stored rows into the JSON shape used by the API and the dashboard."""

from __future__ import annotations

from typing import Any

from evalkit.store import Store

SAMPLE_DISCLAIMER = (
    "Sample output produced by evalkit against local fixture endpoints. "
    "These numbers are not a benchmark of any real model. "
    "Latency is the localhost round trip from the run that wrote this file. "
    "Token counts are the usage field returned by the fixture, not a tokenizer. "
    "Cost multiplies those counts by the illustrative rates stored with the run."
)

MEASURED_NOTE = (
    "Measured by evalkit. Cost is list price times reported token counts. "
    "A blank cost means this model had no price in the task file or the built-in catalog."
)


def build_run_payload(store: Store, run_id: str) -> dict[str, Any] | None:
    run = store.get_run(run_id)
    if run is None:
        return None
    config = run["config"]
    grouped = _group_samples(store.samples(run_id), config)
    kind = "sample" if run["label"] == "sample" else "measured"
    targets = []
    for target_meta, samples in grouped:
        public_samples = [_public_sample(sample) for sample in samples]
        summary = summarize(public_samples)
        summary["targetId"] = target_meta["id"]
        summary["model"] = target_meta["model"]
        summary["provider"] = target_meta["provider"]
        targets.append(
            {
                "targetId": target_meta["id"],
                "provider": target_meta["provider"],
                "model": target_meta["model"],
                "baseUrl": target_meta.get("baseUrl"),
                "summary": summary,
                "samples": public_samples,
            }
        )
    return {
        "kind": kind,
        "disclaimer": SAMPLE_DISCLAIMER if kind == "sample" else MEASURED_NOTE,
        "run": {
            "id": run["id"],
            "taskName": run["task_name"],
            "taskVersion": run["task_version"],
            "description": (config.get("description") or "").strip(),
            "createdAt": run["created_at"],
            "label": run["label"],
            "metrics": config.get("metrics") or [],
            "pricing": config.get("pricing") or {},
            "targets": targets,
        },
    }


def summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    errors = sum(1 for sample in samples if sample.get("error"))
    exact = _binary(samples, "exactMatch")
    schema = _binary(samples, "jsonSchema")
    judge_scores = [sample["metrics"]["judge"] for sample in samples if sample["metrics"]["judge"] is not None]
    latencies = [sample["latencyMs"] for sample in samples if sample.get("latencyMs") is not None]
    costs = [sample["costUsd"] for sample in samples]
    known_costs = [cost for cost in costs if cost is not None]
    complete = len(samples) > 0 and len(known_costs) == len(samples)
    mean_cost = _mean(known_costs) if complete else None
    return {
        "n": len(samples),
        "errors": errors,
        "exactMatch": exact,
        "jsonSchema": schema,
        "judgeMean": _round(_mean(judge_scores), 6),
        "judgeScored": len(judge_scores),
        "latencyMsMean": _round(_mean(latencies), 3),
        "latencyMsP50": _round(_p50(latencies), 3),
        "liveLatencyCount": len(latencies),
        "costUsdTotal": _round(sum(known_costs), 12) if complete else None,
        "costPer1kUsd": _round(mean_cost * 1000, 12) if mean_cost is not None else None,
        "costComplete": complete,
    }


def generation_failed(payload: dict[str, Any]) -> bool:
    for target in payload["run"]["targets"]:
        for sample in target["samples"]:
            if sample.get("error"):
                return True
    return False


def _group_samples(
    rows: list[dict[str, Any]], config: dict[str, Any]
) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    meta = {item["id"]: item for item in config.get("targets") or []}
    order = [item["id"] for item in config.get("targets") or []]
    sample_order = {sample_id: index for index, sample_id in enumerate(config.get("sampleOrder") or [])}
    buckets: dict[str, list[dict[str, Any]]] = {target_id: [] for target_id in order}
    for row in rows:
        buckets.setdefault(row["target_id"], []).append(row)
        if row["target_id"] not in meta:
            meta[row["target_id"]] = {
                "id": row["target_id"],
                "provider": row["provider"],
                "model": row["model"],
                "baseUrl": row["base_url"],
            }
            order.append(row["target_id"])
    grouped = []
    for target_id in order:
        samples = buckets.get(target_id) or []
        samples.sort(key=lambda row: sample_order.get(row["sample_id"], 10**6))
        grouped.append((meta[target_id], samples))
    return grouped


def _public_sample(row: dict[str, Any]) -> dict[str, Any]:
    metrics = row.get("metrics") or {}
    exact = metrics.get("exact_match") or {}
    schema = metrics.get("json_schema") or {}
    judge = metrics.get("llm_judge") or {}
    return {
        "sampleId": row["sample_id"],
        "input": row["input_text"],
        "expected": row["expected"],
        "predictionText": row["prediction_text"],
        "parsed": row["parsed"],
        "promptTokens": row["prompt_tokens"],
        "completionTokens": row["completion_tokens"],
        "latencyMs": _round(row["latency_ms"], 3),
        "costUsd": _round(row["cost_usd"], 12),
        "cached": bool(row["cached"]),
        "attempts": row["attempts"],
        "error": row["error"],
        "metrics": {
            "exactMatch": exact.get("score"),
            "jsonSchema": schema.get("score"),
            "judge": judge.get("score"),
            "judgeReason": judge.get("reason"),
            "judgeError": judge.get("error"),
            "schemaErrors": schema.get("errors") or [],
            "mismatchedFields": exact.get("mismatchedFields") or [],
        },
    }


def _binary(samples: list[dict[str, Any]], key: str) -> dict[str, Any]:
    scores = [sample["metrics"][key] for sample in samples]
    scored = [score for score in scores if score is not None]
    passes = sum(1 for score in scored if score == 1.0)
    return {
        "passes": passes,
        "scored": len(scored),
        "rate": (passes / len(scored)) if scored else None,
    }


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _p50(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = (len(ordered) - 1) / 2
    low = int(mid)
    high = min(low + 1, len(ordered) - 1)
    frac = mid - low
    return ordered[low] * (1 - frac) + ordered[high] * frac


def _round(value: float | None, digits: int) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)
