"""Authorized resource inventory and task evidence for coordinator and specialists."""
from __future__ import annotations

from sqlalchemy import func, select

from app.models import AgentSession, BaseResource, Dataset, DatasetItem, EvalModel, EvalResult, EvalTask, TaskEvent, User
from app.services.object_policy import apply_object_scope, object_is_visible
from app.utils.jsonutil import loads


async def resource_inventory(db, actor, *, limit=60):
    from app.services.multimodal import media_of, capabilities as model_capabilities, media_summary, without_media_bytes
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
        from app.services.safety_protocol import sample_of
        safety_items = (await db.scalars(select(DatasetItem).where(DatasetItem.version_id == row.current_version_id, DatasetItem.status == "active"))).all() if row.current_version_id else []
        safety_dimensions = sorted({sample_of(item).get("dimension") for item in safety_items if sample_of(item).get("dimension")})
        modality_counts = {}
        transport_modalities, processing = set(), set()
        media_errors = []
        for item in safety_items:
            try:
                media = media_of(item)
                for m in media:
                    transport_modalities.add("image" if m["modality"] == "video" and m.get("video_mode") == "frames" else m["modality"])
                    if m["modality"] == "video" and m.get("has_audio"):
                        transport_modalities.add("audio")
                    processing.add(m["processing"])
                for mode in {m["modality"] for m in media} or {"text"}:
                    modality_counts[mode] = modality_counts.get(mode, 0) + 1
            except ValueError as exc:
                media_errors.append(str(exc))
        count = await db.scalar(select(func.count(DatasetItem.id)).where(DatasetItem.version_id == row.current_version_id, DatasetItem.status != "deleted")) if row.current_version_id else 0
        dataset_rows.append({"id": row.id, "name": row.name, "scene": row.task_type, "industry": row.domain_type,
                             "tags": row.tags, "status": row.status, "quality_status": row.quality_status,
                             "version_id": row.current_version_id, "input_modalities": modality_counts, "transport_modalities": sorted(transport_modalities or {"text"}), "processing": sorted(processing), "media_errors": media_errors, "samples": count or 0, "safety_dimensions": safety_dimensions,
                             "formal_ready": row.status == "published" and row.quality_status in {"passed", "ok", "good"} and bool(count)})
    model_rows = []
    for row in models:
        if _is_planner_model(row) or not await _acl_allows(db, row.id, user):
            continue
        model_rows.append({"id": row.id, "name": row.name, "status": row.status, "health_status": row.health_status,
                           "version_id": row.current_version_id, "endpoint_configured": bool(row.api_url),
                           "input_modalities": sorted(model_capabilities(row)[0]), "output_modalities": sorted(model_capabilities(row)[1]),
                           "scenes": loads(row.scene_white_list, []), "scenario": row.applicable_scenario,
                           "callable": bool(row.api_url) and actor.has_permission("model:invoke")})
    tool_rows = []
    for row in resources:
        manifest = loads(row.manifest_json, {})
        capabilities = manifest.get("capabilities") or {}
        tool_rows.append({"resource_id": row.resource_id, "name": row.name, "type": row.resource_type,
                          "description": row.description, "version": row.version, "status": row.status,
                          "health_status": row.health_status, "input_schema": capabilities.get("input_schema") or {},
                          "output_schema": capabilities.get("output_schema") or {},
                          "input_modalities": capabilities.get("input_modalities", []), "media_scope": capabilities.get("media_scope", "undeclared")})
    from app.services.safety_protocol import SafetyConfig, DIMENSIONS
    return {"datasets": dataset_rows, "models": model_rows, "tools": tool_rows,
            "safety": {"dimensions": DIMENSIONS, "config_schema": SafetyConfig.model_json_schema(),
                       "can_create": actor.is_admin or actor.has_permission("safety:create"),
                       "human_review_required": True, "watermark_scope": "文本显式标识与输出元数据"},
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

    safety = None
    if task.judge_resource_id == "builtin/safety_protocol" and (actor.is_admin or actor.has_permission("safety:view")):
        from app.services.safety_assessments import assessment_payload
        import hashlib
        from app.utils.jsonutil import dumps
        safety = await assessment_payload(db, task)
        safety["review_evidence_hash"] = hashlib.sha256(dumps([
            {"id": row["id"], "evidence_hash": row["evidence_hash"], "review": row["review"]}
            for row in safety["results"]
        ]).encode()).hexdigest()
        from app.services.multimodal import without_media_bytes
        safety["results"] = without_media_bytes(safety["results"][:max(1, min(max_samples, 50))])

    from app.services.multimodal import media_summary
    return redact_secrets({
        "task_id": task.id, "name": task.name, "status": task.status, "progress": task.progress,
        "safety_assessment": safety,
        "dataset_id": task.dataset_id, "dataset_version_id": task.dataset_version_id,
        "model_id": task.model_id, "model_version_id": task.model_version_id,
        "judge_resource_id": task.judge_resource_id, "total": task.total,
        "success_count": task.success_count, "fail_count": task.fail_count, "skip_count": task.skip_count,
        "avg_score": task.avg_score, "pass_rate": task.pass_rate, "tokens_used": task.tokens_used,
        "trial_run": bool(task.trial_run), "simulation": bool(task.simulation),
        "report_available": bool(task.report_path), "summary": task.report_summary,
        "error": safe_error_message(task.error_message or ""),
        "samples": [{"result_id": row.id, "media": media_summary(loads(row.metrics_json, {}).get("media", [])),
                     "measurement_scope": loads(row.metrics_json, {}).get("measurement_scope", "文本；旧记录未声明媒体"),
                     "output_audio": {k:v for k,v in (loads(row.metrics_json, {}).get("output_audio") or {}).items() if k != "data_url"}, "item_no": row.item_no, "input": row.input_content[:1500], "output": row.model_output[:2000],
                     "reference": row.reference_answer[:1000], "score": row.score, "passed": row.passed,
                     "execution_status": row.execution_status, "score_status": row.score_status,
                     "error_code": row.error_code, "error": safe_error_message(row.error_message or "")} for row in rows],
        "events": [{"id": event.id, "type": event.event_type, "payload": loads(event.payload_json, {})} for event in reversed(events)],
        "sample_limit": max_samples,
    })
