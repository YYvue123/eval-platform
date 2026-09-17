"""被测模型调用：OpenAI 兼容 /v1/chat/completions；无地址时使用本地 Mock。"""
from __future__ import annotations

import time

import httpx

from app.models.eval_model import EvalModel


def _chat_url(api_url: str) -> str:
    url = (api_url or "").rstrip("/")
    if not url:
        return ""
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return url + "/chat/completions"
    return url + "/v1/chat/completions"


async def invoke_model(model: EvalModel, prompt: str) -> dict:
    started = time.perf_counter()
    url = _chat_url(model.api_url)
    if not url:
        text = f"[mock:{model.name}] {prompt[:800]}"
        return {
            "output": text,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "tokens": len(prompt) + len(text),
            "mock": True,
        }
    headers = {"Content-Type": "application/json"}
    if model.api_key:
        if model.auth_type == "api_key":
            headers["X-API-Key"] = model.api_key
        else:
            headers["Authorization"] = f"Bearer {model.api_key}"
    body = {
        "model": model.served_model_name or model.name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    timeout = httpx.Timeout(model.timeout or 60)
    last_error = None
    retries = max(model.retry_count or 0, 0) + 1
    for _ in range(retries):
        try:
            async with httpx.AsyncClient(timeout=timeout, verify=model.channel_type != "plain") as client:
                resp = await client.request(model.request_method or "POST", url, headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
            text = (
                data.get("choices", [{}])[0].get("message", {}).get("content")
                or data.get("output")
                or data.get("text")
                or ""
            )
            usage = data.get("usage") or {}
            tokens = int(usage.get("total_tokens") or 0)
            return {
                "output": str(text),
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "tokens": tokens,
                "mock": False,
            }
        except Exception as exc:
            last_error = str(exc)
    raise RuntimeError(last_error or "模型调用失败")


async def health_check(model: EvalModel) -> dict:
    if not model.api_url:
        return {"ok": True, "status": "mock", "detail": "未配置接口，评测将使用本地 Mock 输出"}
    url = _chat_url(model.api_url)
    headers = {}
    if model.api_key:
        headers["Authorization"] = f"Bearer {model.api_key}"
    try:
        async with httpx.AsyncClient(timeout=10, verify=model.channel_type != "plain") as client:
            resp = await client.get(url.rsplit("/chat/completions", 1)[0] + "/models", headers=headers)
            if resp.status_code < 500:
                return {"ok": True, "status": "online", "detail": f"HTTP {resp.status_code}"}
            return {"ok": False, "status": "offline", "detail": f"HTTP {resp.status_code}"}
    except Exception as exc:
        return {"ok": False, "status": "offline", "detail": str(exc)}
