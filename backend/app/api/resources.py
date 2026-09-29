"""智能工具底座：Manifest 注册、发现、信封调用、事件。"""
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_actor
from app.database import get_db
from app.models import BaseResource, ResourceCallLog, ResourceEvent
from app.services.actor_context import ActorContext
from app.services.audit import get_client_ip, log_audit
from app.services.http_adapter import health_http_tool
from app.services.mcp.catalog import catalog_summary
from app.services.mcp.errors import McpError
from app.services.mcp.stdio_transport import list_stdio_aliases
from app.services.object_policy import apply_object_scope, object_is_visible
from app.services.protocol import executable_errors, validate_manifest
from app.services.redaction import evidence_digest, redact_secrets
from app.services.serializers import now
from app.services.tool_gateway import ensure_resource_version, invoke_tool, manifests_equal
from app.utils.jsonutil import dumps, iso, loads

router = APIRouter()


class ManifestBody(BaseModel):
    manifest: dict


class InvokeBody(BaseModel):
    resource_id: str
    body: dict = {}
    tenant_id: str = ""
    correlation_id: str | None = None
    priority: str = "normal"


class MatchBody(BaseModel):
    resource_type: str = ""
    judge_type: str = ""
    call_mode: str = ""
    name: str = ""


def _redact_manifest(manifest: dict) -> dict:
    return redact_secrets(manifest or {})


def resource_out(r: BaseResource):
    return {
        "id": r.id,
        "resource_id": r.resource_id,
        "resource_type": r.resource_type,
        "name": r.name,
        "version": r.version,
        "spec_version": r.spec_version,
        "description": r.description,
        "status": r.status,
        "builtin": r.builtin,
        "tenant_id": r.tenant_id,
        "visibility": r.visibility,
        "health_status": r.health_status,
        "call_count": r.call_count,
        "fail_count": r.fail_count,
        "manifest": _redact_manifest(loads(r.manifest_json, {})),
        "quality_report": loads(r.quality_report, {}),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


async def _emit(db, event_type: str, resource_id: str, payload: dict | None = None):
    db.add(ResourceEvent(event_type=event_type, resource_id=resource_id, payload_json=dumps(payload or {})))


async def _load_resource(db, rid: str) -> BaseResource | None:
    r = (await db.execute(select(BaseResource).where(BaseResource.resource_id == rid))).scalar_one_or_none()
    if r:
        return r
    try:
        return await db.get(BaseResource, int(rid))
    except ValueError:
        return None


async def _visible_resource(db, rid: str, actor: ActorContext) -> BaseResource:
    r = await _load_resource(db, rid)
    if not r or not object_is_visible(r, actor):
        raise HTTPException(404, "资源不存在或无权访问")
    return r


@router.get("")
async def list_resources(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    resource_type: str = Query(""),
    status: str = Query(""),
    search: str = Query(""),
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("resource:list")),
):
    q = apply_object_scope(select(BaseResource), BaseResource, actor)
    if resource_type:
        q = q.where(BaseResource.resource_type == resource_type)
    if status:
        q = q.where(BaseResource.status == status)
    if search:
        q = q.where(or_(BaseResource.name.contains(search), BaseResource.resource_id.contains(search)))
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (await db.execute(q.order_by(BaseResource.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [resource_out(r) for r in rows], "total": total or 0}


@router.post("/match")
async def match_resources(
    body: MatchBody,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("resource:list")),
):
    rows = (await db.execute(select(BaseResource).where(BaseResource.status == "online"))).scalars().all()
    rows = [r for r in rows if object_is_visible(r, actor)]
    matched = []
    for r in rows:
        mf = loads(r.manifest_json, {})
        spec = mf.get("evaluation_spec") or {}
        caps = mf.get("capabilities") or {}
        if body.resource_type and r.resource_type != body.resource_type:
            continue
        if body.judge_type and spec.get("judge_type") != body.judge_type:
            continue
        if body.call_mode and caps.get("call_mode") != body.call_mode:
            continue
        if body.name and body.name.lower() not in (r.name or "").lower() and body.name.lower() not in r.resource_id:
            continue
        matched.append(resource_out(r))
    return {"items": matched, "total": len(matched)}


@router.get("/registry")
async def resource_registry(
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("resource:list")),
):
    """进程内注册中心：在线资源发现；连续失败 5 次健康剔除。"""
    rows = (await db.execute(select(BaseResource))).scalars().all()
    items = []
    for r in rows:
        if not object_is_visible(r, actor):
            continue
        if not r.builtin and int(r.consecutive_fail or 0) >= 5 and r.status == "online":
            r.status = "unhealthy"
            r.health_status = "abnormal"
            await _emit(db, "resource.unhealthy", r.resource_id, {"consecutive_fail": r.consecutive_fail})
        if r.status in {"online", "pending"}:
            items.append({
                **resource_out(r),
                "instance": "in-process",
                "last_heartbeat": iso(getattr(r, "last_heartbeat", None) or r.updated_at),
            })
    return {"items": items, "total": len(items), "backend": "in-process"}


