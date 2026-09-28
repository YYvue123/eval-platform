"""多智能体编排入口：主 Agent 计划，监控/诊断只分析，关键操作需确认。"""
import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission, require_actor
from app.database import get_db
from app.models import (
    AgentApproval,
    AgentMessage,
    AgentRun,
    AgentSession,
    AgentSuggestion,
    Dataset,
    EvalModel,
    EvalTask,
    KnowledgeEntry,
    User,
)
from app.services.actor_context import ActorContext, effective_tenant_id
from app.services.agent_orchestrator import draft_plan
from app.services import agent_runtime as runtime
from app.services import approval_service
from app.services import collaboration
from app.services import knowledge_trust
from app.services.agent_tools import archive_experience, diagnose_task, monitor_task, search_knowledge, validate_eval_config
from app.services.audit import get_client_ip, log_audit
from app.services.goal_spec import canonical_plan_hash
from app.services.object_policy import apply_object_scope, get_visible_or_404
from app.services.task_events import emit_event
from app.services.task_from_plan import create_task_from_plan
from app.services.task_queue import dispatch_queue, enqueue_task
from app.utils.jsonutil import dumps, iso, loads

router = APIRouter()


class KnowledgeIn(BaseModel):
    category: str = "case"
    title: str
    content: str = ""
    tags: list[str] | None = None


class KnowledgeReviewIn(BaseModel):
    approve: bool = True
    reason: str = ""
    ttl_days: int = 365


class CollaborateIn(BaseModel):
    roles: list[str] | None = None
    budget_total: int = 100


class SessionIn(BaseModel):
    requirement: str
    objective: str = ""
    token_budget: int = 0


class ClarifyIn(BaseModel):
    objective: str = ""
    token_budget: int | None = None
    dataset_id: int | None = None
    model_id: int | None = None
    scene: str = ""
    industry: str = ""
    trial_run: bool | None = None


class ApproveIn(BaseModel):
    ttl_minutes: int = 30


class ConfirmIn(BaseModel):
    execute: bool = True
    approval_id: int | None = None
    client_invocation_id: str = ""


class SuggestionAct(BaseModel):
    accepted: bool = False


class RunIn(BaseModel):
    message: str = ""
    provider: str = "mock"
    max_rounds: int = 8
    token_budget: int = 0
    client_message_id: str = ""
    sync: bool = True


def _session_out(s: AgentSession, messages=None, suggestions=None, approvals=None):
    return {
        "id": s.id,
        "title": s.title,
        "requirement": s.requirement,
        "status": s.status,
        "plan": loads(s.plan_json, {}),
        "task_id": s.task_id,
        "active_run_id": getattr(s, "active_run_id", None),
        "created_at": iso(s.created_at),
        "messages": messages or [],
        "suggestions": suggestions or [],
        "approvals": approvals or [],
    }


def _msg_out(m: AgentMessage):
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "tool_name": m.tool_name,
        "payload": loads(m.payload_json, {}),
        "created_at": iso(m.created_at),
    }


@router.get("/knowledge")
async def list_knowledge(
    category: str = Query(""),
    q: str = Query(""),
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("agent:list")),
):
    items = await search_knowledge(db, q, category, tenant_id=actor.tenant_id)
    # 再按 visibility/scope 过滤
    from app.models import KnowledgeEntry
    visible = []
    for it in items:
        row = await db.get(KnowledgeEntry, it["id"])
        from app.services.object_policy import object_is_visible
        if object_is_visible(row, actor):
            visible.append(it)
    return {"items": visible, "total": len(visible)}


@router.post("/knowledge")
async def add_knowledge(
    body: KnowledgeIn,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("agent:invoke")),
):
    """写入知识候选；审核通过前不进入可信检索。"""
    c = await knowledge_trust.submit_candidate(
        db,
        title=body.title,
        content=body.content,
        category=body.category,
        tenant_id=actor.tenant_id,
        tags=body.tags,
    )
    return knowledge_trust.candidate_out(c)


@router.get("/knowledge/candidates")
async def list_knowledge_candidates(
    status: str = Query("pending"),
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("agent:list")),
):
    rows = await knowledge_trust.list_candidates(db, actor.tenant_id, status=status)
    return {"items": [knowledge_trust.candidate_out(c) for c in rows], "total": len(rows)}


@router.post("/knowledge/candidates/{cid}/review")
async def review_knowledge_candidate(
    cid: int,
    body: KnowledgeReviewIn,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("agent:confirm")),
):
    c = await knowledge_trust.review_candidate(
        db,
        cid,
        approve=body.approve,
        reviewer_id=actor.user_id,
        reason=body.reason,
        ttl_days=body.ttl_days,
        actor_tenant_id=actor.tenant_id,
    )
    return knowledge_trust.candidate_out(c)


