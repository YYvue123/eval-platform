"""Opt-in real-provider acceptance, using only a dedicated isolated DB and gated APIs.

Run from backend: .venv/Scripts/python scripts/verify_langgraph_live.py
Requires L3_MODEL_* configuration. Never prints credentials or model response bodies.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + (ROOT / "tests/_isolated/langgraph-live.db").as_posix()
from tests import isolated_env  # noqa: E402,F401

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.config import settings
from app.database import async_session
from app.main import app
from app.models import AgentDelegation, EvalModel, ModelAccessConfig, ResourceCallLog
from app.utils.jsonutil import loads
from tests.followup_helpers import login_admin, stats_service, tool_manifest


def checked(response):
    if response.status_code != 200:
        raise RuntimeError(f"api_http_{response.status_code}:{response.request.url.path}")
    return response.json()


async def evidence_facts(session_id, resource_id):
    async with async_session() as db:
        delegations = (await db.execute(select(AgentDelegation).where(AgentDelegation.session_id == session_id))).scalars().all()
        calls = (await db.execute(select(ResourceCallLog).where(ResourceCallLog.resource_id == resource_id))).scalars().all()
        return {
            "delegations": [{"id": d.id, "status": d.status, "engine": loads(d.result_json, {}).get("engine"),
                             "tool_calls": loads(d.result_json, {}).get("tool_calls", 0)} for d in delegations],
            "mcp_calls": [{"status": c.status, "actor_present": bool(c.user_id and c.tenant_id),
                           "source": c.source} for c in calls],
        }


async def clear_keys(model_ids):
    async with async_session() as db:
        await db.execute(update(EvalModel).where(EvalModel.id.in_(model_ids)).values(api_key=""))
        configs = (await db.execute(select(ModelAccessConfig).where(ModelAccessConfig.model_id.in_(model_ids)))).scalars().all()
        for config in configs:
            auth = loads(config.auth_config, {})
            auth.pop("api_key", None)
            auth.pop("token", None)
            auth["has_key"] = False
            config.auth_config = json.dumps(auth)
        await db.commit()


def main():
    evidence = {"started_at": datetime.now(timezone.utc).isoformat(), "engine": "langgraph-v1", "steps": [], "ok": False}
    model_ids = []
    if not all([settings.L3_MODEL_API_URL, settings.L3_MODEL_API_KEY, settings.L3_MODEL_PRIMARY]):
        evidence["error"] = "live_model_configuration_missing"
    else:
        try:
            with TestClient(app) as client, stats_service() as url:
                headers = login_admin(client)
                suffix = uuid.uuid4().hex[:8]
                for name in [f"planner-graph-{suffix}", f"target-graph-{suffix}"]:
                    model = checked(client.post("/api/models", headers=headers, json={
                        "name": name, "api_url": settings.L3_MODEL_API_URL, "api_key": settings.L3_MODEL_API_KEY,
                        "served_model_name": settings.L3_MODEL_PRIMARY, "channel_type": settings.L3_MODEL_CHANNEL,
                        "auth_type": "bearer_token", "status": "online", "timeout": 60,
                    }))
                    model_ids.append(model["id"])
                planner_id, target_id = model_ids
                checked(client.put("/api/agents/profile", headers=headers, json={"model_config": {"max_tokens": 1024}, "max_iterations": 8}))
                rid = f"live/graph_stats_{suffix}"
                manifest = tool_manifest(rid, url, resource_type="mcp", interfaces={
                    "transport": "streamable_http", "endpoint": f"{url}/mcp", "method": "POST",
                })
                checked(client.post("/api/resources/register", headers=headers, json={"manifest": manifest}))
                probe = checked(client.post("/api/resources/mcp/probe", headers=headers, json={"resource_id": rid, "method": "tools/list"}))
                if not probe.get("ok"):
                    raise RuntimeError("mcp_probe_failed")
                role = f"stats_{suffix}"
                checked(client.post("/api/agents/definitions", headers=headers, json={
                    "role": role, "name": "统计分析专家", "available_tools": ["call_mcp"], "max_iterations": 4,
                    "system_prompt": "必须调用已绑定 MCP 的 compute_stats，输入 values 为三项对象数组，每项为 value 数字和 unit 字符串 m。value 分别是2、4、6，target_unit 用 m。根据工具返回回答均值，不要心算替代工具。工具报错时根据错误纠正参数并重试。",
                    "model_config": {"max_tokens": 1024},
                }))
                session = checked(client.post("/api/agents/sessions", headers=headers, json={
                    "requirement": "验证统计工具协作", "planner_model_id": planner_id,
                    "subagent_roles": [role], "mcp_resource_ids": [rid],
                }))
                sid = session["id"]
                run = checked(client.post(f"/api/agents/sessions/{sid}/runs", headers=headers, json={
                    "message": f"必须先调用 delegate_agent，role={role}，让该专家通过 MCP {rid} 的 compute_stats 计算 2m、4m、6m 的均值。收到子 Agent 结果后汇总。不要直接心算，不创建评测任务。",
                    "planner_model_id": planner_id, "max_rounds": 6,
                }))
                facts = asyncio.run(evidence_facts(sid, rid))
                collaboration_ok = (
                    run["status"] == "success"
                    and any(d["status"] == "success" and d["engine"] == "langgraph" and d["tool_calls"] > 0 for d in facts["delegations"])
                    and any(c["actor_present"] and c["source"] == "agent_runtime" and c["status"] == "success" for c in facts["mcp_calls"])
                )
                evidence["steps"].append({"code": "real_model_subagent_mcp", "ok": collaboration_ok, "run_id": run["id"], "run_status": run["status"], **facts})

                dataset = checked(client.post("/api/datasets", headers=headers, json={"name": f"graph-live-{suffix}", "task_type": "chat"}))
                dsid = dataset["id"]
                payload = json.dumps([{"input": "Reply with exactly the five uppercase letters L G O K X joined together, with no punctuation or explanation.", "reference": "LGOKX"}]).encode()
                checked(client.post(f"/api/datasets/{dsid}/import", headers=headers, files={"file": ("graph.json", payload, "application/json")}))
                quality = checked(client.post("/api/quality/run", headers=headers, params={"dataset_id": dsid}))
                checked(client.post(f"/api/datasets/{dsid}/publish", headers=headers))
                session2 = checked(client.post("/api/agents/sessions", headers=headers, json={"requirement": "验证审批和正式评测执行", "objective": "完成一条真实样本评测并生成报告", "planner_model_id": planner_id}))
                sid2 = session2["id"]
                clarified = checked(client.post(f"/api/agents/sessions/{sid2}/clarify", headers=headers, json={
                    "dataset_id": dsid, "model_id": target_id, "trial_run": False, "token_budget": 4096,
                    "judge_resource_id": "builtin/exact_match", "objective": "完成一条真实样本评测并生成报告",
                }))
                if not clarified["plan"].get("ready"):
                    raise RuntimeError("formal_plan_not_ready")
                pending = checked(client.post(f"/api/agents/sessions/{sid2}/runs", headers=headers, json={
                    "message": "方案已就绪。现在必须调用 request_task_execution 请求用户审批，不能自己审批，也不要仅用文字代替工具。",
                    "planner_model_id": planner_id,
                }))
                waiting = pending["status"] == "waiting" and pending["checkpoint"].get("phase") == "await_approval"
                evidence["steps"].append({"code": "real_model_approval_interrupt", "ok": waiting, "run_id": pending["id"]})
                if not waiting:
                    raise RuntimeError("approval_interrupt_not_observed")
                # Human-equivalent explicit confirm API; the graph cannot issue this approval.
                confirmed = checked(client.post(f"/api/agents/sessions/{sid2}/confirm", headers=headers, json={"execute": True, "client_invocation_id": f"live-{suffix}"}))
                again = checked(client.post(f"/api/agents/sessions/{sid2}/confirm", headers=headers, json={"execute": True, "client_invocation_id": f"live-{suffix}"}))
                final = checked(client.post(f"/api/agents/runs/{pending['id']}/resume", headers=headers))
                evidence["steps"].append({
                    "code": "formal_taskservice_execution_and_verification", "ok": final["completion"].get("objective_verified") is True and again.get("idempotent") is True and again["task_id"] == confirmed["task_id"],
                    "task_id": confirmed["task_id"], "confirmation_idempotent": again.get("idempotent") is True and again["task_id"] == confirmed["task_id"],
                    "completion": final["completion"], "run_status": final["status"],
                })
                evidence["ok"] = all(s["ok"] for s in evidence["steps"])
        except Exception as exc:
            # Persist only the exception type: provider errors may contain URLs or credentials.
            evidence["error_type"] = type(exc).__name__
        finally:
            if model_ids:
                asyncio.run(clear_keys(model_ids))
    evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
    path = ROOT.parent / "docs/delivery/evidence/LANGGRAPH-LIVE.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": evidence["ok"], "steps": [{"code": s["code"], "ok": s["ok"]} for s in evidence["steps"]], "error_type": evidence.get("error_type"), "evidence_path": str(path)}))
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
