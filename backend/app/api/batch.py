"""批量评测 MUST 接口：/batch/run|status|shards|results。"""
import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.database import get_db
from app.models import BatchJob, BatchShardResult, BatchSnapshot, User
from app.services.batch_store import create_batch, load_snapshot_items, shard_slice
from app.utils.jsonutil import dumps, iso, loads

router = APIRouter()


class BatchRunBody(BaseModel):
    dataset_id: int
    version_id: int | None = None
    shard_size: int = 50
    token_budget: int = 0


def _job_out(job: BatchJob, snap: BatchSnapshot | None = None) -> dict:
    return {
        "batch_id": job.batch_id,
        "snapshot_id": job.snapshot_id,
        "dataset_id": job.dataset_id,
        "version_id": job.version_id,
        "status": job.status,
        "shard_size": job.shard_size,
        "shard_count": job.shard_count,
        "progress": job.progress,
        "token_budget": job.token_budget,
        "tokens_used": job.tokens_used,
        "error_code": job.error_code,
        "failed_details": loads(job.failed_details, []),
        "checksum": snap.checksum if snap else "",
        "item_count": snap.item_count if snap else 0,
        "created_at": iso(job.created_at),
    }


async def _get_job(db, batch_id: str) -> BatchJob:
    job = (await db.execute(select(BatchJob).where(BatchJob.batch_id == batch_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(404, "批次不存在")
    return job


@router.post("/run")
async def batch_run(
    body: BatchRunBody,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("resource:invoke")),
):
    try:
        job = await create_batch(db, body.dataset_id, body.version_id, body.shard_size, body.token_budget, current.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    snap = (await db.execute(select(BatchSnapshot).where(BatchSnapshot.snapshot_id == job.snapshot_id))).scalar_one_or_none()
    return _job_out(job, snap)


@router.get("/status/{batch_id}")
async def batch_status(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("resource:view")),
):
    job = await _get_job(db, batch_id)
    snap = (await db.execute(select(BatchSnapshot).where(BatchSnapshot.snapshot_id == job.snapshot_id))).scalar_one_or_none()
    return _job_out(job, snap)


@router.delete("/{batch_id}")
async def batch_cancel(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("resource:invoke")),
):
    job = await _get_job(db, batch_id)
    if job.status not in {"success", "cancelled"}:
        job.status = "cancelled"
    return {"ok": True, "status": job.status}


@router.get("/{batch_id}/shards/{shard_id}")
async def get_shard(
    batch_id: str,
    shard_id: int,
    snapshot_id: str = Query(""),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("resource:invoke")),
):
    job = await _get_job(db, batch_id)
    if job.status == "cancelled":
        raise HTTPException(400, "批次已取消")
    sid = snapshot_id or job.snapshot_id
    snap = (await db.execute(select(BatchSnapshot).where(BatchSnapshot.snapshot_id == sid))).scalar_one_or_none()
    if not snap:
        raise HTTPException(404, "快照不存在或已过期")
    items = load_snapshot_items(snap)
    part, done = shard_slice(items, shard_id, job.shard_size)
    return {
        "batch_id": batch_id,
        "snapshot_id": sid,
        "shard_id": shard_id,
        "checksum": snap.checksum,
        "items": part,
        "done": done,
    }


@router.put("/{batch_id}/shards/{shard_id}/results")
async def put_shard_results(
    batch_id: str,
    shard_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("resource:invoke")),
):
    job = await _get_job(db, batch_id)
    if job.status == "cancelled":
        raise HTTPException(400, "批次已取消")
    rows = body.get("results") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        raise HTTPException(400, "results 必须是数组")
    tokens = int(body.get("tokens_used") or 0)
    failed = [x for x in rows if isinstance(x, dict) and x.get("error_code")]
    existing = (await db.execute(
        select(BatchShardResult).where(BatchShardResult.batch_id == batch_id, BatchShardResult.shard_id == shard_id)
    )).scalar_one_or_none()
    prev_tokens = existing.tokens_used if existing else 0
    if existing:
        existing.results_json = dumps(rows)
        existing.tokens_used = tokens
        existing.status = "done"
    else:
        db.add(BatchShardResult(batch_id=batch_id, shard_id=shard_id, results_json=dumps(rows), tokens_used=tokens, status="done"))
    job.tokens_used = max(job.tokens_used - prev_tokens + tokens, 0)
    details = loads(job.failed_details, [])
    details.extend(failed)
    job.failed_details = dumps(details)
    await db.flush()
    n = (await db.scalar(select(func.count()).select_from(BatchShardResult).where(BatchShardResult.batch_id == batch_id))) or 0
    job.progress = int(n / max(job.shard_count, 1) * 100) if job.shard_count else 100
    if job.token_budget and job.tokens_used >= job.token_budget:
        job.status = "failed"
        job.error_code = "BUDGET_EXHAUSTED"
    elif n >= job.shard_count:
        job.status = "success"
        job.progress = 100
    return {"ok": True, "progress": job.progress, "status": job.status, "error_code": job.error_code}


@router.get("/{batch_id}/results")
async def batch_results(
    batch_id: str,
    fmt: str = Query("jsonl"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("resource:view")),
):
    job = await _get_job(db, batch_id)
    shards = (await db.execute(
        select(BatchShardResult).where(BatchShardResult.batch_id == batch_id).order_by(BatchShardResult.shard_id)
    )).scalars().all()
    rows = []
    for sh in shards:
        part = loads(sh.results_json, [])
        if isinstance(part, list):
            rows.extend(part)
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["item_no", "score", "error_code", "skipped"])
        writer.writeheader()
        for r in rows:
            if not isinstance(r, dict):
                continue
            writer.writerow({
                "item_no": r.get("item_no", ""),
                "score": r.get("score", ""),
                "error_code": r.get("error_code", ""),
                "skipped": r.get("skipped", ""),
            })
        data = buf.getvalue().encode("utf-8-sig")
        return StreamingResponse(io.BytesIO(data), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{batch_id}.csv"'})
    lines = [json.dumps(r, ensure_ascii=False) for r in rows]
    data = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    return StreamingResponse(io.BytesIO(data), media_type="application/jsonl", headers={"Content-Disposition": f'attachment; filename="{batch_id}.jsonl"'})
