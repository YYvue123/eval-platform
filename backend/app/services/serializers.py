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
        "review_comment": getattr(d, "review_comment", "") or "",
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


def model_out(m, hide_key=True, meta=None):
    key = m.api_key or ""
    extra = {}
    if meta:
        extra = {
            "train_data_desc": meta.train_data_desc,
            "finetune_method": meta.finetune_method,
            "infer_framework": meta.infer_framework,
            "hardware": meta.hardware,
            "company_name": meta.company_name,
            "company_model_code": meta.company_model_code,
            "contact_name": meta.contact_name,
            "contact_email": meta.contact_email,
            "source_type": meta.source_type,
            "base_model": meta.base_model,
            "deploy_cluster": meta.deploy_cluster,
            "industry": meta.industry,
        }
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
        "current_version_id": getattr(m, "current_version_id", None),
        "api_url": m.api_url,
        "request_method": m.request_method,
        "auth_type": m.auth_type,
        "api_key_set": bool(key),
        "api_key": (key[:4] + "****") if hide_key and key else "",
        "served_model_name": m.served_model_name,
        "timeout": m.timeout,
        "retry_count": m.retry_count,
        "channel_type": m.channel_type,
        "request_template": getattr(m, "request_template", "") or "",
        "response_mapping": getattr(m, "response_mapping", "") or "",
        "scene_white_list": loads(getattr(m, "scene_white_list", "[]") or "[]", []),
        "parallel_limit": getattr(m, "parallel_limit", 4) or 4,
        "support_stream": bool(getattr(m, "support_stream", False)),
        "probe_interval_sec": getattr(m, "probe_interval_sec", 300) or 300,
        "consecutive_fail": getattr(m, "consecutive_fail", 0) or 0,
        "circuit_open_until": iso(getattr(m, "circuit_open_until", None)),
        "status": m.status,
        "health_status": m.health_status,
        "last_health_at": iso(m.last_health_at),
        "last_error": m.last_error,
        "created_at": iso(m.created_at),
        "updated_at": iso(m.updated_at),
        **extra,
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
        "tags": loads(getattr(p, "tags", "[]") or "[]", []),
        "constraints": getattr(p, "constraints", "") or "",
        "review_comment": getattr(p, "review_comment", "") or "",
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
        "trial_run": bool(getattr(t, "trial_run", False)),
        "simulation": bool(getattr(t, "simulation", False)),
        "model_version_id": getattr(t, "model_version_id", None),
        "template_code": getattr(t, "template_code", "") or "",
        "priority": getattr(t, "priority", 5) or 5,
        "depends_on_id": getattr(t, "depends_on_id", None),
        "metric_weights": loads(getattr(t, "metric_weights_json", None) or "{}", {}),
        "token_quota": getattr(t, "token_quota", 0) or 0,
        "tokens_used": getattr(t, "tokens_used", 0) or 0,
        "skip_count": getattr(t, "skip_count", 0) or 0,
        "window_start": iso(getattr(t, "window_start", None)),
        "window_end": iso(getattr(t, "window_end", None)),
        "report_path": getattr(t, "report_path", "") or "",
        "tool_version": getattr(t, "tool_version", "") or "",
        "lease_owner": getattr(t, "lease_owner", "") or "",
        "lease_until": iso(getattr(t, "lease_until", None)),
        "fencing_token": getattr(t, "fencing_token", 0) or 0,
        "cancel_requested": bool(getattr(t, "cancel_requested", False)),
        "attempt": getattr(t, "attempt", 0) or 0,
        "started_at": iso(t.started_at),
        "finished_at": iso(t.finished_at),
        "created_at": iso(t.created_at),
    }


def now():
    return datetime.utcnow()
