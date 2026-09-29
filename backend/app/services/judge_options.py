"""打分候选：Tool、带 score 的 Skill，以及 MCP 目录中的工具。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BaseResource, ResourceEvent
from app.services.object_policy import apply_object_scope
from app.utils.jsonutil import loads


def parse_mcp_judge(judge_id: str) -> tuple[str, str] | None:
    text = (judge_id or "").strip()
    if not text.startswith("mcp:") or "#" not in text:
        return None
    parent, tool = text[4:].rsplit("#", 1)
    if not parent or not tool:
        return None
    return parent, tool


def mcp_judge_id(resource_id: str, tool_name: str) -> str:
    return f"mcp:{resource_id}#{tool_name}"


def unwrap_judge(raw) -> dict:
    """从工具或 MCP JSON-RPC 结果中取出 score / passed。缺少这两项则失败。"""
    current = raw
    for _ in range(4):
        if not isinstance(current, dict):
            break
        if "score" in current or "passed" in current:
            break
        nested = current.get("result")
        if isinstance(nested, dict):
            current = nested
            continue
        content = current.get("content")
        if isinstance(content, list):
            text = ""
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    text = block["text"]
                    break
            parsed = loads(text, None) if text else None
            if isinstance(parsed, dict):
                current = parsed
                continue
        break
    if not isinstance(current, dict) or ("score" not in current and "passed" not in current):
        raise RuntimeError("打分结果缺少 score 或 passed")
    if current.get("score") is None:
        score = 1.0 if current.get("passed") else 0.0
    else:
        score = float(current.get("score"))
    passed = bool(current["passed"]) if "passed" in current else score >= 1.0
    metrics = current.get("metrics") if isinstance(current.get("metrics"), dict) else {}
    return {"score": score, "passed": passed, "metrics": metrics}


def _skill_can_score(manifest: dict) -> bool:
    spec = manifest.get("evaluation_spec") or {}
    if spec.get("judge_type"):
        return True
    props = ((manifest.get("capabilities") or {}).get("output_schema") or {}).get("properties") or {}
    return "score" in props


async def list_judge_options(db: AsyncSession, actor) -> list[dict]:
    rows = (
        await db.execute(apply_object_scope(select(BaseResource), BaseResource, actor).order_by(BaseResource.id.asc()))
    ).scalars().all()
    items: list[dict] = []
    for row in rows:
        manifest = loads(row.manifest_json, {})
        if row.resource_type == "tool":
            items.append(
                {
                    "resource_id": row.resource_id,
                    "name": row.name,
                    "source": "tool",
                    "description": row.description or "",
                }
            )
        elif row.resource_type == "skill" and _skill_can_score(manifest):
            items.append(
                {
                    "resource_id": row.resource_id,
                    "name": row.name,
                    "source": "skill",
                    "description": row.description or "",
                }
            )
        elif row.resource_type == "mcp":
            catalog = await db.scalar(
                select(ResourceEvent)
                .where(
                    ResourceEvent.resource_id == row.resource_id,
                    ResourceEvent.event_type == "mcp.catalog",
                )
                .order_by(ResourceEvent.id.desc())
            )
            payload = loads(catalog.payload_json, {}) if catalog else {}
            tools = payload.get("tools") if isinstance(payload.get("tools"), list) else []
            if not tools:
                tools = [{"name": name, "description": ""} for name in (payload.get("tool_names") or [])]
            for tool in tools:
                if not isinstance(tool, dict) or not tool.get("name"):
                    continue
                name = str(tool["name"])
                items.append(
                    {
                        "resource_id": mcp_judge_id(row.resource_id, name),
                        "name": f"{row.name} / {name}",
                        "source": "mcp",
                        "parent_resource_id": row.resource_id,
                        "mcp_tool": name,
                        "description": tool.get("description") or "",
                    }
                )
    return items


async def invoke_judge(db: AsyncSession, *, actor, judge_id: str, prediction: str, reference: str, task_id: int | None):
    from app.services.tool_gateway import invoke_tool, response_result

    parsed = parse_mcp_judge(judge_id)
    body = {"prediction": prediction, "reference": reference, "pattern": reference}
    if parsed:
        parent, tool_name = parsed
        envelope = await invoke_tool(
            db,
            actor=actor,
            resource_id=parent,
            body={
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": body},
            },
            task_id=task_id,
            caller_id="task_runner",
        )
    else:
        envelope = await invoke_tool(
            db,
            actor=actor,
            resource_id=judge_id,
            body=body,
            task_id=task_id,
            caller_id="task_runner",
        )
    if (envelope.get("body") or {}).get("status") == "error":
        message = ((envelope.get("body") or {}).get("error") or {}).get("message") or "judge failed"
        raise RuntimeError(message)
    return unwrap_judge(response_result(envelope))
