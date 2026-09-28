"""可信知识：候选审核入库；检索强制租户 / 审核状态 / 过期。"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeCandidate, KnowledgeEntry
from app.utils.jsonutil import dumps, loads


def content_hash(title: str, content: str, category: str = "") -> str:
    raw = f"{category}|{title}|{content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def candidate_out(c: KnowledgeCandidate) -> dict:
    return {
        "id": c.id,
        "tenant_id": c.tenant_id,
        "source_session_id": c.source_session_id,
        "source_run_id": c.source_run_id,
        "source_hash": c.source_hash,
        "category": c.category,
        "title": c.title,
        "claim": loads(c.claim_json, {}),
        "status": c.status,
        "reviewer_id": c.reviewer_id,
        "reason": c.reason or "",
        "entry_id": c.entry_id,
        "created_at": c.created_at.isoformat() + "Z" if c.created_at else None,
        "reviewed_at": c.reviewed_at.isoformat() + "Z" if c.reviewed_at else None,
    }


def entry_out(r: KnowledgeEntry) -> dict:
    return {
        "id": r.id,
        "category": r.category,
        "title": r.title,
        "content": r.content,
        "tags": loads(r.tags_json, []),
        "ref_type": r.ref_type,
        "ref_id": r.ref_id,
        "source_hash": getattr(r, "source_hash", "") or "",
        "review_status": getattr(r, "review_status", "approved") or "approved",
        "valid_until": r.valid_until.isoformat() + "Z" if getattr(r, "valid_until", None) else None,
        "tenant_id": r.tenant_id,
    }


async def submit_candidate(
    db: AsyncSession,
    *,
    title: str,
    content: str,
    category: str = "case",
    tenant_id: int | None,
    source_session_id: int | None = None,
    source_run_id: int | None = None,
    tags: list | None = None,
) -> KnowledgeCandidate:
    sh = content_hash(title, content, category)
    existing = await db.scalar(
        select(KnowledgeCandidate).where(
            KnowledgeCandidate.source_hash == sh,
            KnowledgeCandidate.tenant_id == tenant_id,
            KnowledgeCandidate.status == "pending",
        )
    )
    if existing:
        return existing
    row = KnowledgeCandidate(
        tenant_id=tenant_id,
        source_session_id=source_session_id,
        source_run_id=source_run_id,
        source_hash=sh,
        category=category,
        title=title[:200],
        claim_json=dumps({"content": content, "tags": tags or []}),
        status="pending",
    )
    db.add(row)
    await db.flush()
    return row


async def review_candidate(
    db: AsyncSession,
    candidate_id: int,
    *,
    approve: bool,
    reviewer_id: int,
    reason: str = "",
    ttl_days: int = 365,
    actor_tenant_id: int | None = None,
) -> KnowledgeCandidate:
    c = await db.get(KnowledgeCandidate, candidate_id)
    if not c:
        raise HTTPException(404, "知识候选不存在")
    if actor_tenant_id is not None and c.tenant_id is not None and c.tenant_id != actor_tenant_id:
        raise HTTPException(403, "跨租户禁止审核")
    if c.status != "pending":
        raise HTTPException(400, f"候选状态不可审核: {c.status}")
    c.reviewer_id = reviewer_id
    c.reason = reason
    c.reviewed_at = datetime.utcnow()
    if not approve:
        c.status = "rejected"
        await db.flush()
        return c

    claim = loads(c.claim_json, {})
    entry = KnowledgeEntry(
        category=c.category,
        title=c.title,
        content=claim.get("content") or "",
        tags_json=dumps(claim.get("tags") or []),
        source_hash=c.source_hash,
        review_status="approved",
        valid_until=datetime.utcnow() + timedelta(days=max(1, ttl_days)),
        creator_id=reviewer_id,
        tenant_id=c.tenant_id,
        visibility="private",
    )
    db.add(entry)
    await db.flush()
    c.status = "approved"
    c.entry_id = entry.id
    await db.flush()
    return c


async def trusted_search(
    db: AsyncSession,
    query: str,
    *,
    tenant_id: int | None,
    category: str = "",
    include_expired: bool = False,
) -> list[dict]:
    """仅返回已审核且未过期、同租户（或共享）条目；候选不进入检索。"""
    if tenant_id is None:
        return []
    now = datetime.utcnow()
    q = select(KnowledgeEntry).where(
        KnowledgeEntry.tenant_id == tenant_id,
        KnowledgeEntry.review_status == "approved",
    )
    if not include_expired:
        q = q.where(or_(KnowledgeEntry.valid_until.is_(None), KnowledgeEntry.valid_until > now))
    if category:
        q = q.where(KnowledgeEntry.category == category)
    if query:
        q = q.where(
            or_(
                KnowledgeEntry.title.contains(query),
                KnowledgeEntry.content.contains(query),
                KnowledgeEntry.tags_json.contains(query),
            )
        )
    rows = (await db.execute(q.order_by(KnowledgeEntry.id.desc()).limit(20))).scalars().all()
    return [entry_out(r) for r in rows]


async def list_candidates(db: AsyncSession, tenant_id: int | None, status: str = "pending") -> list[KnowledgeCandidate]:
    q = select(KnowledgeCandidate).order_by(KnowledgeCandidate.id.desc()).limit(50)
    if tenant_id is not None:
        q = q.where(KnowledgeCandidate.tenant_id == tenant_id)
    if status:
        q = q.where(KnowledgeCandidate.status == status)
    return list((await db.execute(q)).scalars().all())
