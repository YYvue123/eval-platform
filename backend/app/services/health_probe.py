"""周期探测被测模型健康状态。"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from app.database import async_session
from app.models import EvalModel, ModelHealthSample
from app.services.model_client import health_check

log = logging.getLogger(__name__)
PROBE_TICK = 30


async def record_probe(model: EvalModel, result: dict, db) -> None:
    model.health_status = result["status"]
    model.last_health_at = datetime.utcnow()
    model.last_error = "" if result.get("ok") else (result.get("detail") or "")[:2000]
    if result.get("ok"):
        model.consecutive_fail = 0
        model.circuit_open_until = None
        if model.status in {"draft", "pending_check"}:
            model.status = "online"
    else:
        model.consecutive_fail = int(model.consecutive_fail or 0) + 1
        if model.status == "online":
            model.status = result.get("status") if result.get("status") in {"abnormal", "timeout"} else "abnormal"
    db.add(ModelHealthSample(
        model_id=model.id,
        ok=bool(result.get("ok")),
        status=result.get("status") or "",
        latency_ms=int(result.get("latency_ms") or 0),
        detail=(result.get("detail") or "")[:2000],
    ))


async def probe_due_models() -> int:
    now = datetime.utcnow()
    async with async_session() as db:
        rows = (await db.execute(
            select(EvalModel).where(EvalModel.status.notin_(["deleted", "archived", "disabled"]))
        )).scalars().all()
        n = 0
        for m in rows:
            interval = max(int(m.probe_interval_sec or 300), 30)
            if m.last_health_at and now - m.last_health_at < timedelta(seconds=interval):
                continue
            result = await health_check(m)
            await record_probe(m, result, db)
            n += 1
        if n:
            await db.commit()
        return n


async def health_probe_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=PROBE_TICK)
        except asyncio.TimeoutError:
            pass
        if stop.is_set():
            break
        try:
            await probe_due_models()
            from app.services.batch_store import gc_expired_snapshots
            async with async_session() as db:
                n = await gc_expired_snapshots(db)
                if n:
                    await db.commit()
        except Exception:
            log.exception("model health probe failed")
