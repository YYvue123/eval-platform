"""批量评测快照：冻结分片、绑定租户、7 天 GC（活动引用保护）。"""
from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import BatchJob, BatchSnapshot, Dataset, DatasetItem, DatasetVersion, EvalTask
from app.services.budget import open_reservation
from app.utils.jsonutil import dumps

SNAPSHOT_TTL_DAYS = 7
ACTIVE_BATCH_STATUSES = {"queued", "running", "paused_budget"}
ACTIVE_TASK_STATUSES = {"queued", "running", "paused_budget"}


def _snapshot_dir() -> Path:
    p = Path(settings.UPLOAD_DIR) / "snapshots"
    p.mkdir(parents=True, exist_ok=True)
    return p


def results_content_hash(rows: list, tokens_used: int) -> str:
    raw = json.dumps(
        {"results": rows, "tokens_used": int(tokens_used or 0)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def freeze_snapshot(
    db: AsyncSession,
    dataset_id: int,
    version_id: int | None,
    *,
    tenant_id: int | None = None,
    creator_id: int | None = None,
) -> BatchSnapshot:
    ds = await db.get(Dataset, dataset_id)
    if not ds or ds.status == "deleted":
        raise ValueError("数据集不存在")
    vid = version_id or ds.current_version_id
    if not vid:
        raise ValueError("数据集没有可用版本")
    ver = await db.get(DatasetVersion, vid)
    if not ver or ver.dataset_id != dataset_id:
        raise ValueError("版本不属于该数据集")
    tid = tenant_id if tenant_id is not None else getattr(ds, "tenant_id", None)
    items = (
        await db.execute(
            select(DatasetItem)
            .where(DatasetItem.version_id == vid, DatasetItem.status != "deleted")
            .order_by(DatasetItem.item_no)
        )
    ).scalars().all()
    payload = [
        {
            "id": x.id,
            "item_no": x.item_no,
            "input": x.input_content,
            "reference": x.reference_answer,
            "expected": x.expected_output,
        }
        for x in items
    ]
    raw = dumps(payload).encode("utf-8")
    checksum = hashlib.sha256(raw).hexdigest()
    sid = uuid.uuid4().hex[:16]
    path = _snapshot_dir() / f"{sid}.json"
    # 原子写：先临时文件再 rename
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(raw)
    tmp.replace(path)
    snap = BatchSnapshot(
        snapshot_id=sid,
        dataset_id=dataset_id,
        version_id=vid,
        checksum=checksum,
        item_count=len(payload),
        file_path=str(path),
        tenant_id=tid,
        visibility=getattr(ds, "visibility", None) or "private",
        creator_id=creator_id,
        expires_at=datetime.utcnow() + timedelta(days=SNAPSHOT_TTL_DAYS),
    )
    db.add(snap)
    await db.flush()
    return snap


def load_snapshot_items(snap: BatchSnapshot) -> list[dict]:
    path = Path(snap.file_path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def shard_slice(items: list[dict], shard_id: int, shard_size: int) -> tuple[list[dict], bool]:
    if shard_id < 0:
        raise ValueError("分片号不能为负")
    start = shard_id * shard_size
    part = items[start:start + shard_size]
    done = start + shard_size >= len(items)
    return part, done


async def create_batch(
    db: AsyncSession,
    dataset_id: int,
    version_id: int | None,
    shard_size: int,
    token_budget: int,
    user_id: int | None,
    *,
    tenant_id: int | None = None,
) -> BatchJob:
    snap = await freeze_snapshot(db, dataset_id, version_id, tenant_id=tenant_id, creator_id=user_id)
    size = max(int(shard_size or 50), 1)
    count = math.ceil(snap.item_count / size) if snap.item_count else 0
    budget = int(token_budget or 0)
    job = BatchJob(
        batch_id=str(uuid.uuid4()),
        snapshot_id=snap.snapshot_id,
        dataset_id=dataset_id,
        version_id=snap.version_id,
        status="success" if count == 0 else "running",
        shard_size=size,
        shard_count=count,
        progress=100 if count == 0 else 0,
        token_budget=budget,
        tokens_reserved=budget,
        tenant_id=snap.tenant_id,
        creator_id=user_id,
    )
    db.add(job)
    await db.flush()
    if budget > 0:
        await open_reservation(
            db,
            subject_type="batch",
            subject_id=job.batch_id,
            amount=budget,
            tenant_id=str(snap.tenant_id or ""),
        )
    return job


async def gc_expired_snapshots(db: AsyncSession) -> int:
    now = datetime.utcnow()
    active_batch_sids = (
        await db.execute(select(BatchJob.snapshot_id).where(BatchJob.status.in_(list(ACTIVE_BATCH_STATUSES))))
    ).scalars().all()
    active_task_sids = (
        await db.execute(
            select(EvalTask.snapshot_id).where(
                EvalTask.status.in_(list(ACTIVE_TASK_STATUSES)),
                EvalTask.snapshot_id != "",
                EvalTask.snapshot_id.is_not(None),
            )
        )
    ).scalars().all()
    protected = {s for s in list(active_batch_sids) + list(active_task_sids) if s}
    rows = (
        await db.execute(
            select(BatchSnapshot).where(BatchSnapshot.expires_at.is_not(None), BatchSnapshot.expires_at < now)
        )
    ).scalars().all()
    n = 0
    for snap in rows:
        if snap.snapshot_id in protected:
            continue
        path = Path(snap.file_path)
        if path.exists():
            path.unlink()
        await db.delete(snap)
        n += 1
    return n
