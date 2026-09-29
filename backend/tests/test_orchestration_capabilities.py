"""编排能力：子 Agent、编排 Skill、经验复用，以及 MCP 工具进入打分候选。"""
from __future__ import annotations

import asyncio
import unittest
import uuid

from tests import isolated_env  # noqa: F401

from fastapi.testclient import TestClient

from app.database import async_session
from app.main import app
from app.services.actor_context import ActorContext
from app.services.judge_options import unwrap_judge
from app.services.mcp.catalog import persist_catalog


class KnowledgeCandidateApiTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.assertEqual(login.status_code, 200, login.text)
        self.h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_add_and_delete_pending_candidate(self):
        created = self.client.post(
            "/api/agents/knowledge",
            headers=self.h,
            json={"title": f"候选{uuid.uuid4().hex[:6]}", "content": "失败时先看模型超时", "category": "exception"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        cid = created.json()["id"]
        listed = self.client.get("/api/agents/knowledge/candidates", headers=self.h, params={"status": "pending"})
        self.assertTrue(any(item["id"] == cid for item in listed.json()["items"]))
        deleted = self.client.delete(f"/api/agents/knowledge/candidates/{cid}", headers=self.h)
        self.assertEqual(deleted.status_code, 200, deleted.text)
        again = self.client.get("/api/agents/knowledge/candidates", headers=self.h, params={"status": "all"})
        self.assertFalse(any(item["id"] == cid for item in again.json()["items"]))


class JudgeUnwrapTest(unittest.TestCase):
    def test_nested_mcp_score(self):
        out = unwrap_judge({"jsonrpc": "2.0", "result": {"score": 0.4, "passed": False}})
        self.assertEqual(out["score"], 0.4)
        self.assertFalse(out["passed"])

    def test_missing_score_is_not_a_pass(self):
        with self.assertRaises(RuntimeError):
            unwrap_judge({"content": [{"type": "text", "text": "看起来还行"}]})


class OrchestrationCapabilityApiTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.assertEqual(login.status_code, 200, login.text)
        self.h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_catalog_has_required_and_designed_agents(self):
        res = self.client.get("/api/agents/catalog", headers=self.h)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        roles = {item["role"]: item for item in body["subagents"]}
        self.assertTrue(roles["monitor"]["required"])
        self.assertTrue(roles["diagnose"]["required"])
        for role in ("plan_analyst", "report_reviewer", "param_advisor"):
            self.assertIn(role, roles)
            self.assertFalse(roles[role]["required"])
        codes = {item["code"] for item in body["skills"]}
        self.assertIn("similar_case", codes)
        self.assertEqual(body["knowledge"]["role"], "experience_store")

    def test_bind_skill_and_reuse_recipe(self):
        created = self.client.post(
            "/api/agents/sessions",
            headers=self.h,
            json={
                "requirement": f"复用编排 {uuid.uuid4().hex[:6]}",
                "skill_codes": ["similar_case", "draft_report"],
                "subagent_roles": ["plan_analyst", "report_reviewer"],
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        bound = created.json()["plan"]["capabilities"]
        self.assertEqual(bound["skill_codes"], ["similar_case", "draft_report"])
        for role in ("monitor", "diagnose", "plan_analyst", "report_reviewer"):
            self.assertIn(role, bound["subagent_roles"])
        saved = self.client.post(f"/api/agents/sessions/{created.json()['id']}/recipe", headers=self.h)
        self.assertEqual(saved.status_code, 200, saved.text)
        again = self.client.post(
            "/api/agents/sessions",
            headers=self.h,
            json={"requirement": "沿用上次配置", "recipe_id": saved.json()["id"]},
        )
        self.assertEqual(again.status_code, 200, again.text)
        reused = again.json()["plan"]["capabilities"]
        self.assertEqual(reused["skill_codes"], ["similar_case", "draft_report"])
        self.assertIn("plan_analyst", reused["subagent_roles"])

    def test_custom_agent_and_diagnosis_does_not_recover(self):
        role = f"c_{uuid.uuid4().hex[:8]}"
        created_agent = self.client.post(
            "/api/agents/definitions",
            headers=self.h,
            json={"role": role, "name": "覆盖检查", "system_prompt": "只报告缺口，不创建任务"},
        )
        self.assertEqual(created_agent.status_code, 200, created_agent.text)
        session = self.client.post(
            "/api/agents/sessions",
            headers=self.h,
            json={"requirement": "诊断边界", "subagent_roles": [role]},
        )
        self.assertEqual(session.status_code, 200, session.text)
        sid = session.json()["id"]
        diagnosed = self.client.post(
            f"/api/agents/sessions/{sid}/delegate",
            headers=self.h,
            json={"role": "diagnose"},
        )
        self.assertEqual(diagnosed.status_code, 200, diagnosed.text)
        self.assertEqual(diagnosed.json()["result"]["status"], "no_failure")
        self.assertTrue(diagnosed.json()["result"]["requires_main_approval"])
        custom = self.client.post(
            f"/api/agents/sessions/{sid}/delegate",
            headers=self.h,
            json={"role": role},
        )
        self.assertEqual(custom.status_code, 200, custom.text)
        self.assertFalse(custom.json()["result"].get("executes_recovery", True))

    def test_judges_include_skill_and_mcp_tool(self):
        async def seed():
            async with async_session() as db:
                actor = ActorContext(
                    user_id=1,
                    username="admin",
                    tenant_id=1,
                    role_code="admin",
                    data_scope="all",
                    permissions=set(),
                    is_admin=True,
                )
                await persist_catalog(
                    db,
                    "builtin/mcp_gateway",
                    [{"name": "score_echo", "description": "返回分数", "inputSchema": {"type": "object"}}],
                    changed=False,
                    actor=actor,
                )
                await db.commit()

        asyncio.run(seed())
        res = self.client.get("/api/resources/judges", headers=self.h)
        self.assertEqual(res.status_code, 200, res.text)
        ids = [item["resource_id"] for item in res.json()["items"]]
        self.assertIn("builtin/exact_match", ids)
        self.assertIn("builtin/skill_dual_judge", ids)
        self.assertIn("mcp:builtin/mcp_gateway#score_echo", ids)


class DialogueResourceProposalTest(unittest.TestCase):
    def test_chat_plan_rejects_planner_and_dialogue_can_retarget(self):
        async def run():
            from app.models import AgentSession, BaseResource, Dataset, EvalModel
            from app.services.agent_orchestrator import apply_resource_proposal, draft_plan, search_eval_resources
            from app.utils.jsonutil import dumps

            async with async_session() as db:
                suffix = uuid.uuid4().hex[:8]
                planner = EvalModel(name=f"real06-planner-{suffix}", status="ready", api_url="http://127.0.0.1:9")
                target = EvalModel(
                    name=f"customer-sut-{suffix}",
                    status="ready",
                    api_url="http://127.0.0.1:9",
                    applicable_scenario="chat",
                )
                unrelated = Dataset(
                    name=f"pack-safety-hallucination-{suffix}",
                    status="published",
                    task_type="safety",
                    tags="safety",
                    quality_status="passed",
                )
                chat = Dataset(
                    name=f"客服对话包-{suffix}",
                    status="published",
                    task_type="chat",
                    tags="chat",
                    quality_status="passed",
                )
                judge = BaseResource(
                    resource_id=f"tool/chat-judge-{suffix}",
                    resource_type="tool",
                    name=f"客服打分-{suffix}",
                    status="active",
                    health_status="online",
                )
                db.add_all([planner, target, unrelated, chat, judge])
                await db.flush()

                plan = await draft_plan(
                    db,
                    "客服对话评测",
                    None,
                    token_budget=10,
                    overrides={"exclude_model_ids": [planner.id]},
                )
                self.assertNotEqual(plan.get("model_id"), planner.id)
                self.assertNotEqual(plan.get("dataset_id"), unrelated.id)

                found = await search_eval_resources(db, target.name, "model")
                self.assertTrue(any(item["id"] == target.id for item in found["models"]))
                self.assertFalse(any(item["id"] == planner.id for item in found["models"]))

                session = AgentSession(
                    title="客服对话",
                    requirement="客服对话评测",
                    status="planning",
                    plan_json=dumps(plan),
                    creator_id=1,
                    planner_model_id=planner.id,
                )
                db.add(session)
                await db.flush()
                updated = await apply_resource_proposal(
                    db,
                    session,
                    {"dataset_id": chat.id, "model_id": target.id, "judge_resource_id": judge.resource_id},
                )
                self.assertEqual(updated["dataset_id"], chat.id)
                self.assertEqual(updated["model_id"], target.id)
                self.assertEqual(updated["judge_resource_id"], judge.resource_id)
                with self.assertRaises(ValueError):
                    await apply_resource_proposal(db, session, {"model_id": planner.id})

        asyncio.run(run())


class MainProfileTest(unittest.TestCase):
    def test_descriptor_helpers(self):
        from app.services.agent_capabilities import (
            clip_to_token_budget,
            filter_tool_schemas,
            normalize_model_config,
            normalize_tool_names,
            redact_secrets,
        )

        self.assertEqual(filter_tool_schemas({"a": 1, "b": 2}, ["b"]), {"b": 2})
        self.assertEqual(normalize_tool_names(["nope", "infer_dims"]), ["infer_dims"])
        self.assertEqual(normalize_model_config({"temperature": 9, "max_tokens": -3})["temperature"], 2.0)
        self.assertEqual(normalize_model_config({"max_tokens": -3})["max_tokens"], 0)
        text, clipped = clip_to_token_budget("abcdefghij", 1)
        self.assertTrue(clipped)
        self.assertEqual(len(text), 4)
        self.assertEqual(redact_secrets({"api_key": "sk", "name": "x"})["api_key"], "[redacted]")

    def test_profile_roundtrip(self):
        with TestClient(app) as client:
            login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
            self.assertEqual(login.status_code, 200, login.text)
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            current = client.get("/api/agents/profile", headers=headers)
            self.assertEqual(current.status_code, 200, current.text)
            body = current.json()
            self.assertEqual(body["role"], "coordinator")
            self.assertIn("system_prompt", body)
            self.assertEqual(body["max_iterations"], 10)
            saved = client.put(
                "/api/agents/profile",
                headers=headers,
                json={
                    "system_prompt": "只做编排，不直接打分。",
                    "model_config": {"model_name": "planner-a", "temperature": 0.2, "max_tokens": 128},
                    "available_tools": ["search_knowledge", "propose_resources"],
                    "max_iterations": 10,
                    "supports_stream": True,
                    "human_in_the_loop": True,
                    "evaluation_spec": None,
                    "timeout_seconds": 90,
                },
            )
            self.assertEqual(saved.status_code, 200, saved.text)
            again = client.get("/api/agents/profile", headers=headers)
            data = again.json()
            self.assertEqual(data["system_prompt"], "只做编排，不直接打分。")
            self.assertEqual(data["model_config"]["model_name"], "planner-a")
            self.assertEqual(data["available_tools"], ["search_knowledge", "propose_resources"])
            self.assertTrue(data["supports_stream"])
            self.assertEqual(data["timeout_seconds"], 90)

    def test_subagent_and_skill_crud(self):
        with TestClient(app) as client:
            login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            created = client.post(
                "/api/agents/definitions",
                headers=headers,
                json={
                    "role": "coverage_checker",
                    "name": "覆盖检查",
                    "system_prompt": "只检查覆盖。",
                    "available_tools": ["search_knowledge"],
                    "skill_codes": ["clarify_goal"],
                    "max_iterations": 10,
                },
            )
            self.assertEqual(created.status_code, 200, created.text)
            updated = client.put(
                "/api/agents/definitions/coverage_checker",
                headers=headers,
                json={
                    "role": "coverage_checker",
                    "name": "覆盖检查",
                    "system_prompt": "只检查覆盖。",
                    "available_tools": ["search_knowledge", "infer_dims"],
                    "skill_codes": ["clarify_goal", "similar_case"],
                    "max_iterations": 10,
                },
            )
            self.assertEqual(updated.status_code, 200, updated.text)
            body = updated.json()
            self.assertEqual(body["available_tools"], ["search_knowledge", "infer_dims"])
            self.assertEqual(body["skill_codes"], ["clarify_goal", "similar_case"])
            blocked = client.delete("/api/agents/definitions/monitor", headers=headers)
            self.assertEqual(blocked.status_code, 400, blocked.text)
            removed = client.delete("/api/agents/definitions/coverage_checker", headers=headers)
            self.assertEqual(removed.status_code, 200, removed.text)
            skill = client.put(
                "/api/agents/skills/clarify_goal",
                headers=headers,
                json={
                    "code": "clarify_goal",
                    "name": "目标澄清",
                    "execution_type": "prompt_template",
                    "entry_point": "只列缺口。",
                },
            )
            self.assertEqual(skill.status_code, 200, skill.text)
            self.assertEqual(skill.json()["entry_point"], "只列缺口。")
            hidden = client.delete("/api/agents/skills/similar_case", headers=headers)
            self.assertEqual(hidden.status_code, 200, hidden.text)
            self.assertFalse(hidden.json()["enabled"])
