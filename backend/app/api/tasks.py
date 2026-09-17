"""评测任务、榜单、评测服务。"""
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.database import get_db
from app.models import (
    AlertPolicy,
    Dataset,
    EvalModel,
    EvalResult,
    EvalLineage,
    EvalServiceRequest,
    EvalTask,
    EvalWorkspace,
    LeaderboardWeight,
    ModelCost,
    PromptTemplate,
    TaskEvent,
    TaskSubtask,
    TaskTemplate,
    User,
)
from app.api.models import _acl_allows
from app.services.audit import get_client_ip, log_audit
from app.services.serializers import task_out
from app.services.leaderboard import compute_board, last_snapshot, radar_payload, save_snapshot
from app.services.task_catalog import find_template, industry_options, scene_options
from app.services.task_events import emit_event
from app.services.task_queue import dispatch_queue, enqueue_task
from app.utils.jsonutil import dumps, iso, loads

router = APIRouter()
service_router = APIRouter()
leaderboard_router = APIRouter()


class TaskCreate(BaseModel):
    name: str
    task_type: str = "capability"
    scene: str = "qa"
    industry: str = "general"
    dataset_id: int
    dataset_version_id: int | None = None
    model_id: int
    prompt_id: int | None = None
    prompt_version_id: int | None = None
    judge_resource_id: str = "builtin/exact_match"
    trial_run: bool = False
    model_version_id: int | None = None
    template_code: str = ""
    priority: int = 5
    depends_on_id: int | None = None
    token_quota: int = 0
    window_start: datetime | None = None
    window_end: datetime | None = None
    metric_weights: dict | None = None


class AuditBody(BaseModel):
    approved: bool = True
    comment: str = ""


class AlertPatch(BaseModel):
    enabled: bool | None = None
    title: str | None = None


class ServiceCreate(BaseModel):
    title: str
    industry: str = "general"
    requirement: str = ""
    task_id: int | None = None
    workspace_id: int | None = None
    dataset_id: int | None = None
    model_id: int | None = None
    scene: str = "chat"
    quote_mode: str = "auto"


class QuoteBody(BaseModel):
    mode: str = "auto"
    amount: float | None = None


class WorkspaceCreate(BaseModel):
    name: str
    code: str
    quota_tokens: int = 100000
    quota_calls: int = 10000


class WeightItem(BaseModel):
    board_type: str
    dim_key: str
    weight: float


class CostBody(BaseModel):
    token_price_per_1k: float = 0.002
    latency_price_per_sec: float = 0.01
    gpu_hour_price: float = 0.0


def _tpl_out(t: TaskTemplate, pack_dataset_id: int | None = None):
    return {
        "id": t.id,
        "code": t.code,
        "name": t.name,
        "category": t.category,
        "scene": t.scene,
        "industry": t.industry,
        "task_type": t.task_type,
        "judge_resource_id": t.judge_resource_id,
        "metric_weights": loads(t.metric_weights_json, {}),
        "default_prompt": t.default_prompt,
        "rubric": t.rubric,
        "description": t.description,
        "status": t.status,
        "pack_dataset_id": pack_dataset_id,
        "pack_name": f"pack:{t.code}",
    }


@router.get("/catalog")
async def task_catalog(_: User = Depends(require_permission("task:list"))):
    return {"scenes": scene_options(), "industries": industry_options()}


@router.get("/templates")
async def list_templates(
    category: str = Query(""),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("task:list")),
):
    q = select(TaskTemplate).where(TaskTemplate.status == "active")
    if category:
        q = q.where(TaskTemplate.category == category)
    rows = (await db.execute(q.order_by(TaskTemplate.category, TaskTemplate.code))).scalars().all()
    names = [f"pack:{t.code}" for t in rows]
    packs = {}
    if names:
        ds_rows = (await db.execute(select(Dataset).where(Dataset.name.in_(names)))).scalars().all()
        packs = {d.name: d.id for d in ds_rows}
    return {"items": [_tpl_out(t, packs.get(f"pack:{t.code}")) for t in rows], "total": len(rows)}


