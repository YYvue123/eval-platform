"""Skill 链式 $ref 与 MCP JSON-RPC 运行时（规格 2.5）。不改调度主路径。"""
from __future__ import annotations

from app.services.builtin_tools import run_builtin_tool


def run_skill(manifest: dict, body: dict) -> dict:
    skill = manifest.get("skill") or {}
    chain = skill.get("chain") or []
    if not chain:
        raise ValueError("Skill 未声明 chain")
    steps = []
    for step in chain:
        rid = str(step.get("$ref") or step.get("ref") or "")
        if not rid:
            raise ValueError("Skill 步骤缺少 $ref")
        payload = {**(body or {}), **(step.get("input") or {})}
        result = run_builtin_tool(rid, payload)
        steps.append({"ref": rid, "result": result})
    scores = [float(s["result"].get("score") or 0) for s in steps]
    passed = all(bool(s["result"].get("passed")) for s in steps)
    avg = round(sum(scores) / len(scores), 4) if scores else 0.0
    return {
        "score": avg,
        "passed": passed,
        "metrics": {"chain_score": avg, "steps": len(steps)},
        "steps": steps,
        "priority": skill.get("priority", 0),
    }


def run_mcp(body: dict) -> dict:
    method = str(body.get("method") or "")
    params = body.get("params") if isinstance(body.get("params"), dict) else {}
    req_id = body.get("id", 1)
    if method in {"tools/list", "list_tools"}:
        from app.services.builtin_manifests import BUILTIN_MANIFESTS
        tools = [
            {"name": m["resource_id"], "description": m.get("description") or m["name"], "resource_type": m["resource_type"]}
            for m in BUILTIN_MANIFESTS
            if m.get("resource_type") == "tool"
        ]
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}
    if method in {"tools/call", "call_tool"}:
        name = str(params.get("name") or params.get("resource_id") or "")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        if not name:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": "缺少 tool name"}}
        result = run_builtin_tool(name, arguments)
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"未知方法 {method}"}}
