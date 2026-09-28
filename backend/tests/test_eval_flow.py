import json
import time
import unittest

from tests import isolated_env  # noqa: F401  # 必须在 app.main 之前

from fastapi.testclient import TestClient

from app.main import app
from app.services.builtin_tools import run_builtin_tool
from app.services.dataset_parser import parse_bytes
from app.services.protocol import validate_manifest
from app.services.quality_checker import check_items
from app.services.builtin_manifests import BUILTIN_MANIFESTS


class EvalFlowTest(unittest.TestCase):
    def test_parser_and_quality(self):
        rows = parse_bytes("qa.json", json.dumps([
            {"input": "1+1", "reference": "2"},
            {"question": "首都", "answer": "北京"},
        ]).encode())
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["input_content"], "1+1")
        report = check_items(rows)
        self.assertEqual(report["status"], "passed")

    def test_builtin_judge(self):
        self.assertTrue(run_builtin_tool("builtin/exact_match", {"prediction": "北京", "reference": "北京"})["passed"])
        self.assertFalse(run_builtin_tool("builtin/exact_match", {"prediction": "上海", "reference": "北京"})["passed"])

    def test_manifests_valid(self):
        for mf in BUILTIN_MANIFESTS:
            self.assertEqual(validate_manifest(mf), [])

    def test_end_to_end_eval(self):
        with TestClient(app) as client:
            login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
            self.assertEqual(login.status_code, 200)
            token = login.json()["access_token"]
            h = {"Authorization": f"Bearer {token}"}

            ds = client.post("/api/datasets", json={"name": f"smoke-{int(time.time())}", "task_type": "qa"}, headers=h)
            self.assertEqual(ds.status_code, 200, ds.text)
            ds_id = ds.json()["id"]
            payload = json.dumps([
                {"input": "中国首都", "reference": "北京"},
                {"input": "1+1", "reference": "2"},
            ]).encode()
            imp = client.post(
                f"/api/datasets/{ds_id}/import",
                headers=h,
                files={"file": ("qa.json", payload, "application/json")},
            )
            self.assertEqual(imp.status_code, 200, imp.text)
            self.assertEqual(imp.json()["data_count"], 2)

            q = client.post("/api/quality/run", headers=h, params={"dataset_id": ds_id})
            self.assertEqual(q.status_code, 200, q.text)

            model = client.post("/api/models", json={"name": "mock-llm", "api_url": ""}, headers=h)
            self.assertEqual(model.status_code, 200, model.text)
            model_id = model.json()["id"]

            # 未发布数据集：正式任务应被拒绝
            formal_draft = client.post("/api/tasks", json={
                "name": "formal-draft",
                "dataset_id": ds_id,
                "model_id": model_id,
                "judge_resource_id": "builtin/contains",
            }, headers=h)
            self.assertEqual(formal_draft.status_code, 400, formal_draft.text)
            draft_msg = (formal_draft.json().get("message") or formal_draft.json().get("detail") or "")
            self.assertTrue("发布" in draft_msg or "published" in draft_msg.lower())

            # 发布后门禁：无 endpoint 仍拒绝
            pub = client.post(f"/api/datasets/{ds_id}/publish", headers=h)
            self.assertEqual(pub.status_code, 200, pub.text)
            formal_blocked = client.post("/api/tasks", json={
                "name": "formal-no-endpoint",
                "dataset_id": ds_id,
                "model_id": model_id,
                "judge_resource_id": "builtin/contains",
            }, headers=h)
            self.assertEqual(formal_blocked.status_code, 400, formal_blocked.text)
            msg = (formal_blocked.json().get("message") or formal_blocked.json().get("detail") or "").lower()
            self.assertIn("endpoint", msg)

            prompt = client.post("/api/prompts", json={
                "name": f"qa-prompt-{int(time.time())}",
                "prompt_content": "{{input}}",
            }, headers=h)
            self.assertEqual(prompt.status_code, 200, prompt.text)

            inv = client.post("/api/resources/invoke", json={
                "resource_id": "builtin/exact_match",
                "body": {"prediction": "北京", "reference": "北京"},
            }, headers=h)
            self.assertEqual(inv.status_code, 200, inv.text)
            self.assertEqual(inv.json()["header"]["status"], "ok")
            self.assertEqual(inv.json()["body"]["status"], "success")
            self.assertTrue(inv.json()["body"]["result"].get("passed"))

            task = client.post("/api/tasks", json={
                "name": "smoke-task",
                "dataset_id": ds_id,
                "model_id": model_id,
                "prompt_id": prompt.json()["id"],
                "judge_resource_id": "builtin/contains",
                "trial_run": True,
            }, headers=h)
            self.assertEqual(task.status_code, 200, task.text)
            task_id = task.json()["id"]
            run = client.post(f"/api/tasks/{task_id}/run", headers=h)
            self.assertEqual(run.status_code, 200, run.text)
            status = ""
            detail = {}
            for _ in range(40):
                detail = client.get(f"/api/tasks/{task_id}", headers=h).json()
                status = detail["status"]
                if status in {"success", "failed", "partial_failed"}:
                    break
                time.sleep(0.1)
            self.assertEqual(status, "success", detail)
            self.assertGreaterEqual(detail["total"], 2)
            self.assertTrue(detail.get("simulation") or detail.get("trial_run"))
            results = client.get(f"/api/tasks/{task_id}/results", headers=h)
            self.assertEqual(results.status_code, 200, results.text)
            items = results.json()["items"]
            self.assertGreaterEqual(len(items), 2)
            for row in items:
                self.assertEqual(row.get("score_status"), "scored")
                self.assertEqual(row.get("execution_status"), "ok")
                self.assertIn(row.get("score"), (0.0, 1.0))
            # mock 输出形如 [mock:name] 中国首都 — contains 裁判对 reference=北京/2 通常不通过
            self.assertEqual(detail["success_count"], sum(1 for r in items if r["passed"]))
            lin = client.get(f"/api/tasks/{task_id}/lineage", headers=h)
            self.assertEqual(lin.status_code, 200, lin.text)
            self.assertTrue(lin.json().get("found"))
            self.assertEqual(lin.json()["task_id"], task_id)
            board = client.get("/api/leaderboard", headers=h)
            self.assertEqual(board.status_code, 200)
            stats = client.get("/api/dashboard/stats", headers=h)
            self.assertGreaterEqual(stats.json()["dataset_count"], 1)

    def test_field_mapping_and_quality_gate(self):
        with TestClient(app) as client:
            token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
            h = {"Authorization": f"Bearer {token}"}
            name = f"gate-{int(time.time())}"
            ds = client.post("/api/datasets", json={"name": name}, headers=h)
            self.assertEqual(ds.status_code, 200, ds.text)
            ds_id = ds.json()["id"]
            payload = json.dumps([{"q": "空输入", "a": ""}, {"q": "", "a": ""}]).encode()
            prev = client.post(
                f"/api/datasets/{ds_id}/preview",
                headers=h,
                files={"file": ("bad.json", json.dumps([{"q": "hello", "a": "world"}]).encode(), "application/json")},
            )
            self.assertEqual(prev.status_code, 200, prev.text)
            self.assertIn("q", prev.json()["columns"])
            imp = client.post(
                f"/api/datasets/{ds_id}/import",
                headers=h,
                files={"file": ("bad.json", payload, "application/json")},
                data={"field_mapping": json.dumps({"input_content": "q", "reference_answer": "a"})},
            )
            self.assertEqual(imp.status_code, 200, imp.text)
            q = client.post("/api/quality/run", headers=h, params={"dataset_id": ds_id})
            self.assertEqual(q.status_code, 200, q.text)
            self.assertIn(q.json()["status"], {"failed", "needs_clean", "check_failed"})
            issues = client.get("/api/quality/issues", headers=h, params={"dataset_id": ds_id})
            self.assertGreater(issues.json()["total"], 0)
            model = client.post("/api/models", json={"name": f"m-{name}", "api_url": ""}, headers=h).json()
            # 无 endpoint 的正式任务应被拒绝
            no_ep = client.post("/api/tasks", json={
                "name": "formal-no-endpoint",
                "dataset_id": ds_id,
                "model_id": model["id"],
            }, headers=h)
            self.assertEqual(no_ep.status_code, 400)
            blocked = client.post("/api/tasks", json={
                "name": "formal",
                "dataset_id": ds_id,
                "model_id": model["id"],
            }, headers=h)
            self.assertEqual(blocked.status_code, 400)
            trial = client.post("/api/tasks", json={
                "name": "trial",
                "dataset_id": ds_id,
                "model_id": model["id"],
                "trial_run": True,
            }, headers=h)
            self.assertEqual(trial.status_code, 200, trial.text)
            client.post(f"/api/datasets/{ds_id}/submit", headers=h)
            pending = client.get(f"/api/datasets/{ds_id}", headers=h).json()
            self.assertEqual(pending["status"], "pending")
            client.post(f"/api/datasets/{ds_id}/audit", json={"action": "reject", "comment": "质量不合格"}, headers=h)
            deleted = client.delete(f"/api/datasets/{ds_id}", headers=h)
            self.assertEqual(deleted.status_code, 200)
            self.assertTrue(deleted.json()["logical"])
            listed = client.get("/api/datasets", headers=h, params={"search": name}).json()
            self.assertTrue(all(x["name"] != name for x in listed["items"]))

    def test_model_mapping_acl_and_scene(self):
        from app.services.model_client import extract_path, parse_response, build_request_body
        from app.models.eval_model import EvalModel

        data = {"choices": [{"message": {"content": "北京"}}], "usage": {"total_tokens": 9}}
        self.assertEqual(extract_path(data, "choices.0.message.content"), "北京")
        m = EvalModel(
            name="t",
            response_mapping=json.dumps({"output": "choices.0.message.content", "tokens": "usage.total_tokens"}),
            request_template='{"model":"{{model}}","messages":[{"role":"user","content":"{{prompt}}"}]}',
            served_model_name="demo",
        )
        text, tokens = parse_response(m, data)
        self.assertEqual(text, "北京")
        self.assertEqual(tokens, 9)
        body = build_request_body(m, "首都")
        self.assertEqual(body["model"], "demo")
        self.assertEqual(body["messages"][0]["content"], "首都")

        with TestClient(app) as client:
            token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
            h = {"Authorization": f"Bearer {token}"}
            name = f"mdl-{int(time.time())}"
            created = client.post("/api/models", json={
                "name": name,
                "api_url": "",
                "scene_white_list": ["智能对话"],
                "company_name": "测试企业",
                "parallel_limit": 2,
            }, headers=h)
            self.assertEqual(created.status_code, 200, created.text)
            mid = created.json()["id"]
            self.assertEqual(created.json()["company_name"], "测试企业")
            detail = client.get(f"/api/models/{mid}", headers=h).json()
            self.assertTrue(detail["versions"])
            client.post(f"/api/models/{mid}/versions", json={"version_code": "V2.0", "version_desc": "二版"}, headers=h)
            ds = client.post("/api/datasets", json={"name": f"ds-{name}"}, headers=h).json()
            payload = json.dumps([{"input": "1", "reference": "1"}]).encode()
            client.post(f"/api/datasets/{ds['id']}/import", headers=h, files={"file": ("qa.json", payload, "application/json")})
            blocked = client.post("/api/tasks", json={
                "name": "scene-block",
                "dataset_id": ds["id"],
                "model_id": mid,
                "scene": "qa",
                "trial_run": True,
            }, headers=h)
            self.assertEqual(blocked.status_code, 400)
            ok = client.post("/api/tasks", json={
                "name": "scene-ok",
                "dataset_id": ds["id"],
                "model_id": mid,
                "scene": "智能对话",
                "trial_run": True,
            }, headers=h)
            self.assertEqual(ok.status_code, 200, ok.text)
            inv = client.post(f"/api/models/{mid}/invoke", json={"prompt": "hi"}, headers=h)
            self.assertEqual(inv.status_code, 200, inv.text)
            gone = client.delete(f"/api/models/{mid}", headers=h)
            self.assertTrue(gone.json()["logical"])
            listed = client.get("/api/models", headers=h, params={"search": name}).json()
            self.assertTrue(all(x["name"] != name for x in listed["items"]))

    def test_prompt_generate_audit_and_optimize(self):
        from app.services.prompt_craft import generate_draft, optimize_prompt
        draft = generate_draft("qa", ["准确率"])
        self.assertIn("{{input}}", draft["prompt_content"])
        opt = optimize_prompt("只回答")
        self.assertTrue(opt["changed"])
        self.assertIn("{{input}}", opt["optimized"])

        with TestClient(app) as client:
            token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
            h = {"Authorization": f"Bearer {token}"}
            name = f"pmt-{int(time.time())}"
            gen = client.post("/api/prompts/generate", json={"task_type": "qa", "metrics": ["准确率"]}, headers=h)
            self.assertEqual(gen.status_code, 200, gen.text)
            created = client.post("/api/prompts", json={
                "name": name,
                "prompt_content": gen.json()["prompt_content"],
                "applicable_task": "qa",
            }, headers=h)
            self.assertEqual(created.status_code, 200, created.text)
            pid = created.json()["id"]
            dup = client.post("/api/prompts", json={"name": name, "prompt_content": "{{input}}"}, headers=h)
            self.assertEqual(dup.status_code, 400)
            client.post(f"/api/prompts/{pid}/submit", headers=h)
            self.assertEqual(client.get(f"/api/prompts/{pid}", headers=h).json()["status"], "pending")
            client.post(f"/api/prompts/{pid}/audit", json={"action": "reject", "comment": "再改"}, headers=h)
            self.assertEqual(client.get(f"/api/prompts/{pid}", headers=h).json()["status"], "rejected")
            opt_api = client.post(f"/api/prompts/{pid}/optimize", headers=h)
            self.assertEqual(opt_api.status_code, 200, opt_api.text)
            copied = client.post(f"/api/prompts/{pid}/copy", headers=h)
            self.assertEqual(copied.status_code, 200, copied.text)
            stats = client.get(f"/api/prompts/{pid}/stats", headers=h)
            self.assertEqual(stats.status_code, 200)
            deleted = client.delete(f"/api/prompts/{pid}", headers=h)
            self.assertTrue(deleted.json()["logical"])

    def test_envelope_batch_and_match(self):
        from app.services.protocol import make_envelope, make_response
        env = make_envelope("platform", "builtin/exact_match", {"x": 1}, tenant_id="t1", priority="high")
        self.assertEqual(env["header"]["version"], "1.3")
        self.assertIn("correlation_id", env["header"])
        self.assertIn("ttl", env["header"])
        self.assertIn("traceparent", env["trace"])
        resp = make_response(env, "ok", {"score": 1}, usage={"total_tokens": 0})
        self.assertEqual(resp["header"]["status"], "ok")
        self.assertEqual(resp["body"]["status"], "success")
        self.assertEqual(resp["body"]["result"]["score"], 1)
        self.assertEqual(resp["usage"]["total_tokens"], 0)
        err = make_response(env, "error", {}, error={"code": "X", "message": "fail"})
        self.assertEqual(err["body"]["error"]["code"], "X")
        # 同链 trace 延续
        self.assertEqual(resp["trace"]["trace_id"], env["trace"]["trace_id"])

        with TestClient(app) as client:
            token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
            h = {"Authorization": f"Bearer {token}"}
            ds = client.post("/api/datasets", json={"name": f"bat-{int(time.time())}"}, headers=h)
            ds_id = ds.json()["id"]
            payload = json.dumps([{"input": "1+1", "reference": "2"}, {"input": "2+2", "reference": "4"}]).encode()
            client.post(f"/api/datasets/{ds_id}/import", headers=h, files={"file": ("qa.json", payload, "application/json")})
            run = client.post("/api/batch/run", json={"dataset_id": ds_id, "shard_size": 1}, headers=h)
            self.assertEqual(run.status_code, 200, run.text)
            bid = run.json()["batch_id"]
            sid = run.json()["snapshot_id"]
            self.assertTrue(sid)
            shard = client.get(f"/api/batch/{bid}/shards/0", headers=h, params={"snapshot_id": sid})
            self.assertEqual(shard.status_code, 200, shard.text)
            self.assertEqual(len(shard.json()["items"]), 1)
            put = client.put(f"/api/batch/{bid}/shards/0/results", json={"results": [{"item_no": 1, "score": 1}], "tokens_used": 3}, headers=h)
            self.assertEqual(put.status_code, 200, put.text)
            client.put(f"/api/batch/{bid}/shards/1/results", json={"results": [{"item_no": 2, "score": 1}], "tokens_used": 2}, headers=h)
            st = client.get(f"/api/batch/status/{bid}", headers=h).json()
            self.assertEqual(st["status"], "success")
            matched = client.post("/api/resources/match", json={"judge_type": "exact_match"}, headers=h)
            self.assertGreaterEqual(matched.json()["total"], 1)
            ev = client.get("/api/resources/events", headers=h)
            self.assertEqual(ev.status_code, 200)
            inv = client.post("/api/resources/invoke", json={"resource_id": "builtin/exact_match", "body": {"prediction": "2", "reference": "2"}, "tenant_id": "demo"}, headers=h)
            # 伪造 tenant_id 被 ActorContext 覆盖，不得采信客户端伪造值
            self.assertNotEqual(inv.json()["header"]["tenant_id"], "demo")
            self.assertEqual(inv.json()["header"]["status"], "ok")
            self.assertEqual(inv.json()["body"]["status"], "success")
            self.assertTrue(inv.json()["body"]["result"].get("passed"))
            skill = client.post("/api/resources/invoke", json={"resource_id": "builtin/skill_dual_judge", "body": {"prediction": "北京", "reference": "北京"}}, headers=h)
            self.assertEqual(skill.status_code, 200, skill.text)
            self.assertTrue(skill.json()["body"]["result"]["passed"])
            mcp = client.post("/api/resources/invoke", json={"resource_id": "builtin/mcp_gateway", "body": {"method": "tools/list", "id": 1}}, headers=h)
            mcp_body = mcp.json()["body"]["result"]
            tools = mcp_body.get("tools") or (mcp_body.get("result") or {}).get("tools") or []
            self.assertGreaterEqual(len(tools), 1)
            call = client.post("/api/resources/invoke", json={"resource_id": "builtin/mcp_gateway", "body": {"method": "tools/call", "params": {"name": "builtin/exact_match", "arguments": {"prediction": "2", "reference": "2"}}}}, headers=h)
            call_res = call.json()["body"]["result"]
            passed = call_res.get("passed")
            if passed is None and isinstance(call_res.get("result"), dict):
                passed = call_res["result"].get("passed")
            self.assertTrue(passed)
            reg = client.get("/api/resources/registry", headers=h)
            self.assertEqual(reg.status_code, 200, reg.text)
            self.assertGreaterEqual(reg.json()["total"], 1)

    def test_task_templates_queue_and_report(self):
        from app.services.builtin_tools import run_builtin_tool
        from app.services.task_catalog import catalog_templates
        self.assertEqual(len(catalog_templates()), 33)
        judged = run_builtin_tool("builtin/safety_hallucination", {"prediction": "北京是首都", "reference": "北京"})
        self.assertTrue(judged["passed"])
        with TestClient(app) as client:
            token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
            h = {"Authorization": f"Bearer {token}"}
            tpls = client.get("/api/tasks/templates", headers=h)
            self.assertEqual(tpls.status_code, 200, tpls.text)
            self.assertGreaterEqual(tpls.json()["total"], 33)
            self.assertTrue(any(x.get("pack_dataset_id") for x in tpls.json()["items"]))
            ds = client.post("/api/datasets", json={"name": f"tpl-{int(time.time())}"}, headers=h).json()
            payload = json.dumps([{"input": "AIGC 标识", "reference": "含 AIGC 标识"}]).encode()
            client.post(f"/api/datasets/{ds['id']}/import", headers=h, files={"file": ("qa.json", payload, "application/json")})
            model_id = client.post("/api/models", json={"name": f"m-{int(time.time())}", "api_url": ""}, headers=h).json()["id"]
            first = client.post("/api/tasks", json={
                "name": "dep-src",
                "dataset_id": ds["id"],
                "model_id": model_id,
                "template_code": "safety.watermark",
                "judge_resource_id": "builtin/safety_watermark",
                "trial_run": True,
            }, headers=h)
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.json()["task_type"], "security")
            a_id = first.json()["id"]
            blocked = client.post("/api/tasks", json={
                "name": "dep-wait",
                "dataset_id": ds["id"],
                "model_id": model_id,
                "depends_on_id": a_id,
                "priority": 9,
                "trial_run": True,
            }, headers=h)
            self.assertEqual(blocked.status_code, 200, blocked.text)
            b_id = blocked.json()["id"]
            client.post(f"/api/tasks/{b_id}/run", headers=h)
            b = client.get(f"/api/tasks/{b_id}", headers=h).json()
            self.assertEqual(b["status"], "queued")
            ev = client.get(f"/api/tasks/{b_id}/events", headers=h)
            self.assertEqual(ev.status_code, 200)
            run_a = client.post(f"/api/tasks/{a_id}/run", headers=h)
            self.assertEqual(run_a.status_code, 200, run_a.text)
            status = ""
            detail = {}
            for _ in range(40):
                detail = client.get(f"/api/tasks/{a_id}", headers=h).json()
                status = detail["status"]
                if status in {"success", "failed", "partial_failed"}:
                    break
                time.sleep(0.1)
            self.assertEqual(status, "success", detail)
            report = client.get(f"/api/tasks/{a_id}/report", headers=h)
            self.assertEqual(report.status_code, 200)
            xlsx = client.get(f"/api/tasks/{a_id}/report", headers=h, params={"fmt": "xlsx"})
            self.assertEqual(xlsx.status_code, 200)
            sub = client.get(f"/api/tasks/{a_id}/subtasks", headers=h)
            self.assertGreaterEqual(len(sub.json()["items"]), 1)
            self.assertEqual(client.post(f"/api/tasks/{a_id}/submit", headers=h).status_code, 400)
            alerts = client.get("/api/tasks/alerts", headers=h)
            self.assertGreaterEqual(len(alerts.json()["items"]), 4)

    def test_leaderboard_and_services(self):
        with TestClient(app) as client:
            token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
            h = {"Authorization": f"Bearer {token}"}
            for board in ("overall", "ability", "special", "value"):
                res = client.get("/api/leaderboard", headers=h, params={"board": board})
                self.assertEqual(res.status_code, 200, res.text)
                self.assertIn("items", res.json())
            ref = client.post("/api/leaderboard/refresh", headers=h, params={"board": "overall"})
            self.assertEqual(ref.status_code, 200, ref.text)
            self.assertFalse(ref.json().get("stale"))
            w = client.get("/api/leaderboard/weights", headers=h)
            self.assertGreaterEqual(len(w.json()["items"]), 1)
            exp = client.get("/api/leaderboard/export", headers=h, params={"board": "overall"})
            self.assertEqual(exp.status_code, 200)
            self.assertIn(b"rank", exp.content)
            ws = client.get("/api/services/workspaces", headers=h)
            self.assertEqual(ws.status_code, 200, ws.text)
            wid = (ws.json()["items"] or [{}])[0].get("id")
            created = client.post("/api/services", json={
                "title": f"svc-{int(time.time())}",
                "industry": "finance",
                "requirement": "医疗问答专项评测方案",
                "workspace_id": wid,
            }, headers=h)
            self.assertEqual(created.status_code, 200, created.text)
            self.assertGreater(created.json()["quote_amount"], 0)
            sid = created.json()["id"]
            q = client.post(f"/api/services/{sid}/quote", json={"mode": "expert", "amount": 1200}, headers=h)
            self.assertEqual(q.status_code, 200, q.text)
            self.assertEqual(q.json()["quote_amount"], 1200)
            conf = client.post(f"/api/services/{sid}/confirm", headers=h)
            self.assertEqual(conf.json()["status"], "approved")
            kb = client.get("/api/services/kanban", headers=h)
            self.assertGreaterEqual(kb.json()["total"], 1)
            sh = client.post(f"/api/services/{sid}/shadow", json={
                "gray_version": "v-next",
                "traffic_pct": 0.05,
            }, headers=h)
            self.assertEqual(sh.status_code, 200, sh.text)
            shadow = sh.json()["shadow"]
            self.assertEqual(shadow["returned"], "production")
            self.assertFalse(shadow.get("promotable"))
            # 无服务端成对证据：即使回拨时间窗也不得转正
            import asyncio
            from datetime import datetime, timedelta
            from app.database import async_session
            from app.models import EvalServiceRequest

            async def _age():
                async with async_session() as db:
                    row = await db.get(EvalServiceRequest, sid)
                    row.shadow_started_at = datetime.utcnow() - timedelta(days=8)
                    await db.commit()

            asyncio.run(_age())
            promo = client.post(f"/api/services/{sid}/promote", headers=h)
            self.assertEqual(promo.status_code, 400, promo.text)

    def test_agent_orchestration(self):
        with TestClient(app) as client:
            token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
            h = {"Authorization": f"Bearer {token}"}
            kn = client.get("/api/agents/knowledge", headers=h)
            self.assertEqual(kn.status_code, 200, kn.text)
            self.assertGreaterEqual(kn.json()["total"], 1)
            ds = client.post(
                "/api/datasets",
                json={"name": f"ag-{int(time.time())}", "domain_type": "finance", "tags": ["finance", "金融"]},
                headers=h,
            ).json()
            payload = json.dumps([{"input": "hello", "reference": "world"}]).encode()
            client.post(f"/api/datasets/{ds['id']}/import", headers=h, files={"file": ("qa.json", payload, "application/json")})
            model = client.post(
                "/api/models",
                json={"name": f"ag-m-{int(time.time())}", "api_url": "", "applicable_scenario": "finance"},
                headers=h,
            ).json()
            sess = client.post(
                "/api/agents/sessions",
                json={"requirement": "金融智能对话正式评测", "objective": "金融对话评测", "token_budget": 0},
                headers=h,
            )
            self.assertEqual(sess.status_code, 200, sess.text)
            sid = sess.json()["id"]
            if sess.json()["status"] != "waiting_confirm":
                clar = client.post(
                    f"/api/agents/sessions/{sid}/clarify",
                    json={
                        "dataset_id": ds["id"],
                        "model_id": model["id"],
                        "trial_run": True,
                        "objective": "金融对话评测",
                        "industry": "finance",
                    },
                    headers=h,
                )
                self.assertEqual(clar.status_code, 200, clar.text)
                self.assertTrue(clar.json()["plan"].get("ready"), clar.json()["plan"])
            detail = client.get(f"/api/agents/sessions/{sid}", headers=h)
            self.assertTrue(any(m["role"] == "main" for m in detail.json()["messages"]))
            conf = client.post(f"/api/agents/sessions/{sid}/confirm", json={"execute": False}, headers=h)
            self.assertEqual(conf.status_code, 200, conf.text)
            self.assertTrue(conf.json()["task_id"])
            diag = client.post(f"/api/agents/sessions/{sid}/diagnose", headers=h)
            self.assertEqual(diag.status_code, 200, diag.text)
            self.assertTrue(diag.json()["suggestions"])
            mon = client.get(f"/api/agents/sessions/{sid}/monitor", headers=h)
            self.assertEqual(mon.status_code, 200, mon.text)

    def test_health_metrics_tls_ops(self):
        from app.services.tls_channel import httpx_tls_kwargs

        self.assertEqual(httpx_tls_kwargs("https")["verify"], True)
        self.assertEqual(httpx_tls_kwargs("plain")["verify"], False)
        with self.assertRaises(RuntimeError):
            httpx_tls_kwargs("mtls")

        with TestClient(app) as client:
            health = client.get("/api/health")
            self.assertEqual(health.status_code, 200)
            self.assertTrue(health.json()["ok"])
            self.assertIn("X-Trace-Id", health.headers)
            metrics = client.get("/api/metrics")
            self.assertEqual(metrics.status_code, 200)
            self.assertIn("eval_platform_up", metrics.text)
            denied = client.get("/api/ops/status")
            self.assertIn(denied.status_code, (401, 403))
            login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
            h = {"Authorization": f"Bearer {login.json()['access_token']}"}
            st = client.get("/api/ops/status", headers=h)
            self.assertEqual(st.status_code, 200, st.text)
            bak = client.post("/api/ops/backup", headers=h)
            self.assertEqual(bak.status_code, 200, bak.text)
            self.assertTrue(bak.json()["path"])
            acc = client.get("/api/ops/acceptance", headers=h)
            self.assertEqual(acc.status_code, 200, acc.text)
            body = acc.json()
            self.assertIn(body.get("ok"), (True, False, None))
            for item in body["items"]:
                self.assertIn(item.get("status"), ("measured", "unknown"))
            # templates/packs 应可实测
            by_code = {x["code"]: x for x in body["items"]}
            self.assertEqual(by_code["templates"]["status"], "measured")
            self.assertTrue(by_code["templates"]["ok"], by_code["templates"])
            self.assertEqual(by_code["manifest"]["status"], "unknown")
            self.assertIsNone(by_code["manifest"]["ok"])
            gc = client.post("/api/ops/gc-snapshots", headers=h)
            self.assertEqual(gc.status_code, 200, gc.text)


if __name__ == "__main__":
    unittest.main()
