# evalkit

**Live leaderboard:** https://naveecode.github.io/llm-evalkit/

Evaluate chat models on tasks you define, then compare quality, latency, and cost. One runner talks to any server that implements the OpenAI chat completions API: OpenAI, Groq, Ollama, vLLM, or another compatible endpoint.

The live site is a measured run of three small Ollama models on CPU. Fixture output stays in `web/data/sample-results.json` and at `/sample`, labeled sample on that page.

## Measured CPU run

Live leaderboard: https://naveecode.github.io/llm-evalkit/

`web/data/measured-results.json` was written by `scripts/export_measured_results.py` on 2026-10-16. The numbers below are the summaries in that file. `tests/test_measured_results.py` recomputes exact match, schema validity, and cost from the stored predictions.

### Machine

- CPU: `Intel(R) Xeon(R) Processor`, family 6, model 207, stepping 2, 4 logical CPUs (`/proc/cpuinfo`)
- Memory: 15.63 GiB (`MemTotal` 16780574720 bytes). 3.45 GiB was available when the file was written.
- Server: Ollama 0.40.5, runner `llamacpp`, context length 4096 from `/api/ps`
- Library mapped into `llama-server`: `libggml-cpu-sapphirerapids.so`, plus `libggml-base.so.0.27.0`, `libggml.so.0.27.0`, `libllama.so.0.7.0`, `libllama-common.so.0.7.0`, and `libllama-server-impl.so`
- `/api/ps` reported a non-zero `size_vram` for these processes. The mapped libraries above are the CPU build. No CUDA, HIP, Vulkan, or Metal library was mapped.

### Models

Quantization and parameter size are `details.quantization_level` and `details.parameter_size` from `POST /api/show` for the tag that was requested.

| Tag | Quantization | Parameters | Family | Digest |
| --- | --- | --- | --- | --- |
| `qwen2.5:0.5b` | Q4_K_M | 494.03M | qwen2 | `a8b0c5157701` |
| `smollm2:360m` | F16 | 361.82M | llama | `297281b699fc` |
| `llama3.2:1b` | Q8_0 | 1.2B | llama | `baf6a787fdff` |

The SmolLM2 tag on this Ollama build is F16. The Llama 3.2 1B tag is Q8_0. The Qwen2.5 0.5B tag is Q4_K_M.

### Scores

Both task files were run in full, so n=8 for every row. Temperature was 0. Requests ran one at a time, all samples of one model before the next. Each model was stopped before the task, so the first sample's wall time can include weight load. In this file the first sample is the slowest row for every model. The judge was not called. Cost uses a price of $0 per million tokens, source `local Ollama; no provider bill`, times the token counts Ollama returned. Every target finished with 0 request errors.

`json_extract`, 2026-10-16 05:09:30 UTC:

| Model | Quant | Exact | Schema | p50 |
| --- | --- | --- | --- | --- |
| `qwen2.5:0.5b` | Q4_K_M | 1/8 | 8/8 | 716.447 ms |
| `smollm2:360m` | F16 | 0/8 | 7/8 | 1149.926 ms |
| `llama3.2:1b` | Q8_0 | 3/8 | 8/8 | 1122.961 ms |

On the schema-valid misses, the only mismatched field is `issue`. Name, email, and order id matched the reference. Qwen2.5-0.5B's exact match is `cancel`. Llama-3.2-1B's exact matches are `billing`, `size`, and `cancel`. SmolLM2-360M failed the schema on `damaged` because the JSON object was cut off.

`classification`, 2026-10-16 05:09:59 UTC:

| Model | Quant | Exact | Schema | p50 |
| --- | --- | --- | --- | --- |
| `qwen2.5:0.5b` | Q4_K_M | 4/8 | 8/8 | 170.027 ms |
| `smollm2:360m` | F16 | 0/8 | 0/8 | 677.082 ms |
| `llama3.2:1b` | Q8_0 | 2/8 | 4/8 | 432.381 ms |

Qwen2.5-0.5B returned one allowed label on every ticket. The matches are both product tickets and both account tickets. Both billing tickets were labeled `account`. The shipping tickets were labeled `product` and `account`.

Llama-3.2-1B matched both billing tickets. `not-delivered` and `close-account` were schema-valid and labeled `billing`. On `late-ship`, `broken-unit`, `wrong-color`, and `cannot-login` the label string was a copy of the ticket, which fails the enum.

SmolLM2-360M added extra keys on seven tickets (`status`, `message`, and on `late-ship` further status fields), which `additionalProperties: false` rejects. `wrong-color` was prose. Every parsed object that included `label` set it to `billing`.

The first-sample latencies, which include model load, were 1852.707 ms, 2669.229 ms, and 3733.178 ms on `json_extract`, and 1324.719 ms, 1903.94 ms, and 2786.443 ms on `classification`, in model order Qwen, SmolLM2, Llama.

n=8 is the whole file. These figures describe this machine, these Ollama tags, and these 16 prompts.

### Reproduce

```bash
ollama serve   # Ollama 0.40.5 on 127.0.0.1:11434 in this run
ollama pull qwen2.5:0.5b
ollama pull smollm2:360m
ollama pull llama3.2:1b
pip install -e .
python scripts/export_measured_results.py \
  --base-url http://127.0.0.1:11434/v1 \
  --api-key ollama \
  --model qwen2.5:0.5b \
  --model smollm2:360m \
  --model llama3.2:1b
```

That rewrites `web/data/measured-results.json`. A later run will not reproduce these latencies. Scores can also move if a tag's weights or quantization change.

Live leaderboard: https://naveecode.github.io/llm-evalkit/

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

`tasks/json_extract.yaml` extracts name, email, order id, and issue from eight synthetic support tickets. `tasks/classification.yaml` labels eight short tickets as billing, shipping, product, or account. Both files ship a JSON schema and the same five metrics. A target needs a provider, a model name, and usually `api_key_env`. Providers fill in a default base URL when you omit one.

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

The Next.js app reads two committed files and does not call a model at build time.

- `web/data/measured-results.json` is the leaderboard at `/`. Each row shows the model tag, the Ollama quantization, n, and the run date. The hardware strip shows the CPU, memory, Ollama version, and the mapped ggml library.
- `web/data/sample-results.json` is the fixture page at `/sample`. It stays labeled sample.

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
tasks/          json_extract and classification
scripts/        regenerate the sample file and the measured results
web/            Next.js 14 dashboard
notebooks/      QLoRA Colab recipe
tests/
```

API keys are read from the environment and are not written to SQLite.

## Limits

Chat completions only. Exact match is strict on purpose; the judge is the fuzzy metric, and it is only as good as the model you point it at. The published CPU run left the judge unscored. Cost ignores prompt-cache discounts. SQLite is the store: one machine, one writer. The leaderboard is the measured file. Fixture output is only on `/sample`.