@router.get("/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("agent:list")),
):
    q = apply_object_scope(select(AgentSession), AgentSession, actor)
    rows = (await db.execute(q.order_by(AgentSession.id.desc()).limit(50))).scalars().all()
    return {"items": [_session_out(s) for s in rows], "total": len(rows)}


@router.post("/sessions")
async def create_session(
    body: SessionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("agent:invoke")),
):
    current = await db.get(User, actor.user_id)
    plan = await draft_plan(
        db,
        body.requirement,
        current,
        token_budget=body.token_budget,
        objective=body.objective or body.requirement,
    )
    s = AgentSession(
        title=plan.get("name") or "编排会话",
        requirement=body.requirement,
        status="waiting_confirm" if plan.get("ready") else "planning",
        plan_json=dumps(plan),
        creator_id=actor.user_id,
        tenant_id=effective_tenant_id(actor, None),
        visibility="private",
    )
    db.add(s)
    await db.flush()
    db.add(AgentMessage(session_id=s.id, role="user", content=body.requirement))
    if plan.get("ready"):
        summary = "已生成编排计划，请审批确认后才会创建/执行任务。"
    else:
        bits = plan.get("clarifications") or []
        qs = "；".join(c.get("question") or "" for c in bits) or "；".join(plan.get("validation_errors") or ["配置未就绪"])
        summary = "需要澄清：" + qs
    db.add(AgentMessage(session_id=s.id, role="main", content=summary, tool_name="draft_plan", payload_json=dumps(plan)))
    await log_audit(db, "agent", "invoke", user_id=actor.user_id, username=actor.username, target_id=s.id, ip=get_client_ip(request))
    return _session_out(s)


@router.get("/sessions/{sid}")
async def get_session(
    sid: int,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("agent:view")),
):
    s = await get_visible_or_404(db, AgentSession, sid, actor, not_found="会话不存在或无权访问")
    msgs = (await db.execute(select(AgentMessage).where(AgentMessage.session_id == sid).order_by(AgentMessage.id))).scalars().all()
    sugg = (await db.execute(select(AgentSuggestion).where(AgentSuggestion.session_id == sid).order_by(AgentSuggestion.id.desc()))).scalars().all()
    apprs = (await db.execute(select(AgentApproval).where(AgentApproval.session_id == sid).order_by(AgentApproval.id.desc()).limit(10))).scalars().all()
    return _session_out(
        s,
        [_msg_out(m) for m in msgs],
        [{"id": g.id, "action": g.action, "reason": g.reason, "status": g.status, "task_id": g.task_id} for g in sugg],
        [approval_service.approval_out(a) for a in apprs],
    )


@router.post("/sessions/{sid}/clarify")
async def clarify_session(
    sid: int,
    body: ClarifyIn,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("agent:invoke")),
):
    s = await get_visible_or_404(db, AgentSession, sid, actor, not_found="会话不存在或无权访问")
    current = await db.get(User, actor.user_id)
    overrides = {}
    if body.dataset_id is not None:
        overrides["dataset_id"] = body.dataset_id
    if body.model_id is not None:
        overrides["model_id"] = body.model_id
    if body.scene:
        overrides["scene"] = body.scene
    if body.industry:
        overrides["industry"] = body.industry
    if body.trial_run is not None:
        overrides["trial_run"] = body.trial_run
    if body.token_budget is not None:
        overrides["token_budget"] = body.token_budget
    if body.objective:
        overrides["objective"] = body.objective
    plan = await draft_plan(db, s.requirement, current, objective=body.objective or s.requirement, overrides=overrides)
    if body.token_budget is not None:
        plan["token_budget"] = body.token_budget
        plan["goal_spec"] = {**(plan.get("goal_spec") or {}), "token_budget": body.token_budget, "objective": body.objective or (plan.get("goal_spec") or {}).get("objective")}
        plan["canonical_hash"] = canonical_plan_hash(plan)
    await approval_service.invalidate_if_plan_changed(db, s.id, plan)
    s.plan_json = dumps(plan)
    s.status = "waiting_confirm" if plan.get("ready") else "planning"
    s.updated_at = __import__("datetime").datetime.utcnow()
    db.add(AgentMessage(session_id=s.id, role="user", content="澄清更新", tool_name="clarify", payload_json=dumps(overrides)))
    db.add(AgentMessage(session_id=s.id, role="main", content="计划已根据澄清更新", tool_name="draft_plan", payload_json=dumps({"ready": plan.get("ready"), "hash": plan.get("canonical_hash")})))
    return _session_out(s)


