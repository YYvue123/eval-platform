"""Infrastructure regression only: scripted model responses are not live-model acceptance."""
from __future__ import annotations

from tests import isolated_env  # noqa: F401

import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException

from sqlalchemy import select, func

from app.database import Base, engine, async_session
from app.models import (
    AgentApproval, AgentDefinition, AgentGraphCheckpoint, AgentRun, AgentSession,
    BaseResource, EvalModel, EvalResult, EvalTask, ResourceCallLog, Tenant, User,
)
from app.services import agent_runtime as runtime
from app.services.actor_context import build_actor
from app.services.agent_capabilities import run_subagent
from app.services.agent_graph import task_completion
from app.services.goal_spec import canonical_plan_hash
from app.services.mcp.catalog import persist_catalog
from app.utils.jsonutil import dumps, loads
from tests.followup_helpers import stats_service, tool_manifest


def answer(text="已分析真实工具结果", tokens=7):
    return {"content": text, "tool_calls": [], "tokens": tokens, "finish_reason": "stop"}


def call(name, args, call_id="call_1"):
    return {"content": "", "tokens": 5, "finish_reason": "tool_calls", "tool_calls": [{
        "id": call_id, "type": "function", "function": {"name": name, "arguments": dumps(args)},
    }]}


class LangGraphRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not getattr(type(self), "_tables_ready", False):
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            type(self)._tables_ready = True
        self.db = async_session()
        suffix = uuid.uuid4().hex[:12]
        self.tenant = Tenant(code=f"graph-{suffix}", name="graph isolated test")
        self.db.add(self.tenant)
        await self.db.flush()
        self.user = User(username=f"graph-{suffix}", password_hash="unused", role="admin", tenant_id=self.tenant.id)
        self.db.add(self.user)
        await self.db.flush()
        self.model = EvalModel(name=f"planner-{suffix}", api_url="https://example.invalid/v1", tenant_id=self.tenant.id, creator_id=self.user.id)
        self.db.add(self.model)
        await self.db.flush()
        self.session = AgentSession(
            title="graph", requirement="核对工具结果", tenant_id=self.tenant.id,
            creator_id=self.user.id, planner_model_id=self.model.id,
            plan_json=dumps({"capabilities": {"subagent_roles": ["monitor", "diagnose"], "skill_codes": [], "mcp_resource_ids": []}}),
        )
        self.db.add(self.session)
        await self.db.flush()
        self.actor = await build_actor(self.db, self.user)
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()

    async def create(self, **kwargs):
        return await runtime.create_run(self.db, self.session, message="测试工具调用", **kwargs)

    async def run_graph(self, **kwargs):
        run = await self.create(**kwargs)
        _, token = await runtime.claim_run(self.db, run.id)
        return await runtime.execute_until_idle(self.db, run.id, fencing_token=token)

    async def test_real_graph_keeps_protocol_and_distinguishes_conversation(self):
        async def invoke(model, messages, tools, **kwargs):
            if not any(item["role"] == "tool" for item in messages):
                return call("infer_dims", {"text": "对话"})
            assistant = next(item for item in messages if item.get("tool_calls"))
            self.assertEqual(assistant["tool_calls"][0]["id"], "call_1")
            return answer()

        with patch("app.services.model_client.invoke_chat_tools", side_effect=invoke):
            run = await self.run_graph()
        self.assertEqual(run.status, "success", run.error_message)
        self.assertEqual(run.graph_version, "langgraph-v1")
        self.assertFalse(runtime.run_out(run)["completion"]["objective_verified"])
        self.assertGreater(await self.db.scalar(select(func.count()).select_from(AgentGraphCheckpoint).where(AgentGraphCheckpoint.run_id == run.id)), 2)

    async def test_restart_resumes_next_node_without_repeating_model_or_tool(self):
        invoke = AsyncMock(side_effect=[call("infer_dims", {"text": "对话"}), answer()])
        execute = runtime._execute_tool
        with patch("app.services.model_client.invoke_chat_tools", invoke), patch("app.services.agent_runtime._execute_tool", wraps=execute) as tools:
            run = await self.create()
            _, token = await runtime.claim_run(self.db, run.id)
            await runtime.step_once(self.db, run, fencing_token=token)
            await runtime.step_once(self.db, run, fencing_token=token)
            run.status = "waiting"
            run.lease_until = None
            rid = run.id
            await self.db.commit()
            await self.db.close()
            self.db = async_session()
            run = await self.db.get(AgentRun, rid)
            await runtime.resume_run(self.db, run)
        self.assertEqual(run.status, "success", run.error_message)
        self.assertEqual(invoke.await_count, 2)
        self.assertEqual(tools.await_count, 1)

    async def test_completed_first_tool_not_replayed_when_second_fails(self):
        calls = call("infer_dims", {"text": "对话"})
        calls["tool_calls"].append(call("search_knowledge", {"query": "x"}, "call_2")["tool_calls"][0])
        executed = []

        async def execute(db, run, name, args, schemas):
            executed.append(name)
            if len(executed) == 2:
                raise ValueError("temporary failure")
            return {"count": 0}

        with patch("app.services.model_client.invoke_chat_tools", side_effect=[calls, answer()]), patch("app.services.agent_runtime._execute_tool", side_effect=execute):
            run = await self.run_graph()
            self.assertEqual(run.status, "failed")
            await runtime.resume_run(self.db, run)
        self.assertEqual(run.status, "success", run.error_message)
        self.assertEqual(executed, ["infer_dims", "search_knowledge", "search_knowledge"])

    async def test_real_mcp_http_receives_arguments_and_actor(self):
        with stats_service() as url:
            rid = f"graph/stats_{uuid.uuid4().hex[:8]}"
            manifest = tool_manifest(rid, url, resource_type="mcp", interfaces={"transport": "streamable_http", "endpoint": f"{url}/mcp", "method": "POST"})
            resource = BaseResource(resource_id=rid, resource_type="mcp", name="stats", tenant_id=self.tenant.id, creator_id=self.user.id, manifest_json=dumps(manifest), status="online")
            self.db.add(resource)
            await persist_catalog(self.db, rid, [{"name": "compute_stats", "inputSchema": {
                "type": "object", "properties": {"values": {"type": "array", "items": {
                    "type": "object", "properties": {"value": {"type": "number"}, "unit": {"type": "string"}},
                    "required": ["value", "unit"],
                }}}, "required": ["values"],
            }}], changed=False, actor=self.actor)
            plan = loads(self.session.plan_json, {})
            plan["capabilities"]["mcp_resource_ids"] = [rid]
            self.session.plan_json = dumps(plan)
            invalid_call = call("call_mcp", {"resource_id": rid, "tool_name": "compute_stats", "arguments": {"values": [{"value": 2, "unit": "meters"}]}})
            fixed_call = call("call_mcp", {"resource_id": rid, "tool_name": "compute_stats", "arguments": {"values": [{"value": v, "unit": "m"} for v in [2, 4, 6]]}}, "call_fixed")
            with patch("app.services.model_client.invoke_chat_tools", side_effect=[invalid_call, fixed_call, answer()]):
                run = await self.run_graph()
            self.assertEqual(run.status, "success", run.error_message)
            observations = loads(run.checkpoint_json, {})["observations"]
            self.assertIn("error", observations[0]["result"])
            result = observations[-1]["result"]["result"]
            self.assertIn("4", dumps(result))
            log = await self.db.scalar(select(ResourceCallLog).where(ResourceCallLog.resource_id == rid))
            self.assertEqual(log.user_id, self.user.id)
            self.assertEqual(log.tenant_id, str(self.tenant.id))

    async def test_mcp_schema_rejects_missing_required_argument(self):
        plan = loads(self.session.plan_json, {})
        plan["capabilities"]["mcp_resource_ids"] = ["graph/schema"]
        self.session.plan_json = dumps(plan)
        await persist_catalog(self.db, "graph/schema", [{"name": "calc", "inputSchema": {"type": "object", "required": ["values"]}}], changed=False, actor=self.actor)
        with patch("app.services.model_client.invoke_chat_tools", return_value=call("call_mcp", {"resource_id": "graph/schema", "tool_name": "calc", "arguments": {}})), patch("app.services.tool_gateway.invoke_tool") as gateway:
            run = await self.run_graph()
        self.assertEqual(run.error_code, "tool_failed")
        gateway.assert_not_called()

    async def test_custom_subagent_uses_model_and_tool_loop(self):
        role = f"expert_{uuid.uuid4().hex[:8]}"
        spec = AgentDefinition(role=role, name="专家", system_prompt="分析行业", available_tools_json=dumps(["infer_dims"]), tenant_id=self.tenant.id, creator_id=self.user.id)
        self.db.add(spec)
        plan = loads(self.session.plan_json, {})
        plan["capabilities"]["subagent_roles"].append(role)
        self.session.plan_json = dumps(plan)
        await self.db.flush()
        # Main -> child model -> child tool -> child answer -> main answer.
        responses = [call("delegate_agent", {"role": role, "input": "判断对话场景"}), call("infer_dims", {"text": "对话"}, "child_1"), answer("子 Agent 的实际分析"), answer("主 Agent 汇总")]
        with patch("app.services.model_client.invoke_chat_tools", side_effect=responses) as invoke:
            run = await self.run_graph()
        self.assertEqual(run.status, "success", run.error_message)
        child = loads(run.checkpoint_json, {})["observations"][0]["result"]["result"]
        self.assertEqual(child["summary"], "子 Agent 的实际分析")
        self.assertEqual(child["tool_calls"], 1)
        self.assertEqual(invoke.await_count, 4)
        self.assertEqual(run.tokens_used, 24)

    async def test_subagent_cannot_write_plan_or_delegate(self):
        role = f"expert_{uuid.uuid4().hex[:8]}"
        self.db.add(AgentDefinition(role=role, name="专家", available_tools_json=dumps(["propose_resources", "delegate_agent"]), tenant_id=self.tenant.id, creator_id=self.user.id))
        plan = loads(self.session.plan_json, {})
        plan["capabilities"]["subagent_roles"].append(role)
        self.session.plan_json = dumps(plan)
        await self.db.flush()
        with patch("app.services.model_client.invoke_chat_tools", side_effect=[call("delegate_agent", {"role": role}), call("propose_resources", {"dataset_id": 1}, "child_bad")]):
            run = await self.run_graph()
        self.assertEqual(run.status, "failed")
        self.assertNotIn("dataset_id", loads(self.session.plan_json, {}))

    async def test_approval_interrupt_cannot_resume_without_consumed_approval(self):
        plan = loads(self.session.plan_json, {})
        plan["ready"] = True
        self.session.plan_json = dumps(plan)
        with patch("app.services.model_client.invoke_chat_tools", return_value=call("request_task_execution", {})):
            run = await self.run_graph()
        self.assertEqual(run.status, "waiting", run.error_message)
        self.assertEqual(loads(run.checkpoint_json, {})["phase"], "await_approval")
        await runtime.resume_run(self.db, run)
        self.assertEqual(run.status, "waiting")
        self.assertIsNone(self.session.task_id)
        task = await self.make_task(status="queued")
        self.db.add(AgentApproval(session_id=self.session.id, tenant_id=self.tenant.id, plan_hash=canonical_plan_hash(plan), status="consumed", consumed_task_id=task.id))
        await self.db.flush()
        await runtime.resume_run(self.db, run)
        self.assertEqual(run.status, "waiting", run.error_message)
        self.assertEqual(loads(run.checkpoint_json, {})["phase"], "verify")
        task.status = "failed"  # Synthetic failure fixture, never formal evaluation evidence.
        await self.db.flush()
        await runtime.resume_run(self.db, run)
        self.assertEqual(run.status, "failed", run.error_message)
        self.assertEqual(run.error_code, "evaluation_task_failed")

    async def make_task(self, **kwargs):
        task = EvalTask(name="synthetic verification fixture", dataset_id=0, model_id=self.model.id, tenant_id=self.tenant.id, creator_id=self.user.id, **kwargs)
        self.db.add(task)
        await self.db.flush()
        self.session.task_id = task.id
        return task

    async def test_success_status_without_measured_results_is_unverified(self):
        await self.make_task(status="success", total=1, report_path="fixture.json", trial_run=False)
        run = await self.create()
        result = await task_completion(self.db, run)
        self.assertFalse(result["objective_verified"])
        self.assertEqual(result["measured_results"], 0)

    async def test_trial_and_simulated_results_never_verify_formal_execution(self):
        task = await self.make_task(status="success", total=1, report_path="fixture.json", trial_run=True)
        self.db.add(EvalResult(task_id=task.id, execution_status="ok", score_status="scored", simulation=True))
        await self.db.flush()
        result = await task_completion(self.db, await self.create())
        self.assertFalse(result["objective_verified"])

    async def test_unknown_usage_and_budget_apply_to_children(self):
        role = f"expert_{uuid.uuid4().hex[:8]}"
        self.db.add(AgentDefinition(role=role, name="专家", tenant_id=self.tenant.id, creator_id=self.user.id))
        plan = loads(self.session.plan_json, {})
        plan["capabilities"]["subagent_roles"].append(role)
        self.session.plan_json = dumps(plan)
        await self.db.flush()
        with patch("app.services.model_client.invoke_chat_tools", side_effect=[call("delegate_agent", {"role": role}), answer(tokens=100)]):
            run = await self.run_graph(token_budget=10)
        self.assertEqual(run.status, "paused_budget", run.error_message)

    async def test_stale_fencing_token_cannot_advance(self):
        run = await self.create()
        _, token = await runtime.claim_run(self.db, run.id)
        with self.assertRaises(HTTPException) as error:
            await runtime.step_once(self.db, run, fencing_token=token - 1)
        self.assertEqual(error.exception.status_code, 409)
        rid = run.id
        await self.db.commit()
        from sqlalchemy import update
        async with async_session() as replacement:
            await replacement.execute(update(AgentRun).where(AgentRun.id == rid).values(fencing_token=token + 1))
            await replacement.commit()
        # The cached ORM token is intentionally stale; the database check must catch it.
        with patch("app.services.model_client.invoke_chat_tools") as invoke:
            with self.assertRaises(HTTPException) as error:
                await runtime.step_once(self.db, run, fencing_token=token)
        self.assertEqual(error.exception.status_code, 409)
        invoke.assert_not_called()
        await self.db.rollback()

    async def test_disabled_creator_cannot_continue(self):
        run = await self.create()
        self.user.status = "disabled"
        await self.db.flush()
        with patch("app.services.model_client.invoke_chat_tools") as invoke:
            _, token = await runtime.claim_run(self.db, run.id)
            await runtime.step_once(self.db, run, fencing_token=token)
        self.assertEqual(run.status, "failed")
        invoke.assert_not_called()

    async def test_runtime_cannot_call_other_tenant_mcp(self):
        rid = f"graph/other_{uuid.uuid4().hex[:8]}"
        self.db.add(BaseResource(resource_id=rid, name="foreign", resource_type="mcp", status="online", tenant_id=self.tenant.id + 100000, creator_id=self.user.id))
        await persist_catalog(self.db, rid, [{"name": "read", "inputSchema": {"type": "object"}}], changed=False, actor=self.actor)
        plan = loads(self.session.plan_json, {})
        plan["capabilities"]["mcp_resource_ids"] = [rid]  # Deliberately corrupted binding fixture.
        self.session.plan_json = dumps(plan)
        with patch("app.services.model_client.invoke_chat_tools", return_value=call("call_mcp", {"resource_id": rid, "tool_name": "read", "arguments": {}})):
            run = await self.run_graph()
        self.assertEqual(run.status, "failed")
        count = await self.db.scalar(select(func.count(ResourceCallLog.id)).where(ResourceCallLog.resource_id == rid))
        self.assertEqual(count, 0)

    async def test_subagent_without_model_never_returns_prompt_as_result(self):
        role = f"expert_{uuid.uuid4().hex[:8]}"
        self.db.add(AgentDefinition(role=role, name="expert", system_prompt="不是分析结果", tenant_id=self.tenant.id, creator_id=self.user.id))
        plan = loads(self.session.plan_json, {})
        plan["capabilities"]["subagent_roles"].append(role)
        self.session.plan_json = dumps(plan)
        self.session.planner_model_id = None
        await self.db.flush()
        with self.assertRaises(HTTPException) as error:
            await run_subagent(self.db, self.session, self.actor, role)
        self.assertEqual(error.exception.status_code, 400)

    async def test_empty_tool_whitelist_is_not_replaced_by_default_tools(self):
        self.assertEqual(runtime._openai_tools({}), [])
        with self.assertRaises(ValueError):
            runtime._validate_tool_args("infer_dims", {"text": "x"}, {})

    async def test_checkpoint_rolls_back_with_business_transaction(self):
        run = await self.create()
        rid = run.id
        await self.db.commit()
        _, token = await runtime.claim_run(self.db, rid)
        with patch("app.services.model_client.invoke_chat_tools", return_value=answer()):
            await runtime.step_once(self.db, run, fencing_token=token)
        self.assertGreater(await self.db.scalar(select(func.count(AgentGraphCheckpoint.run_id)).where(AgentGraphCheckpoint.run_id == rid)), 0)
        await self.db.rollback()
        count = await self.db.scalar(select(func.count(AgentGraphCheckpoint.run_id)).where(AgentGraphCheckpoint.run_id == rid))
        self.assertEqual(count, 0)

    async def test_worker_executes_queued_run_and_recovers_expired_lease(self):
        from app.services.agent_worker import dispatch_agent_once

        run = await self.create()
        run.status = "running"
        run.lease_until = datetime.utcnow() - timedelta(seconds=1)
        rid = run.id
        await self.db.commit()
        with patch("app.services.model_client.invoke_chat_tools", return_value=answer()):
            for _ in range(4):
                await dispatch_agent_once(run_id=rid)
        await self.db.refresh(run)
        self.assertEqual(run.id, rid)
        self.assertEqual(run.status, "success", run.error_message)
