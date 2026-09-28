"""数据集修订：条目变更复制出新版本，保证历史 version 不可变。"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Dataset, DatasetItem, DatasetVersion
from app.utils.jsonutil import dumps


def content_checksum_for_items(items: list[DatasetItem] | list[dict]) -> str:
    """条目内容规范 hash：按 item_no 排序的关键字段。"""
    rows = []
    for it in items:
        if isinstance(it, dict):
            rows.append({
                "item_no": int(it.get("item_no") or 0),
                "input_content": it.get("input_content") or "",
                "reference_answer": it.get("reference_answer") or "",
                "expected_output": it.get("expected_output") or "",
                "status": it.get("status") or "active",
            })
        else:
            rows.append({
                "item_no": int(it.item_no or 0),
                "input_content": it.input_content or "",
                "reference_answer": it.reference_answer or "",
                "expected_output": it.expected_output or "",
                "status": it.status or "active",
            })
    rows.sort(key=lambda x: x["item_no"])
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _next_version_code(current: str) -> str:
    cur = (current or "V1.0").strip() or "V1.0"
    if cur.upper().startswith("V"):
        body = cur[1:]
        parts = body.split(".")
        try:
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0
            return f"V{major}.{minor + 1}"
        except ValueError:
            pass
    return f"{cur}-r"


async def apply_item_changes(
    db: AsyncSession,
    *,
    dataset: Dataset,
    source_item_id: int,
    changes: dict[str, Any],
    creator_id: int | None = None,
    change_desc: str = "条目修订",
) -> DatasetItem:
    """复制当前版本全部条目到新版本，仅对新副本应用 changes；返回新条目。"""
    if not dataset.current_version_id:
        raise HTTPException(400, "请先导入数据")
    src_item = await db.get(DatasetItem, source_item_id)
    if not src_item or src_item.dataset_id != dataset.id:
        raise HTTPException(404, "条目不存在")
    if src_item.version_id != dataset.current_version_id:
        raise HTTPException(400, "只能修订当前版本条目；请先回滚/切换到目标版本")

    old_items = (
        await db.execute(
            select(DatasetItem).where(DatasetItem.version_id == dataset.current_version_id).order_by(DatasetItem.item_no)
        )
    ).scalars().all()
    if not old_items:
        raise HTTPException(400, "当前版本无条目")

    code = _next_version_code(dataset.current_version)
    ver = DatasetVersion(
        dataset_id=dataset.id,
        version_code=code,
        version_desc=change_desc,
        change_content=dumps({"source_version_id": dataset.current_version_id, "item_id": source_item_id, "changes": changes}),
        file_path="",
        data_count=len(old_items),
        checksum="",
        content_checksum="",
        quality_status="unchecked",
        creator_id=creator_id,
    )
    db.add(ver)
    await db.flush()

    new_target: DatasetItem | None = None
    clones: list[DatasetItem] = []
    for old in old_items:
        clone = DatasetItem(
            dataset_id=dataset.id,
            version_id=ver.id,
            item_no=old.item_no,
            input_content=old.input_content,
            reference_answer=old.reference_answer,
            expected_output=old.expected_output,
            task_requirement=old.task_requirement,
            difficulty_level=old.difficulty_level,
            data_label=old.data_label,
            extended_content=old.extended_content,
            quality_flag=old.quality_flag,
            status=old.status,
        )
        if old.id == source_item_id:
            for k, v in changes.items():
                if hasattr(clone, k) and k not in {"id", "dataset_id", "version_id", "item_no", "created_at"}:
                    setattr(clone, k, v)
            new_target = clone
        db.add(clone)
        clones.append(clone)
    await db.flush()

    ver.content_checksum = content_checksum_for_items(clones)
    ver.checksum = ver.content_checksum
    ver.data_count = len(clones)
    dataset.current_version = code
    dataset.current_version_id = ver.id
    dataset.data_count = len(clones)
    dataset.quality_status = "unchecked"
    if dataset.status in {"published", "pending"}:
        dataset.status = "draft"
    if new_target is None:
        raise HTTPException(500, "修订失败：未找到目标条目副本")
    return new_target
