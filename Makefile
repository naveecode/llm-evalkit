.PHONY: test lint sample measured web

PY ?= python

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check evalkit tests scripts

sample:
	$(PY) scripts/export_sample_results.py

measured:
	$(PY) scripts/export_measured_results.py \
		--base-url http://127.0.0.1:11434/v1 \
		--api-key ollama \
		--model qwen2.5:0.5b \
		--model smollm2:360m \
		--model llama3.2:1b

web:
	cd web && npm run lint && npm run typecheck
