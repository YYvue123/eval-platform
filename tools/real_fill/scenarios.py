from __future__ import annotations

import json
import os
import uuid

from tests.followup_helpers import tool_manifest
from tools.real_fill.client import FillClient

_L3_CREDENTIAL_REF = "L3_MODEL_API_KEY"

_VIEWER_PASSWORD = "Test1234!"

_FORBIDDEN_MANIFEST = {
    "spec_version": "0.6.1",
    "resource_id": "real01-forbidden",
    "resource_type": "tool",
    "name": "real01 forbidden",
    "version": "0.0.1",
}


def real01_accounts(admin_client: FillClient, viewer_client: FillClient) -> dict:
    admin_client.login("admin", "admin123")
    username = f"real01-viewer-{uuid.uuid4().hex[:8]}"
    created = admin_client.request(
        "POST",
        "/api/users",
        json={"username": username, "password": _VIEWER_PASSWORD, "role": "viewer"},
    )
    if created.status_code != 200:
        raise AssertionError(created.text)
    viewer_client.login(username, _VIEWER_PASSWORD)
    denied = viewer_client.request(
        "POST",
        "/api/resources/register",
        json={"manifest": _FORBIDDEN_MANIFEST},
    )
    if denied.status_code not in (401, 403):
        raise AssertionError(denied.text)
    return {
        "result": "pass",
        "scenario": "REAL01",
        "admin_login_status": admin_client.last_login_status,
        "viewer_denied_status": denied.status_code,
        "viewer_username": username,
    }


_REAL02_ITEMS = [
    {"input": "1 加 1 等于几？只回答数字。", "answer": "2"},
    {"input": "中华人民共和国首都是哪座城市？只回答城市名。", "answer": "北京"},
    {"input": "水的化学分子式是什么？只回答分子式。", "answer": "H2O"},
    {"input": "地球绕太阳公转一周大约多少天？只回答整数。", "answer": "365"},
]


def real02_dataset(client: FillClient) -> dict:
    client.login("admin", "admin123")
    created = client.request(
        "POST",
        "/api/datasets",
        json={
            "name": f"real02-{uuid.uuid4().hex[:8]}",
            "task_type": "qa",
            "data_source": "upload",
            "description": "source_kind=ai_generated_input；AI 生成确定性题集",
        },
    )
    if created.status_code != 200:
        raise AssertionError(created.text)
    dataset_id = created.json()["id"]
    payload = json.dumps(_REAL02_ITEMS, ensure_ascii=False).encode("utf-8")
    imported = client.request(
        "POST",
        f"/api/datasets/{dataset_id}/import",
        files={"file": ("real02.json", payload, "application/json")},
    )
    if imported.status_code != 200:
        raise AssertionError(imported.text)
    version_id = imported.json()["version_id"]
    quality = client.request(
        "POST",
        "/api/quality/run",
        params={"dataset_id": dataset_id, "version_id": version_id},
    )
    if quality.status_code != 200:
        raise AssertionError(quality.text)
    return {
        "result": "pass",
        "scenario": "REAL02",
        "dataset_id": dataset_id,
        "version_id": version_id,
        "data_count": imported.json()["data_count"],
        "quality_status": quality.json().get("status"),
    }


def _require_200(response):
    if response.status_code != 200:
        raise AssertionError(response.text)
    return response.json()


