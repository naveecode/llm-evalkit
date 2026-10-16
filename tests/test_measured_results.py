"""The committed measured file must be harness output for the local CPU run."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalkit.metrics import exact_match, json_schema_metric
from evalkit.task import load_task

ROOT = Path(__file__).resolve().parents[1]
MEASURED_PATH = ROOT / "web" / "data" / "measured-results.json"
SAMPLE_PATH = ROOT / "web" / "data" / "sample-results.json"

PUBLISHED = {
    "json_extract": {
        "createdAt": "2026-10-16T05:09:30.774202+00:00",
        "qwen2.5:0.5b": {"exact": 1, "schema": 8, "p50": 716.447},
        "smollm2:360m": {"exact": 0, "schema": 7, "p50": 1149.926},
        "llama3.2:1b": {"exact": 3, "schema": 8, "p50": 1122.961},
    },
    "classification": {
        "createdAt": "2026-10-16T05:09:59.639367+00:00",
        "qwen2.5:0.5b": {"exact": 4, "schema": 8, "p50": 170.027},
        "smollm2:360m": {"exact": 0, "schema": 0, "p50": 677.082},
        "llama3.2:1b": {"exact": 2, "schema": 4, "p50": 432.381},
    },
}


def test_measured_file_matches_the_metrics():
    data = json.loads(MEASURED_PATH.read_text(encoding="utf-8"))
    assert data["kind"] == "measured"
    assert data["judgeRan"] is False
    assert data["generator"] == "scripts/export_measured_results.py"
    assert "judge was not called" in data["disclaimer"]
    assert "fixture-exact" not in MEASURED_PATH.read_text(encoding="utf-8")

    hardware = data["hardware"]
    assert hardware["cpuModel"] == "Intel(R) Xeon(R) Processor"
    assert hardware["cpuFamily"] == 6
    assert hardware["cpuModelId"] == 207
    assert hardware["cpuStepping"] == 2
    assert hardware["logicalCpus"] == 4
    assert hardware["memoryTotalBytes"] == 16780574720
    assert hardware["backend"] == "ollama"
    assert hardware["backendVersion"] == "0.40.5"
    assert hardware["runner"] == "llamacpp"
    assert hardware["acceleratorLibraries"] == []
    assert "libggml-cpu-sapphirerapids.so" in hardware["ggmlLibraries"]

    models = data["models"]
    assert [model["model"] for model in models] == ["qwen2.5:0.5b", "smollm2:360m", "llama3.2:1b"]
    assert [model["quantization"] for model in models] == ["Q4_K_M", "F16", "Q8_0"]
    by_model = {}
    for model in models:
        assert model["quantization"] == model["ollamaDetails"]["quantization_level"]
        assert model["parameterSize"] == model["ollamaDetails"]["parameter_size"]
        assert model["contextLength"] == 4096
        assert len(model["digest"]) == 64
        by_model[model["model"]] = model

    assert [run["taskName"] for run in data["runs"]] == ["json_extract", "classification"]
    for run in data["runs"]:
        expected = PUBLISHED[run["taskName"]]
        assert run["label"] == "measured"
        assert run["createdAt"] == expected["createdAt"]
        task = load_task(ROOT / "tasks" / f"{run['taskName']}.yaml")
        schema = task.output.json_schema
        assert len(run["targets"]) == 3
        for target in run["targets"]:
            assert not target["targetId"].startswith("fixture-")
            assert target["quantization"] == by_model[target["model"]]["quantization"]
            price = run["pricing"][target["model"]]
            assert price["inputPerMillion"] == 0
            assert price["outputPerMillion"] == 0
            assert price["source"] == "local Ollama; no provider bill"
            samples = target["samples"]
            exact_passes = 0
            schema_passes = 0
            for sample in samples:
                exact = exact_match(sample["expected"], sample["predictionText"])["score"]
                validity = json_schema_metric(sample["predictionText"], schema)["score"]
                assert sample["metrics"]["exactMatch"] == exact
                assert sample["metrics"]["jsonSchema"] == validity
                assert sample["metrics"]["judge"] is None
                assert sample["cached"] is False
                assert sample["error"] is None
                assert sample["promptTokens"] > 0
                assert sample["completionTokens"] > 0
                cost = (
                    sample["promptTokens"] * price["inputPerMillion"]
                    + sample["completionTokens"] * price["outputPerMillion"]
                ) / 1_000_000
                assert sample["costUsd"] == pytest.approx(cost)
                exact_passes += exact == 1.0
                schema_passes += validity == 1.0
            summary = target["summary"]
            published = expected[target["model"]]
            assert summary["n"] == len(samples) == len(task.dataset.samples)
            assert summary["errors"] == 0
            assert summary["exactMatch"]["passes"] == exact_passes == published["exact"]
            assert summary["jsonSchema"]["passes"] == schema_passes == published["schema"]
            assert summary["judgeMean"] is None
            assert summary["judgeScored"] == 0
            assert summary["latencyMsP50"] == pytest.approx(published["p50"])
            assert summary["costComplete"] is True
            assert summary["costPer1kUsd"] == 0


def test_sample_file_stays_separate():
    sample = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    measured = json.loads(MEASURED_PATH.read_text(encoding="utf-8"))
    assert sample["kind"] == "sample"
    assert measured["kind"] == "measured"
    assert sample["run"]["id"] not in {run["id"] for run in measured["runs"]}
    results = (ROOT / "web" / "lib" / "results.ts").read_text(encoding="utf-8")
    home = (ROOT / "web" / "app" / "page.tsx").read_text(encoding="utf-8")
    sample_page = (ROOT / "web" / "app" / "sample" / "page.tsx").read_text(encoding="utf-8")
    assert "sample-results.json" in results
    assert "measured-results.json" in results
    assert 'kind !== "sample"' in results
    assert 'kind !== "measured"' in results
    assert "measuredResults" in home
    assert "sampleResults" not in home
    assert "sampleResults" in sample_page
    assert "measuredResults" not in sample_page
