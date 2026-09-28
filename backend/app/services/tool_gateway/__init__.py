"""统一工具网关：信封校验、幂等、限流、分发。"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BaseResource, IdempotencyRecord, ResourceCallLog, ResourceVersion, User
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
from app.services.skill_runtime import run_mcp, run_skill
from app.services.side_effect_policy import has_side_effects, stub_side_effect_result
from app.utils.jsonutil import dumps, loads


class IdempotencyConflict(HTTPException):
    def __init__(self, detail: str = "幂等键冲突：相同 correlation 不同 payload"):
        super().__init__(status_code=409, detail=detail)


async def ensure_resource_version(db: AsyncSession, r: BaseResource, creator_id: int | None = None) -> ResourceVersion:
    ver = r.version or "1.0.0"
    existing = await db.scalar(
        select(ResourceVersion).where(
            ResourceVersion.resource_id == r.resource_id,
            ResourceVersion.version == ver,
        )
    )
    if existing:
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
    parent_trace_id: str | None = None,
    continue_trace_id: str | None = None,
    task_id: int | None = None,
    caller_id: str = "gateway",
    require_action: bool = False,
) -> dict:
    """统一调用入口，返回标准响应信封。"""
    r = (await db.execute(select(BaseResource).where(BaseResource.resource_id == resource_id))).scalar_one_or_none()
    if not r or r.status not in {"online", "pending"}:
        raise HTTPException(404, "资源不可用")

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

    manifest = loads(r.manifest_json, {})
    if has_side_effects(manifest):
        try:
            result = stub_side_effect_result(manifest)
        except PermissionError as exc:
            resp = make_response(
                req,
                "error",
                {},
                error={"code": "SIDE_EFFECT_DENIED", "message": str(exc), "retryable": False, "trace_id": req["trace"]["trace_id"]},
            )
            db.add(ResourceCallLog(resource_id=resource_id, task_id=task_id, status="failed", correlation_id=cid, error_message=str(exc)[:500]))
            return resp
        record_gateway(r.resource_id, True)
        r.call_count = int(r.call_count or 0) + 1
        resp = make_response(req, "success", result, usage={"total_tokens": 0})
        await _persist_idempotent(db, tenant_key, resource_id, rv.version, action, cid, rh, resp)
        db.add(ResourceCallLog(resource_id=resource_id, task_id=task_id, status="success", correlation_id=cid))
        return resp

    try:
        if r.resource_type == "skill":
            result = run_skill(manifest, params)
        elif r.resource_type == "mcp":
            result = await run_mcp(manifest, params)
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
        await _persist_idempotent(db, tenant_key, resource_id, rv.version, action, cid, rh, resp)
        db.add(ResourceCallLog(resource_id=resource_id, task_id=task_id, status="success", correlation_id=cid))
        return resp
    except HTTPException:
        raise
    except Exception as exc:
        r.fail_count = int(r.fail_count or 0) + 1
        r.consecutive_fail = int(r.consecutive_fail or 0) + 1
        record_gateway(r.resource_id, False)
        resp = make_response(
            req,
            "error",
            {},
            error={"code": "TOOL_EXEC_FAILED", "message": str(exc), "retryable": True, "trace_id": req["trace"]["trace_id"]},
        )
        db.add(ResourceCallLog(
            resource_id=resource_id,
            task_id=task_id,
            status="failed",
            error_message=str(exc)[:2000],
            correlation_id=cid,
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
