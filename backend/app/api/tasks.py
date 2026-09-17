"""评测任务、榜单、评测服务。"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.database import get_db
from app.models import Dataset, EvalModel, EvalResult, EvalServiceRequest, EvalTask, PromptTemplate, User
from app.services.audit import get_client_ip, log_audit
from app.services.serializers import task_out
from app.services.task_runner import run_eval_task
from app.utils.jsonutil import iso, loads

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


class ServiceCreate(BaseModel):
    title: str
    industry: str = "general"
    requirement: str = ""
    task_id: int | None = None


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
    if not ds:
        raise HTTPException(400, "数据集不存在")
    model = await db.get(EvalModel, body.model_id)
    if not model:
        raise HTTPException(400, "被测模型不存在")
    if body.prompt_id:
        prompt = await db.get(PromptTemplate, body.prompt_id)
        if not prompt:
            raise HTTPException(400, "提示词不存在")
    data = body.model_dump()
    data["dataset_version_id"] = body.dataset_version_id or ds.current_version_id
    t = EvalTask(**data, creator_id=current.id)
    db.add(t)
    await db.flush()
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
    t.status = "queued"
    t.progress = 0
    t.error_message = ""
    await db.flush()
    background.add_task(run_eval_task, task_id)
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
    if t.status in {"success", "failed"}:
        raise HTTPException(400, "任务已结束")
    t.status = "cancelled"
    return task_out(t)


@leaderboard_router.get("")
async def leaderboard(
    industry: str = Query(""),
    scene: str = Query(""),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("leaderboard:view")),
):
    q = select(EvalTask).where(EvalTask.status == "success")
    if industry:
        q = q.where(EvalTask.industry == industry)
    if scene:
        q = q.where(EvalTask.scene == scene)
    tasks = (await db.execute(q.order_by(EvalTask.finished_at.desc()))).scalars().all()
    best: dict[int, EvalTask] = {}
    for t in tasks:
        prev = best.get(t.model_id)
        if not prev or (t.avg_score, t.pass_rate) > (prev.avg_score, prev.pass_rate):
            best[t.model_id] = t
    ranked = sorted(best.values(), key=lambda x: (x.avg_score, x.pass_rate), reverse=True)
    items = []
    for i, t in enumerate(ranked, start=1):
        model = await db.get(EvalModel, t.model_id)
        items.append({
            "rank": i,
            "model_id": t.model_id,
            "model_name": model.name if model else str(t.model_id),
            "industry": t.industry,
            "scene": t.scene,
            "avg_score": t.avg_score,
            "pass_rate": t.pass_rate,
            "task_id": t.id,
            "task_name": t.name,
            "updated_at": iso(t.finished_at),
        })
    return {"items": items, "total": len(items)}


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
    return {
        "items": [
            {
                "id": s.id,
                "title": s.title,
                "industry": s.industry,
                "requirement": s.requirement,
                "status": s.status,
                "task_id": s.task_id,
                "report_summary": s.report_summary,
                "created_at": iso(s.created_at),
            }
            for s in rows
        ],
        "total": total or 0,
    }


@service_router.post("")
async def create_service(
    body: ServiceCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("service:create")),
):
    s = EvalServiceRequest(**body.model_dump(), creator_id=current.id)
    db.add(s)
    await db.flush()
    await log_audit(db, "service", "create", user_id=current.id, username=current.username, target_id=s.id, ip=get_client_ip(request))
    return {"id": s.id, "title": s.title, "status": s.status}


@service_router.post("/{sid}/status")
async def update_service_status(
    sid: int,
    status: str = Query(...),
    report_summary: str = Query(""),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("service:edit")),
):
    s = await db.get(EvalServiceRequest, sid)
    if not s:
        raise HTTPException(404, "评测服务单不存在")
    allowed = {"submitted", "reviewing", "approved", "running", "delivered", "rejected"}
    if status not in allowed:
        raise HTTPException(400, "非法状态")
    s.status = status
    if report_summary:
        s.report_summary = report_summary
    if status == "delivered" and s.task_id:
        t = await db.get(EvalTask, s.task_id)
        if t:
            s.report_summary = s.report_summary or t.report_summary
    return {"id": s.id, "status": s.status, "report_summary": s.report_summary}
