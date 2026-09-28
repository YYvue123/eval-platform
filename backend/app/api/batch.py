"""批量评测 MUST 接口：/batch/run|status|shards|results。"""
import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_actor, require_permission
from app.database import get_db
from app.models import BatchJob, BatchShardResult, BatchSnapshot, User
from app.services.actor_context import ActorContext, effective_tenant_id
from app.services.batch_store import (
    create_batch,
    load_snapshot_items,
    results_content_hash,
    shard_slice,
)
from app.services.budget import release_reservation, settle_tokens
from app.utils.jsonutil import dumps, iso, loads

router = APIRouter()


class BatchRunBody(BaseModel):
    dataset_id: int
    version_id: int | None = None
    shard_size: int = 50
    token_budget: int = 0
    tenant_id: int | None = None


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
        "tokens_reserved": getattr(job, "tokens_reserved", 0) or 0,
        "tenant_id": getattr(job, "tenant_id", None),
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
    actor: ActorContext = Depends(require_actor("resource:invoke")),
):
    tenant = effective_tenant_id(actor, body.tenant_id)
    try:
        job = await create_batch(
            db,
            body.dataset_id,
            body.version_id,
            body.shard_size,
            body.token_budget,
            actor.user_id,
            tenant_id=tenant,
        )
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
        await release_reservation(db, "batch", job.batch_id, note="批次取消")
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
    if job.status == "paused_budget":
        raise HTTPException(400, "批次因预算耗尽已暂停")
    if shard_id < 0 or (job.shard_count and shard_id >= job.shard_count):
        raise HTTPException(400, "分片号越界")
    if snapshot_id and snapshot_id != job.snapshot_id:
        raise HTTPException(400, "snapshot_id 与批次绑定不一致")
    sid = job.snapshot_id
    snap = (await db.execute(select(BatchSnapshot).where(BatchSnapshot.snapshot_id == sid))).scalar_one_or_none()
    if not snap:
        raise HTTPException(404, "快照不存在或已过期")
    if getattr(job, "tenant_id", None) is not None and snap.tenant_id is not None and job.tenant_id != snap.tenant_id:
        raise HTTPException(403, "批次与快照租户不一致")
    items = load_snapshot_items(snap)
    try:
        part, done = shard_slice(items, shard_id, job.shard_size)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
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
        raise HTTPException(400, "批次已取消，拒绝结算")
    if job.status == "paused_budget":
        raise HTTPException(400, "批次已因预算暂停，拒绝新回写")
    if shard_id < 0 or (job.shard_count and shard_id >= job.shard_count):
        raise HTTPException(400, "分片号越界")

    rows = body.get("results") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        raise HTTPException(400, "results 必须是数组")
    tokens = int(body.get("tokens_used") or 0)
    if tokens < 0:
        raise HTTPException(400, "tokens_used 不能为负")

    snap = (await db.execute(select(BatchSnapshot).where(BatchSnapshot.snapshot_id == job.snapshot_id))).scalar_one_or_none()
    if not snap:
        raise HTTPException(404, "快照不存在或已过期")
    items = load_snapshot_items(snap)
    try:
        part, _ = shard_slice(items, shard_id, job.shard_size)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    allowed = {int(x.get("item_no")) for x in part if isinstance(x, dict) and x.get("item_no") is not None}
    for r in rows:
        if not isinstance(r, dict):
            raise HTTPException(400, "结果项必须是对象")
        if "item_no" not in r:
            raise HTTPException(400, "结果缺少 item_no")
        if int(r["item_no"]) not in allowed:
            raise HTTPException(400, f"未知或不属于本分片的样本: {r['item_no']}")

    content_hash = results_content_hash(rows, tokens)
    existing = (
        await db.execute(
            select(BatchShardResult).where(BatchShardResult.batch_id == batch_id, BatchShardResult.shard_id == shard_id)
        )
    ).scalar_one_or_none()
    if existing:
        if (existing.content_hash or "") == content_hash:
            return {
                "ok": True,
                "progress": job.progress,
                "status": job.status,
                "error_code": job.error_code,
                "idempotent": True,
            }
        raise HTTPException(409, "同分片结果内容不一致，拒绝覆盖")

    prev_tokens = 0
    ok, err = await settle_tokens(
        db,
        subject_type="batch",
        subject_id=job.batch_id,
        amount=tokens,
        budget=job.token_budget,
        already_used=job.tokens_used,
        tenant_id=str(getattr(job, "tenant_id", "") or ""),
    )
    if not ok:
        job.status = "paused_budget"
        job.error_code = err or "BUDGET_EXHAUSTED"
        return {"ok": False, "progress": job.progress, "status": job.status, "error_code": job.error_code}

    db.add(
        BatchShardResult(
            batch_id=batch_id,
            shard_id=shard_id,
            results_json=dumps(rows),
            tokens_used=tokens,
            content_hash=content_hash,
            immutable=True,
            status="done",
        )
    )
    job.tokens_used = max(job.tokens_used - prev_tokens + tokens, 0)
    failed = [x for x in rows if isinstance(x, dict) and x.get("error_code")]
    # 按 item_no 去重合并失败明细
    details = {str(x.get("item_no")): x for x in loads(job.failed_details, []) if isinstance(x, dict)}
    for f in failed:
        details[str(f.get("item_no"))] = f
    job.failed_details = dumps(list(details.values()))
    await db.flush()
    n = (await db.scalar(select(func.count()).select_from(BatchShardResult).where(BatchShardResult.batch_id == batch_id))) or 0
    job.progress = int(n / max(job.shard_count, 1) * 100) if job.shard_count else 100
    if job.token_budget and job.tokens_used >= job.token_budget and n < job.shard_count:
        job.status = "paused_budget"
        job.error_code = "BUDGET_EXHAUSTED"
    elif n >= job.shard_count:
        job.status = "success"
        job.progress = 100
        job.error_code = ""
    return {"ok": True, "progress": job.progress, "status": job.status, "error_code": job.error_code}


@router.get("/{batch_id}/results")
async def batch_results(
    batch_id: str,
    fmt: str = Query("jsonl"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("resource:view")),
):
    job = await _get_job(db, batch_id)
    shards = (
        await db.execute(select(BatchShardResult).where(BatchShardResult.batch_id == batch_id).order_by(BatchShardResult.shard_id))
    ).scalars().all()
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
