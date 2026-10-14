"""Async client for any server that speaks the OpenAI chat completions API."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from evalkit.cache import ResponseCache, cache_key

RETRY_STATUSES = {408, 429, 500, 502, 503, 504}


class ChatError(Exception):
    def __init__(self, message: str, *, attempts: int) -> None:
        super().__init__(message)
        self.attempts = attempts


@dataclass
class ChatResponse:
    content: str
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: float | None
    original_latency_ms: float | None
    cached: bool
    attempts: int


class OpenAICompatibleClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        cache: ResponseCache | None,
        *,
        max_retries: int = 3,
        backoff_s: float = 0.25,
        max_backoff_s: float = 8.0,
    ) -> None:
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1")
        self._http = http
        self._cache = cache
        self._max_retries = max_retries
        self._backoff_s = backoff_s
        self._max_backoff_s = max_backoff_s

    async def chat(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        extra: dict[str, Any] | None = None,
    ) -> ChatResponse:
        extra = extra or {}
        key = cache_key(
            base_url=base_url,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            extra=extra,
        )
        if self._cache is not None:
            cached = self._cache.get(key)
            if cached is not None:
                return ChatResponse(
                    content=str(cached.get("content") or ""),
                    prompt_tokens=_optional_int(cached.get("prompt_tokens")),
                    completion_tokens=_optional_int(cached.get("completion_tokens")),
                    latency_ms=None,
                    original_latency_ms=_optional_float(cached.get("latency_ms")),
                    cached=True,
                    attempts=0,
                )

        url = base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        body.update(extra)
        delay = self._backoff_s
        last_error = "request failed"
        for attempt in range(1, self._max_retries + 1):
            started = time.perf_counter()
            try:
                response = await self._http.post(url, headers=headers, json=body)
            except httpx.TransportError as exc:
                last_error = f"transport error: {exc}"
                if attempt >= self._max_retries:
                    raise ChatError(last_error, attempts=attempt) from exc
                await _sleep(delay)
                delay = min(delay * 2, self._max_backoff_s)
                continue
            elapsed_ms = (time.perf_counter() - started) * 1000
            if response.status_code in RETRY_STATUSES and attempt < self._max_retries:
                last_error = _http_error(response)
                await _sleep(delay)
                delay = min(delay * 2, self._max_backoff_s)
                continue
            if response.status_code >= 400:
                raise ChatError(_http_error(response), attempts=attempt)
            try:
                payload = response.json()
                content, prompt_tokens, completion_tokens = _parse_completion(payload)
            except ValueError as exc:
                raise ChatError(str(exc), attempts=attempt) from exc
            if self._cache is not None:
                self._cache.put(
                    key,
                    {
                        "content": content,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "latency_ms": elapsed_ms,
                    },
                )
            return ChatResponse(
                content=content,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=elapsed_ms,
                original_latency_ms=elapsed_ms,
                cached=False,
                attempts=attempt,
            )
        raise ChatError(last_error, attempts=self._max_retries)


def _http_error(response: httpx.Response) -> str:
    snippet = response.text[:300].replace("\n", " ")
    return f"HTTP {response.status_code}: {snippet}"


def _parse_completion(payload: Any) -> tuple[str, int | None, int | None]:
    if not isinstance(payload, dict):
        raise ValueError("completion payload was not an object")
    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("completion payload has no choices[0].message") from exc
    content = _message_text(message.get("content") if isinstance(message, dict) else None)
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return (
        content,
        _optional_int(usage.get("prompt_tokens")),
        _optional_int(usage.get("completion_tokens")),
    )


def _message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content)


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


async def _sleep(seconds: float) -> None:
    if seconds <= 0:
        return
    import asyncio

    await asyncio.sleep(seconds)