@router.get("/alerts")
async def list_alerts(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("task:view")),
):
    rows = (await db.execute(select(AlertPolicy).order_by(AlertPolicy.id))).scalars().all()
    return {"items": [{"id": p.id, "code": p.code, "event_type": p.event_type, "title": p.title, "enabled": p.enabled} for p in rows]}


@router.put("/alerts/{pid}")
async def patch_alert(
    pid: int,
    body: AlertPatch,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("task:edit")),
):
    p = await db.get(AlertPolicy, pid)
    if not p:
        raise HTTPException(404, "告警策略不存在")
    if body.enabled is not None:
        p.enabled = body.enabled
    if body.title is not None:
        p.title = body.title
    return {"id": p.id, "enabled": p.enabled, "title": p.title}


@router.get("")
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=200),
    status: str = Query(""),
    search: str = Query(""),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("task:list")),
):
    q = select(EvalTask)
    if status:
        q = q.where(EvalTask.status == status)
    if search:
        q = q.where(EvalTask.name.contains(search))
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (await db.execute(q.order_by(EvalTask.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [task_out(t) for t in rows], "total": total or 0}


@router.post("")
async def create_task(
    body: TaskCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("task:create")),
):
    ds = await db.get(Dataset, body.dataset_id)
    if not ds or ds.status == "deleted":
        raise HTTPException(400, "数据集不存在")
    blocked = {"failed", "check_failed"}
    if not body.trial_run and ds.quality_status in blocked:
        raise HTTPException(400, "质量不合格或检测失败的数据不能进入正式评测，请先清洗或勾选仅测试")
    model = await db.get(EvalModel, body.model_id)
    if not model or model.status == "deleted":
        raise HTTPException(400, "被测模型不存在")
    if model.status in {"disabled", "archived"}:
        raise HTTPException(400, "模型已停用或归档")
    if not await _acl_allows(db, model.id, current):
        raise HTTPException(403, "没有该模型的调用权限")
    if body.prompt_id:
        prompt = await db.get(PromptTemplate, body.prompt_id)
        if not prompt:
            raise HTTPException(400, "提示词不存在")
    data = body.model_dump()
    weights = data.pop("metric_weights", None)
    tpl_code = (data.get("template_code") or "").strip()
    if tpl_code:
        tpl = await db.scalar(select(TaskTemplate).where(TaskTemplate.code == tpl_code))
        cat = find_template(tpl_code)
        src = tpl
        if src:
            data["task_type"] = src.task_type
            data["scene"] = src.scene
            data["industry"] = src.industry
            data["judge_resource_id"] = src.judge_resource_id
            if not weights:
                weights = loads(src.metric_weights_json, {})
        elif cat:
            data["task_type"] = cat["task_type"]
            data["scene"] = cat["scene"]
            data["industry"] = cat["industry"]
            data["judge_resource_id"] = cat["judge_resource_id"]
            weights = weights or cat["metric_weights"]
    whitelist = loads(model.scene_white_list or "[]", [])
    if whitelist and data.get("scene") not in whitelist:
        raise HTTPException(400, f"场景 {data.get('scene')} 不在模型白名单中")
    if body.depends_on_id:
        dep = await db.get(EvalTask, body.depends_on_id)
        if not dep:
            raise HTTPException(400, "依赖任务不存在")
        if body.depends_on_id == 0:
            data["depends_on_id"] = None
    data["dataset_version_id"] = body.dataset_version_id or ds.current_version_id
    data["model_version_id"] = body.model_version_id or model.current_version_id
    data["metric_weights_json"] = dumps(weights or {})
    t = EvalTask(**data, creator_id=current.id)
    db.add(t)
    await db.flush()
    await emit_event(db, t.id, "created", {"template_code": tpl_code})
    await log_audit(db, "task", "create", user_id=current.id, username=current.username, target_id=t.id, ip=get_client_ip(request))
    return task_out(t)


@router.get("/{task_id}")
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("task:view")),
):
    t = await db.get(EvalTask, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    return task_out(t)


@router.post("/{task_id}/submit")
async def submit_task(
    task_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("task:edit")),
):
    t = await db.get(EvalTask, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    if t.status not in {"draft", "pending_review"}:
        raise HTTPException(400, "仅草稿可提交审核")
    t.status = "pending_review"
    await emit_event(db, t.id, "pending_review", {})
    await log_audit(db, "task", "submit", user_id=current.id, username=current.username, target_id=t.id, ip=get_client_ip(request))
    return task_out(t)


@router.post("/{task_id}/audit")
async def audit_task(
    task_id: int,
    body: AuditBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("task:audit")),
):
    t = await db.get(EvalTask, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    if t.status != "pending_review":
        raise HTTPException(400, "任务不在待审核")
    if body.approved:
        await enqueue_task(db, t)
        await emit_event(db, t.id, "approved", {"comment": body.comment})
    else:
        t.status = "draft"
        t.error_message = body.comment
        await emit_event(db, t.id, "rejected", {"comment": body.comment})
    await log_audit(db, "task", "audit", user_id=current.id, username=current.username, target_id=t.id, ip=get_client_ip(request), detail=body.comment)
    return task_out(t)


@router.get("/{task_id}/events")
async def task_events(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("task:view")),
):
    rows = (await db.execute(select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.id.desc()).limit(200))).scalars().all()
    return {"items": [{"id": e.id, "event_type": e.event_type, "payload": loads(e.payload_json, {}), "created_at": iso(e.created_at)} for e in rows]}


