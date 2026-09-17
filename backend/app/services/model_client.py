"""被测模型调用：OpenAI 兼容 /v1/chat/completions；模板映射、并发限流、熔断。"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta

import httpx

from app.models.eval_model import EvalModel
from app.services.tls_channel import httpx_tls_kwargs
from app.services.metrics import observe_model_invoke
from app.utils.jsonutil import loads

_semaphores: dict[int, asyncio.Semaphore] = {}
CIRCUIT_FAILS = 3
CIRCUIT_COOLDOWN = timedelta(seconds=30)

DEFAULT_RESPONSE_MAPPING = {
    "output": "choices.0.message.content",
    "tokens": "usage.total_tokens",
}


def _chat_url(api_url: str) -> str:
    url = (api_url or "").rstrip("/")
    if not url:
        return ""
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return url + "/chat/completions"
    return url + "/v1/chat/completions"


def extract_path(data, path: str):
    cur = data
    for part in str(path).split("."):
        if cur is None:
            return None
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def build_request_body(model: EvalModel, prompt: str) -> dict:
    values = {
        "prompt": prompt,
        "model": model.served_model_name or model.name,
        "temperature": 0,
    }
    raw = (getattr(model, "request_template", "") or "").strip()
    if raw:
        rendered = raw
        for k, v in values.items():
            rendered = rendered.replace("{{" + k + "}}", json.dumps(v) if not isinstance(v, str) else v)
        try:
            body = json.loads(rendered)
            if isinstance(body, dict):
                return body
        except json.JSONDecodeError:
            pass
    return {
        "model": values["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }


def parse_response(model: EvalModel, data: dict) -> tuple[str, int]:
    mapping = loads(getattr(model, "response_mapping", "") or "", {}) or {}
    if not mapping:
        mapping = DEFAULT_RESPONSE_MAPPING
    output_path = mapping.get("output") or DEFAULT_RESPONSE_MAPPING["output"]
    token_path = mapping.get("tokens") or DEFAULT_RESPONSE_MAPPING["tokens"]
    text = extract_path(data, output_path)
    if text is None:
        text = (
            data.get("choices", [{}])[0].get("message", {}).get("content")
            if isinstance(data.get("choices"), list) and data.get("choices")
            else None
        ) or data.get("output") or data.get("text") or ""
    tokens = extract_path(data, token_path)
    try:
        tokens = int(tokens or 0)
    except (TypeError, ValueError):
        tokens = 0
    return str(text), tokens


def _semaphore(model: EvalModel) -> asyncio.Semaphore:
    limit = max(int(getattr(model, "parallel_limit", 0) or 4), 1)
    sem = _semaphores.get(model.id)
    if sem is None or getattr(sem, "_limit", limit) != limit:
        sem = asyncio.Semaphore(limit)
        sem._limit = limit  # type: ignore[attr-defined]
        _semaphores[model.id] = sem
    return sem


def circuit_blocked(model: EvalModel) -> str | None:
    until = getattr(model, "circuit_open_until", None)
    if until and until > datetime.utcnow():
        return f"模型熔断中，将于 {until.isoformat()} 后半开重试"
    return None


def mark_success(model: EvalModel) -> None:
    model.consecutive_fail = 0
    model.circuit_open_until = None


def mark_failure(model: EvalModel) -> None:
    model.consecutive_fail = int(getattr(model, "consecutive_fail", 0) or 0) + 1
    if model.consecutive_fail >= CIRCUIT_FAILS:
        model.circuit_open_until = datetime.utcnow() + CIRCUIT_COOLDOWN
        model.health_status = "abnormal"


async def invoke_model(model: EvalModel, prompt: str) -> dict:
    blocked = circuit_blocked(model)
    if blocked:
        raise RuntimeError(blocked)
    async with _semaphore(model):
        return await _invoke_once(model, prompt)


async def _invoke_once(model: EvalModel, prompt: str) -> dict:
    started = time.perf_counter()
    url = _chat_url(model.api_url)
    if not url:
        text = f"[mock:{model.name}] {prompt[:800]}"
        mark_success(model)
        observe_model_invoke(True)
        return {
            "output": text,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "tokens": len(prompt) + len(text),
            "mock": True,
            "finish_reason": "stop",
        }
    headers = {"Content-Type": "application/json"}
    if model.api_key:
        if model.auth_type == "api_key":
            headers["X-API-Key"] = model.api_key
        else:
            headers["Authorization"] = f"Bearer {model.api_key}"
    body = build_request_body(model, prompt)
    timeout = httpx.Timeout(model.timeout or 60)
    last_error = None
    retries = max(model.retry_count or 0, 0) + 1
    for _ in range(retries):
        try:
            async with httpx.AsyncClient(timeout=timeout, **httpx_tls_kwargs(model.channel_type)) as client:
                resp = await client.request(model.request_method or "POST", url, headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
            text, tokens = parse_response(model, data)
            mark_success(model)
            observe_model_invoke(True)
            return {
                "output": str(text),
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "tokens": tokens,
                "mock": False,
                "finish_reason": data.get("choices", [{}])[0].get("finish_reason", "stop") if isinstance(data.get("choices"), list) and data.get("choices") else "stop",
            }
        except Exception as exc:
            last_error = str(exc)
    observe_model_invoke(False)
    mark_failure(model)
    raise RuntimeError(last_error or "模型调用失败")


async def health_check(model: EvalModel) -> dict:
    started = time.perf_counter()
    if not model.api_url:
        return {"ok": True, "status": "mock", "detail": "未配置接口，评测将使用本地 Mock 输出", "latency_ms": 0}
    url = _chat_url(model.api_url)
    headers = {}
    if model.api_key:
        headers["Authorization"] = f"Bearer {model.api_key}"
    try:
        async with httpx.AsyncClient(timeout=10, **httpx_tls_kwargs(model.channel_type)) as client:
            resp = await client.get(url.rsplit("/chat/completions", 1)[0] + "/models", headers=headers)
            latency = int((time.perf_counter() - started) * 1000)
            if resp.status_code < 500:
                return {"ok": True, "status": "online", "detail": f"HTTP {resp.status_code}", "latency_ms": latency}
            return {"ok": False, "status": "abnormal", "detail": f"HTTP {resp.status_code}", "latency_ms": latency}
    except Exception as exc:
        latency = int((time.perf_counter() - started) * 1000)
        status = "timeout" if "timeout" in str(exc).lower() else "abnormal"
        return {"ok": False, "status": status, "detail": str(exc), "latency_ms": latency}
