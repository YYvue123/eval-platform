"""数据质量测试。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.database import get_db
from app.models import Dataset, DatasetItem, DatasetVersion, QualityReport, User
from app.services.quality_checker import check_items
from app.utils.jsonutil import dumps, iso, loads

router = APIRouter()


@router.get("")
async def list_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=200),
    dataset_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("quality:list")),
):
    q = select(QualityReport)
    if dataset_id:
        q = q.where(QualityReport.dataset_id == dataset_id)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (await db.execute(q.order_by(QualityReport.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {
        "items": [
            {
                "id": r.id,
                "dataset_id": r.dataset_id,
                "version_id": r.version_id,
                "status": r.status,
                "score": r.score,
                "report": loads(r.report_json, {}),
                "created_at": iso(r.created_at),
            }
            for r in rows
        ],
        "total": total or 0,
    }


@router.post("/run")
async def run_quality(
    dataset_id: int = Query(...),
    version_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("quality:run")),
):
    d = await db.get(Dataset, dataset_id)
    if not d:
        raise HTTPException(404, "数据集不存在")
    vid = version_id or d.current_version_id
    if not vid:
        raise HTTPException(400, "请先导入数据")
    items = (await db.execute(select(DatasetItem).where(DatasetItem.version_id == vid).order_by(DatasetItem.item_no))).scalars().all()
    payload = [{"input_content": x.input_content, "reference_answer": x.reference_answer} for x in items]
    result = check_items(payload)
    flags = result.pop("flags")
    for item, flag in zip(items, flags):
        item.quality_flag = flag
    ver = await db.get(DatasetVersion, vid)
    if ver:
        ver.quality_score = result["score"]
        ver.quality_status = result["status"]
    d.quality_status = result["status"]
    report = QualityReport(
        dataset_id=d.id,
        version_id=vid,
        status=result["status"],
        score=result["score"],
        report_json=dumps(result),
        creator_id=current.id,
    )
    db.add(report)
    await db.flush()
    return {"id": report.id, "score": result["score"], "status": result["status"], "report": result}
