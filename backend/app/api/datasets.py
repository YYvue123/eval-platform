"""评测数据集管理。"""
import csv
import hashlib
import io
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permission
from app.config import settings
from app.database import get_db
from app.models import Dataset, DatasetItem, DatasetLog, DatasetVersion, DataTag, User
from app.services.audit import get_client_ip, log_audit
from app.services.dataset_parser import parse_bytes
from app.services.quality_checker import check_items
from app.services.serializers import dataset_brief, item_out
from app.utils.jsonutil import dumps, loads

router = APIRouter()


class DatasetCreate(BaseModel):
    name: str
    dataset_type: str = "qa"
    task_type: str = "qa"
    domain_type: str = "general"
    data_source: str = "upload"
    description: str = ""
    tags: list[str] = []
    security_level: str = "internal"


class DatasetUpdate(BaseModel):
    name: str | None = None
    dataset_type: str | None = None
    task_type: str | None = None
    domain_type: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    status: str | None = None
    security_level: str | None = None


class TagCreate(BaseModel):
    name: str
    tag_type: str = "custom"
    parent_id: int | None = None
    description: str = ""


async def _creator_map(db: AsyncSession, ids: list[int]) -> dict[int, str]:
    ids = [i for i in ids if i]
    if not ids:
        return {}
    rows = (await db.execute(select(User.id, User.username).where(User.id.in_(ids)))).all()
    return {r[0]: r[1] for r in rows}


async def _add_log(db, dataset_id, version_id, op, desc, user: User, result="success", err=""):
    db.add(DatasetLog(
        dataset_id=dataset_id,
        version_id=version_id,
        operation_type=op,
        operation_desc=desc,
        operator=user.username,
        operation_result=result,
        error_message=err,
    ))


@router.get("")
async def list_datasets(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=200),
    search: str = Query(""),
    status: str = Query(""),
    domain_type: str = Query(""),
    task_type: str = Query(""),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("dataset:list")),
):
    q = select(Dataset)
    if search:
        q = q.where(or_(Dataset.name.contains(search), Dataset.description.contains(search)))
    if status:
        q = q.where(Dataset.status == status)
    if domain_type:
        q = q.where(Dataset.domain_type == domain_type)
    if task_type:
        q = q.where(Dataset.task_type == task_type)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (await db.execute(q.order_by(Dataset.updated_at.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    names = await _creator_map(db, [d.creator_id for d in rows])
    return {"items": [dataset_brief(d, names.get(d.creator_id or 0, "")) for d in rows], "total": total or 0}


@router.post("")
async def create_dataset(
    body: DatasetCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("dataset:create")),
):
    exists = await db.scalar(select(Dataset.id).where(Dataset.name == body.name))
    if exists:
        raise HTTPException(400, "数据集名称已存在")
    d = Dataset(
        name=body.name.strip(),
        dataset_type=body.dataset_type,
        task_type=body.task_type,
        domain_type=body.domain_type,
        data_source=body.data_source,
        description=body.description,
        tags=dumps(body.tags),
        security_level=body.security_level,
        creator_id=current.id,
    )
    db.add(d)
    await db.flush()
    await _add_log(db, d.id, None, "create", "创建数据集", current)
    await log_audit(db, "dataset", "create", user_id=current.id, username=current.username, target_id=d.id, ip=get_client_ip(request))
    return dataset_brief(d, current.username)


@router.get("/tags")
async def list_tags(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("dataset:list")),
):
    rows = (await db.execute(select(DataTag).order_by(DataTag.id.desc()))).scalars().all()
    return [{"id": t.id, "name": t.name, "tag_type": t.tag_type, "parent_id": t.parent_id, "description": t.description, "status": t.status} for t in rows]


@router.post("/tags")
async def create_tag(
    body: TagCreate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("dataset:edit")),
):
    t = DataTag(name=body.name, tag_type=body.tag_type, parent_id=body.parent_id, description=body.description, creator_id=current.id)
    db.add(t)
    await db.flush()
    return {"id": t.id, "name": t.name, "tag_type": t.tag_type}


