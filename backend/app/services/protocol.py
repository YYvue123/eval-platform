"""V0.6.1 消息信封与 Manifest 校验（平台侧最小实现）。"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

RESOURCE_TYPES = {
    "tool",
    "agent",
    "mcp",
    "skill",
    "datasource",
    "api",
    "model",
    "agent_mut",
    "eval_kit",
}
CALL_MODES = {"sync", "async", "stream", "batch"}
RESOURCE_ID_RE = re.compile(r"^[a-z0-9]{1,32}/[a-z0-9_]{1,64}$")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_envelope(source: str, destination: str, body: dict, message_type: str = "request") -> dict:
    return {
        "header": {
            "message_id": str(uuid.uuid4()),
            "message_type": message_type,
            "version": "1.3",
            "timestamp": utc_now_iso(),
            "source": source,
            "destination": destination,
        },
        "trace": {
            "trace_id": str(uuid.uuid4()).replace("-", ""),
            "span_id": uuid.uuid4().hex[:16],
        },
        "auth": {},
        "body": body or {},
        "correlation_id": str(uuid.uuid4()),
    }


def make_response(request_env: dict, status: str, body: dict) -> dict:
    dest = request_env.get("header", {}).get("source", "platform")
    src = request_env.get("header", {}).get("destination", "resource")
    env = make_envelope(src, dest, body, message_type="response")
    env["header"]["status"] = status
    env["correlation_id"] = request_env.get("correlation_id")
    return env


def validate_manifest(manifest: dict) -> list[str]:
    errors = []
    if not isinstance(manifest, dict):
        return ["Manifest 必须是 JSON 对象"]
    for field in ("spec_version", "resource_id", "resource_type", "name", "version", "description"):
        if not manifest.get(field):
            errors.append(f"缺少必填字段: {field}")
    rid = str(manifest.get("resource_id") or "")
    if rid and not RESOURCE_ID_RE.match(rid):
        errors.append("resource_id 格式必须为 {namespace}/{name}")
    rtype = manifest.get("resource_type")
    if rtype and rtype not in RESOURCE_TYPES:
        errors.append(f"不支持的 resource_type: {rtype}")
    owner = manifest.get("owner")
    if not isinstance(owner, dict) or not owner.get("name"):
        errors.append("owner.name 必填")
    caps = manifest.get("capabilities")
    if not isinstance(caps, dict):
        errors.append("capabilities 必填")
    else:
        if not isinstance(caps.get("input_schema"), dict):
            errors.append("capabilities.input_schema 必填")
        if not isinstance(caps.get("output_schema"), dict):
            errors.append("capabilities.output_schema 必填")
        mode = caps.get("call_mode")
        if mode not in CALL_MODES:
            errors.append("capabilities.call_mode 必须为 sync/async/stream/batch")
        if "idempotent" not in caps:
            errors.append("capabilities.idempotent 必填")
        if not isinstance(caps.get("timeout"), int):
            errors.append("capabilities.timeout 必须为整数秒")
    if not isinstance(manifest.get("interfaces"), dict):
        errors.append("interfaces 必填")
    spec = manifest.get("evaluation_spec")
    if spec:
        if spec.get("judge_type") not in {"llm_judge", "regex", "exact_match", "fuzzy", "custom", "contains"}:
            errors.append("evaluation_spec.judge_type 非法")
        names = spec.get("metric_names")
        if not isinstance(names, list) or not names:
            errors.append("evaluation_spec.metric_names 必填")
        threshold = spec.get("pass_threshold") or {}
        if threshold and isinstance(names, list):
            for key in threshold:
                if key not in names:
                    errors.append(f"pass_threshold 键名未出现在 metric_names: {key}")
    return errors
