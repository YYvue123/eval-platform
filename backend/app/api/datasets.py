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

from app.api.deps import get_current_user, require_permission, require_actor
from app.config import settings
from app.database import get_db
from app.models import Dataset, DatasetItem, DatasetLog, DatasetVersion, DataTag, EvalTask, User
from app.services.actor_context import ActorContext, effective_tenant_id
from app.services.audit import get_client_ip, log_audit
from app.services.dataset_parser import parse_bytes, preview_raw
from app.services.dataset_revision import apply_item_changes, content_checksum_for_items
from app.services.object_policy import apply_object_scope, get_visible_or_404, require_sensitive_export
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
    visibility: str | None = None


class TagCreate(BaseModel):
    name: str
    tag_type: str = "custom"
    parent_id: int | None = None
    description: str = ""


class TagUpdate(BaseModel):
    name: str | None = None
    tag_type: str | None = None
    parent_id: int | None = None
    description: str | None = None
    status: str | None = None


class AuditBody(BaseModel):
    action: str
    comment: str = ""


class ItemPatch(BaseModel):
    input_content: str | None = None
    reference_answer: str | None = None
    expected_output: str | None = None
    task_requirement: str | None = None
    difficulty_level: str | None = None
    data_label: str | None = None
    status: str | None = None


async def _dataset_task_count(db: AsyncSession, dataset_id: int) -> int:
    return (await db.scalar(select(func.count()).select_from(EvalTask).where(EvalTask.dataset_id == dataset_id))) or 0


def _tag_out(t: DataTag) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "tag_type": t.tag_type,
        "parent_id": t.parent_id,
        "description": t.description,
        "use_count": t.use_count,
        "status": t.status,
    }


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
    actor: ActorContext = Depends(require_actor("dataset:list")),
):
    q = select(Dataset).where(Dataset.status != "deleted")
    q = apply_object_scope(q, Dataset, actor)
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
    actor: ActorContext = Depends(require_actor("dataset:create")),
):
    exists = await db.scalar(select(Dataset.id).where(Dataset.name == body.name, Dataset.tenant_id == actor.tenant_id))
    if exists:
        raise HTTPException(400, "数据集名称已存在")
    claimed = getattr(body, "tenant_id", None)
    d = Dataset(
        name=body.name.strip(),
        dataset_type=body.dataset_type,
        task_type=body.task_type,
        domain_type=body.domain_type,
        data_source=body.data_source,
        description=body.description,
        tags=dumps(body.tags),
        security_level=body.security_level,
        creator_id=actor.user_id,
        tenant_id=effective_tenant_id(actor, claimed),
        visibility="private",
    )
    db.add(d)
    await db.flush()
    current = await db.get(User, actor.user_id)
    await _add_log(db, d.id, None, "create", "创建数据集", current)
    await log_audit(db, "dataset", "create", user_id=actor.user_id, username=actor.username, target_id=d.id, ip=get_client_ip(request))
    return dataset_brief(d, actor.username)


@router.get("/tags")
async def list_tags(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("dataset:list")),
):
    rows = (await db.execute(select(DataTag).order_by(DataTag.id.desc()))).scalars().all()
    return [_tag_out(t) for t in rows]


@router.put("/tags/{tag_id}")
async def update_tag(
    tag_id: int,
    body: TagUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("dataset:edit")),
):
    t = await db.get(DataTag, tag_id)
    if not t:
        raise HTTPException(404, "标签不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    return _tag_out(t)


@router.delete("/tags/{tag_id}")
async def delete_tag(
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("dataset:edit")),
):
    t = await db.get(DataTag, tag_id)
    if not t:
        raise HTTPException(404, "标签不存在")
    t.status = "disabled"
    return {"ok": True}


@router.post("/tags")
async def create_tag(
    body: TagCreate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("dataset:edit")),
):
    t = DataTag(name=body.name, tag_type=body.tag_type, parent_id=body.parent_id, description=body.description, creator_id=current.id)
    db.add(t)
    await db.flush()
    return _tag_out(t)


@router.get("/{dataset_id}")
async def get_dataset(
    dataset_id: int,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("dataset:view")),
):
    d = await get_visible_or_404(db, Dataset, dataset_id, actor, not_found="数据集不存在或无权访问")
    if d.status == "deleted":
        raise HTTPException(404, "数据集不存在或无权访问")
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
    actor: ActorContext = Depends(require_actor("dataset:edit")),
):
    d = await get_visible_or_404(db, Dataset, dataset_id, actor, not_found="数据集不存在或无权访问")
    if d.status == "deleted":
        raise HTTPException(404, "数据集不存在或无权访问")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in {"draft", "disabled", "archived", "pending"}:
        raise HTTPException(400, "不允许直接修改为该状态")
    if "visibility" in data and data["visibility"] not in {"private", "shared", "isolated"}:
        raise HTTPException(400, "visibility 无效")
    if "tags" in data:
        d.tags = dumps(data.pop("tags") or [])
    for k, v in data.items():
        setattr(d, k, v)
    current = await db.get(User, actor.user_id)
    await _add_log(db, d.id, None, "update", "更新数据集信息", current)
    await log_audit(db, "dataset", "update", user_id=actor.user_id, username=actor.username, target_id=d.id, ip=get_client_ip(request))
    return dataset_brief(d)