@router.get("/{task_id}/subtasks")
async def task_subtasks(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("task:view")),
):
    rows = (await db.execute(select(TaskSubtask).where(TaskSubtask.task_id == task_id).order_by(TaskSubtask.shard_no))).scalars().all()
    return {"items": [
        {
            "id": s.id,
            "shard_no": s.shard_no,
            "status": s.status,
            "item_from": s.item_from,
            "item_to": s.item_to,
            "progress": s.progress,
            "error_message": s.error_message,
        }
        for s in rows
    ]}


@router.get("/{task_id}/report")
async def download_task_report(
    task_id: int,
    fmt: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("task:view")),
):
    from app.services.report_archive import report_file
    t = await db.get(EvalTask, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    path = report_file(task_id, fmt)
    if not path.exists() and t.report_path and Path(t.report_path).exists() and fmt == "json":
        path = Path(t.report_path)
    if not path.exists():
        raise HTTPException(404, "报告文件不存在")
    media = {
        "json": "application/json",
        "csv": "text/csv",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "html": "text/html",
        "pdf": "application/pdf",
        "md": "text/markdown",
    }.get(fmt, "application/octet-stream")
    return FileResponse(path, filename=path.name, media_type=media)


@router.get("/{task_id}/lineage")
async def task_lineage(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("task:view")),
):
    row = await db.scalar(select(EvalLineage).where(EvalLineage.task_id == task_id))
    if not row:
        return {"task_id": task_id, "found": False}
    return {
        "found": True,
        "task_id": row.task_id,
        "dataset_id": row.dataset_id,
        "dataset_version_id": row.dataset_version_id,
        "checksum": row.checksum,
        "snapshot_id": row.snapshot_id,
        "model_id": row.model_id,
        "model_version_id": row.model_version_id,
        "prompt_id": row.prompt_id,
        "prompt_version_id": row.prompt_version_id,
        "judge_resource_id": row.judge_resource_id,
        "tool_version": row.tool_version,
        "trace_id": row.trace_id,
        "parent_trace_id": row.parent_trace_id,
        "tenant_id": row.tenant_id,
        "channel_type": row.channel_type,
        "created_at": iso(row.created_at),
    }


