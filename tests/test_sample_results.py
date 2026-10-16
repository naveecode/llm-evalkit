"""The committed dashboard file must be harness output, and it must say so."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from evalkit.metrics import exact_match, json_schema_metric
from evalkit.task import load_task

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from export_sample_results import field_overlap  # noqa: E402

SAMPLE_PATH = ROOT / "web" / "data" / "sample-results.json"
RESULTS_SOURCE = ROOT / "web" / "lib" / "results.ts"


def test_sample_file_matches_the_metrics():
    data = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    assert data["kind"] == "sample"
    assert data["run"]["label"] == "sample"
    assert "not a benchmark" in data["disclaimer"].lower()
    assert data["generator"] == "scripts/export_sample_results.py"
    assert "fixture-judge" in data["fixtures"]
    assert "not an LLM" in data["fixtures"]["fixture-judge"]
    task = load_task(ROOT / "tasks" / "json_extract.yaml")
    schema = task.output.json_schema
    assert data["run"]["targets"], "sample file has no targets"
    for target in data["run"]["targets"]:
        assert target["targetId"].startswith("fixture-")
        assert not target["targetId"].lower().startswith("gpt")
        price = data["run"]["pricing"][target["model"]]
        samples = target["samples"]
        exact_passes = 0
        schema_passes = 0
        judge_scores = []
        for sample in samples:
            exact = exact_match(sample["expected"], sample["predictionText"])["score"]
            validity = json_schema_metric(sample["predictionText"], schema)["score"]
            overlap = field_overlap(sample["expected"], sample["predictionText"])
            assert sample["metrics"]["exactMatch"] == exact
            assert sample["metrics"]["jsonSchema"] == validity
            assert sample["metrics"]["judge"] == pytest.approx(overlap)
            cost = (
                sample["promptTokens"] * price["inputPerMillion"]
                + sample["completionTokens"] * price["outputPerMillion"]
            ) / 1_000_000
            assert sample["costUsd"] == pytest.approx(cost)
            assert sample["latencyMs"] is not None and sample["latencyMs"] >= 0
            assert sample["cached"] is False
            assert sample["promptTokens"] > 0
            exact_passes += exact == 1.0
            schema_passes += validity == 1.0
            judge_scores.append(sample["metrics"]["judge"])
        summary = target["summary"]
        assert summary["exactMatch"]["passes"] == exact_passes
        assert summary["jsonSchema"]["passes"] == schema_passes
        assert summary["judgeMean"] == pytest.approx(sum(judge_scores) / len(judge_scores))
        assert summary["costComplete"] is True


def test_dashboard_reads_the_sample_file():
    source = RESULTS_SOURCE.read_text(encoding="utf-8")
    assert "sample-results.json" in source
    assert 'kind !== "sample"' in source
    sample_page = (ROOT / "web" / "app" / "sample" / "page.tsx").read_text(encoding="utf-8")
    assert "sampleResults" in sample_page
    assert "Fixture output" in sample_page
