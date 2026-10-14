"""Write web/data/sample-results.json by running the harness against fixtures.

The fixtures are deterministic HTTP handlers, not models. Scores in the file are
whatever evalkit computed for those handlers. Re-run this script to regenerate
the file; do not hand-edit the numbers.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from evalkit.cache import ResponseCache
from evalkit.metrics import build_judge_messages
from evalkit.pricing import ModelPrice
from evalkit.report import build_run_payload
from evalkit.runner import ClientOptions, RunOverrides, execute
from evalkit.schema_model import parse_json_value
from evalkit.store import Store
from evalkit.task import Target, load_task

ROOT = Path(__file__).resolve().parents[1]
TASK_PATH = ROOT / "tasks" / "json_extract.yaml"
OUTPUT_PATH = ROOT / "web" / "data" / "sample-results.json"
PORT = 8765

FIXTURES = {
    "fixture-exact": "Returns the reference JSON object for the ticket.",
    "fixture-mutate": (
        "Even positions in dataset order (0, 2, 4, ...) lowercase order_id. "
        "Odd positions omit email. Every other field is copied from the reference."
    ),
    "fixture-prose": "Returns one sentence and no JSON object.",
    "fixture-judge": (
        "Returns the fraction of reference fields whose values are unchanged in the "
        "parsed prediction. A non-JSON prediction scores 0. This is not an LLM."
    ),
}

PRICING_NOTE = (
    "Each fixture price is an illustrative rate equal to the OpenAI gpt-4o-mini "
    "standard list price observed at https://developers.openai.com/api/docs/pricing "
    "on 2026-10-14 ($0.15 / 1M input, $0.60 / 1M output). "
    "It is applied to token counts the fixture itself put in the usage field "
    "(about 4 characters per token). It is not a bill from any provider."
)

ILLUSTRATIVE = ModelPrice(
    input_per_million=0.15,
    output_per_million=0.60,
    source=(
        "Illustrative rate set to the OpenAI gpt-4o-mini standard list price "
        "(https://developers.openai.com/api/docs/pricing, 2026-10-14). "
        "Applied only to fixture usage counts."
    ),
    as_of="2026-10-14",
)

PROSE = "I extracted a ticket but this fixture does not emit JSON."


def field_overlap(expected: Any, prediction_text: str) -> float:
    if not isinstance(expected, dict) or not expected:
        return 0.0
    parsed, error = parse_json_value(prediction_text)
    if error or not isinstance(parsed, dict):
        return 0.0
    hits = sum(1 for key, value in expected.items() if parsed.get(key) == value)
    return hits / len(expected)


def _usage(messages: list[dict[str, str]], content: str) -> dict[str, int]:
    prompt = "\n".join(message.get("content") or "" for message in messages)
    return {
        "prompt_tokens": max(1, (len(prompt) + 3) // 4),
        "completion_tokens": max(1, (len(content) + 3) // 4),
    }


def _find(user: str, samples: list[Any]) -> tuple[Any, int]:
    for index, sample in enumerate(samples):
        if sample.input in user:
            return sample.expected, index
    raise KeyError("ticket not found in prompt")


def _judge_content(user: str) -> str:
    _marker, rest = user.split("\n\nEXPECTED:\n", 1)
    expected_text, prediction = rest.split("\n\nPREDICTION:\n", 1)
    expected = json.loads(expected_text)
    score = field_overlap(expected, prediction)
    return json.dumps({"score": score, "reason": f"field overlap {score:.3f}"})


def make_handler(samples: list[Any]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            model = body.get("model")
            messages = body.get("messages") or []
            user = next(
                (message.get("content") or "" for message in messages if message.get("role") == "user"),
                "",
            )
            if model == "fixture-judge":
                content = _judge_content(user)
                status = 200
            elif model == "fixture-exact":
                expected, _index = _find(user, samples)
                content = json.dumps(expected)
                status = 200
            elif model == "fixture-mutate":
                expected, index = _find(user, samples)
                mutated = dict(expected)
                if index % 2 == 0:
                    mutated["order_id"] = str(mutated["order_id"]).lower()
                else:
                    mutated.pop("email", None)
                content = json.dumps(mutated)
                status = 200
            elif model == "fixture-prose":
                content = PROSE
                status = 200
            else:
                content = json.dumps({"error": "unknown fixture"})
                status = 400
            if status != 200:
                payload = content.encode("utf-8")
            else:
                payload = json.dumps(
                    {
                        "choices": [{"message": {"role": "assistant", "content": content}}],
                        "usage": _usage(messages, content),
                    }
                ).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    return Handler


def main() -> None:
    # Importing build_judge_messages keeps the fixture markers tied to the harness.
    _ = build_judge_messages(rubric="x", input_text="y", expected={}, prediction="z")
    task = load_task(TASK_PATH)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), make_handler(list(task.dataset.samples)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{PORT}/v1"
    try:
        task.targets = [
            Target(
                id=name,
                provider="openai-compatible",
                model=name,
                base_url=base_url,
                temperature=0,
                max_tokens=200,
            )
            for name in ("fixture-exact", "fixture-mutate", "fixture-prose")
        ]
        if task.judge is None:
            raise SystemExit("task is missing a judge block")
        task.judge = task.judge.model_copy(
            update={
                "model": "fixture-judge",
                "base_url": base_url,
                "api_key": None,
                "api_key_env": None,
            }
        )
        task.pricing = {name: ILLUSTRATIVE for name in ("fixture-exact", "fixture-mutate", "fixture-prose")}
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            store = Store(tmp_path / "results.sqlite")
            cache = ResponseCache(tmp_path / "cache.sqlite")
            import asyncio

            run_id = asyncio.run(
                execute(
                    task,
                    store=store,
                    cache=cache,
                    overrides=RunOverrides(label="sample"),
                    options=ClientOptions(concurrency=4, backoff_s=0),
                )
            )
            payload = build_run_payload(store, run_id)
        if payload is None:
            raise SystemExit("sample run was not stored")
        payload["generator"] = "scripts/export_sample_results.py"
        payload["fixtures"] = FIXTURES
        payload["pricingNote"] = PRICING_NOTE
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {OUTPUT_PATH}")
        for target in payload["run"]["targets"]:
            summary = target["summary"]
            print(
                target["targetId"],
                "exact",
                f"{summary['exactMatch']['passes']}/{summary['exactMatch']['scored']}",
                "schema",
                f"{summary['jsonSchema']['passes']}/{summary['jsonSchema']['scored']}",
                "judge",
                summary["judgeMean"],
            )
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