@router.get("/{task_id}/results")
async def task_results(
    task_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("task:view")),
):
    t = await db.get(EvalTask, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    q = select(EvalResult).where(EvalResult.task_id == task_id)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (await db.execute(q.order_by(EvalResult.item_no).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {
        "items": [
            {
                "id": r.id,
                "item_no": r.item_no,
                "input_content": r.input_content,
                "model_output": r.model_output,
                "reference_answer": r.reference_answer,
                "score": r.score,
                "passed": r.passed,
                "metrics": loads(r.metrics_json, {}),
                "error_message": r.error_message,
                "latency_ms": r.latency_ms,
            }
            for r in rows
        ],
        "total": total or 0,
    }


@router.post("/{task_id}/run")
async def run_task(
    task_id: int,
    background: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("task:run")),
):
    t = await db.get(EvalTask, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    if t.status == "running":
        raise HTTPException(400, "任务正在执行")
    await enqueue_task(db, t)
    await db.commit()
    background.add_task(dispatch_queue, t.id)
    await log_audit(db, "task", "run", user_id=current.id, username=current.username, target_id=t.id, ip=get_client_ip(request))
    return task_out(t)


@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("task:run")),
):
    t = await db.get(EvalTask, task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    if t.status in {"success", "failed", "cancelled"}:
        raise HTTPException(400, "任务已结束")
    t.status = "cancelled"
    t.finished_at = datetime.utcnow()
    await emit_event(db, t.id, "cancelled", {})
    return task_out(t)


@leaderboard_router.get("/weights")
async def list_weights(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("leaderboard:view")),
):
    rows = (await db.execute(select(LeaderboardWeight).order_by(LeaderboardWeight.board_type, LeaderboardWeight.dim_key))).scalars().all()
    return {"items": [{"id": r.id, "board_type": r.board_type, "dim_key": r.dim_key, "weight": r.weight} for r in rows]}


@leaderboard_router.put("/weights")
async def put_weights(
    items: list[WeightItem],
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("leaderboard:edit")),
):
    for it in items:
        row = await db.scalar(select(LeaderboardWeight).where(LeaderboardWeight.board_type == it.board_type, LeaderboardWeight.dim_key == it.dim_key))
        if row:
            row.weight = it.weight
        else:
            db.add(LeaderboardWeight(board_type=it.board_type, dim_key=it.dim_key, weight=it.weight))
    return {"ok": True, "total": len(items)}


@leaderboard_router.get("/costs")
async def list_costs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("leaderboard:view")),
):
    models = (await db.execute(select(EvalModel).where(EvalModel.status != "deleted"))).scalars().all()
    costs = {c.model_id: c for c in (await db.execute(select(ModelCost))).scalars().all()}
    items = []
    for m in models:
        c = costs.get(m.id)
        items.append({
            "model_id": m.id,
            "model_name": m.name,
            "token_price_per_1k": c.token_price_per_1k if c else 0.002,
            "latency_price_per_sec": c.latency_price_per_sec if c else 0.01,
            "gpu_hour_price": c.gpu_hour_price if c else 0.0,
        })
    return {"items": items}


@leaderboard_router.put("/costs/{model_id}")
async def put_cost(
    model_id: int,
    body: CostBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("leaderboard:edit")),
):
    row = await db.scalar(select(ModelCost).where(ModelCost.model_id == model_id))
    if not row:
        row = ModelCost(model_id=model_id)
        db.add(row)
        await db.flush()
    row.token_price_per_1k = body.token_price_per_1k
    row.latency_price_per_sec = body.latency_price_per_sec
    row.gpu_hour_price = body.gpu_hour_price
    return {"model_id": model_id, "ok": True}


@leaderboard_router.get("/radar")
async def leaderboard_radar(
    model_ids: str = Query(""),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("leaderboard:view")),
):
    ids = [int(x) for x in model_ids.split(",") if x.strip().isdigit()][:5]
    if len(ids) < 2:
        raise HTTPException(400, "雷达对比请选择 2–5 个模型")
    return await radar_payload(db, ids)


