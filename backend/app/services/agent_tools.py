"""Agent 工具：只封装已有任务/资源/报告接口，不改调度内部结构。"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BaseResource,
    Dataset,
    EvalModel,
    EvalTask,
    EvalWorkspace,
    KnowledgeEntry,
    TaskEvent,
    TaskTemplate,
)
from app.utils.jsonutil import dumps, loads


async def search_knowledge(db: AsyncSession, query: str, category: str = "") -> list[dict]:
    q = select(KnowledgeEntry)
    if category:
        q = q.where(KnowledgeEntry.category == category)
    if query:
        q = q.where(or_(KnowledgeEntry.title.contains(query), KnowledgeEntry.content.contains(query), KnowledgeEntry.tags_json.contains(query)))
    rows = (await db.execute(q.order_by(KnowledgeEntry.id.desc()).limit(20))).scalars().all()
    if not rows and not query:
        rows = (await db.execute(select(KnowledgeEntry).order_by(KnowledgeEntry.id.desc()).limit(20))).scalars().all()
    return [_k_out(r) for r in rows]


def _k_out(r: KnowledgeEntry) -> dict:
    return {
        "id": r.id,
        "category": r.category,
        "title": r.title,
        "content": r.content,
        "tags": loads(r.tags_json, []),
        "ref_type": r.ref_type,
        "ref_id": r.ref_id,
    }


async def retrieve_templates(db: AsyncSession, scene: str = "", industry: str = "") -> list[dict]:
    q = select(TaskTemplate).where(TaskTemplate.status == "active")
    if industry and industry != "general":
        q = q.where(TaskTemplate.industry == industry)
    elif scene:
        q = q.where(TaskTemplate.scene == scene)
    rows = (await db.execute(q.limit(8))).scalars().all()
    return [{"code": t.code, "name": t.name, "scene": t.scene, "industry": t.industry, "judge_resource_id": t.judge_resource_id} for t in rows]


async def validate_eval_config(db: AsyncSession, plan: dict, user) -> list[str]:
    errors = []
    ds_id = plan.get("dataset_id")
    model_id = plan.get("model_id")
    ds = await db.get(Dataset, ds_id) if ds_id else None
    if not ds or ds.status == "deleted":
        errors.append("数据集不可用")
    elif not plan.get("trial_run") and ds.quality_status in {"failed", "check_failed"}:
        errors.append("质量不合格数据不能进入正式评测")
    model = await db.get(EvalModel, model_id) if model_id else None
    if not model or model.status in {"deleted", "disabled", "archived"}:
        errors.append("被测模型不可用")
    judge = plan.get("judge_resource_id") or "builtin/exact_match"
    res = await db.scalar(select(BaseResource).where(BaseResource.resource_id == judge))
    if not res or res.health_status in {"offline", "circuit_open"}:
        if judge.startswith("builtin/"):
            pass
        else:
            errors.append("打分工具不可用")
    if plan.get("workspace_id"):
        ws = await db.get(EvalWorkspace, plan["workspace_id"])
        if ws and ws.quota_tokens and ws.used_tokens >= ws.quota_tokens:
            errors.append("工作空间配额已用尽")
    return errors


async def monitor_task(db: AsyncSession, task_id: int) -> dict:
    t = await db.get(EvalTask, task_id)
    if not t:
        return {"ok": False, "error": "任务不存在"}
    events = (await db.execute(select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.id.desc()).limit(8))).scalars().all()
    risk = "low"
    if t.status == "failed" or t.fail_count > t.success_count:
        risk = "high"
    elif t.status == "queued":
        risk = "medium"
    return {
        "ok": True,
        "task_id": t.id,
        "status": t.status,
        "progress": t.progress,
        "success_count": t.success_count,
        "fail_count": t.fail_count,
        "risk": risk,
        "summary": t.report_summary or f"进度 {t.progress}%",
        "recent_events": [e.event_type for e in events],
    }


async def diagnose_task(db: AsyncSession, task_id: int) -> dict:
    t = await db.get(EvalTask, task_id)
    if not t:
        return {"ok": False, "suggestions": []}
    suggestions = []
    if t.status == "failed":
        suggestions.append({"action": "retry", "reason": t.error_message or "任务失败，建议人工确认后重跑"})
        suggestions.append({"action": "reconfigure", "reason": "检查数据集质量、模型健康与裁判工具后再改配"})
    elif t.status == "queued":
        suggestions.append({"action": "wait", "reason": "可能在等待依赖或执行窗口，勿直接改队列"})
    elif t.status == "success":
        suggestions.append({"action": "archive", "reason": "可沉淀为知识库案例"})
    else:
        suggestions.append({"action": "monitor", "reason": "继续观察进度，诊断 Agent 不直接恢复"})
    return {"ok": True, "task_id": t.id, "status": t.status, "suggestions": suggestions}


async def archive_experience(db: AsyncSession, title: str, content: str, category: str = "case", tags: list | None = None, user_id: int | None = None) -> dict:
    row = KnowledgeEntry(
        category=category,
        title=title[:200],
        content=content,
        tags_json=dumps(tags or []),
        creator_id=user_id,
    )
    db.add(row)
    await db.flush()
    return _k_out(row)
