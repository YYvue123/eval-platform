from datetime import datetime

from app.utils.jsonutil import iso, loads


def dataset_brief(d, creator_name=""):
    return {
        "id": d.id,
        "name": d.name,
        "dataset_type": d.dataset_type,
        "task_type": d.task_type,
        "domain_type": d.domain_type,
        "data_source": d.data_source,
        "data_format": d.data_format,
        "data_count": d.data_count,
        "description": d.description,
        "current_version": d.current_version,
        "current_version_id": d.current_version_id,
        "quality_status": d.quality_status,
        "status": d.status,
        "tags": loads(d.tags, []),
        "security_level": d.security_level,
        "creator_id": d.creator_id,
        "creator_name": creator_name,
        "created_at": iso(d.created_at),
        "updated_at": iso(d.updated_at),
    }


def item_out(it):
    return {
        "id": it.id,
        "dataset_id": it.dataset_id,
        "version_id": it.version_id,
        "item_no": it.item_no,
        "input_content": it.input_content,
        "reference_answer": it.reference_answer,
        "expected_output": it.expected_output,
        "task_requirement": it.task_requirement,
        "difficulty_level": it.difficulty_level,
        "data_label": it.data_label,
        "extended_content": loads(it.extended_content, {}),
        "quality_flag": it.quality_flag,
        "status": it.status,
    }


def model_out(m, hide_key=True):
    key = m.api_key or ""
    return {
        "id": m.id,
        "name": m.name,
        "model_type": m.model_type,
        "model_source": m.model_source,
        "description": m.description,
        "support_language": m.support_language,
        "support_modal": m.support_modal,
        "deploy_type": m.deploy_type,
        "access_mode": m.access_mode,
        "architecture": m.architecture,
        "parameter_scale": m.parameter_scale,
        "context_length": m.context_length,
        "applicable_scenario": m.applicable_scenario,
        "current_version": m.current_version,
        "api_url": m.api_url,
        "request_method": m.request_method,
        "auth_type": m.auth_type,
        "api_key_set": bool(key),
        "api_key": (key[:4] + "****") if hide_key and key else "",
        "served_model_name": m.served_model_name,
        "timeout": m.timeout,
        "retry_count": m.retry_count,
        "channel_type": m.channel_type,
        "status": m.status,
        "health_status": m.health_status,
        "last_health_at": iso(m.last_health_at),
        "last_error": m.last_error,
        "created_at": iso(m.created_at),
        "updated_at": iso(m.updated_at),
    }


def prompt_out(p):
    return {
        "id": p.id,
        "name": p.name,
        "prompt_type": p.prompt_type,
        "applicable_task": p.applicable_task,
        "applicable_model": p.applicable_model,
        "applicable_scene": p.applicable_scene,
        "description": p.description,
        "current_version": p.current_version,
        "current_version_id": p.current_version_id,
        "status": p.status,
        "created_at": iso(p.created_at),
        "updated_at": iso(p.updated_at),
    }


def task_out(t):
    return {
        "id": t.id,
        "name": t.name,
        "task_type": t.task_type,
        "scene": t.scene,
        "industry": t.industry,
        "dataset_id": t.dataset_id,
        "dataset_version_id": t.dataset_version_id,
        "model_id": t.model_id,
        "prompt_id": t.prompt_id,
        "prompt_version_id": t.prompt_version_id,
        "judge_resource_id": t.judge_resource_id,
        "status": t.status,
        "progress": t.progress,
        "total": t.total,
        "success_count": t.success_count,
        "fail_count": t.fail_count,
        "avg_score": t.avg_score,
        "pass_rate": t.pass_rate,
        "snapshot_id": t.snapshot_id,
        "batch_id": t.batch_id,
        "error_message": t.error_message,
        "report_summary": t.report_summary,
        "started_at": iso(t.started_at),
        "finished_at": iso(t.finished_at),
        "created_at": iso(t.created_at),
    }


def now():
    return datetime.utcnow()