@router.post("/sessions/{sid}/approve")
async def approve_session(
    sid: int,
    body: ApproveIn,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("agent:confirm")),
):
    s = await get_visible_or_404(db, AgentSession, sid, actor, not_found="会话不存在或无权访问")
    plan = loads(s.plan_json, {})
    if not plan.get("ready"):
        raise HTTPException(400, "计划未就绪，请先澄清")
    current = await db.get(User, actor.user_id)
    errors = await validate_eval_config(db, plan, current)
    if errors:
        raise HTTPException(400, "；".join(errors))
    appr = await approval_service.issue_approval(db, s, plan, approver_id=actor.user_id, ttl_minutes=body.ttl_minutes)
    s.status = "approved"
    db.add(AgentMessage(session_id=s.id, role="main", content=f"已签发审批 #{appr.id}，hash={appr.plan_hash[:12]}…", tool_name="approve"))
    return {"approval": approval_service.approval_out(appr), "session": _session_out(s)}


@router.post("/sessions/{sid}/confirm")
async def confirm_session(
    sid: int,
    body: ConfirmIn,
    background: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("agent:confirm")),
):
    s = await db.get(AgentSession, sid)
    if not s:
        raise HTTPException(404, "会话不存在")
    plan = loads(s.plan_json, {})
    plan["canonical_hash"] = plan.get("canonical_hash") or canonical_plan_hash(plan)

    # 无 approval_id：兼容签发并消费（或复用未过期审批）
    if body.approval_id:
        appr = await approval_service.get_valid_approval(db, body.approval_id, session_id=s.id, plan=plan)
    else:
        if not plan.get("ready"):
            raise HTTPException(400, "计划未就绪")
        errors = await validate_eval_config(db, plan, current)
        if errors:
            raise HTTPException(400, "；".join(errors))
        appr = await approval_service.issue_approval(db, s, plan, approver_id=current.id)

    invocation = (body.client_invocation_id or "").strip() or f"confirm-{s.id}-{appr.id}"

    # 已消费：幂等返回同一任务
    if appr.status == "consumed" and appr.consumed_task_id:
        if appr.consumed_invocation_id and appr.consumed_invocation_id != invocation:
            raise HTTPException(409, "审批已消费，禁止重复创建任务")
        t = await db.get(EvalTask, appr.consumed_task_id)
        return {**_session_out(s), "task_id": appr.consumed_task_id, "approval": approval_service.approval_out(appr), "idempotent": True, "task": {"id": t.id} if t else None}

    if s.task_id:
        # 会话已有任务且审批未标记：绑定幂等
        await approval_service.consume_approval(db, appr, task_id=s.task_id, invocation_id=invocation)
        return {**_session_out(s), "task_id": s.task_id, "approval": approval_service.approval_out(appr), "idempotent": True}

    t = await create_task_from_plan(db, plan, current, tenant_id=s.tenant_id)
    await approval_service.consume_approval(db, appr, task_id=t.id, invocation_id=invocation)
    s.task_id = t.id
    if body.execute:
        await enqueue_task(db, t)
        await db.commit()
        background.add_task(dispatch_queue, t.id)
        s.status = "running"
    else:
        s.status = "done"
    db.add(AgentMessage(session_id=s.id, role="main", content=f"已通过审批创建任务 #{t.id}" + (" 并提交执行" if body.execute else ""), tool_name="create_task"))
    await archive_experience(db, f"编排案例 {t.name}", s.requirement, "case", [t.scene, t.industry], current.id)
    await log_audit(db, "agent", "confirm", user_id=current.id, username=current.username, target_id=s.id, ip=get_client_ip(request))
    return {**_session_out(s), "task_id": t.id, "approval": approval_service.approval_out(appr), "idempotent": False}


@router.get("/sessions/{sid}/monitor")
async def session_monitor(
    sid: int,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("agent:view")),
):
    s = await get_visible_or_404(db, AgentSession, sid, actor, not_found="会话不存在或无权访问")
    if not s.task_id:
        raise HTTPException(404, "尚无关联任务")
    out = await collaboration.run_collaborators(db, s, force_roles=["monitor"])
    item = (out.get("items") or [{}])[0]
    return item.get("result") or item


@router.post("/sessions/{sid}/diagnose")
async def session_diagnose(
    sid: int,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("agent:invoke")),
):
    s = await get_visible_or_404(db, AgentSession, sid, actor, not_found="会话不存在或无权访问")
    if not s.task_id:
        raise HTTPException(404, "尚无关联任务")
    out = await collaboration.run_collaborators(db, s, force_roles=["diagnose"])
    item = (out.get("items") or [{}])[0]
    return item.get("result") or item


