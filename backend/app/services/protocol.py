"""V0.6.1 / 信封 1.3 消息构造与校验。

接入 profile: platform-v0.6.1/envelope-1.3
（spec_version 原文歧义见 docs/delivery/WP02.md ADR）
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone

PROFILE = "platform-v0.6.1/envelope-1.3"
RESOURCE_TYPES = {
    "tool", "agent", "mcp", "skill", "datasource", "api",
    "model", "agent_mut", "eval_kit",
}
CALL_MODES = {"sync", "async", "stream", "batch"}
RESOURCE_ID_RE = re.compile(r"^[a-z0-9]{1,32}/[a-z0-9_]{1,64}$")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def request_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_envelope(
    source: str,
    destination: str,
    body: dict,
    message_type: str = "request",
    *,
    correlation_id: str | None = None,
    priority: str = "normal",
    ttl: int = 300,
    tenant_id: str = "",
    parent_trace_id: str | None = None,
    continue_trace_id: str | None = None,
    caller_id: str = "gateway",
    usage: dict | None = None,
) -> dict:
    cid = correlation_id or str(uuid.uuid4())
    trace_id = continue_trace_id or uuid.uuid4().hex
    if len(trace_id) != 32:
        # 兼容传入带连字符的 UUID
        trace_id = trace_id.replace("-", "")[:32].ljust(32, "0")
    parent_span = (parent_trace_id or "")[:16] if parent_trace_id else ""
    span_id = uuid.uuid4().hex[:16]
    header = {
        "message_id": str(uuid.uuid4()),
        "message_type": message_type,
        "version": "1.3",
        "timestamp": utc_now_iso(),
        "source": source,
        "destination": destination,
        "correlation_id": cid,
        "priority": priority or "normal",
        "ttl": int(ttl or 300),
        "tenant_id": tenant_id or "",
        "profile": PROFILE,
    }
    env = {
        "header": header,
        "trace": {
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span,
            "traceparent": f"00-{trace_id}-{span_id}-01",
            "parent_trace_id": parent_trace_id or "",
        },
        "auth": {"caller_id": caller_id or "gateway"},
        "body": body or {},
        "correlation_id": cid,
    }
    if usage is not None:
        env["usage"] = usage
    return env


def make_response(
    request_env: dict,
    status: str,
    body: dict | None = None,
    usage: dict | None = None,
    error: dict | None = None,
) -> dict:
    """标准响应：body.status/result|error/metadata；延续 request.trace.trace_id。"""
    hdr = request_env.get("header") or {}
    tr = request_env.get("trace") or {}
    dest = hdr.get("source", "platform")
    src = hdr.get("destination", "resource")
    ok = status in {"ok", "success"}
    norm_status = "success" if ok else "error"
    result_body = body if isinstance(body, dict) else {"value": body}
    usage_val = usage
    if usage_val is None and isinstance(result_body, dict):
        usage_val = result_body.pop("usage", None) if "usage" in result_body else None
    if norm_status == "error":
        payload = {
            "status": "error",
            "error": error or {
                "code": "TOOL_EXEC_FAILED",
                "message": str((result_body or {}).get("message") or "error"),
                "retryable": False,
                "trace_id": tr.get("trace_id") or "",
            },
            "metadata": {},
        }
    else:
        payload = {
            "status": "success",
            "result": result_body or {},
            "metadata": {},
        }
        if usage_val is not None:
            payload["metadata"]["usage"] = usage_val
    env = make_envelope(
        src,
        dest,
        payload,
        message_type="response",
        correlation_id=hdr.get("correlation_id") or request_env.get("correlation_id"),
        priority=hdr.get("priority", "normal"),
        ttl=hdr.get("ttl", 300),
        tenant_id=hdr.get("tenant_id", ""),
        parent_trace_id=tr.get("span_id") or tr.get("trace_id"),
        continue_trace_id=tr.get("trace_id"),
        caller_id=(request_env.get("auth") or {}).get("caller_id") or "gateway",
    )
    # 兼容旧客户端读取 header.status
    env["header"]["status"] = "ok" if norm_status == "success" else "error"
    if usage_val is not None:
        env["usage"] = usage_val
    return env


def validate_request_envelope(env: dict, *, require_action: bool = True) -> list[str]:
    errors = []
    if not isinstance(env, dict):
        return ["信封必须是对象"]
    hdr = env.get("header")
    if not isinstance(hdr, dict):
        errors.append("缺少 header")
    else:
        for f in ("message_id", "message_type", "version", "timestamp", "source", "destination"):
            if not hdr.get(f):
                errors.append(f"header.{f} 必填")
        if hdr.get("version") and hdr.get("version") != "1.3":
            errors.append("header.version 必须为 1.3")
        if hdr.get("message_type") not in {None, "request", "response", "event", "stream"}:
            errors.append("header.message_type 非法")
    auth = env.get("auth")
    if not isinstance(auth, dict) or not str(auth.get("caller_id") or "").strip():
        errors.append("auth.caller_id 必填")
    body = env.get("body")
    if not isinstance(body, dict):
        errors.append("body 必填")
    elif require_action:
        # 兼容旧扁平调用：无 action 时视为 execute + parameters=body
        if "action" not in body and "parameters" not in body:
            pass  # 兼容模式由网关归一化
        elif "action" in body and not str(body.get("action") or "").strip():
            errors.append("body.action 不能为空")
    if "trace" in env and not isinstance(env.get("trace"), dict):
        errors.append("trace 必须是对象")
    return errors


def normalize_invoke_body(body: dict | None) -> tuple[str, dict]:
    """返回 (action, parameters)。旧客户端直接传工具参数。"""
    body = body or {}
    if "action" in body or "parameters" in body:
        action = str(body.get("action") or "execute").strip() or "execute"
        params = body.get("parameters") if isinstance(body.get("parameters"), dict) else {
            k: v for k, v in body.items() if k not in {"action", "parameters", "metadata"}
        }
        return action, params
    return "execute", dict(body)


_SECRET_KEYS = {"token", "api_key", "apikey", "secret", "password", "authorization"}


def find_plaintext_secrets(node, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            if str(key).lower() in _SECRET_KEYS and isinstance(value, str) and value.strip():
                found.append(here)
            else:
                found.extend(find_plaintext_secrets(value, here))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(find_plaintext_secrets(value, f"{path}[{index}]"))
    return found


def executable_errors(manifest: dict) -> list[str]:
    """注册必须可执行：禁止 local:// 空壳和明文凭证。"""
    errors = [f"禁止保存明文凭证: {item}" for item in find_plaintext_secrets(manifest)]
    rtype = manifest.get("resource_type")
    interfaces = manifest.get("interfaces") or {}
    endpoint = str(interfaces.get("endpoint") or interfaces.get("url") or "")
    if rtype == "tool":
        if not endpoint.startswith("http"):
            errors.append("工具必须配置 http(s) endpoint，不能使用 local://")
    elif rtype == "skill":
        skill = manifest.get("skill") or {}
        execution = skill.get("execution_type") or "workflow"
        if execution not in {"workflow", "prompt_template", "agent"}:
            errors.append("Skill 执行方式仅支持 workflow、prompt_template、agent")
        trigger = skill.get("trigger") if isinstance(skill.get("trigger"), dict) else {}
        trigger_type = trigger.get("type") or "context"
        if trigger_type not in {"keyword", "intent", "entity", "context", "manual"}:
            errors.append("Skill trigger.type 不合法")
        chain = skill.get("chain") or []
        if execution == "workflow":
            if not isinstance(chain, list) or not chain:
                errors.append("workflow Skill 必须声明非空 skill.chain")
            else:
                for index, step in enumerate(chain):
                    if not isinstance(step, dict) or not (step.get("resource_id") or step.get("$ref")):
                        errors.append(f"skill.chain[{index}] 缺少 resource_id")
        elif not str(skill.get("entry_point") or "").strip():
            errors.append("prompt_template 和 agent Skill 需要 entry_point")
    elif rtype == "mcp":
        from app.services.mcp.stdio_transport import list_stdio_aliases

        transport = interfaces.get("transport", "streamable_http")
        if transport == "stdio":
            if interfaces.get("command") or interfaces.get("args"):
                errors.append("stdio MCP 只能使用 command_alias")
            if not interfaces.get("command_alias"):
                errors.append("stdio MCP 必须配置 command_alias")
            elif interfaces["command_alias"] not in list_stdio_aliases():
                errors.append("stdio command_alias 不在服务端白名单")
        elif transport == "streamable_http":
            if not endpoint.startswith("http"):
                errors.append("Streamable HTTP MCP 必须配置 http(s) endpoint")
        else:
            errors.append("MCP transport 仅支持 streamable_http 或 stdio")
    return errors


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
    # 顶层 side_effects 优先（规范）；capabilities.side_effects 仅兼容
    se = manifest.get("side_effects")
    if se is not None and not isinstance(se, (list, str, bool)):
        errors.append("side_effects 必须为数组或字符串")
    spec = manifest.get("evaluation_spec")
    if spec:
        jt = spec.get("judge_type")
        allowed = {"llm_judge", "regex", "exact_match", "fuzzy", "custom", "contains", "rule_based"}
        if jt not in allowed:
            errors.append("evaluation_spec.judge_type 非法")
        names = spec.get("metric_names")
        if not isinstance(names, list) or not names:
            errors.append("evaluation_spec.metric_names 必填")
        threshold = spec.get("pass_threshold") or {}
        if threshold and isinstance(names, list):
            for key in threshold:
                if key not in names:
                    errors.append(f"pass_threshold 键名未出现在 metric_names: {key}")
        if jt == "llm_judge":
            if not (spec.get("judge_prompt_template") and spec.get("judge_model")):
                errors.append("llm_judge 需要同时提供 judge_prompt_template 与 judge_model")
    return errors
