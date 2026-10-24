"""Separate, auditable report revisions; original evaluation facts remain immutable."""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select

from app.config import settings
from app.models import AgentReportRevision, EvalTask
from app.services.object_policy import object_is_visible
from app.utils.jsonutil import dumps


def source_hash(task):
    path = Path(task.report_path or "").resolve()
    root = Path(settings.UPLOAD_DIR).resolve()
    if not task.report_path or not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(409, "原始报告尚未就绪，不能生成或发布优化版本")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def facts_hash(evidence):
    return hashlib.sha256(dumps(evidence).encode()).hexdigest()


async def create_revision(db, session, run, output, actor):
    from app.services.agent_context import task_evidence

    existing = await db.scalar(select(AgentReportRevision).where(AgentReportRevision.delegation_id == output["delegation_id"]))
    if existing:
        return existing
    task = await db.get(EvalTask, session.task_id)
    if not object_is_visible(task, actor) or task.status not in {"success", "failed", "partial_failed"}:
        raise HTTPException(409, "任务尚未结束或无权访问")
    evidence = await task_evidence(db, session, actor, max_samples=20)
    content = (output.get("result") or {}).get("summary") or ""
    if not content.strip():
        raise HTTPException(409, "没有可审核的优化报告内容")
    authoritative = (
        f"# {task.name} 优化报告\n\n状态：待人工审核。模型分析不改变下列原始评测事实。\n\n"
        f"任务 #{task.id}；数据集 #{task.dataset_id}；模型 #{task.model_id}；裁判 {task.judge_resource_id}。\n\n"
        f"| 原始指标 | 实际记录 |\n| --- | --- |\n| 状态 | {task.status} |\n| 样本 | {task.total} |\n"
        f"| 通过 | {task.success_count} |\n| 失败 | {task.fail_count} |\n| 跳过 | {task.skip_count} |\n"
        f"| 平均分 | {task.avg_score} |\n| 通过率 | {task.pass_rate} |\n| 试跑 | {bool(task.trial_run)} |\n"
        f"| 模拟 | {bool(task.simulation)} |\n\n## Agent分析与建议\n\n{content}\n\n"
        "优化仅涉及报告表达和分析建议。业务指标是否达标仍须按验收标准人工判断。"
    )
    row = AgentReportRevision(session_id=session.id, run_id=run.id, task_id=task.id,
                              delegation_id=output["delegation_id"], tenant_id=actor.tenant_id,
                              creator_id=actor.user_id, status="draft", content=authoritative,
                              source_hash=source_hash(task), evidence_hash=facts_hash(evidence))
    db.add(row)
    await db.flush()
    return row


def revision_out(row, *, include_content=False):
    result = {"id": row.id, "session_id": row.session_id, "run_id": row.run_id, "task_id": row.task_id,
              "delegation_id": row.delegation_id, "status": row.status, "source_hash": row.source_hash,
              "created_at": row.created_at.isoformat() + "Z", "published_at": row.published_at.isoformat() + "Z" if row.published_at else None}
    if include_content:
        result["content"] = row.content
    return result


async def publish_revision(db, row, session, actor):
    from app.services.agent_context import task_evidence

    task = await db.get(EvalTask, row.task_id)
    if row.status != "draft":
        raise HTTPException(409, "仅草稿可发布")
    if source_hash(task) != row.source_hash or facts_hash(await task_evidence(db, session, actor, max_samples=20)) != row.evidence_hash:
        raise HTTPException(409, "原报告或评测证据已变化，请重新生成优化稿")
    for previous in (await db.execute(select(AgentReportRevision).where(
        AgentReportRevision.task_id == row.task_id, AgentReportRevision.status == "published",
    ))).scalars().all():
        previous.status = "superseded"
    row.status = "published"
    row.published_at = datetime.utcnow()
    await db.flush()