@router.post("/sessions/{sid}/collaborate")
async def session_collaborate(
    sid: int,
    body: CollaborateIn,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("agent:invoke")),
):
    s = await get_visible_or_404(db, AgentSession, sid, actor, not_found="会话不存在或无权访问")
    return await collaboration.run_collaborators(
        db, s, force_roles=body.roles, budget_total=body.budget_total
    )


@router.get("/sessions/{sid}/delegations")
async def session_delegations(
    sid: int,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("agent:view")),
):
    s = await get_visible_or_404(db, AgentSession, sid, actor, not_found="会话不存在或无权访问")
    rows = await collaboration.list_delegations(db, s.id)
    evidence = []
    for d in rows:
        for e in loads(d.evidence_json, []) or []:
            evidence.append({"delegation_id": d.id, "role": d.role, **e})
    return {
        "items": [collaboration.delegation_out(d) for d in rows],
        "evidence": evidence,
        "total": len(rows),
    }


@router.post("/suggestions/{gid}/act")
async def act_suggestion(
    gid: int,
    body: SuggestionAct,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("agent:confirm")),
):
    g = await db.get(AgentSuggestion, gid)
    if not g:
        raise HTTPException(404, "建议不存在")
    g.status = "accepted" if body.accepted else "rejected"
    if body.accepted and g.action == "retry" and g.task_id:
        t = await db.get(EvalTask, g.task_id)
        if t and t.status != "running":
            await enqueue_task(db, t)
            await db.commit()
            background.add_task(dispatch_queue, t.id)
    return {"id": g.id, "status": g.status}


@router.post("/sessions/{sid}/runs")
async def start_run(
    sid: int,
    body: RunIn,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("agent:invoke")),
):
    s = await get_visible_or_404(db, AgentSession, sid, actor, not_found="会话不存在或无权访问")
    msg = (body.message or s.requirement or "").strip()
    if not msg:
        raise HTTPException(400, "message 不能为空")
    if body.sync:
        run = await runtime.start_and_run(
            db,
            s,
            message=msg,
            provider=body.provider,
            max_rounds=body.max_rounds,
            token_budget=body.token_budget,
        )
    else:
        run = await runtime.create_run(
            db,
            s,
            message=msg,
            provider=body.provider,
            max_rounds=body.max_rounds,
            token_budget=body.token_budget,
            client_message_id=body.client_message_id,
        )
    return runtime.run_out(run)


@router.get("/runs/{rid}")
async def get_run(
    rid: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("agent:view")),
):
    run = await db.get(AgentRun, rid)
    if not run:
        raise HTTPException(404, "run 不存在")
    return runtime.run_out(run)


@router.get("/runs/{rid}/events")
async def get_run_events(
    rid: int,
    after_seq: int = Query(0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("agent:view")),
):
    run = await db.get(AgentRun, rid)
    if not run:
        raise HTTPException(404, "run 不存在")
    evs = await runtime.list_events(db, rid, after_seq=after_seq)
    return {"items": [runtime.event_out(e) for e in evs], "event_seq": run.event_seq}


@router.get("/runs/{rid}/events/stream")
async def stream_run_events(
    rid: int,
    after_seq: int = Query(0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("agent:view")),
):
    run = await db.get(AgentRun, rid)
    if not run:
        raise HTTPException(404, "run 不存在")

    async def gen():
        cursor = after_seq
        idle = 0
        while idle < 40:
            evs = await runtime.list_events(db, rid, after_seq=cursor)
            if evs:
                idle = 0
                for e in evs:
                    cursor = e.seq
                    yield f"data: {json.dumps(runtime.event_out(e), ensure_ascii=False)}\n\n"
            else:
                idle += 1
                r = await db.get(AgentRun, rid)
                if r and r.status in {"success", "failed", "cancelled", "paused_budget"}:
                    yield f"data: {json.dumps({'type': 'run.eof', 'status': r.status, 'seq': cursor})}\n\n"
                    break
                yield ": ping\n\n"
                await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/runs/{rid}/cancel")
async def cancel_run(
    rid: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("agent:invoke")),
):
    run = await db.get(AgentRun, rid)
    if not run:
        raise HTTPException(404, "run 不存在")
    run = await runtime.request_cancel(db, run)
    return runtime.run_out(run)


@router.post("/runs/{rid}/resume")
async def resume_run(
    rid: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("agent:invoke")),
):
    run = await db.get(AgentRun, rid)
    if not run:
        raise HTTPException(404, "run 不存在")
    run = await runtime.resume_run(db, run)
    return runtime.run_out(run)