@router.get("/judges")
async def list_judges(
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("resource:list")),
):
    """打分候选：Tool、输出含 score 的 Skill，以及已同步目录的 MCP 工具。"""
    from app.services.judge_options import list_judge_options

    items = await list_judge_options(db, actor)
    return {"items": items, "total": len(items)}


@router.post("/{rid:path}/heartbeat")
async def resource_heartbeat(
    rid: str,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("resource:invoke")),
):
    r = await _visible_resource(db, rid, actor)
    from datetime import datetime
    r.last_heartbeat = datetime.utcnow()
    r.health_status = "online"
    if r.status == "unhealthy":
        r.status = "online"
        r.consecutive_fail = 0
    return {"ok": True, "resource_id": r.resource_id, "status": r.status}


@router.get("/events")
async def list_events(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("resource:view")),
):
    rows = (await db.execute(select(ResourceEvent).order_by(ResourceEvent.id.desc()).limit(limit * 5))).scalars().all()
    visible = []
    cache: dict[str, bool] = {}
    for e in rows:
        rid = e.resource_id or ""
        if rid not in cache:
            resource = await _load_resource(db, rid) if rid else None
            cache[rid] = bool(resource and object_is_visible(resource, actor))
        if cache[rid]:
            visible.append(e)
        if len(visible) >= limit:
            break
    rows = visible
    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "resource_id": e.resource_id,
            "payload": loads(e.payload_json, {}),
            "created_at": iso(e.created_at),
        }
        for e in rows
    ]