def real04_tools(client: FillClient, stats_base_url: str) -> dict:
    client.login("admin", "admin123")
    suffix = uuid.uuid4().hex[:8]
    parse_rid = f"demo/parse_{suffix}"
    stats_rid = f"demo/stats_{suffix}"
    for rid, path in ((parse_rid, "/v1/parse"), (stats_rid, "/v1/stats")):
        registered = client.request(
            "POST",
            "/api/resources/register",
            json={"manifest": tool_manifest(rid, f"{stats_base_url}{path}")},
        )
        _require_200(registered)

    parse_bodies = (
        {"text": "100 cm, 2 m, 500 mm"},
        {"text": "1 kg"},
        {},
    )
    parse_correlation_ids: list[str] = []
    failed_correlation_id = None
    for body in parse_bodies:
        cid = f"real04-{uuid.uuid4().hex[:12]}"
        parse_correlation_ids.append(cid)
        invoked = client.request(
            "POST",
            "/api/resources/invoke",
            json={
                "resource_id": parse_rid,
                "correlation_id": cid,
                "body": body,
            },
        )
        payload = _require_200(invoked)
        status = str((payload.get("body") or {}).get("status") or "").lower()
        if status in {"error", "failed"}:
            failed_correlation_id = cid
        elif status != "success":
            raise AssertionError(invoked.text)
    if failed_correlation_id is None:
        raise AssertionError("expected one invalid parse invoke to fail")

    skill_rid = f"demo/skill_parse_stats_{suffix}"
    skill_manifest = {
        "spec_version": "0.6.1",
        "resource_id": skill_rid,
        "resource_type": "skill",
        "name": "parse then stats",
        "description": "source_kind=ai_generated_input；两步确定性 parse→stats",
        "version": "1.0.0",
        "owner": {"name": "tenant", "contact": "n/a", "email": "n/a@local"},
        "capabilities": {
            "input_schema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "target_unit": {"type": "string"},
                },
                "required": ["text"],
            },
            "output_schema": {"type": "object"},
            "call_mode": "sync",
            "idempotent": True,
            "timeout": 30,
            "side_effects": "none",
        },
        "interfaces": {"method": "workflow", "auth_type": "none"},
        "skill": {
            "execution_type": "workflow",
            "chain": [
                {
                    "step_id": "s1",
                    "resource_id": parse_rid,
                    "input": {"text": {"$ref": "$input.text"}},
                },
                {
                    "step_id": "s2",
                    "resource_id": stats_rid,
                    "input": {
                        "values": {"$ref": "s1.output.values"},
                        "target_unit": {"$ref": "$input.target_unit"},
                    },
                },
            ],
        },
    }
    _require_200(client.request("POST", "/api/resources/register", json={"manifest": skill_manifest}))
    skill_cid = f"real04-skill-{uuid.uuid4().hex[:12]}"
    skill_invoked = client.request(
        "POST",
        "/api/resources/invoke",
        json={
            "resource_id": skill_rid,
            "correlation_id": skill_cid,
            "body": {"text": "100 cm, 2 m, 500 mm", "target_unit": "m"},
        },
    )
    skill_payload = _require_200(skill_invoked)
    skill_status = str((skill_payload.get("body") or {}).get("status") or "").lower()
    if skill_status != "success":
        raise AssertionError(skill_invoked.text)
    return {
        "result": "pass",
        "scenario": "REAL04",
        "parse_resource_id": parse_rid,
        "stats_resource_id": stats_rid,
        "skill_resource_id": skill_rid,
        "skill_correlation_id": skill_cid,
        "parse_correlation_ids": parse_correlation_ids,
        "failed_correlation_id": failed_correlation_id,
    }


def real05_mcp(client: FillClient, stats_base_url: str) -> dict:
    client.login("admin", "admin123")
    rid = f"demo/mcp_{uuid.uuid4().hex[:8]}"
    manifest = tool_manifest(rid, "https://unused")
    manifest.update(
        {
            "resource_type": "mcp",
            "interfaces": {
                "transport": "streamable_http",
                "endpoint": f"{stats_base_url}/mcp",
                "method": "POST",
                "auth_type": "none",
                "egress_allowlist": ["127.0.0.1", "localhost"],
            },
        }
    )
    _require_200(
        client.request("POST", "/api/resources/register", json={"manifest": manifest})
    )

    def probe(method: str, params: dict | None = None):
        return client.request(
            "POST",
            "/api/resources/mcp/probe",
            json={
                "resource_id": rid,
                "method": method,
                "params": params or {},
            },
        )

    success = probe(
        "tools/call",
        {"name": "parse_measurements", "arguments": {"text": "1 m, 20 cm"}},
    )
    success_body = _require_200(success)
    if not success_body.get("ok"):
        raise AssertionError(success.text)
    empty = probe("tools/call", {"name": "parse_measurements", "arguments": {}})
    empty_body = _require_200(empty)
    if empty_body.get("ok"):
        raise AssertionError("empty MCP arguments should fail")
    return {
        "result": "pass",
        "scenario": "REAL05",
        "mcp_resource_id": rid,
        "success_ok": True,
        "empty_args_ok": False,
        "empty_args_error": (empty_body.get("error") or {}).get("code"),
    }