@leaderboard_router.get("/trend")
async def leaderboard_trend(
    board: str = Query("overall"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("leaderboard:view")),
):
    from app.models import LeaderboardSnapshot
    rows = (await db.execute(
        select(LeaderboardSnapshot).where(LeaderboardSnapshot.board_type == board).order_by(LeaderboardSnapshot.id.desc()).limit(20)
    )).scalars().all()
    points = []
    for snap in reversed(list(rows)):
        payload = loads(snap.payload_json, {})
        top = (payload.get("items") or [{}])[0]
        points.append({"at": iso(snap.created_at), "top_model": top.get("model_name"), "top_score": top.get("norm_score") or top.get("avg_score")})
    return {"board": board, "points": points}


@leaderboard_router.post("/refresh")
async def refresh_leaderboard(
    board: str = Query("overall"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("leaderboard:edit")),
):
    payload = await compute_board(db, board)
    snap = await save_snapshot(db, board, payload)
    payload["snapshot_id"] = snap.id
    payload["stale"] = False
    return payload


@leaderboard_router.get("/export")
async def export_leaderboard(
    board: str = Query("overall"),
    industry: str = Query(""),
    scene: str = Query(""),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("leaderboard:view")),
):
    payload = await compute_board(db, board, industry, scene)
    lines = ["rank,model_name,industry,scene,avg_score,pass_rate,norm_score,task_id"]
    for row in payload.get("items") or []:
        lines.append(
            f"{row.get('rank')},{row.get('model_name')},{row.get('industry')},{row.get('scene')},"
            f"{row.get('avg_score')},{row.get('pass_rate')},{row.get('norm_score')},{row.get('task_id')}"
        )
    data = ("\n".join(lines) + "\n").encode("utf-8-sig")
    return StreamingResponse(iter([data]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=leaderboard-{board}.csv"})


@leaderboard_router.get("")
async def leaderboard(
    board: str = Query("overall"),
    industry: str = Query(""),
    scene: str = Query(""),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("leaderboard:view")),
):
    allowed = {"overall", "ability", "special", "value"}
    if board not in allowed:
        raise HTTPException(400, "未知榜单类型")
    try:
        payload = await compute_board(db, board, industry, scene)
        payload["stale"] = False
        payload["message"] = ""
        return payload
    except Exception:
        snap = await last_snapshot(db, board)
        if snap:
            data = loads(snap.payload_json, {})
            data["stale"] = True
            data["message"] = "数据更新异常，展示上次快照"
            return data
        raise HTTPException(500, "榜单计算失败且无可用快照")


def _service_out(s: EvalServiceRequest):
    return {
        "id": s.id,
        "title": s.title,
        "industry": s.industry,
        "requirement": s.requirement,
        "status": s.status,
        "task_id": s.task_id,
        "report_summary": s.report_summary,
        "quote_mode": getattr(s, "quote_mode", "auto") or "auto",
        "quote_amount": getattr(s, "quote_amount", 0) or 0,
        "quote_detail": loads(getattr(s, "quote_detail_json", None) or "{}", {}),
        "workspace_id": getattr(s, "workspace_id", None),
        "dataset_id": getattr(s, "dataset_id", None),
        "model_id": getattr(s, "model_id", None),
        "scene": getattr(s, "scene", "") or "",
        "gray_version": getattr(s, "gray_version", "") or "",
        "production_version": getattr(s, "production_version", "") or "v1",
        "shadow": loads(getattr(s, "shadow_json", None) or "{}", {}),
        "report_path": getattr(s, "report_path", "") or "",
        "created_at": iso(s.created_at),
    }


def _auto_quote(industry: str, requirement: str) -> dict:
    base = 800.0
    extra = min(len(requirement or "") * 0.5, 400)
    factor = 1.2 if industry in {"finance", "medical", "legal", "金融", "医疗", "司法"} else 1.0
    amount = round((base + extra) * factor, 2)
    return {"mode": "auto", "amount": amount, "base": base, "extra": extra, "factor": factor}


async def _quota_guard(db: AsyncSession, workspace_id: int | None):
    if not workspace_id:
        return
    ws = await db.get(EvalWorkspace, workspace_id)
    if not ws:
        raise HTTPException(400, "工作空间不存在")
    if ws.quota_tokens and ws.used_tokens >= ws.quota_tokens:
        raise HTTPException(400, "工作空间 Token 配额已用尽")
    if ws.quota_calls and ws.used_calls >= ws.quota_calls:
        raise HTTPException(400, "工作空间调用次数配额已用尽")
    tok_ratio = ws.used_tokens / ws.quota_tokens if ws.quota_tokens else 0
    if tok_ratio >= 0.8:
        from app.models import Notification
        db.add(Notification(user_id=None, title="配额预警", message=f"工作空间 {ws.name} Token 使用已达 {tok_ratio:.0%}", type="warning"))


@service_router.get("/workspaces")
async def list_workspaces(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("service:list")),
):
    rows = (await db.execute(select(EvalWorkspace).order_by(EvalWorkspace.id))).scalars().all()
    return {"items": [
        {
            "id": w.id, "name": w.name, "code": w.code,
            "quota_tokens": w.quota_tokens, "used_tokens": w.used_tokens,
            "quota_calls": w.quota_calls, "used_calls": w.used_calls,
        }
        for w in rows
    ]}


