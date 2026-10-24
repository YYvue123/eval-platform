"""Execute queued graphs one committed node at a time, including after a restart."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import or_, select, update

from app.database import async_session
from app.models import AgentRun
from app.services import agent_runtime as runtime
from app.services.agent_graph import can_resume

log = logging.getLogger(__name__)


async def dispatch_agent_once(*, run_id: int | None = None) -> bool:
    async with async_session() as db:
        now = datetime.utcnow()
        # Expired owners are fenced out before a replacement claims the run.
        await db.execute(update(AgentRun).where(
            AgentRun.status == "running",
            or_(AgentRun.lease_until.is_(None), AgentRun.lease_until < now),
        ).values(status="queued", lease_owner="", lease_until=None))
        query = select(AgentRun).where(
            AgentRun.status.in_(["queued", "waiting"]),
        )
        if run_id is not None:
            query = query.where(AgentRun.id == run_id)
        rows = (await db.execute(query.order_by(AgentRun.updated_at, AgentRun.id).limit(100))).scalars().all()
        selected = None
        for run in rows:
            try:
                if run.cancel_requested or await can_resume(db, run):
                    selected = run
                    break
                # Rotate pending approvals/tasks so they cannot starve newer runs.
                run.updated_at = now
            except (ValueError, RuntimeError):
                # Revoked actors must not strand active runs forever.
                run.status = "failed"
                run.error_code = "agent_actor_unavailable"
                run.finished_at = now
                await runtime._clear_active(db, run)
        if selected is None:
            await db.commit()
            return False
        claimed, token = await runtime.claim_run(db, selected.id)
        await db.commit()
        if claimed is None:
            return False
        run_id = claimed.id

    # A graceful reload releases its own lease after the node transaction rolls back.
    try:
        async with async_session() as db:
            run = await db.get(AgentRun, run_id)
            if run.status != "running" or run.fencing_token != token:
                return False
            await runtime.step_once(db, run, fencing_token=token)
            if run.status == "running":
                run.status = "queued"
                run.lease_owner = ""
                run.lease_until = None
            await db.commit()
    except asyncio.CancelledError:
        async with async_session() as recovery:
            await recovery.execute(update(AgentRun).where(
                AgentRun.id == run_id, AgentRun.fencing_token == token,
                AgentRun.status == "running",
            ).values(status="queued", lease_owner="", lease_until=None))
            await recovery.commit()
        raise
    return True


async def agent_worker_loop(stop: asyncio.Event):
    while not stop.is_set():
        try:
            worked = await dispatch_agent_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Agent graph worker failed")
            worked = False
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.05 if worked else 1.0)
        except asyncio.TimeoutError:
            pass
