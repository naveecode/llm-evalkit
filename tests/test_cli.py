from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        if body.get("model") == "judge-model":
            content = '{"score": 1, "reason": "matches"}'
        else:
            content = '{"name": "Ada"}'
        payload = json.dumps(
            {
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def test_cli_run_against_local_server(tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    task = tmp_path / "task.yaml"
    task.write_text(
        f"""
name: cli_task
description: cli
version: "1"
prompt:
  system: Return JSON.
  user: "Ticket: {{{{ input }}}}"
output:
  format: json
  schema:
    type: object
    additionalProperties: false
    required: [name]
    properties:
      name: {{type: string}}
metrics: [exact_match, json_schema, llm_judge, latency, cost]
judge:
  rubric: Score 1 when the name matches.
  model: judge-model
dataset:
  samples:
    - id: s1
      input: Ada ticket
      expected:
        name: Ada
targets:
  - id: local
    provider: openai-compatible
    model: local-fixture
    base_url: http://127.0.0.1:{port}/v1
pricing:
  local-fixture:
    input_per_million: 0.15
    output_per_million: 0.60
    source: cli test rate
""",
        encoding="utf-8",
    )
    db = tmp_path / "results.sqlite"
    cache = tmp_path / "cache.sqlite"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env.pop("EVALKIT_BASE_URL", None)
    env.pop("EVALKIT_MODEL", None)
    env.pop("EVALKIT_API_KEY", None)
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "evalkit",
                "run",
                str(task),
                "--db",
                str(db),
                "--cache",
                str(cache),
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        server.shutdown()
    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert "cli_task" in completed.stdout
    assert "1/1" in completed.stdout
    assert "local" in completed.stdout
