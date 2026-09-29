from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ResourceEvent
from app.utils.jsonutil import dumps, iso, loads


def _safe_tools(tools) -> list[dict]:
    safe = []
    for item in tools or []:
        if not isinstance(item, dict):
            continue
        entry = {
            "name": item.get("name", ""),
            "description": item.get("description", ""),
        }
        schema = item.get("inputSchema") if isinstance(item.get("inputSchema"), dict) else item.get("input_schema")
        if isinstance(schema, dict):
            entry["inputSchema"] = schema
        safe.append(entry)
    return safe


def catalog_hash(tools) -> str:
    canonical = json.dumps(
        sorted(tools, key=lambda x: x.get("name", "")),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


async def persist_catalog(db: AsyncSession, resource_id, tools, *, changed, actor) -> dict:
    safe = _safe_tools(tools)
    digest = catalog_hash(safe) if safe else ""
    last = await db.scalar(
        select(ResourceEvent)
        .where(
            ResourceEvent.resource_id == resource_id,
            ResourceEvent.event_type == "mcp.catalog",
        )
        .order_by(ResourceEvent.id.desc())
    )
    last_hash = ""
    if last:
        last_hash = str((loads(last.payload_json, {}) or {}).get("hash") or "")
    tenant_id = str(getattr(actor, "tenant_id", "") or "")
    hash_changed = bool(safe) and last_hash != digest
    if safe:
        db.add(ResourceEvent(
            event_type="mcp.catalog",
            resource_id=resource_id,
            payload_json=dumps({
                "hash": digest,
                "count": len(safe),
                "tool_names": [item["name"] for item in safe],
                "tools": safe,
                "tenant_id": tenant_id,
            }),
        ))
    if (hash_changed and last is not None) or changed:
        db.add(ResourceEvent(
            event_type="mcp.catalog_changed",
            resource_id=resource_id,
            payload_json=dumps({
                "hash": digest or last_hash,
                "count": len(safe) if safe else None,
                "tenant_id": tenant_id,
            }),
        ))
    await db.flush()
    return {"hash": digest or last_hash, "changed": bool(changed or hash_changed)}


async def catalog_summary(db: AsyncSession, resource_id: str) -> dict:
    catalog = await db.scalar(
        select(ResourceEvent)
        .where(
            ResourceEvent.resource_id == resource_id,
            ResourceEvent.event_type == "mcp.catalog",
        )
        .order_by(ResourceEvent.id.desc())
    )
    changed = await db.scalar(
        select(ResourceEvent)
        .where(
            ResourceEvent.resource_id == resource_id,
            ResourceEvent.event_type == "mcp.catalog_changed",
        )
        .order_by(ResourceEvent.id.desc())
    )
    if not catalog:
        return {
            "hash": "",
            "count": 0,
            "observed_at": None,
            "stale": False,
        }
    payload = loads(catalog.payload_json, {})
    return {
        "hash": payload.get("hash") or "",
        "count": payload.get("count") or 0,
        "observed_at": iso(catalog.created_at),
        "stale": bool(changed and changed.id > catalog.id),
    }