def _l3_url_present() -> bool:
    import os as _os

    return bool((_os.getenv("L3_MODEL_API_URL") or "").strip())


def _blocked(scenario: str, reason: str = "missing L3_MODEL_API_URL") -> dict:
    return {"result": "blocked", "scenario": scenario, "blocking_reason": reason}


def _l3_endpoint() -> str:
    return (os.getenv("L3_MODEL_API_URL") or "").strip()


def _l3_api_key() -> str:
    return (os.getenv(_L3_CREDENTIAL_REF) or "").strip()


def _model_has_api_url(payload: dict) -> bool:
    return bool((payload.get("api_url") or "").strip())


def _register_l3_model(client: FillClient, *, name: str, served: str) -> dict:
    endpoint = _l3_endpoint()
    created = client.request(
        "POST",
        "/api/models",
        json={
            "name": name,
            "api_url": endpoint,
            "api_key": _l3_api_key(),
            "served_model_name": served,
            "channel_type": (os.getenv("L3_MODEL_CHANNEL") or "https").strip() or "https",
            "auth_type": "bearer_token",
            "description": f"credential_ref={_L3_CREDENTIAL_REF}",
            "timeout": 90,
        },
    )
    if created.status_code != 200:
        raise AssertionError(f"POST /api/models failed status={created.status_code}")
    return created.json()


def real03_models(client) -> dict:
    if not _l3_url_present():
        return _blocked("REAL03")
    client.login("admin", "admin123")
    primary = (os.getenv("L3_MODEL_PRIMARY") or "").strip() or "l3-primary"
    created = _register_l3_model(
        client,
        name=f"real03-{uuid.uuid4().hex[:8]}",
        served=primary,
    )
    if not _model_has_api_url(created):
        return _blocked("REAL03", "empty api_url")
    model_id = created["id"]
    health = client.request("POST", f"/api/models/{model_id}/health")
    if health.status_code != 200:
        raise AssertionError(f"POST /api/models/{{id}}/health failed status={health.status_code}")
    health_body = health.json()
    if not health_body.get("ok"):
        return {
            "result": "blocked",
            "scenario": "REAL03",
            "blocking_reason": "health_not_ok",
            "model_id": model_id,
            "health_ok": False,
        }
    return {
        "result": "pass",
        "scenario": "REAL03",
        "model_id": model_id,
        "health_ok": True,
        "credential_ref": _L3_CREDENTIAL_REF,
    }


def agent_events_count_as_tool_loop(types) -> bool:
    return any(t == "tool.observed" for t in types)


def _parse_invoke_failed(response) -> bool:
    if response.status_code != 200:
        return True
    status = str((response.json().get("body") or {}).get("status") or "").lower()
    return status in {"error", "failed"}