@router.post("/register")
async def register_resource(
    body: ManifestBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("resource:create")),
):
    errors = validate_manifest(body.manifest) + executable_errors(body.manifest)
    if errors:
        raise HTTPException(400, "Manifest 校验失败: " + "；".join(errors))
    if body.manifest.get("resource_type") == "skill" and (body.manifest.get("skill") or {}).get("execution_type", "workflow") in {"", "workflow"}:
        chain = (body.manifest.get("skill") or {}).get("chain") or []
        for index, step in enumerate(chain):
            resource_id = (
                str(step.get("resource_id") or "").strip()
                if isinstance(step, dict)
                else ""
            )
            if not resource_id:
                raise HTTPException(400, f"skill.chain[{index}] 缺少 resource_id")
            referenced = await _load_resource(db, resource_id)
            if not referenced or not object_is_visible(referenced, actor):
                raise HTTPException(
                    400,
                    f"skill.chain[{index}] 引用的资源不存在或无权访问",
                )
            if referenced.resource_type == "skill":
                raise HTTPException(
                    400,
                    f"skill.chain[{index}] Skill 不允许嵌套 Skill",
                )
    rid = body.manifest["resource_id"]
    existing = (await db.execute(select(BaseResource).where(BaseResource.resource_id == rid))).scalar_one_or_none()
    report = {"passed": True, "checks": ["schema", "resource_id", "capabilities"]}
    created = False
    if existing:
        if existing.builtin:
            raise HTTPException(403, "禁止覆盖平台内置资源")
        if not object_is_visible(existing, actor):
            raise HTTPException(404, "资源不存在或无权访问")
        if int(existing.tenant_id or -1) != int(actor.tenant_id):
            raise HTTPException(403, "禁止覆盖其他租户资源")
        if (existing.version or "") == str(body.manifest["version"]) and not manifests_equal(existing.manifest_json, body.manifest):
            raise HTTPException(409, "相同版本内容已冻结，请升级 version 后再注册")
        existing.manifest_json = dumps(body.manifest)
        existing.name = body.manifest["name"]
        existing.version = body.manifest["version"]
        existing.description = body.manifest.get("description", "")
        existing.spec_version = str(body.manifest.get("spec_version", "0.6.1"))
        existing.quality_report = dumps(report)
        if existing.status not in {"online", "offline", "unhealthy"}:
            existing.status = "registered"
        existing.health_status = existing.health_status or "unknown"
        existing.updated_at = now()
        r = existing
    else:
        created = True
        r = BaseResource(
            resource_id=rid,
            resource_type=body.manifest["resource_type"],
            name=body.manifest["name"],
            version=body.manifest["version"],
            spec_version=str(body.manifest.get("spec_version", "0.6.1")),
            description=body.manifest.get("description", ""),
            status="registered",
            manifest_json=dumps(body.manifest),
            quality_report=dumps(report),
            health_status="unknown",
            creator_id=actor.user_id,
            tenant_id=actor.tenant_id,
            visibility="private",
        )
        db.add(r)
        await db.flush()
    await ensure_resource_version(db, r, creator_id=actor.user_id)
    await _emit(db, "resource.registered" if created else "resource.updated", rid, {"version": r.version})
    await log_audit(db, "resource", "register", user_id=actor.user_id, username=actor.username, target_id=r.id, ip=get_client_ip(request), detail=rid)
    return resource_out(r)


@router.post("/invoke")
async def invoke_resource(
    body: InvokeBody,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("resource:invoke")),
):
    # body.tenant_id 不可覆盖会话租户（WP01/WP02）
    return await invoke_tool(
        db,
        actor=actor,
        resource_id=body.resource_id,
        body=body.body,
        correlation_id=body.correlation_id,
        caller_id="gateway",
    )


@router.get("/mcp/stdio-aliases")
async def stdio_aliases(
    _: ActorContext = Depends(require_actor("resource:create")),
):
    return {"items": list_stdio_aliases()}


class McpProbeBody(BaseModel):
    endpoint: str = ""
    resource_id: str = ""
    method: str = "initialize"
    params: dict = {}
    token: str = ""
    egress_allowlist: list[str] = []
    transport: str = "streamable_http"
    command_alias: str = ""


def _probe_payload(*, ok, mode, target, transport, run, error):
    session = {
        "protocol_version": "",
        "server_info": {},
        "session_id_present": False,
    }
    notifications = []
    result = None
    if run is not None:
        session = {
            "protocol_version": run.protocol_version,
            "server_info": run.server_info,
            "session_id_present": run.session_id_present,
        }
        notifications = list(run.notifications)
        result = run.result
    return {
        "ok": ok,
        "mode": mode,
        "target": target,
        "transport": transport,
        "probed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session": session,
        "error": error.as_dict() if error else None,
        "result": result if error is None else None,
        "notifications": notifications,
    }


