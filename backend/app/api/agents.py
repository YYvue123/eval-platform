"""多智能体编排入口：主 Agent 计划，监控/诊断只分析，关键操作需确认。"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.database import get_db
from app.models import (
    AgentMessage,
    AgentSession,
    AgentSuggestion,
    Dataset,
    EvalModel,
    EvalTask,
    User,
)
from app.services.agent_orchestrator import draft_plan
from app.services.agent_tools import archive_experience, diagnose_task, monitor_task, search_knowledge, validate_eval_config
from app.services.audit import get_client_ip, log_audit
from app.services.task_events import emit_event
from app.services.task_queue import dispatch_queue, enqueue_task
from app.utils.jsonutil import dumps, iso, loads

router = APIRouter()


class KnowledgeIn(BaseModel):
    category: str = "case"
    title: str
    content: str = ""
    tags: list[str] | None = None


class SessionIn(BaseModel):
    requirement: str


class ConfirmIn(BaseModel):
    execute: bool = True


class SuggestionAct(BaseModel):
    accepted: bool = False


def _session_out(s: AgentSession, messages=None, suggestions=None):
    return {
        "id": s.id,
        "title": s.title,
        "requirement": s.requirement,
        "status": s.status,
        "plan": loads(s.plan_json, {}),
        "task_id": s.task_id,
        "created_at": iso(s.created_at),
        "messages": messages or [],
        "suggestions": suggestions or [],
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
    _: User = Depends(require_permission("agent:list")),
):
    items = await search_knowledge(db, q, category)
    return {"items": items, "total": len(items)}


@router.post("/knowledge")
async def add_knowledge(
    body: KnowledgeIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("agent:invoke")),
):
    row = await archive_experience(db, body.title, body.content, body.category, body.tags, current.id)
    return row


@router.get("/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("agent:list")),
):
    rows = (await db.execute(select(AgentSession).order_by(AgentSession.id.desc()).limit(50))).scalars().all()
    return {"items": [_session_out(s) for s in rows], "total": len(rows)}


@router.post("/sessions")
async def create_session(
    body: SessionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("agent:invoke")),
):
    plan = await draft_plan(db, body.requirement, current)
    s = AgentSession(
        title=plan.get("name") or "编排会话",
        requirement=body.requirement,
        status="waiting_confirm" if plan.get("ready") else "planning",
        plan_json=dumps(plan),
        creator_id=current.id,
    )
    db.add(s)
    await db.flush()
    db.add(AgentMessage(session_id=s.id, role="user", content=body.requirement))
    summary = "已生成编排计划，请确认后才会创建/执行任务。" if plan.get("ready") else "配置未就绪：" + "；".join(plan.get("validation_errors") or ["缺少数据或模型"])
    db.add(AgentMessage(session_id=s.id, role="main", content=summary, tool_name="draft_plan", payload_json=dumps(plan)))
    await log_audit(db, "agent", "invoke", user_id=current.id, username=current.username, target_id=s.id, ip=get_client_ip(request))
    return _session_out(s)


@router.get("/sessions/{sid}")
async def get_session(
    sid: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("agent:view")),
):
    s = await db.get(AgentSession, sid)
    if not s:
        raise HTTPException(404, "会话不存在")
    msgs = (await db.execute(select(AgentMessage).where(AgentMessage.session_id == sid).order_by(AgentMessage.id))).scalars().all()
    sugg = (await db.execute(select(AgentSuggestion).where(AgentSuggestion.session_id == sid).order_by(AgentSuggestion.id.desc()))).scalars().all()
    return _session_out(s, [_msg_out(m) for m in msgs], [
        {"id": g.id, "action": g.action, "reason": g.reason, "status": g.status, "task_id": g.task_id} for g in sugg
    ])


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
    errors = await validate_eval_config(db, plan, current)
    if errors:
        raise HTTPException(400, "；".join(errors))
    ds = await db.get(Dataset, plan["dataset_id"])
    model = await db.get(EvalModel, plan["model_id"])
    t = EvalTask(
        name=plan.get("name") or "编排任务",
        task_type=plan.get("task_type") or "capability",
        scene=plan.get("scene") or "chat",
        industry=plan.get("industry") or "general",
        dataset_id=ds.id,
        dataset_version_id=ds.current_version_id,
        model_id=model.id,
        model_version_id=model.current_version_id,
        judge_resource_id=plan.get("judge_resource_id") or "builtin/exact_match",
        template_code=plan.get("template_code") or "",
        trial_run=bool(plan.get("trial_run")),
        creator_id=current.id,
    )
    db.add(t)
    await db.flush()
    s.task_id = t.id
    await emit_event(db, t.id, "created", {"via": "agent"})
    if body.execute:
        await enqueue_task(db, t)
        await db.commit()
        background.add_task(dispatch_queue, t.id)
        s.status = "running"
    else:
        s.status = "done"
    db.add(AgentMessage(session_id=s.id, role="main", content=f"已通过工具创建任务 #{t.id}" + (" 并提交执行" if body.execute else ""), tool_name="create_task"))
    await archive_experience(db, f"编排案例 {t.name}", s.requirement, "case", [t.scene, t.industry], current.id)
    await log_audit(db, "agent", "confirm", user_id=current.id, username=current.username, target_id=s.id, ip=get_client_ip(request))
    return _session_out(s)


@router.get("/sessions/{sid}/monitor")
async def session_monitor(
    sid: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("agent:view")),
):
    s = await db.get(AgentSession, sid)
    if not s or not s.task_id:
        raise HTTPException(404, "尚无关联任务")
    report = await monitor_task(db, s.task_id)
    db.add(AgentMessage(session_id=s.id, role="monitor", content=report.get("summary") or "", tool_name="monitor_task", payload_json=dumps(report)))
    return report


@router.post("/sessions/{sid}/diagnose")
async def session_diagnose(
    sid: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("agent:invoke")),
):
    s = await db.get(AgentSession, sid)
    if not s or not s.task_id:
        raise HTTPException(404, "尚无关联任务")
    result = await diagnose_task(db, s.task_id)
    for item in result.get("suggestions") or []:
        db.add(AgentSuggestion(session_id=s.id, task_id=s.task_id, action=item["action"], reason=item["reason"]))
    db.add(AgentMessage(session_id=s.id, role="diagnose", content="诊断完成，建议待人工确认后才能执行恢复。", tool_name="diagnose_task", payload_json=dumps(result)))
    return result


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
