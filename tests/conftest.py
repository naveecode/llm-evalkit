from __future__ import annotations

from typing import Any

from evalkit.pricing import ModelPrice
from evalkit.task import Dataset, JudgeSpec, OutputSpec, Prompt, Sample, Target, TaskSpec

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name"],
    "properties": {"name": {"type": "string"}},
}


def make_task(
    base_url: str,
    *,
    model: str = "fixture",
    with_judge: bool = False,
    api_key: str | None = "secret",
    samples: list[Sample] | None = None,
) -> TaskSpec:
    metrics = ["exact_match", "json_schema", "latency", "cost"]
    judge = None
    if with_judge:
        metrics.append("llm_judge")
        judge = JudgeSpec(rubric="Score field overlap from 0 to 1.", model="judge-model")
    return TaskSpec(
        name="json_extract",
        description="unit task",
        dataset=Dataset(
            samples=samples
            or [Sample(id="s1", input="ticket about Ada", expected={"name": "Ada"})]
        ),
        prompt=Prompt(system="Return JSON.", user="Ticket:\n{{ input }}"),
        output=OutputSpec(format="json", json_schema=SCHEMA),
        metrics=metrics,  # type: ignore[arg-type]
        targets=[
            Target(
                id="fixture",
                provider="openai-compatible",
                model=model,
                base_url=base_url,
                api_key=api_key,
            )
        ],
        judge=judge,
        pricing={
            model: ModelPrice(
                input_per_million=0.15,
                output_per_million=0.60,
                source="unit test rate",
            )
        },
    )