@router.post("/mcp/probe")
async def mcp_probe(
    body: McpProbeBody,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("resource:invoke")),
):
    """探测远程、stdio 或已注册 MCP。来源互斥。"""
    import time

    from app.services.mcp.runner import McpRunResult, bind_temp_credential, unbind_temp_credential
    from app.services.skill_runtime import run_mcp

    rid = (body.resource_id or "").strip()
    endpoint = (body.endpoint or "").strip()
    command_alias = (body.command_alias or "").strip()
    sources = [bool(rid), bool(endpoint), bool(command_alias)]
    if sum(sources) > 1:
        raise HTTPException(400, "mcp_source_mutex:resource_id、endpoint 与 command_alias 不能同时提供，请二选一")
    if not rid and not endpoint and not command_alias:
        raise HTTPException(400, "请提供 resource_id、HTTP endpoint 或 command_alias")

    if rid:
        mode = "registered"
        target = rid
        transport = body.transport or "streamable_http"
        envelope = await invoke_tool(
            db,
            actor=actor,
            resource_id=rid,
            body={"method": body.method, "params": body.params or {}, "id": 1},
            caller_id="mcp_probe",
        )
        resp_body = envelope.get("body") or {}
        meta = resp_body.get("metadata") or {}
        session_meta = meta.get("mcp_session") if isinstance(meta.get("mcp_session"), dict) else {}
        error = None
        run = None
        if resp_body.get("status") == "error":
            err = resp_body.get("error") if isinstance(resp_body.get("error"), dict) else {}
            error = McpError(str(err.get("code") or "TOOL_EXEC_FAILED"), str(err.get("message") or "MCP error"))
        else:
            result = resp_body.get("result") if isinstance(resp_body.get("result"), dict) else {}
            run = McpRunResult(
                result=result or {},
                protocol_version=str(session_meta.get("protocol_version") or ""),
                server_info=session_meta.get("server_info") if isinstance(session_meta.get("server_info"), dict) else {},
                session_id_present=bool(session_meta.get("session_id_present")),
                notifications=list(meta.get("mcp_notifications") or []),
                catalog_changed=False,
            )
        r = await _visible_resource(db, rid, actor)
        interfaces = (loads(r.manifest_json, {}) or {}).get("interfaces") or {}
        transport = str(interfaces.get("transport") or transport or "streamable_http")
        return _probe_payload(
            ok=error is None,
            mode=mode,
            target=target,
            transport=transport,
            run=run,
            error=error,
        )

    mode = "remote"
    transport = "stdio" if command_alias else str(body.transport or "streamable_http")
    target = command_alias if command_alias else endpoint
    if command_alias:
        manifest = {
            "interfaces": {"transport": "stdio", "command_alias": command_alias},
            "capabilities": {"timeout": 30},
        }
        host_or_alias = command_alias
    else:
        if not endpoint.startswith("http"):
            raise HTTPException(400, "endpoint 须为 http(s) URL")
        interfaces = {"endpoint": endpoint, "transport": "streamable_http"}
        if body.egress_allowlist:
            interfaces["egress_allowlist"] = body.egress_allowlist
        manifest = {"interfaces": interfaces, "capabilities": {"timeout": 30}}
        host_or_alias = urlparse(endpoint).hostname or "unknown"

    started = time.perf_counter()
    error = None
    run = None
    token_ref = ""
    try:
        if not command_alias and body.token:
            token_ref = bind_temp_credential(body.token)
            manifest["interfaces"].setdefault("auth", {})["credential_ref"] = token_ref
        run = await run_mcp(manifest, body.method, body.params or {}, req_id=1)
    except McpError as exc:
        error = exc
    except Exception as exc:
        error = McpError("TOOL_EXEC_FAILED", str(exc) or type(exc).__name__)
    finally:
        if token_ref:
            unbind_temp_credential(token_ref)

    status = "failed" if error else "success"
    output = error.as_dict() if error else (run.result if run else {})
    input_digest, input_hash = evidence_digest({"method": body.method, "params": body.params or {}})
    output_digest, output_hash = evidence_digest(output)
    db.add(ResourceCallLog(
        resource_id=f"adhoc-mcp:{host_or_alias}",
        task_id=None,
        status=status,
        latency_ms=int((time.perf_counter() - started) * 1000),
        error_message=(error.message if error else "")[:2000],
        correlation_id="",
        parent_correlation_id="",
        tenant_id=str(actor.tenant_id),
        user_id=actor.user_id,
        version="",
        trace_id="",
        input_digest=input_digest,
        output_digest=output_digest,
        input_hash=input_hash,
        output_hash=output_hash,
        source="mcp_probe",
    ))
    return _probe_payload(
        ok=error is None,
        mode=mode,
        target=target,
        transport=transport,
        run=run,
        error=error,
    )


