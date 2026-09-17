"""批量评测快照：冻结分片、7 天 GC、checksum。"""
from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import BatchJob, BatchSnapshot, Dataset, DatasetItem, DatasetVersion
from app.utils.jsonutil import dumps

SNAPSHOT_TTL_DAYS = 7


def _snapshot_dir() -> Path:
    p = Path(settings.UPLOAD_DIR) / "snapshots"
    p.mkdir(parents=True, exist_ok=True)
    return p


async def freeze_snapshot(db: AsyncSession, dataset_id: int, version_id: int | None) -> BatchSnapshot:
    ds = await db.get(Dataset, dataset_id)
    if not ds or ds.status == "deleted":
        raise ValueError("数据集不存在")
    vid = version_id or ds.current_version_id
    if not vid:
        raise ValueError("数据集没有可用版本")
    items = (await db.execute(
        select(DatasetItem).where(DatasetItem.version_id == vid, DatasetItem.status != "deleted").order_by(DatasetItem.item_no)
    )).scalars().all()
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
    ver = await db.get(DatasetVersion, vid)
    if ver and ver.checksum and ver.checksum != checksum:
        # 条目内容与版本文件 checksum 不同仍以冻结内容为准
        pass
    sid = uuid.uuid4().hex[:16]
    path = _snapshot_dir() / f"{sid}.json"
    path.write_bytes(raw)
    snap = BatchSnapshot(
        snapshot_id=sid,
        dataset_id=dataset_id,
        version_id=vid,
        checksum=checksum,
        item_count=len(payload),
        file_path=str(path),
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
    start = shard_id * shard_size
    part = items[start:start + shard_size]
    done = start + shard_size >= len(items)
    return part, done


async def create_batch(db: AsyncSession, dataset_id: int, version_id: int | None, shard_size: int, token_budget: int, user_id: int | None) -> BatchJob:
    snap = await freeze_snapshot(db, dataset_id, version_id)
    size = max(int(shard_size or 50), 1)
    count = math.ceil(snap.item_count / size) if snap.item_count else 0
    job = BatchJob(
        batch_id=str(uuid.uuid4()),
        snapshot_id=snap.snapshot_id,
        dataset_id=dataset_id,
        version_id=snap.version_id,
        status="success" if count == 0 else "running",
        shard_size=size,
        shard_count=count,
        progress=100 if count == 0 else 0,
        token_budget=int(token_budget or 0),
        creator_id=user_id,
    )
    db.add(job)
    await db.flush()
    return job


async def gc_expired_snapshots(db: AsyncSession) -> int:
    now = datetime.utcnow()
    rows = (await db.execute(select(BatchSnapshot).where(BatchSnapshot.expires_at.is_not(None), BatchSnapshot.expires_at < now))).scalars().all()
    n = 0
    for snap in rows:
        path = Path(snap.file_path)
        if path.exists():
            path.unlink()
        await db.delete(snap)
        n += 1
    return n
