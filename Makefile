.PHONY: test lint sample web

PY ?= python

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check evalkit tests scripts

sample:
	$(PY) scripts/export_sample_results.py

web:
	cd web && npm run lint && npm run typecheck