@router.get("/{dataset_id}")
async def get_dataset(
    dataset_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("dataset:view")),
):
    d = await db.get(Dataset, dataset_id)
    if not d:
        raise HTTPException(404, "数据集不存在")
    names = await _creator_map(db, [d.creator_id or 0])
    versions = (await db.execute(select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id).order_by(DatasetVersion.id.desc()))).scalars().all()
    logs = (await db.execute(select(DatasetLog).where(DatasetLog.dataset_id == dataset_id).order_by(DatasetLog.id.desc()).limit(50))).scalars().all()
    return {
        **dataset_brief(d, names.get(d.creator_id or 0, "")),
        "versions": [
            {
                "id": v.id,
                "version_code": v.version_code,
                "version_desc": v.version_desc,
                "data_count": v.data_count,
                "checksum": v.checksum,
                "quality_score": v.quality_score,
                "quality_status": v.quality_status,
                "status": v.status,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ],
        "logs": [
            {
                "id": lg.id,
                "operation_type": lg.operation_type,
                "operation_desc": lg.operation_desc,
                "operator": lg.operator,
                "operation_result": lg.operation_result,
                "created_at": lg.created_at.isoformat() if lg.created_at else None,
            }
            for lg in logs
        ],
    }


@router.put("/{dataset_id}")
async def update_dataset(
    dataset_id: int,
    body: DatasetUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("dataset:edit")),
):
    d = await db.get(Dataset, dataset_id)
    if not d:
        raise HTTPException(404, "数据集不存在")
    data = body.model_dump(exclude_unset=True)
    if "tags" in data:
        d.tags = dumps(data.pop("tags") or [])
    for k, v in data.items():
        setattr(d, k, v)
    await _add_log(db, d.id, None, "update", "更新数据集信息", current)
    await log_audit(db, "dataset", "update", user_id=current.id, username=current.username, target_id=d.id, ip=get_client_ip(request))
    return dataset_brief(d)


@router.delete("/{dataset_id}")
async def delete_dataset(
    dataset_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("dataset:delete")),
):
    d = await db.get(Dataset, dataset_id)
    if not d:
        raise HTTPException(404, "数据集不存在")
    if d.status == "published":
        raise HTTPException(400, "已发布数据集请先停用或归档后再删除")
    await db.execute(DatasetItem.__table__.delete().where(DatasetItem.dataset_id == dataset_id))
    await db.execute(DatasetVersion.__table__.delete().where(DatasetVersion.dataset_id == dataset_id))
    await db.delete(d)
    await log_audit(db, "dataset", "delete", user_id=current.id, username=current.username, target_id=dataset_id, ip=get_client_ip(request))
    return {"ok": True}