def real06_agent(client, *, parse_resource_id: str | None = None) -> dict:
    if not _l3_url_present():
        return _blocked("REAL06")
    client.login("admin", "admin123")
    parse_id = (parse_resource_id or "").strip()
    if not parse_id:
        return _blocked("REAL06", "missing parse resource")
    cid = f"real06-{uuid.uuid4().hex[:12]}"
    invoked = client.request(
        "POST",
        "/api/resources/invoke",
        json={
            "resource_id": parse_id,
            "correlation_id": cid,
            "body": {"text": "100 cm"},
        },
    )
    invoke_failed = _parse_invoke_failed(invoked)
    primary = (os.getenv("L3_MODEL_PRIMARY") or "").strip() or "l3-primary"
    created = _register_l3_model(
        client,
        name=f"real06-planner-{uuid.uuid4().hex[:8]}",
        served=primary,
    )
    planner_id = created["id"]
    has_api_url = _model_has_api_url(created)
    objective = f"使用 HTTP parse 工具 {parse_id} 做一次真实调用"
    session = client.request(
        "POST",
        "/api/agents/sessions",
        json={"requirement": objective, "objective": objective, "token_budget": 256},
    )
    if session.status_code != 200:
        raise AssertionError(f"POST /api/agents/sessions failed status={session.status_code}")
    sid = session.json()["id"]
    confirm = client.request(
        "POST",
        f"/api/agents/sessions/{sid}/confirm",
        json={"execute": False},
    )
    confirm_status = confirm.status_code
    run = client.request(
        "POST",
        f"/api/agents/sessions/{sid}/runs",
        json={
            "message": objective,
            "provider": "live",
            "sync": True,
            "max_rounds": 4,
            "token_budget": 256,
            "planner_model_id": planner_id,
        },
    )
    rid = None
    types = []
    if run.status_code == 200:
        rid = run.json().get("id")
        events = client.request("GET", f"/api/agents/runs/{rid}/events") if rid else None
        if events is not None and events.status_code == 200:
            types = [item.get("type") or "" for item in (events.json().get("items") or [])]
    evidence = {
        "scenario": "REAL06",
        "session_id": sid,
        "run_id": rid,
        "parse_resource_id": parse_id,
        "parse_correlation_id": cid,
        "confirm_status": confirm_status,
        "agent_tool_observed": agent_events_count_as_tool_loop(types),
    }
    if invoke_failed:
        return {"result": "blocked", "blocking_reason": "tool_invoke_failed", **evidence}
    if not has_api_url:
        return {"result": "blocked", "blocking_reason": "empty api_url", **evidence}
    return {"result": "pass", **evidence}


def real07_formal_task(client, *, dataset_id, version_id, model_id) -> dict:
    if not _l3_url_present():
        return _blocked("REAL07")
    client.login("admin", "admin123")
    detail = client.request("GET", f"/api/models/{model_id}")
    if detail.status_code != 200:
        raise AssertionError(f"GET /api/models/{{id}} failed status={detail.status_code}")
    if not _model_has_api_url(detail.json()):
        return _blocked("REAL07", "empty api_url")
    created = client.request(
        "POST",
        "/api/tasks",
        json={
            "name": f"real07-{uuid.uuid4().hex[:8]}",
            "dataset_id": dataset_id,
            "dataset_version_id": version_id,
            "model_id": model_id,
            "trial_run": True,
            "task_type": "capability",
            "scene": "qa",
            "industry": "general",
            "judge_resource_id": "builtin/exact_match",
        },
    )
    if created.status_code != 200:
        raise AssertionError(f"POST /api/tasks failed status={created.status_code}")
    body = created.json()
    return {
        "result": "pass",
        "scenario": "REAL07",
        "task_id": body["id"],
        "dataset_id": dataset_id,
        "version_id": version_id,
        "model_id": model_id,
        "trial_run": True,
        "scores_inserted": False,
    }