@router.delete("/{dataset_id}")
async def delete_dataset(
    dataset_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("dataset:delete")),
):
    d = await db.get(Dataset, dataset_id)
    if not d or d.status == "deleted":
        raise HTTPException(404, "数据集不存在")
    used = await _dataset_task_count(db, dataset_id)
    d.status = "deleted"
    await _add_log(db, d.id, None, "delete", f"逻辑删除，历史任务占用 {used} 个", current)
    await log_audit(db, "dataset", "delete", user_id=current.id, username=current.username, target_id=dataset_id, ip=get_client_ip(request))
    return {"ok": True, "logical": True, "task_count": used}


def _parse_mapping(raw: str) -> dict | None:
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "字段映射不是合法 JSON") from exc
    if not isinstance(data, dict):
        raise HTTPException(400, "字段映射必须是对象")
    return {str(k): v for k, v in data.items() if v}


@router.post("/{dataset_id}/preview")
async def preview_import(
    dataset_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("dataset:edit")),
):
    d = await db.get(Dataset, dataset_id)
    if not d or d.status == "deleted":
        raise HTTPException(404, "数据集不存在")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "空文件禁止导入")
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(400, "文件超过 50MB 限制")
    try:
        preview = preview_raw(file.filename or "data.json", raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    checksum = hashlib.sha256(raw).hexdigest()
    existed = await db.scalar(select(DatasetVersion.id).where(DatasetVersion.checksum == checksum))
    return {**preview, "checksum": checksum, "duplicate_checksum": bool(existed)}


@router.post("/{dataset_id}/import")
async def import_dataset(
    dataset_id: int,
    request: Request,
    file: UploadFile = File(...),
    version_desc: str = Form(""),
    field_mapping: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("dataset:edit")),
):
    d = await db.get(Dataset, dataset_id)
    if not d or d.status == "deleted":
        raise HTTPException(404, "数据集不存在")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "空文件禁止导入")
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(400, "文件超过 50MB 限制")
    mapping = _parse_mapping(field_mapping)
    try:
        rows = parse_bytes(file.filename or "data.json", raw, mapping)
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
        change_content=dumps(mapping or {}),
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
    await db.flush()
    items = (await db.execute(select(DatasetItem).where(DatasetItem.version_id == ver.id))).scalars().all()
    ver.content_checksum = content_checksum_for_items(items)
    d.current_version = version_code
    d.current_version_id = ver.id
    d.data_count = len(rows)
    d.data_format = (Path(file.filename or "").suffix or "").lstrip(".") or d.data_format
    if d.status in {"published", "pending"}:
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
    q = select(DatasetItem).where(DatasetItem.version_id == vid, DatasetItem.status != "deleted")
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
    actor: ActorContext = Depends(require_actor("dataset:export")),
):
    d = await get_visible_or_404(db, Dataset, dataset_id, actor, not_found="数据集不存在或无权访问")
    require_sensitive_export(actor, getattr(d, "security_level", None))
    current = await db.get(User, actor.user_id)
    vid = version_id or d.current_version_id
    rows = (await db.execute(
        select(DatasetItem).where(DatasetItem.version_id == vid, DatasetItem.status != "deleted").order_by(DatasetItem.item_no)
    )).scalars().all()
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
    elif fmt == "txt":
        data = "\n".join(f"{r.item_no}\t{r.input_content}\t{r.reference_answer}" for r in rows).encode("utf-8")
        media = "text/plain"
        filename = f"{d.name}.txt"
    elif fmt in {"xlsx", "xls", "excel"}:
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["item_no", "input", "reference", "label"])
        for r in rows:
            ws.append([r.item_no, r.input_content, r.reference_answer, r.data_label])
        bio = io.BytesIO()
        wb.save(bio)
        data = bio.getvalue()
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"{d.name}.xlsx"
    else:
        lines = [json.dumps({"input": r.input_content, "reference": r.reference_answer, "label": r.data_label}, ensure_ascii=False) for r in rows]
        data = ("\n".join(lines) + "\n").encode("utf-8")
        media = "application/jsonl"
        filename = f"{d.name}.jsonl"
    return StreamingResponse(io.BytesIO(data), media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/{dataset_id}/submit")
async def submit_dataset(
    dataset_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("dataset:edit")),
):
    d = await db.get(Dataset, dataset_id)
    if not d or d.status == "deleted":
        raise HTTPException(404, "数据集不存在")
    if not d.current_version_id:
        raise HTTPException(400, "请先导入数据")
    if d.status not in {"draft", "rejected"}:
        raise HTTPException(400, "仅草稿或已退回的数据集可提交审核")
    d.status = "pending"
    d.review_comment = ""
    await _add_log(db, d.id, d.current_version_id, "submit", "提交审核", current)
    await log_audit(db, "dataset", "submit", user_id=current.id, username=current.username, target_id=d.id, ip=get_client_ip(request))
    return dataset_brief(d)


