"""底座网关：限流与熔断（错误率>50% 或连续失败 5 次，冷却 30s）。"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta
from time import monotonic

from fastapi import HTTPException

WINDOW = 60
RATE_LIMIT = 120
CIRCUIT_FAILS = 5
ERROR_RATE = 0.5
SAMPLE = 20
COOLDOWN = timedelta(seconds=30)

_hits: dict[str, deque] = defaultdict(deque)
_results: dict[str, deque] = defaultdict(deque)
_open_until: dict[str, datetime] = {}
_consecutive: dict[str, int] = defaultdict(int)


def check_gateway(resource_id: str) -> None:
    now_m = monotonic()
    q = _hits[resource_id]
    while q and now_m - q[0] > WINDOW:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(429, "调用过于频繁", headers={"Retry-After": "30"})
    until = _open_until.get(resource_id)
    if until and until > datetime.utcnow():
        retry = max(int((until - datetime.utcnow()).total_seconds()), 1)
        raise HTTPException(429, "资源熔断中（半开冷却）", headers={"Retry-After": str(retry)})
    if until and until <= datetime.utcnow():
        _open_until.pop(resource_id, None)
    q.append(now_m)


def record_gateway(resource_id: str, ok: bool) -> None:
    buf = _results[resource_id]
    buf.append(ok)
    while len(buf) > SAMPLE:
        buf.popleft()
    if ok:
        _consecutive[resource_id] = 0
        return
    _consecutive[resource_id] += 1
    fail_rate = 1 - (sum(1 for x in buf if x) / max(len(buf), 1))
    if _consecutive[resource_id] >= CIRCUIT_FAILS or (len(buf) >= 10 and fail_rate > ERROR_RATE):
        _open_until[resource_id] = datetime.utcnow() + COOLDOWN
        _consecutive[resource_id] = 0
