"""审批签发、有效期校验与消费幂等（防重放）。"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentApproval, AgentSession
from app.services.goal_spec import canonical_plan_hash, plans_semantically_equal
from app.utils.jsonutil import dumps, loads

DEFAULT_TTL_MINUTES = 30


def approval_out(a: AgentApproval) -> dict:
    return {
        "id": a.id,
        "session_id": a.session_id,
        "run_id": a.run_id,
        "plan_hash": a.plan_hash,
        "action_hash": a.action_hash,
        "status": a.status,
        "expires_at": a.expires_at.isoformat() + "Z" if a.expires_at else None,
        "approver_id": a.approver_id,
        "consumed_task_id": a.consumed_task_id,
        "consumed_invocation_id": a.consumed_invocation_id or "",
        "scope": loads(a.scope_json, {}),
        "created_at": a.created_at.isoformat() + "Z" if a.created_at else None,
    }


async def issue_approval(
    db: AsyncSession,
    session: AgentSession,
    plan: dict,
    *,
    approver_id: int | None,
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
    run_id: int | None = None,
    action: str = "create_task",
) -> AgentApproval:
    plan_hash = canonical_plan_hash(plan)
    action_hash = canonical_plan_hash({**plan, "_action": action})
    # 同一 session+plan_hash 未消费的 approved 可复用
    existing = await db.scalar(
        select(AgentApproval).where(
            AgentApproval.session_id == session.id,
            AgentApproval.plan_hash == plan_hash,
            AgentApproval.status == "approved",
        )
    )
    if existing and existing.expires_at and existing.expires_at > datetime.utcnow():
        return existing

    row = AgentApproval(
        session_id=session.id,
        run_id=run_id,
        tenant_id=session.tenant_id,
        plan_hash=plan_hash,
        action_hash=action_hash,
        scope_json=dumps({"actions": [action], "max_uses": 1}),
        status="approved",
        approver_id=approver_id,
        expires_at=datetime.utcnow() + timedelta(minutes=max(1, ttl_minutes)),
        plan_snapshot_json=dumps(plan),
    )
    db.add(row)
    await db.flush()
    return row


async def get_valid_approval(
    db: AsyncSession,
    approval_id: int,
    *,
    session_id: int,
    plan: dict,
) -> AgentApproval:
    row = await db.get(AgentApproval, approval_id)
    if not row or row.session_id != session_id:
        raise HTTPException(404, "审批不存在")
    if row.status == "consumed" and row.consumed_task_id:
        return row
    snap = loads(row.plan_snapshot_json, {})
    if row.status == "invalidated" or not plans_semantically_equal(snap, plan) or row.plan_hash != canonical_plan_hash(plan):
        if row.status == "approved":
            row.status = "invalidated"
            await db.flush()
        raise HTTPException(409, "计划已变更，旧审批失效，请重新审批")
    if row.status != "approved":
        raise HTTPException(400, f"审批状态不可用: {row.status}")
    if row.expires_at and row.expires_at <= datetime.utcnow():
        row.status = "expired"
        await db.flush()
        raise HTTPException(400, "审批已过期，请重新签发")
    return row


async def consume_approval(
    db: AsyncSession,
    approval: AgentApproval,
    *,
    task_id: int,
    invocation_id: str,
) -> AgentApproval:
    """幂等消费：已消费且同 invocation → 原样；异 invocation → 409。"""
    if approval.status == "consumed":
        if approval.consumed_invocation_id == invocation_id:
            return approval
        if approval.consumed_task_id:
            raise HTTPException(409, "审批已消费，禁止重复创建任务")
    if approval.status not in {"approved", "consumed"}:
        raise HTTPException(400, "审批不可消费")
    if approval.expires_at and approval.expires_at <= datetime.utcnow() and approval.status != "consumed":
        approval.status = "expired"
        await db.flush()
        raise HTTPException(400, "审批已过期")

    approval.status = "consumed"
    approval.consumed_task_id = task_id
    approval.consumed_invocation_id = invocation_id
    approval.consumed_at = datetime.utcnow()
    approval.row_version = int(approval.row_version or 0) + 1
    await db.flush()
    return approval


async def invalidate_if_plan_changed(db: AsyncSession, session_id: int, new_plan: dict) -> int:
    """计划变更时作废未消费审批。"""
    new_hash = canonical_plan_hash(new_plan)
    rows = (
        await db.execute(
            select(AgentApproval).where(
                AgentApproval.session_id == session_id,
                AgentApproval.status == "approved",
            )
        )
    ).scalars().all()
    n = 0
    for row in rows:
        if row.plan_hash != new_hash:
            row.status = "invalidated"
            n += 1
    if n:
        await db.flush()
    return n
