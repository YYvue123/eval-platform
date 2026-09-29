"""统一工具网关：信封校验、幂等、限流、分发。"""
from __future__ import annotations

import time

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BaseResource, IdempotencyRecord, ResourceCallLog, ResourceVersion
from app.services.actor_context import ActorContext
from app.services.builtin_tools import run_builtin_tool
from app.services.gateway import check_gateway, record_gateway
from app.services.http_adapter import invoke_http_tool
from app.services.protocol import (
    make_envelope,
    make_response,
    normalize_invoke_body,
    request_hash,
    validate_request_envelope,
)
from app.services.mcp.catalog import persist_catalog
from app.services.skill_runtime import run_mcp, run_skill
from app.services.object_policy import object_is_visible
from app.services.redaction import evidence_digest, redact_error_text
from app.services.side_effect_policy import has_side_effects, side_effect_block
from app.utils.jsonutil import dumps, loads


class IdempotencyConflict(HTTPException):
    def __init__(self, detail: str = "幂等键冲突：相同 correlation 不同 payload"):
        super().__init__(status_code=409, detail=detail)


class NestedSkillError(RuntimeError):
    code = "SKILL_NESTING_FORBIDDEN"
    public_message = "Skill 不允许嵌套 Skill"


def _canon(value):
    if isinstance(value, dict):
        return {k: _canon(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [_canon(x) for x in value]
    return value


def manifests_equal(left, right) -> bool:
    def load(raw):
        if isinstance(raw, str):
            return loads(raw, {})
        return raw or {}

    return dumps(_canon(load(left))) == dumps(_canon(load(right)))


def _evidence_log(
    *,
    resource_id: str,
    task_id: int | None,
    status: str,
    latency_ms: int,
    error_message: str,
    correlation_id: str,
    parent_correlation_id: str,
    tenant_id: str,
    user_id: int | None,
    version: str,
    trace_id: str,
    source: str,
    params: dict,
    output,
) -> ResourceCallLog:
    input_digest, input_hash = evidence_digest(params)
    output_digest, output_hash = evidence_digest(output)
    return ResourceCallLog(
        resource_id=resource_id,
        task_id=task_id,
        status=status,
        latency_ms=latency_ms,
        error_message=error_message,
        correlation_id=correlation_id,
        parent_correlation_id=parent_correlation_id,
        tenant_id=tenant_id,
        user_id=user_id,
        version=version,
        trace_id=trace_id,
        input_digest=input_digest,
        output_digest=output_digest,
        input_hash=input_hash,
        output_hash=output_hash,
        source=source,
    )


async def ensure_resource_version(db: AsyncSession, r: BaseResource, creator_id: int | None = None) -> ResourceVersion:
    ver = r.version or "1.0.0"
    existing = await db.scalar(
        select(ResourceVersion).where(
            ResourceVersion.resource_id == r.resource_id,
            ResourceVersion.version == ver,
        )
    )
    current = r.manifest_json or "{}"
    if existing:
        if not manifests_equal(existing.manifest_json, current):
            raise HTTPException(409, "同版本 Manifest 内容与冻结快照不一致，请升级 version")
        return existing
    row = ResourceVersion(
        resource_id=r.resource_id,
        version=ver,
        manifest_json=r.manifest_json or "{}",
        creator_id=creator_id,
        immutable=True,
    )
    db.add(row)
    await db.flush()
    return row


async def invoke_tool(
    db: AsyncSession,
    *,
    actor: ActorContext | None,
    resource_id: str,
    body: dict | None,
    correlation_id: str | None = None,
    parent_correlation_id: str | None = None,
    parent_trace_id: str | None = None,
    continue_trace_id: str | None = None,
    task_id: int | None = None,
    caller_id: str = "gateway",
    require_action: bool = False,
    _depth: int = 0,
) -> dict:
    """统一调用入口，返回标准响应信封。"""
    r = (await db.execute(select(BaseResource).where(BaseResource.resource_id == resource_id))).scalar_one_or_none()
    if not r or r.status not in {"online", "pending", "registered"}:
        raise HTTPException(404, "资源不可用")
    if actor is not None:
        if not object_is_visible(r, actor):
            raise HTTPException(404, "资源不存在或无权访问")
    elif not r.builtin:
        raise HTTPException(404, "资源不存在或无权访问")

    tenant_key = str(actor.tenant_id) if actor else ""
    action, params = normalize_invoke_body(body)
    req = make_envelope(
        "platform",
        resource_id,
        {"action": action, "parameters": params},
        tenant_id=tenant_key,
        correlation_id=correlation_id,
        parent_trace_id=parent_trace_id,
        continue_trace_id=continue_trace_id,
        caller_id=caller_id,
    )
    verrs = validate_request_envelope(req, require_action=require_action)
    if verrs:
        raise HTTPException(422, {"code": "SCHEMA_VALIDATION_FAILED", "message": "; ".join(verrs), "details": verrs})

    check_gateway(r.resource_id)
    rv = await ensure_resource_version(db, r, creator_id=actor.user_id if actor else None)
    rh = request_hash({"action": action, "parameters": params})
    cid = req["header"]["correlation_id"]

    existing = await db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == tenant_key,
            IdempotencyRecord.resource_id == resource_id,
            IdempotencyRecord.version == rv.version,
            IdempotencyRecord.action == action,
            IdempotencyRecord.correlation_id == cid,
        )
    )
    if existing:
        if existing.request_hash != rh:
            raise IdempotencyConflict()
        return loads(existing.response_json, {})

    manifest = loads(rv.manifest_json, {})
    trace_id = (req.get("trace") or {}).get("trace_id") or ""
    actor_user = actor.user_id if actor else None
    started = time.perf_counter()
    if has_side_effects(manifest):
        blocked = side_effect_block(manifest)
        error = {
            "code": blocked.code,
            "message": str(blocked),
            "retryable": False,
            "trace_id": trace_id,
        }
        resp = make_response(
            req,
            "error",
            {},
            error=error,
        )
        db.add(_evidence_log(
            resource_id=resource_id,
            task_id=task_id,
            status="blocked",
            latency_ms=int((time.perf_counter() - started) * 1000),
            correlation_id=cid,
            error_message=str(blocked)[:500],
            parent_correlation_id=parent_correlation_id or "",
            tenant_id=tenant_key,
            user_id=actor_user,
            version=rv.version,
            trace_id=trace_id,
            source=caller_id,
            params=params,
            output=error,
        ))
        return resp

    try:
        if r.resource_type == "skill":
            if _depth >= 1:
                raise NestedSkillError()

            async def invoke_skill_step(
                step_id: str,
                step_resource_id: str,
                step_payload: dict,
            ) -> dict:
                return await invoke_tool(
                    db,
                    actor=actor,
                    resource_id=step_resource_id,
                    body=step_payload,
                    correlation_id=f"{cid}:{step_id}",
                    parent_correlation_id=cid,
                    parent_trace_id=trace_id,
                    continue_trace_id=trace_id,
                    task_id=task_id,
                    caller_id="skill_step",
                    _depth=_depth + 1,
                )

            result = await run_skill(
                manifest,
                params,
                step_invoker=invoke_skill_step,
            )
        elif r.resource_type == "mcp":
            method = str(params.get("method") or "")
            rpc_params = params.get("params") if isinstance(params.get("params"), dict) else {}
            req_id = params.get("id", 1)
            run = await run_mcp(manifest, method, rpc_params, req_id=req_id)
            result = run.result
            tools = []
            if method in {"tools/list", "list_tools"} and isinstance(result, dict):
                tools = result.get("tools")
                if not isinstance(tools, list):
                    inner = result.get("result")
                    tools = inner.get("tools") if isinstance(inner, dict) else []
                if not isinstance(tools, list):
                    tools = []
                await persist_catalog(
                    db, resource_id, tools, changed=run.catalog_changed, actor=actor,
                )
            elif run.catalog_changed:
                await persist_catalog(db, resource_id, [], changed=True, actor=actor)
        elif r.resource_id.startswith("builtin/") or r.builtin:
            result = run_builtin_tool(r.resource_id, params)
        else:
            result = await invoke_http_tool(manifest, req)
        r.call_count = int(r.call_count or 0) + 1
        r.consecutive_fail = 0
        r.health_status = "online"
        record_gateway(r.resource_id, True)
        usage = result.get("usage") if isinstance(result, dict) else None
        resp = make_response(req, "success", result if isinstance(result, dict) else {"result": result}, usage=usage)
        if r.resource_type == "mcp":
            meta = resp["body"].setdefault("metadata", {})
            meta["mcp_session"] = {
                "protocol_version": run.protocol_version,
                "server_info": run.server_info,
                "session_id_present": run.session_id_present,
            }
            meta["mcp_notifications"] = list(run.notifications)
        await _persist_idempotent(db, tenant_key, resource_id, rv.version, action, cid, rh, resp)
        db.add(_evidence_log(
            resource_id=resource_id,
            task_id=task_id,
            status="success",
            correlation_id=cid,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error_message="",
            parent_correlation_id=parent_correlation_id or "",
            tenant_id=tenant_key,
            user_id=actor_user,
            version=rv.version,
            trace_id=trace_id,
            source=caller_id,
            params=params,
            output=result,
        ))
        return resp
    except HTTPException:
        raise
    except Exception as exc:
        r.fail_count = int(r.fail_count or 0) + 1
        r.consecutive_fail = int(r.consecutive_fail or 0) + 1
        record_gateway(r.resource_id, False)
        public_message = getattr(exc, "public_message", None)
        safe_message = (
            redact_error_text(public_message)
            if isinstance(public_message, str) and public_message.strip()
            else f"工具执行失败 ({type(exc).__name__})"
        )
        error = {
            "code": getattr(exc, "code", "TOOL_EXEC_FAILED") or "TOOL_EXEC_FAILED",
            "message": safe_message,
            "retryable": True,
            "trace_id": req["trace"]["trace_id"],
        }
        resp = make_response(
            req,
            "error",
            {},
            error=error,
        )
        db.add(_evidence_log(
            resource_id=resource_id,
            task_id=task_id,
            status="failed",
            error_message=safe_message[:2000],
            correlation_id=cid,
            latency_ms=int((time.perf_counter() - started) * 1000),
            parent_correlation_id=parent_correlation_id or "",
            tenant_id=tenant_key,
            user_id=actor_user,
            version=rv.version,
            trace_id=trace_id,
            source=caller_id,
            params=params,
            output=error,
        ))
        # 失败不写入幂等成功记录，允许重试
        return resp


async def _persist_idempotent(
    db: AsyncSession,
    tenant_id: str,
    resource_id: str,
    version: str,
    action: str,
    correlation_id: str,
    rh: str,
    resp: dict,
) -> None:
    db.add(IdempotencyRecord(
        tenant_id=tenant_id,
        resource_id=resource_id,
        version=version,
        action=action,
        correlation_id=correlation_id,
        request_hash=rh,
        response_json=dumps(resp),
        status="done",
    ))
    await db.flush()


def response_result(envelope: dict) -> dict:
    """从标准响应取出业务 result；兼容旧 header.status。"""
    body = envelope.get("body") or {}
    if isinstance(body, dict) and "result" in body:
        return body.get("result") or {}
    return body if isinstance(body, dict) else {}
