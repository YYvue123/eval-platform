"""Authorized resource inventory and task evidence for coordinator and specialists."""
from __future__ import annotations

from sqlalchemy import func, select

from app.models import AgentSession, BaseResource, Dataset, DatasetItem, EvalModel, EvalResult, EvalTask, TaskEvent, User
from app.services.object_policy import apply_object_scope, object_is_visible
from app.utils.jsonutil import loads


async def resource_inventory(db, actor, *, limit=60):
    from app.api.models import _acl_allows
    from app.services.agent_orchestrator import _is_planner_model

    datasets = (await db.execute(apply_object_scope(select(Dataset).where(Dataset.status != "deleted"), Dataset, actor)
                                .order_by(Dataset.id.desc()).limit(limit))).scalars().all()
    models = (await db.execute(apply_object_scope(select(EvalModel).where(EvalModel.status.notin_(["deleted", "disabled", "archived"])), EvalModel, actor)
                              .order_by(EvalModel.id.desc()).limit(limit))).scalars().all()
    resources = (await db.execute(apply_object_scope(select(BaseResource).where(BaseResource.status.in_(["online", "registered", "pending"])), BaseResource, actor)
                                 .order_by(BaseResource.id.desc()).limit(limit))).scalars().all()
    user = await db.get(User, actor.user_id)
    dataset_rows = []
    for row in datasets:
        count = await db.scalar(select(func.count(DatasetItem.id)).where(DatasetItem.version_id == row.current_version_id, DatasetItem.status != "deleted")) if row.current_version_id else 0
        dataset_rows.append({"id": row.id, "name": row.name, "scene": row.task_type, "industry": row.domain_type,
                             "tags": row.tags, "status": row.status, "quality_status": row.quality_status,
                             "version_id": row.current_version_id, "samples": count or 0,
                             "formal_ready": row.status == "published" and row.quality_status in {"passed", "ok", "good"} and bool(count)})
    model_rows = []
    for row in models:
        if _is_planner_model(row) or not await _acl_allows(db, row.id, user):
            continue
        model_rows.append({"id": row.id, "name": row.name, "status": row.status, "health_status": row.health_status,
                           "version_id": row.current_version_id, "endpoint_configured": bool(row.api_url),
                           "scenes": loads(row.scene_white_list, []), "scenario": row.applicable_scenario,
                           "callable": bool(row.api_url) and actor.has_permission("model:invoke")})
    tool_rows = []
    for row in resources:
        manifest = loads(row.manifest_json, {})
        capabilities = manifest.get("capabilities") or {}
        tool_rows.append({"resource_id": row.resource_id, "name": row.name, "type": row.resource_type,
                          "description": row.description, "version": row.version, "status": row.status,
                          "health_status": row.health_status, "input_schema": capabilities.get("input_schema") or {},
                          "output_schema": capabilities.get("output_schema") or {}})
    return {"datasets": dataset_rows, "models": model_rows, "tools": tool_rows,
            "scope": "current_actor", "limit_per_type": limit,
            "notice": "仅为当前授权资源快照；选定ID仍需校验版本、正式门禁、额度和审批。没有凭证或连接秘密。"}


async def task_evidence(db, session: AgentSession, actor, *, max_samples=20):
    if not session.task_id:
        return {"status": "no_task", "samples": []}
    task = await db.get(EvalTask, session.task_id)
    if not object_is_visible(task, actor):
        raise ValueError("task_not_visible")
    rows = (await db.execute(select(EvalResult).where(EvalResult.task_id == task.id)
                             .order_by(EvalResult.item_no).limit(max(1, min(max_samples, 50))))).scalars().all()
    events = (await db.execute(select(TaskEvent).where(TaskEvent.task_id == task.id)
                               .order_by(TaskEvent.id.desc()).limit(12))).scalars().all()
    from app.services.redaction import redact_secrets, safe_error_message

    return redact_secrets({
        "task_id": task.id, "name": task.name, "status": task.status, "progress": task.progress,
        "dataset_id": task.dataset_id, "dataset_version_id": task.dataset_version_id,
        "model_id": task.model_id, "model_version_id": task.model_version_id,
        "judge_resource_id": task.judge_resource_id, "total": task.total,
        "success_count": task.success_count, "fail_count": task.fail_count, "skip_count": task.skip_count,
        "avg_score": task.avg_score, "pass_rate": task.pass_rate, "tokens_used": task.tokens_used,
        "trial_run": bool(task.trial_run), "simulation": bool(task.simulation),
        "report_available": bool(task.report_path), "summary": task.report_summary,
        "error": safe_error_message(task.error_message or ""),
        "samples": [{"item_no": row.item_no, "input": row.input_content[:1500], "output": row.model_output[:2000],
                     "reference": row.reference_answer[:1000], "score": row.score, "passed": row.passed,
                     "execution_status": row.execution_status, "score_status": row.score_status,
                     "error_code": row.error_code, "error": safe_error_message(row.error_message or "")} for row in rows],
        "events": [{"id": event.id, "type": event.event_type, "payload": loads(event.payload_json, {})} for event in reversed(events)],
        "sample_limit": max_samples,
    })