@service_router.post("/workspaces")
async def create_workspace(
    body: WorkspaceCreate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("service:edit")),
):
    if await db.scalar(select(EvalWorkspace.id).where(EvalWorkspace.code == body.code)):
        raise HTTPException(400, "工作空间编码已存在")
    w = EvalWorkspace(**body.model_dump(), owner_id=current.id)
    db.add(w)
    await db.flush()
    return {"id": w.id, "code": w.code}


@service_router.get("/kanban")
async def service_kanban(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("service:list")),
):
    rows = (await db.execute(select(EvalServiceRequest))).scalars().all()
    buckets = {"submitted": 0, "reviewing": 0, "approved": 0, "running": 0, "delivered": 0, "rejected": 0, "configuring": 0}
    for s in rows:
        buckets[s.status] = buckets.get(s.status, 0) + 1
    return {"buckets": buckets, "total": len(rows)}


@service_router.get("")
async def list_services(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("service:list")),
):
    q = select(EvalServiceRequest)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (await db.execute(q.order_by(EvalServiceRequest.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [_service_out(s) for s in rows], "total": total or 0}


@service_router.post("")
async def create_service(
    body: ServiceCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("service:create")),
):
    await _quota_guard(db, body.workspace_id)
    quote = _auto_quote(body.industry, body.requirement) if body.quote_mode != "expert" else {"mode": "expert", "amount": 0}
    data = body.model_dump()
    s = EvalServiceRequest(
        **data,
        quote_amount=quote["amount"],
        quote_detail_json=dumps(quote),
        creator_id=current.id,
    )
    db.add(s)
    await db.flush()
    await log_audit(db, "service", "create", user_id=current.id, username=current.username, target_id=s.id, ip=get_client_ip(request))
    return _service_out(s)


@service_router.post("/{sid}/quote")
async def quote_service(
    sid: int,
    body: QuoteBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("service:edit")),
):
    s = await db.get(EvalServiceRequest, sid)
    if not s:
        raise HTTPException(404, "评测服务单不存在")
    if body.mode == "expert":
        if body.amount is None:
            raise HTTPException(400, "专家报价需要金额")
        quote = {"mode": "expert", "amount": float(body.amount)}
    else:
        quote = _auto_quote(s.industry, s.requirement)
    s.quote_mode = quote["mode"]
    s.quote_amount = quote["amount"]
    s.quote_detail_json = dumps(quote)
    s.status = "reviewing"
    return _service_out(s)


