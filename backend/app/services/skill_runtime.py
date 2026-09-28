"""Skill 链式执行与 MCP JSON-RPC 运行时。"""
from __future__ import annotations

import re
from typing import Any

from app.services.builtin_tools import run_builtin_tool
from app.services.mcp_client import mcp_initialize, mcp_request, mcp_tools_call, mcp_tools_list

STEP_REF = re.compile(r"^(?:step_(\d+)|([A-Za-z_][\w-]*))(?:\.(.+))?$")


def _dig(obj: Any, path: str) -> Any:
    cur = obj
    if not path:
        return cur
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            if part in cur:
                cur = cur[part]
            elif part == "output" and "result" in cur:
                cur = cur["result"]
            else:
                cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def resolve_value(value: Any, *, inputs: dict, steps_by_id: dict[str, dict], step_index: int) -> Any:
    if isinstance(value, list):
        return [resolve_value(v, inputs=inputs, steps_by_id=steps_by_id, step_index=step_index) for v in value]
    if not isinstance(value, dict):
        return value
    if "$ref" not in value:
        return {k: resolve_value(v, inputs=inputs, steps_by_id=steps_by_id, step_index=step_index) for k, v in value.items()}

    ref = str(value.get("$ref") or "")
    if ref.startswith("$input.") or ref == "$input":
        path = "" if ref == "$input" else ref[len("$input."):]
        return _dig(inputs, path) if path else inputs
    if ref.startswith("$global."):
        return _dig(inputs.get("$global") or {}, ref[len("$global."):])

    m = STEP_REF.match(ref)
    if not m:
        # 当作资源 ID 字面量（兼容旧 chain）
        return ref
    idx_s, sid, rest = m.group(1), m.group(2), m.group(3) or ""
    if idx_s is not None:
        idx = int(idx_s)
        if idx >= step_index:
            raise ValueError(f"非法向前引用: {ref}")
        key = f"step_{idx}"
        if key not in steps_by_id:
            raise ValueError(f"未知步骤引用: {ref}")
        target = steps_by_id[key]
    else:
        if sid not in steps_by_id:
            raise ValueError(f"未知或向前引用步骤: {ref}")
        target = steps_by_id[sid]
    path = rest
    if path.startswith("output."):
        path = path[len("output."):]
        return _dig(target.get("result") or target.get("output") or {}, path)
    if path == "output":
        return target.get("result") or target.get("output")
    return _dig(target, path) if path else target


def _detect_resource_cycle(chain: list[dict]) -> None:
    """简单环：同一 resource 在依赖图中自引用（步骤引用自身 resource 输出再调自身）— 用资源 ID 重复无害；
    这里检测 step 绑定引用形成的环通过向前引用已拒绝。额外：chain 中 resource 互相只靠 $ref 资源名循环配置。"""
    ids = []
    for step in chain:
        rid = str(step.get("resource_id") or step.get("$ref") or step.get("ref") or "")
        if rid and not rid.startswith("step_") and not rid.startswith("$"):
            ids.append(rid)
    # 无向自环配置：A 的唯一步骤引用 A 自身作为资源且 input 引自身输出 — 由向前引用覆盖
    return


def run_skill(manifest: dict, body: dict) -> dict:
    skill = manifest.get("skill") or {}
    chain = skill.get("chain") or []
    if not chain:
        raise ValueError("Skill 未声明 chain")
    _detect_resource_cycle(chain)
    execution_type = str(skill.get("execution_type") or "workflow")
    if execution_type not in {"workflow", "prompt_template", "code", "agent"}:
        raise ValueError(f"不支持的 Skill execution_type: {execution_type}")
    if execution_type != "workflow":
        # 本会话仅完整实现 workflow；其它类型明确拒绝，避免假成功
        raise ValueError(f"本版本仅支持 workflow Skill，收到: {execution_type}")

    inputs = dict(body or {})
    steps_out: list[dict] = []
    steps_by_id: dict[str, dict] = {}

    for i, step in enumerate(chain):
        step_id = str(step.get("step_id") or f"step_{i}")
        rid = str(step.get("resource_id") or step.get("$ref") or step.get("ref") or "")
        if not rid:
            raise ValueError(f"Skill 步骤 {step_id} 缺少 resource_id/$ref")
        if rid.startswith("step_") or rid.startswith("$"):
            raise ValueError(f"步骤 {step_id} 的 resource_id 非法: {rid}")

        raw_input = step.get("input") if isinstance(step.get("input"), dict) else {}
        # 兼容：无 input 绑定时合并 body
        if not raw_input:
            payload = {**inputs, **(step.get("params") or {})}
        else:
            payload = resolve_value(raw_input, inputs=inputs, steps_by_id=steps_by_id, step_index=i)
            if not isinstance(payload, dict):
                raise ValueError(f"步骤 {step_id} 解析后的 input 必须是对象")

        result = run_builtin_tool(rid, payload)
        entry = {"step_id": step_id, "ref": rid, "resource_id": rid, "result": result, "output": result}
        steps_out.append(entry)
        steps_by_id[step_id] = entry
        steps_by_id[f"step_{i}"] = entry

    scores = [float((s["result"] or {}).get("score") or 0) for s in steps_out]
    passed = all(bool((s["result"] or {}).get("passed")) for s in steps_out) if steps_out else False
    avg = round(sum(scores) / len(scores), 4) if scores else 0.0
    return {
        "score": avg,
        "passed": passed,
        "metrics": {"chain_score": avg, "steps": len(steps_out), "execution_type": execution_type},
        "steps": steps_out,
        "priority": skill.get("priority", 0),
    }


async def run_mcp(manifest: dict | None, body: dict) -> dict:
    """本地 builtin 或远程 HTTP MCP。"""
    method = str(body.get("method") or "")
    params = body.get("params") if isinstance(body.get("params"), dict) else {}
    req_id = body.get("id", 1)
    mf = manifest or {}
    interfaces = mf.get("interfaces") or {}
    endpoint = str(interfaces.get("endpoint") or interfaces.get("url") or "")
    auth = interfaces.get("auth") or {}
    token = auth.get("token") if isinstance(auth, dict) else None
    timeout = int((mf.get("capabilities") or {}).get("timeout") or 30)
    channel = str(interfaces.get("channel") or "https")

    if endpoint.startswith("http"):
        if method in {"initialize", "mcp/initialize"}:
            data = await mcp_initialize(endpoint, req_id=req_id, auth_token=token, timeout=timeout, channel=channel, manifest=mf)
            return data
        if method in {"tools/list", "list_tools"}:
            data = await mcp_tools_list(endpoint, req_id=req_id, auth_token=token, timeout=timeout, channel=channel, manifest=mf)
            return data
        if method in {"tools/call", "call_tool"}:
            name = str(params.get("name") or params.get("resource_id") or "")
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            if not name:
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": "缺少 tool name"}}
            data = await mcp_tools_call(
                endpoint, name, arguments, req_id=req_id, auth_token=token, timeout=timeout, channel=channel, manifest=mf
            )
            return data
        data = await mcp_request(
            endpoint, method, params, req_id=req_id, auth_token=token, timeout=timeout, channel=channel, manifest=mf
        )
        return data

    # 本地内置网关
    if method in {"initialize", "mcp/initialize"}:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "eval-platform-builtin-mcp", "version": "1.0.0"},
            },
        }
    if method in {"tools/list", "list_tools"}:
        from app.services.builtin_manifests import BUILTIN_MANIFESTS

        tools = [
            {
                "name": m["resource_id"],
                "description": m.get("description") or m["name"],
                "resource_type": m["resource_type"],
            }
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
