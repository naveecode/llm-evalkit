# llm-evalkit
Evaluate and fine-tune open-weight LLMs on your own tasks, and compare cost/quality in a dashboard.

**Goal:** a reproducible eval harness (exact-match, JSON-schema validity, LLM-as-judge, latency, $/1k requests) across OpenAI-compatible endpoints (OpenAI, Groq, Ollama, vLLM) plus a QLoRA fine-tuning recipe and before/after comparisons.

**Scope (v1):** YAML task specs · async runner with caching + retries · Pydantic structured-output checks · results in SQLite/Postgres · Next.js (TypeScript) dashboard with leaderboard + per-sample diffs · QLoRA (Unsloth/TRL) Colab recipe · published demo.

Status: scaffolding. Built in public, roadmap in issues.