@service_router.post("/{sid}/confirm")
async def confirm_service(
    sid: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("service:edit")),
):
    s = await db.get(EvalServiceRequest, sid)
    if not s:
        raise HTTPException(404, "评测服务单不存在")
    await _quota_guard(db, s.workspace_id)
    s.status = "approved"
    return _service_out(s)


class ShadowBody(BaseModel):
    gray_version: str = "v-next"
    production: dict = {}
    candidate: dict = {}


@service_router.post("/{sid}/shadow")
async def shadow_service(
    sid: int,
    body: ShadowBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("service:edit")),
):
    s = await db.get(EvalServiceRequest, sid)
    if not s:
        raise HTTPException(404, "评测服务单不存在")
    prod = body.production or {}
    cand = body.candidate or {}
    ps, cs = float(prod.get("score") or 0), float(cand.get("score") or 0)
    pl, cl = float(prod.get("latency_ms") or 0), float(cand.get("latency_ms") or 0)
    diff = abs(cs - ps) / ps if ps else (cs if cs else 0)
    lat_diff = abs(cl - pl) / pl if pl else 0
    stable = diff <= 0.05 and lat_diff <= 0.2
    s.gray_version = body.gray_version
    s.shadow_json = dumps({
        "production": prod,
        "candidate": cand,
        "score_diff_rate": round(diff, 4),
        "latency_diff_rate": round(lat_diff, 4),
        "stable": stable,
        "returned": "production",
    })
    return _service_out(s)


@service_router.post("/{sid}/promote")
async def promote_service(
    sid: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("service:edit")),
):
    s = await db.get(EvalServiceRequest, sid)
    if not s:
        raise HTTPException(404, "评测服务单不存在")
    shadow = loads(s.shadow_json, {})
    if shadow and not shadow.get("stable", True):
        raise HTTPException(400, "影子测试未达稳定性阈值，禁止转正")
    if s.gray_version:
        s.production_version = s.gray_version
    return _service_out(s)


@service_router.post("/{sid}/rollback")
async def rollback_service(
    sid: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("service:edit")),
):
    s = await db.get(EvalServiceRequest, sid)
    if not s:
        raise HTTPException(404, "评测服务单不存在")
    s.gray_version = ""
    return _service_out(s)


@service_router.get("/{sid}/report")
async def service_report(
    sid: int,
    fmt: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("service:view")),
):
    from app.services.report_archive import report_file
    s = await db.get(EvalServiceRequest, sid)
    if not s:
        raise HTTPException(404, "评测服务单不存在")
    if s.task_id:
        path = report_file(s.task_id, fmt)
        if path.exists():
            return FileResponse(path, filename=path.name)
    if fmt == "json" and s.report_path and Path(s.report_path).exists():
        return FileResponse(s.report_path, filename=f"service-{sid}.json", media_type="application/json")
    raise HTTPException(404, "报告文件不存在")


@service_router.post("/{sid}/status")
async def update_service_status(
    sid: int,
    status: str = Query(...),
    report_summary: str = Query(""),
    gray_version: str = Query(""),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("service:edit")),
):
    s = await db.get(EvalServiceRequest, sid)
    if not s:
        raise HTTPException(404, "评测服务单不存在")
    allowed = {"submitted", "reviewing", "approved", "configuring", "running", "delivered", "rejected"}
    if status not in allowed:
        raise HTTPException(400, "非法状态")
    if status in {"approved", "running", "configuring"}:
        await _quota_guard(db, s.workspace_id)
    s.status = status
    if gray_version:
        s.gray_version = gray_version
    if report_summary:
        s.report_summary = report_summary
    if status == "delivered" and s.task_id:
        t = await db.get(EvalTask, s.task_id)
        if t:
            s.report_summary = s.report_summary or t.report_summary
            s.report_path = t.report_path or s.report_path
            if s.workspace_id:
                ws = await db.get(EvalWorkspace, s.workspace_id)
                if ws:
                    ws.used_tokens += int(getattr(t, "tokens_used", 0) or 0)
                    ws.used_calls += 1
    return _service_out(s)