@router.post("/{dataset_id}/import")
async def import_dataset(
    dataset_id: int,
    request: Request,
    file: UploadFile = File(...),
    version_desc: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("dataset:edit")),
):
    d = await db.get(Dataset, dataset_id)
    if not d:
        raise HTTPException(404, "数据集不存在")
    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(400, "文件超过 50MB 限制")
    try:
        rows = parse_bytes(file.filename or "data.json", raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not rows:
        raise HTTPException(400, "文件中没有可导入的数据")
    dest_dir = Path(settings.UPLOAD_DIR) / "datasets" / str(d.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "data.bin").suffix or ".bin"
    checksum = hashlib.sha256(raw).hexdigest()
    stored = dest_dir / f"{checksum[:12]}{suffix}"
    stored.write_bytes(raw)

    count = (await db.scalar(select(func.count()).select_from(DatasetVersion).where(DatasetVersion.dataset_id == d.id))) or 0
    version_code = f"V{count + 1}.0"
    ver = DatasetVersion(
        dataset_id=d.id,
        version_code=version_code,
        version_desc=version_desc or f"导入 {file.filename}",
        file_path=str(stored),
        data_count=len(rows),
        checksum=checksum,
        creator_id=current.id,
    )
    db.add(ver)
    await db.flush()
    for row in rows:
        db.add(DatasetItem(
            dataset_id=d.id,
            version_id=ver.id,
            item_no=row["item_no"],
            input_content=row["input_content"],
            reference_answer=row["reference_answer"],
            expected_output=row["expected_output"],
            task_requirement=row["task_requirement"],
            difficulty_level=row["difficulty_level"],
            data_label=row["data_label"],
            extended_content=dumps(row["extended_content"]),
        ))
    d.current_version = version_code
    d.current_version_id = ver.id
    d.data_count = len(rows)
    d.data_format = (Path(file.filename or "").suffix or "").lstrip(".") or d.data_format
    d.status = "draft"
    d.quality_status = "unchecked"
    await _add_log(db, d.id, ver.id, "import", f"导入 {len(rows)} 条", current)
    await log_audit(db, "dataset", "import", user_id=current.id, username=current.username, target_id=d.id, ip=get_client_ip(request))
    preview = [item_out(DatasetItem(
        id=0, dataset_id=d.id, version_id=ver.id,
        item_no=r["item_no"], input_content=r["input_content"], reference_answer=r["reference_answer"],
        expected_output=r["expected_output"], task_requirement=r["task_requirement"],
        difficulty_level=r["difficulty_level"], data_label=r["data_label"],
        extended_content=dumps(r["extended_content"]), quality_flag="normal", status="active",
    )) for r in rows[:20]]
    return {"version_id": ver.id, "version_code": version_code, "data_count": len(rows), "checksum": checksum, "preview": preview}


@router.get("/{dataset_id}/items")
async def list_items(
    dataset_id: int,
    version_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str = Query(""),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("dataset:view")),
):
    d = await db.get(Dataset, dataset_id)
    if not d:
        raise HTTPException(404, "数据集不存在")
    vid = version_id or d.current_version_id
    if not vid:
        return {"items": [], "total": 0}
    q = select(DatasetItem).where(DatasetItem.version_id == vid)
    if search:
        q = q.where(or_(DatasetItem.input_content.contains(search), DatasetItem.reference_answer.contains(search)))
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (await db.execute(q.order_by(DatasetItem.item_no).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [item_out(x) for x in rows], "total": total or 0, "version_id": vid}


@router.get("/{dataset_id}/export")
async def export_dataset(
    dataset_id: int,
    version_id: int | None = None,
    fmt: str = Query("jsonl"),
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("dataset:export")),
):
    d = await db.get(Dataset, dataset_id)
    if not d:
        raise HTTPException(404, "数据集不存在")
    vid = version_id or d.current_version_id
    rows = (await db.execute(select(DatasetItem).where(DatasetItem.version_id == vid).order_by(DatasetItem.item_no))).scalars().all()
    await _add_log(db, d.id, vid, "export", f"导出 {fmt}", current)
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["item_no", "input", "reference", "label"])
        writer.writeheader()
        for r in rows:
            writer.writerow({"item_no": r.item_no, "input": r.input_content, "reference": r.reference_answer, "label": r.data_label})
        data = buf.getvalue().encode("utf-8-sig")
        media = "text/csv"
        filename = f"{d.name}.csv"
    else:
        lines = [json.dumps({"input": r.input_content, "reference": r.reference_answer, "label": r.data_label}, ensure_ascii=False) for r in rows]
        data = ("\n".join(lines) + "\n").encode("utf-8")
        media = "application/jsonl"
        filename = f"{d.name}.jsonl"
    return StreamingResponse(io.BytesIO(data), media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/{dataset_id}/publish")
async def publish_dataset(
    dataset_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("dataset:edit")),
):
    d = await db.get(Dataset, dataset_id)
    if not d:
        raise HTTPException(404, "数据集不存在")
    if not d.current_version_id:
        raise HTTPException(400, "请先导入数据")
    d.status = "published"
    await _add_log(db, d.id, d.current_version_id, "publish", "发布数据集", current)
    await log_audit(db, "dataset", "publish", user_id=current.id, username=current.username, target_id=d.id, ip=get_client_ip(request))
    return dataset_brief(d)
