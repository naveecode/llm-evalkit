# evalkit

**Live demo (static, GitHub Pages):** https://naveecode.github.io/llm-evalkit/

Evaluate chat models on tasks you define, then compare quality, latency, and cost. One runner talks to any server that implements the OpenAI chat completions API: OpenAI, Groq, Ollama, vLLM, or another compatible endpoint.

The dashboard in this repo is **sample output**. It was produced by running the harness against local fixture endpoints. It is not a benchmark of any real model.

## Run a task

```bash
pip install -e ".[dev]"
export OPENAI_API_KEY=sk-...
evalkit run tasks/json_extract.yaml
```

That writes `evalkit.sqlite` and prints a leaderboard. Cached responses live in `.evalkit/cache.sqlite`. A second run of the same prompts does not call the provider again.

Other endpoints use the same file:

```bash
# Ollama
evalkit run tasks/json_extract.yaml \
  --base-url http://127.0.0.1:11434/v1 \
  --model llama3.1 \
  --api-key ollama

# Groq
evalkit run tasks/json_extract.yaml \
  --base-url https://api.groq.com/openai/v1 \
  --model llama-3.3-70b-versatile \
  --api-key "$GROQ_API_KEY"

# vLLM
evalkit run tasks/json_extract.yaml \
  --base-url http://127.0.0.1:8000/v1 \
  --model your-model \
  --api-key local
```

Flags override the task file. The same values can come from `EVALKIT_BASE_URL`, `EVALKIT_MODEL`, `EVALKIT_API_KEY`, `EVALKIT_JUDGE_BASE_URL`, `EVALKIT_JUDGE_MODEL`, and `EVALKIT_SKIP_JUDGE=1`.

Serve the database:

```bash
evalkit serve
# GET /api/health  /api/runs  /api/runs/{id}  /api/leaderboard
```

## Task file

`tasks/json_extract.yaml` is the worked example: eight synthetic support tickets, a JSON schema, and five metrics. A target needs a provider, a model name, and usually `api_key_env`. Providers fill in a default base URL when you omit one.

| provider | default base URL |
| --- | --- |
| `openai` | `https://api.openai.com/v1` |
| `groq` | `https://api.groq.com/openai/v1` |
| `ollama` | `http://127.0.0.1:11434/v1` |
| `vllm` | `http://127.0.0.1:8000/v1` |
| `openai-compatible` | `https://api.openai.com/v1` |

The prompt may contain `{{ input }}`. The runner sends `temperature` and `max_tokens` to `POST {base_url}/chat/completions`.

Put prices on the task when you care about cost for a model that is not in the built-in catalog:

```yaml
pricing:
  llama3.1:
    input_per_million: 0
    output_per_million: 0
    source: "local Ollama; no provider bill"
```

A model with no task price and no catalog entry is left blank. The harness does not guess.

## Metrics

- **Exact match.** Parsed JSON must equal the reference. Key order is ignored. Non-JSON scores 0. A failed HTTP call is unscored and counted as an error.
- **JSON schema.** The output is parsed, then validated with a Pydantic model built from the task schema. `additionalProperties: false` rejects extra keys. Fenced ` ```json ` blocks are accepted.
- **LLM-as-judge.** A second completion must return `{"score": <0 to 1>, "reason": "..."}`. Scores outside that range, or output that is not that object, are recorded as a judge error. The judge can share the target endpoint or use `judge.base_url` / `--judge-base-url`.
- **Latency.** Wall time of the successful call, in milliseconds. Retries back off on 408, 429, and 5xx. A cache hit stores no new latency, so averages are not pulled down by the cache.
- **Cost.** `prompt_tokens` and `completion_tokens` from the response, times a price per million tokens. Missing usage stays blank. The built-in catalog is OpenAI standard short-context list price, read from the [OpenAI pricing page](https://developers.openai.com/api/docs/pricing) on 2026-10-14. Cached-input discounts and long-context tiers are not applied.

## Dashboard

The Next.js app reads the committed file `web/data/sample-results.json`. It does not call a model at build time, so it deploys on Vercel with no API key.

On Vercel, set the project root to `web`. Framework preset: Next.js.

```bash
cd web
npm install
npm run dev
```

The file is written by `python scripts/export_sample_results.py`. That script serves three fixtures and one grader, then runs the real CLI path (`evalkit.runner.execute`) against them:

- `fixture-exact` returns the reference object.
- `fixture-mutate` lowercases `order_id` on even rows and drops `email` on odd rows.
- `fixture-prose` returns a sentence.
- `fixture-judge` returns the fraction of reference fields that still match. It is not an LLM.

Token counts in that file are the fixture's own `usage` field (about four characters per token). Cost multiplies those counts by an illustrative rate equal to the gpt-4o-mini list price, so the column shows the formula. Latency is localhost round-trip from the run that wrote the file. `tests/test_sample_results.py` recomputes exact match, schema validity, judge overlap, and cost from the stored predictions. If you edit a number by hand, that test fails.

Regenerate the file instead of editing it. Latency will change because it is a measurement.

## Fine-tuning

[notebooks/qlora_finetune.ipynb](notebooks/qlora_finetune.ipynb) is a Colab recipe: 4-bit Llama 3.2 1B Instruct, LoRA adapters through Unsloth, supervised fine-tuning through TRL. The training rows are format examples and are not the eval tickets. The notebook does not report a score. After you train, serve the base and the adapter on OpenAI-compatible endpoints and run the same YAML through `evalkit`.

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/naveecode/llm-evalkit/blob/main/notebooks/qlora_finetune.ipynb)

## Tests

```bash
pytest -q
cd web && npm run lint && npm run typecheck
```

Python tests mock HTTP with `respx`. `tests/test_cli.py` starts a local server and runs `python -m evalkit run`. CI does both the pytest job and the Next.js lint and typecheck.

## Layout

```
evalkit/        runner, metrics, SQLite, FastAPI, CLI
tasks/          YAML task definitions
scripts/        regenerate the sample dashboard file
web/            Next.js 14 dashboard
notebooks/      QLoRA Colab recipe
tests/
```

API keys are read from the environment and are not written to SQLite.

## Limits

Chat completions only. Exact match is strict on purpose; the judge is the fuzzy metric, and it is only as good as the model you point it at. Cost ignores prompt-cache discounts. SQLite is the store: one machine, one writer. The published dashboard is fixture output, labeled sample on every page.