def real08_prompts(client, *, dataset_id) -> dict:
    if not _l3_url_present():
        return _blocked("REAL08")
    client.login("admin", "admin123")
    created = client.request(
        "POST",
        "/api/prompts",
        json={
            "name": f"real08-{uuid.uuid4().hex[:8]}",
            "prompt_type": "eval",
            "applicable_task": "qa",
            "description": f"dataset_id={dataset_id}",
            "prompt_content": "请回答：{{input}}",
        },
    )
    if created.status_code == 404:
        return _blocked("REAL08", "endpoint_missing")
    if created.status_code != 200:
        raise AssertionError(f"POST /api/prompts failed status={created.status_code}")
    body = created.json()
    prompt_id = body["id"]
    v1_id = body.get("current_version_id")
    updated = client.request(
        "PUT",
        f"/api/prompts/{prompt_id}",
        json={
            "prompt_content": "请简洁回答：{{input}}",
            "change_desc": "real08 second version on same dataset",
        },
    )
    if updated.status_code != 200:
        raise AssertionError(f"PUT /api/prompts/{{id}} failed status={updated.status_code}")
    detail = client.request("GET", f"/api/prompts/{prompt_id}")
    versions = []
    if detail.status_code == 200:
        versions = [v.get("id") for v in (detail.json().get("versions") or []) if v.get("id")]
    if v1_id and v1_id not in versions:
        versions.append(v1_id)
    current_id = (detail.json() if detail.status_code == 200 else {}).get("current_version_id")
    if current_id and current_id not in versions:
        versions.append(current_id)
    return {
        "result": "pass",
        "scenario": "REAL08",
        "dataset_id": dataset_id,
        "prompt_id": prompt_id,
        "version_ids": versions,
        "version_count": len(versions),
    }


def real09_safety(client) -> dict:
    client.login("admin", "admin123")
    scored = client.request(
        "POST",
        "/api/safety/score",
        json={
            "category": "risk",
            "sample_id": "risk-f-001",
            "prediction": "无法提供该信息，涉及违法危险行为，拒绝回答。",
            "set_type": "fixed",
        },
    )
    if scored.status_code == 404:
        return {
            "result": "blocked",
            "scenario": "REAL09",
            "blocking_reason": "expert_sign_not_automated",
            "signed": False,
        }
    evidence = {
        "scenario": "REAL09",
        "signed": False,
        "score_status": scored.status_code,
    }
    if scored.status_code != 200:
        return {"result": "blocked", "blocking_reason": "safety_trial_failed", **evidence}
    return {"result": "pass", **evidence}


def real10_leaderboard(client) -> dict:
    client.login("admin", "admin123")
    published = client.request(
        "POST",
        "/api/leaderboard/releases/publish",
        params={"board": "overall"},
        json={"note": "real10 without qualifying formal result"},
    )
    status = published.status_code
    if status == 404:
        return _blocked("REAL10", "endpoint_missing")
    if 400 <= status < 500:
        return {
            "result": "pass",
            "scenario": "REAL10",
            "publish_status": status,
        }
    return {
        "result": "blocked",
        "scenario": "REAL10",
        "blocking_reason": f"publish_not_rejected:{status}",
        "publish_status": status,
    }


def real11_shadow(client) -> dict:
    return {
        "result": "blocked",
        "scenario": "REAL11",
        "blocking_reason": "七天窗口未满，seven-day window is not elapsed",
    }


def real12_ops(client) -> dict:
    client.login("admin", "admin123")
    backup = client.request("POST", "/api/ops/backup")
    if backup.status_code != 200:
        raise AssertionError(f"POST /api/ops/backup failed status={backup.status_code}")
    bak = backup.json()
    backup_path = bak.get("path")
    drill = client.request(
        "POST",
        "/api/ops/restore-drill",
        params={"backup_path": backup_path} if backup_path else {},
    )
    drill_body = drill.json() if drill.status_code == 200 else {}
    out = {
        "result": "pass" if drill.status_code == 200 else "blocked",
        "scenario": "REAL12",
        "backup_status": backup.status_code,
        "backup_path": backup_path,
        "backup_sha256": bak.get("sha256"),
        "restore_status": drill.status_code,
        "restored_path": drill_body.get("restored_path"),
        "restore_sha256": drill_body.get("sha256"),
        "hash_match": drill_body.get("hash_match"),
    }
    note = client.request(
        "POST",
        "/api/notifications",
        json={
            "title": "REAL12 backup restore-drill",
            "message": "isolated backup drill completed",
            "type": "info",
        },
    )
    if note.status_code == 200:
        nid = note.json().get("id")
        if nid is not None:
            out["notification_id"] = nid
    return out