@router.post("/{dataset_id}/audit")
async def audit_dataset(
    dataset_id: int,
    body: AuditBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("dataset:audit")),
):
    d = await db.get(Dataset, dataset_id)
    if not d or d.status == "deleted":
        raise HTTPException(404, "数据集不存在")
    if d.status != "pending":
        raise HTTPException(400, "仅待审核数据集可审核")
    if body.action not in {"approve", "reject"}:
        raise HTTPException(400, "action 必须是 approve 或 reject")
    if body.action == "approve":
        ver = await db.get(DatasetVersion, d.current_version_id) if d.current_version_id else None
        qstat = (ver.quality_status if ver else d.quality_status) or d.quality_status
        if qstat not in {"passed", "ok", "good"}:
            raise HTTPException(400, "质检未通过，不能发布；请先运行质检并达到 passed")
        d.status = "published"
        d.review_comment = body.comment
        op = "publish"
        desc = "审核通过并发布"
    else:
        d.status = "rejected"
        d.review_comment = body.comment or "审核退回"
        op = "reject"
        desc = f"审核退回：{d.review_comment}"
    await _add_log(db, d.id, d.current_version_id, op, desc, current)
    await log_audit(db, "dataset", op, user_id=current.id, username=current.username, target_id=d.id, ip=get_client_ip(request))
    return dataset_brief(d)


@router.post("/{dataset_id}/publish")
async def publish_dataset(
    dataset_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("dataset:audit")),
):
    d = await db.get(Dataset, dataset_id)
    if not d or d.status == "deleted":
        raise HTTPException(404, "数据集不存在")
    if not d.current_version_id:
        raise HTTPException(400, "请先导入数据")
    ver = await db.get(DatasetVersion, d.current_version_id)
    qstat = (ver.quality_status if ver else d.quality_status) or d.quality_status
    if qstat not in {"passed", "ok", "good"}:
        raise HTTPException(400, "质检未通过，不能发布；请先运行质检并达到 passed")
    d.status = "published"
    d.review_comment = ""
    await _add_log(db, d.id, d.current_version_id, "publish", "发布数据集", current)
    await log_audit(db, "dataset", "publish", user_id=current.id, username=current.username, target_id=d.id, ip=get_client_ip(request))
    return dataset_brief(d)


@router.post("/{dataset_id}/versions/{version_id}/rollback")
async def rollback_version(
    dataset_id: int,
    version_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("dataset:edit")),
):
    d = await db.get(Dataset, dataset_id)
    if not d or d.status == "deleted":
        raise HTTPException(404, "数据集不存在")
    ver = await db.get(DatasetVersion, version_id)
    if not ver or ver.dataset_id != dataset_id:
        raise HTTPException(404, "版本不存在")
    d.current_version = ver.version_code
    d.current_version_id = ver.id
    d.data_count = ver.data_count
    d.quality_status = ver.quality_status
    if d.status == "published":
        d.status = "draft"
    await _add_log(db, d.id, ver.id, "rollback", f"回滚到 {ver.version_code}", current)
    await log_audit(db, "dataset", "rollback", user_id=current.id, username=current.username, target_id=d.id, ip=get_client_ip(request))
    return dataset_brief(d)


@router.patch("/{dataset_id}/items/{item_id}")
async def patch_item(
    dataset_id: int,
    item_id: int,
    body: ItemPatch,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("dataset:edit")),
):
    d = await db.get(Dataset, dataset_id)
    if not d or d.status == "deleted":
        raise HTTPException(404, "数据集不存在")
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        item = await db.get(DatasetItem, item_id)
        if not item or item.dataset_id != dataset_id:
            raise HTTPException(404, "条目不存在")
        return item_out(item)
    new_item = await apply_item_changes(
        db,
        dataset=d,
        source_item_id=item_id,
        changes=changes,
        creator_id=current.id,
        change_desc=f"修正条目",
    )
    await _add_log(db, dataset_id, new_item.version_id, "update", f"修正条目产生新版本 {d.current_version}", current)
    return item_out(new_item)
