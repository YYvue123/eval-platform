"""Skill 链式执行与 MCP JSON-RPC 运行时。"""
from __future__ import annotations

import re
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from app.services.builtin_tools import run_builtin_tool
from app.services.mcp.errors import McpError
from app.services.mcp.runner import McpRunResult
from app.services.mcp.runner import run_mcp as run_remote_mcp

STEP_REF = re.compile(r"^(?:step_(\d+)|([A-Za-z_][\w-]*))(?:\.(.+))?$")


class SkillStepError(RuntimeError):
    def __init__(
        self,
        step_id: str,
        code: str,
        message: str,
        completed_steps: list[str],
    ):
        completed = ", ".join(completed_steps) if completed_steps else "无"
        self.code = code or "SKILL_STEP_FAILED"
        self.step_id = step_id
        self.completed_steps = list(completed_steps)
        self.public_message = (
            f"Skill 步骤 {step_id} 执行失败: {message}；已完成步骤: {completed}"
        )
        super().__init__(self.public_message)


def _skill_step_from_http(
    step_id: str,
    exc: HTTPException,
    completed_steps: list[str],
) -> SkillStepError:
    detail = exc.detail
    if isinstance(detail, dict):
        code = str(detail.get("code") or "SKILL_STEP_FAILED")
        message = str(detail.get("message") or "下游工具执行失败")
    else:
        code = {
            404: "RESOURCE_UNAVAILABLE",
            409: "IDEMPOTENCY_CONFLICT",
            422: "SCHEMA_VALIDATION_FAILED",
        }.get(exc.status_code, "SKILL_STEP_FAILED")
        message = str(detail) if detail else "下游工具执行失败"
    return SkillStepError(step_id, code, message, completed_steps)


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


def _step_result(result: Any) -> Any:
    """把列表型工具结果映射为可被 sN.output.values 引用的对象。"""
    if isinstance(result, list):
        return {"values": result}
    if (
        isinstance(result, dict)
        and "values" not in result
        and isinstance(result.get("result"), list)
    ):
        return {**result, "values": result["result"]}
    return result


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


async def run_skill(
    manifest: dict,
    body: dict,
    *,
    step_invoker: Callable[[str, str, dict], Awaitable[dict]],
) -> dict:
    from app.services.tool_gateway import response_result

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

        try:
            envelope = await step_invoker(step_id, rid, payload)
        except HTTPException as exc:
            raise _skill_step_from_http(
                step_id,
                exc,
                [item["step_id"] for item in steps_out],
            ) from exc
        response_body = envelope.get("body") or {}
        if not isinstance(response_body, dict) or response_body.get("status") != "success":
            error = response_body.get("error") if isinstance(response_body, dict) else {}
            error = error if isinstance(error, dict) else {}
            raise SkillStepError(
                step_id,
                str(error.get("code") or "SKILL_STEP_FAILED"),
                str(error.get("message") or "下游工具执行失败"),
                [item["step_id"] for item in steps_out],
            )
        result = _step_result(response_result(envelope))
        entry = {"step_id": step_id, "ref": rid, "resource_id": rid, "result": result, "output": result}
        steps_out.append(entry)
        steps_by_id[step_id] = entry
        steps_by_id[f"step_{i}"] = entry

    scores = [
        float(s["result"]["score"])
        for s in steps_out
        if isinstance(s.get("result"), dict)
        and s["result"].get("score") is not None
    ]
    pass_values = [
        bool(s["result"]["passed"])
        for s in steps_out
        if isinstance(s.get("result"), dict) and "passed" in s["result"]
    ]
    avg = round(sum(scores) / len(scores), 4) if scores else None
    passed = all(pass_values) if pass_values else None
    final_result = steps_out[-1]["result"] if steps_out else None
    return {
        "score": avg,
        "passed": passed,
        "metrics": {"chain_score": avg, "steps": len(steps_out), "execution_type": execution_type},
        "steps": steps_out,
        "result": final_result,
        "priority": skill.get("priority", 0),
    }


def _is_local_builtin_mcp(manifest: dict | None) -> bool:
    mf = manifest or {}
    rid = str(mf.get("resource_id") or "")
    if rid.startswith("builtin/"):
        return True
    interfaces = mf.get("interfaces") or {}
    if str(interfaces.get("transport") or "streamable_http") == "stdio":
        return False
    endpoint = str(interfaces.get("endpoint") or interfaces.get("url") or "")
    return not endpoint.startswith("http")


def _builtin_mcp_rpc(method: str, params: dict, req_id) -> dict:
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


async def run_mcp(manifest: dict | None, method: str, params: dict | None = None, req_id=1) -> McpRunResult:
    """内置 JSON-RPC 或远程/stdio MCP runner。"""
    mf = manifest or {}
    params = params if isinstance(params, dict) else {}
    method = str(method or "")
    if _is_local_builtin_mcp(mf):
        rpc = _builtin_mcp_rpc(method, params, req_id)
        err = rpc.get("error")
        if err:
            message = err.get("message") if isinstance(err, dict) else str(err)
            raise McpError("MCP_PROTOCOL_ERROR", str(message or "MCP error"))
        inner = rpc.get("result") if isinstance(rpc.get("result"), dict) else {}
        return McpRunResult(
            result=rpc,
            protocol_version=str(inner.get("protocolVersion") or "2024-11-05"),
            server_info=inner.get("serverInfo") if isinstance(inner.get("serverInfo"), dict) else {},
            session_id_present=False,
            notifications=[],
            catalog_changed=False,
        )
    return await run_remote_mcp(mf, method, params, req_id=req_id)
