"""Safety workbench APIs; execution remains in /tasks and TaskService."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_actor, require_permission
from app.database import get_db
from app.models import Dataset, DatasetItem, EvalResult, EvalTask, SafetyRecord, User
from app.services.object_policy import apply_object_scope, get_visible_or_404
from app.services.safety_protocol import CATEGORIES, DIMENSIONS, VERSION, evidence_hash, validate_sample, sample_of
from app.services.safety_benchmark import benchmark_template
from app.utils.jsonutil import dumps, loads, iso

router = APIRouter()


@router.get("/workbench")
async def workbench(db: AsyncSession = Depends(get_db), actor=Depends(require_actor("safety:view")), _: User = Depends(require_permission("safety:view"))):
    tasks = (await db.scalars(apply_object_scope(select(EvalTask).where(EvalTask.task_type == "security"), EvalTask, actor).order_by(EvalTask.id.desc()).limit(100))).all()
    datasets = (await db.scalars(apply_object_scope(select(Dataset).where(Dataset.status != "deleted"), Dataset, actor))).all()
    items = (await db.scalars(select(DatasetItem).where(DatasetItem.dataset_id.in_([d.id for d in datasets]), DatasetItem.status == "active"))).all() if datasets else []
    safety_versions = {}
    for item in items:
        sample = loads(item.extended_content, {}).get("safety")
        dimension = sample.get("dimension") if isinstance(sample, dict) else None
        if dimension in DIMENSIONS:
            safety_versions.setdefault(item.version_id, set()).add(dimension)
    return {"protocol": VERSION, "categories": CATEGORIES, "dimensions": DIMENSIONS,
            "tasks": [{"id": t.id, "name": t.name, "status": t.status, "model_id": t.model_id, "progress": t.progress, "configured": bool(loads(t.safety_config_json, {}))} for t in tasks],
            "datasets": [{"id": d.id, "name": d.name, "status": d.status, "version_id": d.current_version_id, "dimensions": sorted(safety_versions[d.current_version_id])} for d in datasets if d.current_version_id in safety_versions]}


@router.get("/benchmark-template")
async def template(template_id: str = "comprehensive", _: User = Depends(require_permission("safety:view"))):
    try:
        return benchmark_template(template_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


class BenchmarkValidate(BaseModel):
    samples: list[dict] = Field(min_length=1, max_length=2000)


@router.post("/benchmarks/validate")
async def validate_benchmark(body: BenchmarkValidate, _: User = Depends(require_permission("safety:create"))):
    counts = {}
    ids = set()
    for number, row in enumerate(body.samples, 1):
        try:
            if not isinstance(row.get("input"), str) or not row["input"].strip():
                raise ValueError("问题不能为空")
            sample = row.get("safety")
            dimension = validate_sample(sample)
            sid = sample.get("id")
            if not isinstance(sid, str) or not sid.strip() or sid in ids:
                raise ValueError("样本编号必须非空且唯一")
            ids.add(sid)
            counts[dimension] = counts.get(dimension, 0) + 1
        except ValueError as exc:
            raise HTTPException(400, f"第{number}题：{exc}") from exc
    return {"valid": True, "validation_scope": "schema_only", "sample_count":len(body.samples), "dimensions":counts}


@router.get("/benchmarks/{dataset_id}")
async def get_benchmark(dataset_id: int, db: AsyncSession = Depends(get_db), actor=Depends(require_actor("safety:view")),
                        _: User = Depends(require_permission("dataset:view"))):
    dataset = await get_visible_or_404(db, Dataset, dataset_id, actor)
    rows = (await db.scalars(select(DatasetItem).where(DatasetItem.version_id == dataset.current_version_id, DatasetItem.status == "active").order_by(DatasetItem.item_no))).all()
    if not rows or any(not isinstance(sample_of(row), dict) or sample_of(row).get("dimension") not in DIMENSIONS for row in rows):
        raise HTTPException(400, "请选择包含有效安全题目的基准")
    return {"id":dataset.id, "name":dataset.name, "source":dataset.description, "version_id":dataset.current_version_id,
            "samples":[{**loads(r.extended_content, {}), "input":r.input_content, "answer":r.reference_answer,
                        "data_label":r.data_label, "difficulty":r.difficulty_level, "safety":sample_of(r)} for r in rows]}


async def visible_task(db, task_id, actor):
    task = await get_visible_or_404(db, EvalTask, task_id, actor)
    if task.task_type != "security" or not loads(task.safety_config_json, {}):
        raise HTTPException(400, "该任务未使用V2安全协议，不能推断专项结论")
    return task


from app.services.safety_assessments import assessment_payload


@router.get("/assessments/{task_id}")
async def assessment(task_id: int, db: AsyncSession = Depends(get_db), actor=Depends(require_actor("safety:view")), _: User = Depends(require_permission("safety:view"))):
    return await assessment_payload(db, await visible_task(db, task_id, actor))


class ReviewBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    result_id: int
    evidence_hash: str
    label: str = Field(pattern="^(approved|rejected|needs_evidence)$")
    note: str = Field(min_length=1, max_length=5000)


@router.post("/assessments/{task_id}/reviews")
async def review(task_id: int, body: ReviewBody, db: AsyncSession = Depends(get_db), actor=Depends(require_actor("safety:review")), _: User = Depends(require_permission("safety:review"))):
    task = await visible_task(db, task_id, actor)
    if task.status not in {"success", "failed", "partial_failed", "cancelled"}:
        raise HTTPException(409, "请等待任务终态再复核")
    result = await db.get(EvalResult, body.result_id)
    if not result or result.task_id != task.id:
        raise HTTPException(404, "结果不属于该任务")
    if body.evidence_hash != evidence_hash(result):
        raise HTTPException(409, "结果证据已变化，请刷新后复核")
    row = SafetyRecord(kind="review", task_id=task.id, result_id=result.id, tenant_id=actor.tenant_id,
                       creator_id=actor.user_id, payload_json=dumps(body.model_dump(exclude={"result_id"})))
    db.add(row)
    await db.flush()
    return {"id": row.id, "label": body.label, "original_score_preserved": True}


class GoldRow(BaseModel):
    result_id: int
    evidence_hash: str
    score: float = Field(ge=0, le=1, allow_inf_nan=False)


class CalibrationBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    samples: list[GoldRow] = Field(min_length=2, max_length=500)
    note: str = Field(min_length=1, max_length=5000)


@router.post("/assessments/{task_id}/calibrations")
async def calibrate(task_id: int, body: CalibrationBody, db: AsyncSession = Depends(get_db), actor=Depends(require_actor("safety:edit")), _: User = Depends(require_permission("safety:edit"))):
    task = await visible_task(db, task_id, actor)
    if len({g.result_id for g in body.samples}) != len(body.samples):
        raise HTTPException(400, "金标样本不得重复")
    details = []
    for gold in body.samples:
        result = await db.get(EvalResult, gold.result_id)
        if not result or result.task_id != task.id or result.simulation or result.score_status != "scored" or result.execution_status != "ok":
            raise HTTPException(400, "校准只接受本任务的真实已评分结果")
        if evidence_hash(result) != gold.evidence_hash:
            raise HTTPException(409, "校准证据已变化")
        details.append({**gold.model_dump(), "measured_score": result.score, "agree": (gold.score >= .5) == result.passed, "absolute_error": abs(gold.score-result.score)})
    agreement = sum(d["agree"] for d in details) / len(details)
    payload = {"protocol": VERSION, "config": loads(task.safety_config_json, {}), "agreement": agreement,
               "mean_absolute_error": sum(d["absolute_error"] for d in details)/len(details),
               "sample_count": len(details), "ok": agreement >= .9, "details": details, "note": body.note,
               "scope": "仅对所选人工金标样本的一致率，不代表全基准已校准"}
    record = SafetyRecord(kind="calibration", task_id=task.id, tenant_id=actor.tenant_id, creator_id=actor.user_id, payload_json=dumps(payload))
    db.add(record)
    await db.flush()
    return {"id": record.id, **payload}


@router.get("/assessments/{task_id}/records")
async def records(task_id: int, db: AsyncSession = Depends(get_db), actor=Depends(require_actor("safety:view")), _: User = Depends(require_permission("safety:view"))):
    await visible_task(db, task_id, actor)
    rows = (await db.scalars(select(SafetyRecord).where(SafetyRecord.task_id == task_id).order_by(SafetyRecord.id.desc()))).all()
    names = dict((await db.execute(select(User.id, User.username).where(User.id.in_({r.creator_id for r in rows})))).all()) if rows else {}
    return {"items": [{"id": r.id, "kind": r.kind, "reviewer_name": names.get(r.creator_id, "用户已注销"), "result_id": r.result_id, "reviewer_id": r.creator_id, "created_at": iso(r.created_at), "payload": loads(r.payload_json, {})} for r in rows]}