@router.post("/{rid:path}/health")
async def resource_health(
    rid: str,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("resource:view")),
):
    r = await _visible_resource(db, rid, actor)
    if r.builtin or r.resource_id.startswith("builtin/"):
        r.health_status = "online"
        return {"ok": True, "status": "online", "detail": "builtin"}
    manifest = loads(r.manifest_json, {})
    if r.resource_type == "skill":
        result = await _health_skill(db, manifest)
    else:
        result = await health_http_tool(manifest)
    r.health_status = "online" if result.get("ok") else "abnormal"
    return result


async def _health_skill(db: AsyncSession, manifest: dict) -> dict:
    """提示词和转交子 Agent 在进程内执行，不探测网络。工作流只检查步骤里的工具是否仍可引用。"""
    skill = manifest.get("skill") or {}
    execution = skill.get("execution_type") or "workflow"
    if execution in {"prompt_template", "agent"}:
        if not str(skill.get("entry_point") or "").strip():
            return {"ok": False, "status": "abnormal", "detail": "缺少执行入口"}
        label = "提示词" if execution == "prompt_template" else "转交子 Agent"
        return {"ok": True, "status": "online", "detail": f"{label}在进程内执行，不需要网络地址"}
    if execution != "workflow":
        return {"ok": False, "status": "abnormal", "detail": f"未支持的执行方式 {execution}"}
    chain = skill.get("chain") or []
    if not isinstance(chain, list) or not chain:
        return {"ok": False, "status": "abnormal", "detail": "工作流没有步骤"}
    missing = []
    blocked = []
    for step in chain:
        if not isinstance(step, dict):
            missing.append("无效步骤")
            continue
        target = str(step.get("resource_id") or step.get("$ref") or "").strip()
        if not target:
            missing.append("缺少工具")
            continue
        row = await db.scalar(select(BaseResource).where(BaseResource.resource_id == target))
        if row is None:
            missing.append(target)
        elif row.status == "offline" or row.health_status in {"offline", "circuit_open"}:
            blocked.append(target)
    if missing or blocked:
        parts = []
        if missing:
            parts.append("找不到工具：" + "、".join(missing))
        if blocked:
            parts.append("工具已下线：" + "、".join(blocked))
        return {"ok": False, "status": "abnormal", "detail": "；".join(parts)}
    return {"ok": True, "status": "online", "detail": "工作流步骤均已注册且未下线"}


@router.post("/{rid:path}/offline")
async def offline_resource(
    rid: str,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("resource:edit")),
):
    r = await _visible_resource(db, rid, actor)
    if r.builtin:
        raise HTTPException(400, "内置工具不可下线")
    r.status = "offline"
    await _emit(db, "resource.offline", r.resource_id, {})
    return resource_out(r)


@router.get("/calls/{rid:path}")
async def resource_call_history(
    rid: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = Query(""),
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("resource:view")),
):
    resource = await _visible_resource(db, rid, actor)
    query = select(ResourceCallLog).where(
        ResourceCallLog.resource_id == resource.resource_id,
        ResourceCallLog.tenant_id == str(actor.tenant_id),
    )
    if status:
        query = query.where(ResourceCallLog.status == status)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db.execute(
            query.order_by(ResourceCallLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": row.id,
                "resource_id": row.resource_id,
                "status": row.status,
                "latency_ms": row.latency_ms,
                "error_message": row.error_message,
                "correlation_id": row.correlation_id,
                "parent_correlation_id": row.parent_correlation_id,
                "tenant_id": row.tenant_id,
                "user_id": row.user_id,
                "version": row.version,
                "trace_id": row.trace_id,
                "input_digest": row.input_digest,
                "output_digest": row.output_digest,
                "input_hash": row.input_hash,
                "output_hash": row.output_hash,
                "source": row.source,
                "created_at": iso(row.created_at),
            }
            for row in rows
        ],
        "total": total or 0,
    }


@router.get("/{rid:path}")
async def get_resource(
    rid: str,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("resource:view")),
):
    r = await _visible_resource(db, rid, actor)
    payload = resource_out(r)
    if r.resource_type == "mcp":
        payload["mcp_catalog"] = await catalog_summary(db, r.resource_id)
    return payload
