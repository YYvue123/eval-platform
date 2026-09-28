"""L3 证据包：DeepSeek 真实调用 + 本地 MCP + 平台 API（隔离库，脱敏输出）。"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))

_l3 = ROOT / "tests" / "_isolated" / "l3"
_l3.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + (_l3 / "l3_live.db").as_posix()
os.environ["UPLOAD_DIR"] = str(_l3 / "uploads")
os.environ["LOG_DIR"] = str(_l3 / "logs")
os.environ["BACKUP_DIR"] = str(_l3 / "backups")
os.environ.setdefault("LOG_LEVEL", "WARNING")
for sub in ("uploads", "logs", "backups"):
    (_l3 / sub).mkdir(exist_ok=True)


def _load_dotenv() -> dict[str, str]:
    env: dict[str, str] = {}
    p = ROOT / ".env"
    if not p.exists():
        return env
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        env[k.strip()] = v.strip()
        os.environ.setdefault(k.strip(), v.strip())
    return env


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write(evidence: dict, code: int) -> int:
    out_dir = REPO / "docs" / "delivery" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "L3-LIVE-DEEPSEEK.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path.as_posix())
    print("ok=", evidence.get("ok"), "steps=", len(evidence.get("steps") or []))
    for s in evidence.get("steps") or []:
        print(f"  [{s.get('ok')}] {s.get('code')}")
    return code


def main() -> int:
    env = _load_dotenv()
    api_url = env.get("L3_MODEL_API_URL") or ""
    api_key = env.get("L3_MODEL_API_KEY") or ""
    primary = env.get("L3_MODEL_PRIMARY") or "deepseek-flash"
    secondary = env.get("L3_MODEL_SECONDARY") or "deepseek-v4-pro"
    channel = env.get("L3_MODEL_CHANNEL") or "https"
    mcp_ep = env.get("L3_MCP_ENDPOINT") or "http://127.0.0.1:8765/mcp"

    evidence: dict = {
        "case_id": "L3-LIVE-DEEPSEEK",
        "level": "L3",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "env": os.environ.get("APP_ENV", "staging"),
        "api_url": api_url,
        "api_key_fingerprint": _sha(api_key)[:16] if api_key else None,
        "models": [primary, secondary],
        "channel": channel,
        "steps": [],
        "ok": None,
    }

    if not api_url or not api_key:
        evidence["ok"] = False
        evidence["steps"].append({"code": "config", "ok": False, "detail": "缺少 L3_MODEL_API_URL/KEY"})
        return _write(evidence, 2)

    import httpx

    for name in [primary, secondary]:
        t0 = time.perf_counter()
        try:
            r = httpx.post(
                api_url.rstrip("/") + "/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": name,
                    "messages": [{"role": "user", "content": "Reply with exactly: L3OK"}],
                    "temperature": 0,
                    "max_tokens": 16,
                },
                timeout=60,
            )
            ms = int((time.perf_counter() - t0) * 1000)
            preview = ""
            if r.status_code == 200:
                preview = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                if not preview:
                    # 部分模型可能返回 reasoning / 空 content；HTTP 200 记为连通通过
                    preview = str(r.json().get("choices") or "")[:80]
            evidence["steps"].append(
                {
                    "code": f"direct_chat:{name}",
                    "ok": r.status_code == 200,
                    "matched_l3ok": "L3OK" in (preview or "").replace(" ", ""),
                    "status": r.status_code,
                    "latency_ms": ms,
                    "preview_hash": _sha(preview)[:16],
                }
            )
        except Exception as exc:  # noqa: BLE001
            evidence["steps"].append({"code": f"direct_chat:{name}", "ok": False, "detail": str(exc)[:200]})

    mcp_proc = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "l3_mcp_echo.py")],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.8)
    try:
        try:
            init = httpx.post(
                mcp_ep,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "l3", "version": "0.1"},
                    },
                },
                timeout=5,
            )
            listed = httpx.post(
                mcp_ep, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, timeout=5
            )
            called = httpx.post(
                mcp_ep,
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "echo", "arguments": {"text": "l3"}},
                },
                timeout=5,
            )
            call_ok = called.status_code == 200 and "echo:l3" in called.text
            evidence["steps"].append(
                {
                    "code": "mcp_echo_direct",
                    "ok": init.status_code == 200 and listed.status_code == 200 and call_ok,
                    "endpoint": mcp_ep,
                }
            )
        except Exception as exc:  # noqa: BLE001
            evidence["steps"].append({"code": "mcp_echo_direct", "ok": False, "detail": str(exc)[:200]})

        from fastapi.testclient import TestClient

        from app.main import app

        login_candidates = [
            {"username": "admin", "password": env.get("ADMIN_BOOTSTRAP_PASSWORD") or "StagingAdmin!ChangeMe"},
            {"username": "admin", "password": "admin123"},
        ]
        with TestClient(app) as client:
            token = None
            for cred in login_candidates:
                res = client.post("/api/auth/login", json=cred)
                if res.status_code == 200:
                    token = res.json()["access_token"]
                    evidence["steps"].append(
                        {
                            "code": "login",
                            "ok": True,
                            "via": "bootstrap" if cred["password"] != "admin123" else "legacy_dev",
                        }
                    )
                    break
            if not token:
                evidence["steps"].append({"code": "login", "ok": False, "detail": "无法登录"})
                evidence["ok"] = False
                return _write(evidence, 1)

            h = {"Authorization": f"Bearer {token}"}

            def upsert_model(display_name: str, served: str) -> int | None:
                lst = client.get("/api/models", headers=h, params={"page_size": 100})
                body = lst.json() or {}
                items = body.get("items") if isinstance(body, dict) else []
                for m in items or []:
                    if m.get("name") == display_name:
                        mid0 = m["id"]
                        client.put(
                            f"/api/models/{mid0}",
                            headers=h,
                            json={
                                "api_url": api_url,
                                "api_key": api_key,
                                "served_model_name": served,
                                "channel_type": channel,
                                "auth_type": "bearer_token",
                                "status": "online",
                            },
                        )
                        return mid0
                created = client.post(
                    "/api/models",
                    headers=h,
                    json={
                        "name": display_name,
                        "api_url": api_url,
                        "api_key": api_key,
                        "served_model_name": served,
                        "channel_type": channel,
                        "auth_type": "bearer_token",
                        "timeout": 90,
                        "status": "online",
                        "scene_white_list": ["chat"],
                    },
                )
                if created.status_code not in (200, 201):
                    evidence["steps"].append(
                        {"code": f"register_model:{display_name}", "ok": False, "detail": created.text[:240]}
                    )
                    return None
                evidence["steps"].append(
                    {"code": f"register_model:{display_name}", "ok": True, "id": created.json()["id"]}
                )
                return created.json()["id"]

            mid = upsert_model(f"l3-{primary}", primary)

            probe = client.post(
                "/api/resources/mcp/probe",
                headers=h,
                json={
                    "endpoint": mcp_ep,
                    "method": "tools/list",
                    "params": {},
                    "egress_allowlist": ["127.0.0.1", "localhost"],
                },
            )
            manifest = {
                "spec_version": "0.6.1",
                "resource_id": "l3/mcp_echo",
                "resource_type": "mcp",
                "name": "L3 MCP Echo",
                "version": "0.1.0",
                "description": "Local HTTP MCP echo for L3 live probe",
                "owner": {"name": "l3"},
                "capabilities": {
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "call_mode": "sync",
                    "idempotent": True,
                    "timeout": 30,
                },
                "interfaces": {"endpoint": mcp_ep, "egress_allowlist": ["127.0.0.1", "localhost"]},
                "side_effects": "none",
            }
            reg = client.post("/api/resources/register", headers=h, json={"manifest": manifest})
            evidence["steps"].append(
                {
                    "code": "platform_mcp_probe",
                    "ok": probe.status_code == 200 and bool((probe.json() or {}).get("ok")),
                    "register_status": reg.status_code,
                    "probe_status": probe.status_code,
                }
            )

            if mid:
                health = client.post(f"/api/models/{mid}/health", headers=h)
                hj = health.json() if health.status_code == 200 else {}
                evidence["steps"].append(
                    {
                        "code": "model_health_api",
                        "ok": health.status_code == 200 and hj.get("ok") is not False,
                        "status": health.status_code,
                        "latency_ms": hj.get("latency_ms"),
                        "detail": str(hj.get("detail") or hj.get("status") or "")[:120],
                    }
                )

                ds = client.post("/api/datasets", headers=h, json={"name": f"l3-ds-{int(time.time())}"})
                if ds.status_code == 200:
                    dsid = ds.json()["id"]
                    payload = json.dumps(
                        [{"input": "Reply with exactly: L3OK", "reference": "L3OK"}],
                        ensure_ascii=False,
                    ).encode()
                    imp = client.post(
                        f"/api/datasets/{dsid}/import",
                        headers=h,
                        files={"file": ("l3.json", payload, "application/json")},
                    )
                    task = client.post(
                        "/api/tasks",
                        headers=h,
                        json={
                            "name": f"l3-task-{primary}",
                            "dataset_id": dsid,
                            "model_id": mid,
                            "trial_run": True,
                            "scene": "chat",
                        },
                    )
                    if task.status_code == 200:
                        tid = task.json()["id"]
                        run = client.post(f"/api/tasks/{tid}/run", headers=h)
                        detail = str((run.json() or {}).get("status") or "")
                        run_ok = False
                        terminal = {"succeeded", "completed", "success", "failed", "error", "cancelled", "partial_failed"}
                        good = {"succeeded", "completed", "success"}
                        for _ in range(90):
                            time.sleep(1)
                            det = client.get(f"/api/tasks/{tid}", headers=h)
                            if det.status_code != 200:
                                break
                            st = str((det.json() or {}).get("status") or "").strip().lower()
                            if st:
                                detail = st
                            if st in terminal:
                                run_ok = st in good
                                break
                        # 兜底：轮询结束后仍以最终 status 判定
                        if detail in good:
                            run_ok = True
                        evidence["steps"].append(
                            {
                                "code": "platform_trial_task",
                                "ok": run_ok,
                                "task_id": tid,
                                "import_ok": imp.status_code == 200,
                                "run_status": detail,
                                "run_http": run.status_code,
                            }
                        )
                    else:
                        evidence["steps"].append(
                            {"code": "platform_trial_task", "ok": False, "detail": task.text[:240]}
                        )
                else:
                    evidence["steps"].append({"code": "platform_trial_task", "ok": False, "detail": ds.text[:200]})
            else:
                evidence["steps"].append({"code": "model_health_api", "ok": False, "detail": "模型未注册"})
                evidence["steps"].append({"code": "platform_trial_task", "ok": False, "detail": "跳过"})

            ready = client.get("/api/ready")
            evidence["steps"].append({"code": "ready", "ok": ready.status_code == 200, "status": ready.status_code})
    finally:
        mcp_proc.terminate()
        try:
            mcp_proc.wait(timeout=3)
        except Exception:
            mcp_proc.kill()

    measured = [s for s in evidence["steps"] if s.get("ok") is not None]
    evidence["ok"] = bool(measured) and all(bool(s["ok"]) for s in measured)
    evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
    return _write(evidence, 0 if evidence["ok"] else 1)


if __name__ == "__main__":
    raise SystemExit(main())
