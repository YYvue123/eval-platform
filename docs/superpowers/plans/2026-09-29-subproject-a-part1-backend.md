# 子项目 A 实施计划（1/3）：后端基础

> 先读总计划：`docs/superpowers/plans/2026-09-29-subproject-a-d2-closeout.md`。

## Task 1：强制测试隔离

**Files:**
- Modify: `backend/tests/isolated_env.py`
- Create: `backend/tests/test_isolation_guard.py`

**Interfaces:**
- Produces: `assert_isolated_database(url: str) -> Path`
- Rule: SQLite 文件必须位于 `backend/tests/_isolated/`；非 SQLite URL 和业务库路径均拒绝。

- [ ] **Step 1：写失败测试**

```python
# backend/tests/test_isolation_guard.py
import unittest
from pathlib import Path
from tests.isolated_env import assert_isolated_database


class IsolationGuardTest(unittest.TestCase):
    def test_accepts_database_inside_isolated_root(self):
        path = assert_isolated_database(
            "sqlite+aiosqlite:///" + (
                Path(__file__).parent / "_isolated" / "guard.db"
            ).as_posix()
        )
        self.assertEqual(path.name, "guard.db")

    def test_rejects_business_database(self):
        with self.assertRaises(RuntimeError):
            assert_isolated_database("sqlite+aiosqlite:///../eval_platform.db")

    def test_rejects_non_sqlite_database(self):
        with self.assertRaises(RuntimeError):
            assert_isolated_database("postgresql+asyncpg://localhost/eval")
```

- [ ] **Step 2：确认失败**

Run:

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_isolation_guard -v
```

Expected: FAIL，提示无法导入 `assert_isolated_database`。

- [ ] **Step 3：实现强制隔离**

将 `setdefault` 改为显式设置，并在任何 `app` 导入前完成：

```python
# backend/tests/isolated_env.py
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

_ROOT = (Path(__file__).resolve().parent / "_isolated").resolve()
for name in ("uploads", "logs", "backups"):
    (_ROOT / name).mkdir(parents=True, exist_ok=True)


def assert_isolated_database(url: str) -> Path:
    if not url.startswith("sqlite+aiosqlite:///"):
        raise RuntimeError("测试只允许使用 tests/_isolated 内的 SQLite 数据库")
    raw = unquote(urlparse(url).path)
    if os.name == "nt" and raw.startswith("/") and len(raw) > 2 and raw[2] == ":":
        raw = raw[1:]
    path = Path(raw)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()
    try:
        path.relative_to(_ROOT)
    except ValueError as exc:
        raise RuntimeError(f"测试数据库不在隔离目录: {path}") from exc
    return path


candidate = os.environ.get("DATABASE_URL", "")
try:
    assert_isolated_database(candidate)
except RuntimeError:
    candidate = "sqlite+aiosqlite:///" + (_ROOT / "wp00_test.db").as_posix()

os.environ["DATABASE_URL"] = candidate
assert_isolated_database(os.environ["DATABASE_URL"])
os.environ["UPLOAD_DIR"] = str(_ROOT / "uploads")
os.environ["LOG_DIR"] = str(_ROOT / "logs")
os.environ["BACKUP_DIR"] = str(_ROOT / "backups")
os.environ["LOG_LEVEL"] = "WARNING"
```

- [ ] **Step 4：验证隔离**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_isolation_guard -v
.venv\Scripts\python.exe -c "import os; os.environ['DATABASE_URL']='sqlite+aiosqlite:///E:/eval-platform/backend/eval_platform.db'; from tests import isolated_env; print(os.environ['DATABASE_URL'])"
```

Expected: 3 tests PASS；第二条输出路径位于 `backend/tests/_isolated/`。

- [ ] **Step 5：记录文件清单**

记录：`backend/tests/isolated_env.py`、`backend/tests/test_isolation_guard.py`。

## Task 2：修复任务后台调度导致的 SQLite 写锁

**Files:**
- Modify: `backend/app/api/tasks.py`
- Modify: `backend/app/api/agents.py`
- Modify: `backend/tests/test_eval_flow.py`
- Test: `backend/tests/test_eval_flow.py`

**Cause:** `BackgroundTasks` 在响应依赖 `get_db()` 最终提交前执行；当前代码先登记 `dispatch_queue`，随后请求会话继续写审计/消息，后台会话与请求会话争夺 SQLite 写锁。

- [ ] **Step 1：把现有失败留作回归基线**

已有证据：`docs/superpowers/eval_flow_baseline.log` 中两条 `database is locked`，栈进入 `task_service.recover_expired_leases`。

- [ ] **Step 2：先改 Mock 回退的过时断言**

将 `test_model_mapping_acl_and_scene` 末尾改为：

```python
inv = client.post(f"/api/models/{mid}/invoke", json={"prompt": "hi"}, headers=h)
self.assertEqual(inv.status_code, 400, inv.text)
self.assertIn("model_api_url_required", inv.text)
```

Expected: 保留“无 api_url 不允许调用”的负例，不恢复 Mock。

- [ ] **Step 3：调整 Tasks 写入顺序**

`run_task` 和 `retry_task_api` 使用同一顺序：

```python
await enqueue_task(db, t)
await log_audit(
    db, "task", "run",
    user_id=current.id,
    username=current.username,
    target_id=t.id,
    ip=get_client_ip(request),
)
await db.commit()
background.add_task(dispatch_queue, t.id)
return task_out(t)
```

`retry` 使用 action `"retry"`。后台任务登记之后不得再写 `db`。

- [ ] **Step 4：调整 Agents 两处调度顺序**

`confirm_plan` 中先完成 `s.status`、消息、experience、audit，再 `await db.commit()`，最后登记后台任务：

```python
should_dispatch = False
if body.execute:
    await enqueue_task(db, t)
    s.status = "running"
    should_dispatch = True
else:
    s.status = "done"
# add message, archive experience, audit
await db.commit()
if should_dispatch:
    background.add_task(dispatch_queue, t.id)
```

`act_suggestion` 同样先更新状态和队列并提交，最后登记后台任务。

- [ ] **Step 5：运行锁回归**

Run:

```powershell
.venv\Scripts\python.exe -m unittest `
  tests.test_eval_flow.EvalFlowTest.test_end_to_end_eval `
  tests.test_eval_flow.EvalFlowTest.test_task_templates_queue_and_report `
  tests.test_eval_flow.EvalFlowTest.test_model_mapping_acl_and_scene -v
```

Expected: 3 tests PASS，输出无 `database is locked`。

- [ ] **Step 6：记录文件清单**

记录：`backend/app/api/tasks.py`、`backend/app/api/agents.py`、`backend/tests/test_eval_flow.py`。

## Task 3：实现确定性统计核心

**Files:**
- Create: `tools/__init__.py`
- Create: `tools/stats_service/__init__.py`
- Create: `tools/stats_service/core.py`
- Create: `tools/stats_service/tests/__init__.py`
- Create: `tools/stats_service/tests/test_core.py`

**Interfaces:**
- `parse_measurements(text: str) -> list[dict[str, float | str]]`
- `compute_stats(values: list[dict], target_unit: str | None = None) -> dict`

- [ ] **Step 1：写核心失败测试**

```python
from unittest import TestCase
from tools.stats_service.core import compute_stats, parse_measurements


class StatsCoreTest(TestCase):
    def test_parse_then_compute_length(self):
        values = parse_measurements("样本为 100 cm、2 m 和 500 mm")
        result = compute_stats(values, "m")
        self.assertEqual(result["converted"], [1.0, 2.0, 0.5])
        self.assertEqual(result["count"], 3)
        self.assertAlmostEqual(result["mean"], 3.5 / 3)
        self.assertEqual(result["dimension"], "length")

    def test_population_variance(self):
        result = compute_stats(
            [{"value": 1, "unit": "m"}, {"value": 3, "unit": "m"}], "m"
        )
        self.assertEqual(result["variance"], 1.0)

    def test_rejects_mixed_dimensions(self):
        with self.assertRaisesRegex(ValueError, "量纲"):
            compute_stats(
                [{"value": 1, "unit": "m"}, {"value": 1, "unit": "kg"}]
            )

    def test_rejects_non_finite_values(self):
        with self.assertRaisesRegex(ValueError, "有限"):
            compute_stats([{"value": float("nan"), "unit": "m"}])
```

- [ ] **Step 2：确认失败**

Run:

```powershell
cd E:\eval-platform
backend\.venv\Scripts\python.exe -m unittest tools.stats_service.tests.test_core -v
```

Expected: FAIL，模块不存在。

- [ ] **Step 3：实现单位表与纯函数**

`core.py` 采用基准单位倍率：

```python
UNITS = {
    "mm": ("length", 0.001), "cm": ("length", 0.01),
    "m": ("length", 1.0), "km": ("length", 1000.0),
    "mg": ("mass", 0.000001), "g": ("mass", 0.001), "kg": ("mass", 1.0),
    "ms": ("time", 0.001), "s": ("time", 1.0),
    "min": ("time", 60.0), "h": ("time", 3600.0),
}
MEASUREMENT = re.compile(
    r"(?<![\\w.])([-+]?(?:\\d+(?:\\.\\d+)?|\\.\\d+))\\s*"
    r"(mm|cm|km|mg|kg|ms|min|m|g|s|h)\\b",
    re.I,
)
```

实现要求：
- 使用 `math.isfinite`；
- 所有输入转换到 `target_unit` 后计算；
- 总体方差为 `sum((x-mean)**2)/count`；
- 空数组、未知单位、目标单位量纲不一致均抛 `ValueError`；
- 返回值只含 JSON 可序列化类型。

- [ ] **Step 4：运行核心测试**

Run: `backend\.venv\Scripts\python.exe -m unittest tools.stats_service.tests.test_core -v`

Expected: 4 tests PASS。

- [ ] **Step 5：记录文件清单**

记录：`tools/__init__.py`、`tools/stats_service/__init__.py`、`core.py`、核心测试。

## Task 4：提供真实 HTTP 与 MCP 测试服务

**Files:**
- Create: `tools/stats_service/mcp_protocol.py`
- Create: `tools/stats_service/app.py`
- Create: `tools/stats_service/stdio_server.py`
- Create: `tools/stats_service/run.ps1`
- Create: `tools/stats_service/tests/test_http.py`

**Interfaces:**
- HTTP: `GET /health`、`POST /v1/parse`、`POST /v1/stats`
- MCP: `POST/GET/DELETE /mcp`
- stdio: newline-delimited JSON-RPC

- [ ] **Step 1：写 HTTP/MCP 失败测试**

```python
from fastapi.testclient import TestClient
from tools.stats_service.app import app

client = TestClient(app)


def test_http_stats_accepts_platform_envelope():
    response = client.post("/v1/stats", json={
        "body": {"parameters": {
            "values": [{"value": 100, "unit": "cm"}],
            "target_unit": "m",
        }}
    })
    assert response.json()["result"]["converted"] == [1.0]


def test_mcp_catalog_is_paginated():
    init = client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
    })
    sid = init.headers["Mcp-Session-Id"]
    first = client.post(
        "/mcp", headers={"Mcp-Session-Id": sid},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ).json()["result"]
    assert len(first["tools"]) == 1
    assert first["nextCursor"]


def test_mcp_invalid_arguments_return_is_error():
    init = client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
    })
    sid = init.headers["Mcp-Session-Id"]
    headers = {"Mcp-Session-Id": sid}
    client.post("/mcp", headers=headers, json={
        "jsonrpc": "2.0", "method": "notifications/initialized", "params": {},
    })
    response = client.post("/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "compute_stats", "arguments": {"values": []}},
    })
    assert response.json()["result"]["isError"] is True
```

- [ ] **Step 2：实现共享 JSON-RPC 分发器**

`mcp_protocol.py` 提供：

```python
PROTOCOL_VERSION = "2024-11-05"
TOOLS = {
    "parse_measurements": {
        "name": "parse_measurements",
        "description": "从文本提取数值和单位",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "minLength": 1}},
            "required": ["text"],
        },
    },
    "compute_stats": {
        "name": "compute_stats",
        "description": "转换单位并计算描述统计",
        "inputSchema": {
            "type": "object",
            "properties": {
                "values": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "number"},
                            "unit": {"type": "string"},
                        },
                        "required": ["value", "unit"],
                    },
                    "minItems": 1,
                },
                "target_unit": {"type": "string"},
            },
            "required": ["values"],
        },
    },
}

def dispatch(message: dict, sessions: set[str] | None = None) -> tuple[dict | None, dict]:
    """返回 (JSON-RPC response 或 None, metadata)。通知没有 response。"""
```

要求：
- initialize 返回 serverInfo、capabilities.tools.listChanged=true；
- `notifications/initialized` 无响应；
- `tools/list` 每页一个工具，用 `"1"` 作为第二页 cursor；
- `tools/call` 捕获 `ValueError` 并返回 `result.isError=true`，content 中有可操作错误；
- 未知方法返回 JSON-RPC `-32601`。

- [ ] **Step 3：实现 FastAPI 服务**

`POST /v1/parse` 和 `/v1/stats` 必须严格返回：

```python
{"status": "success", "result": result}
```

输入错误返回 HTTP 200：

```python
{"status": "error", "error": {"code": "INVALID_INPUT", "message": str(exc)}}
```

`POST /mcp`：
- initialize 生成 session id，并写响应头 `Mcp-Session-Id`；
- 非 initialize 请求必须携带有效 session；
- `Accept` 含 `text/event-stream` 且 `_meta.stream=true` 时返回 SSE；
- `_meta.announce_list_changed=true` 时先发通知事件；
- `_meta.drop_before_response=true` 时缓存响应并只发送带 `id:` 的通知；`GET /mcp` 携带 `Last-Event-ID` 后返回缓存响应；
- `DELETE /mcp` 删除 session。

- [ ] **Step 4：实现 stdio 与启动脚本**

`stdio_server.py` 从 stdin 逐行读取 JSON，调用共享 `dispatch`，对非通知逐行输出 JSON 并立即 flush。

```powershell
# tools/stats_service/run.ps1
param([int]$Port = 8765)
$root = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $root
& "$root\backend\.venv\Scripts\python.exe" -m uvicorn `
  tools.stats_service.app:app --host 127.0.0.1 --port $Port
```

- [ ] **Step 5：运行服务单测**

Run:

```powershell
backend\.venv\Scripts\python.exe -m unittest `
  tools.stats_service.tests.test_core `
  tools.stats_service.tests.test_http -v
```

Expected: 全部 PASS；测试不启动业务后端、不写业务库。

- [ ] **Step 6：记录文件清单**

记录 Task 4 全部新增文件。

## Task 5：调用证据字段、脱敏与历史 API

**Files:**
- Create: `backend/app/services/redaction.py`
- Modify: `backend/app/models/resource.py`
- Modify: `backend/app/database.py`
- Modify: `backend/app/services/tool_gateway/__init__.py`
- Modify: `backend/app/api/resources.py`
- Create: `backend/tests/followup_helpers.py`
- Create: `backend/tests/test_review_followup_a.py`

**Interfaces:**
- `redact_secrets(value: Any) -> Any`
- `evidence_digest(value: Any, limit: int = 4000) -> tuple[str, str]`
- `GET /api/resources/calls/{rid:path}?page=1&page_size=20&status=`

- [ ] **Step 1：建立集成测试帮助模块**

`followup_helpers.py` 提供：

```python
import contextlib
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def login_admin(client) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def tool_manifest(rid: str, endpoint: str, **overrides) -> dict:
    manifest = {
        "spec_version": "0.6.1",
        "resource_id": rid,
        "resource_type": "tool",
        "name": rid.rsplit("/", 1)[-1],
        "description": "follow-up integration fixture",
        "version": "1.0.0",
        "owner": {"name": "test", "contact": "test", "email": "test@local"},
        "capabilities": {
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "call_mode": "sync",
            "idempotent": True,
            "timeout": 5,
            "side_effects": "none",
        },
        "interfaces": {"endpoint": endpoint, "method": "POST", "auth_type": "none"},
    }
    manifest.update(overrides)
    return manifest


def create_other_tenant_admin(client) -> dict[str, str]:
    # 复用 test_review_followup_d1.ResourceAclTest 中创建 Tenant/User/
    # TenantMembership 的异步数据库步骤，返回该用户登录后的 Authorization header。
    return create_tenant_admin_header(client, prefix="followup-a")

@contextmanager
def stats_service():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    process = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "tools.stats_service.app:app",
            "--host", "127.0.0.1", "--port", str(port),
        ],
        cwd=REPO,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"{base_url}/health", timeout=0.5) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("统计服务未在 10 秒内就绪")
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
```

`create_tenant_admin_header` 从 `test_review_followup_d1.py` 的现有逻辑抽到本模块，函数签名为
`create_tenant_admin_header(client, prefix: str) -> dict[str, str]`；移动时保持
Tenant、User、TenantMembership 与登录断言完整，不复制第二套实现。子进程不传业务数据库配置。

- [ ] **Step 2：写证据与权限失败测试**

在 `test_review_followup_a.py` 添加：

```python
class ResourceCallEvidenceTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        self.headers = login_admin(self.client)

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_success_and_failure_are_persisted_and_paginated(self):
        rid = f"demo/stats-{uuid.uuid4().hex[:8]}"
        with stats_service() as base_url:
            manifest = tool_manifest(rid, f"{base_url}/v1/stats")
            registered = self.client.post(
                "/api/resources/register",
                json={"manifest": manifest},
                headers=self.headers,
            )
            self.assertEqual(registered.status_code, 200, registered.text)
            good = self.client.post(
                "/api/resources/invoke",
                json={
                    "resource_id": rid,
                    "correlation_id": f"good-{uuid.uuid4().hex}",
                    "body": {
                        "values": [{"value": 100, "unit": "cm"}],
                        "target_unit": "m",
                    },
                },
                headers=self.headers,
            )
            bad = self.client.post(
                "/api/resources/invoke",
                json={
                    "resource_id": rid,
                    "correlation_id": f"bad-{uuid.uuid4().hex}",
                    "body": {"values": []},
                },
                headers=self.headers,
            )
        self.assertEqual(good.json()["body"]["status"], "success")
        self.assertEqual(bad.json()["body"]["status"], "error")
        history = self.client.get(
            f"/api/resources/calls/{rid}",
            params={"page": 1, "page_size": 1},
            headers=self.headers,
        )
        self.assertEqual(history.status_code, 200, history.text)
        payload = history.json()
        self.assertEqual(payload["total"], 2)
        self.assertEqual(len(payload["items"]), 1)
        item = payload["items"][0]
        self.assertIn(item["status"], {"success", "failed"})
        self.assertGreaterEqual(item["latency_ms"], 0)
        self.assertEqual(len(item["input_hash"]), 64)
        self.assertNotIn("authorization", item["input_digest"].lower())
        self.assertNotIn("token", item["input_digest"].lower())

    def test_other_tenant_cannot_read_call_history(self):
        rid = f"demo/private-{uuid.uuid4().hex[:8]}"
        manifest = tool_manifest(rid, "https://example.com/tool")
        registered = self.client.post(
            "/api/resources/register",
            json={"manifest": manifest},
            headers=self.headers,
        )
        self.assertEqual(registered.status_code, 200, registered.text)
        other_headers = create_other_tenant_admin(self.client)
        history = self.client.get(
            f"/api/resources/calls/{rid}",
            headers=other_headers,
        )
        self.assertEqual(history.status_code, 404, history.text)
```

- [ ] **Step 3：确认测试失败**

Run:

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest `
  tests.test_review_followup_a.ResourceCallEvidenceTest -v
```

Expected: FAIL，历史路由或字段不存在。

- [ ] **Step 4：实现统一脱敏与摘要**

```python
SECRET_KEYS = {
    "token", "api_key", "apikey", "authorization",
    "secret", "password", "credential",
}

def evidence_digest(value, limit=4000):
    redacted = redact_secrets(value)
    raw = json.dumps(redacted, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return raw[:limit], hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

`resources.py::_redact_manifest` 改为调用 `redact_secrets`，避免两套规则。

- [ ] **Step 5：增加模型列与 SQLite 迁移**

`ResourceCallLog` 增加：

```python
input_digest: Mapped[str] = mapped_column(Text, default="")
output_digest: Mapped[str] = mapped_column(Text, default="")
input_hash: Mapped[str] = mapped_column(String(64), default="")
output_hash: Mapped[str] = mapped_column(String(64), default="")
source: Mapped[str] = mapped_column(String(32), default="gateway")
parent_correlation_id: Mapped[str] = mapped_column(String(128), default="")
```

在 `init_db()` 的兼容迁移列表增加：

```python
("resource_call_logs", "input_digest",
 "ALTER TABLE resource_call_logs ADD COLUMN input_digest TEXT DEFAULT ''"),
("resource_call_logs", "output_digest",
 "ALTER TABLE resource_call_logs ADD COLUMN output_digest TEXT DEFAULT ''"),
("resource_call_logs", "input_hash",
 "ALTER TABLE resource_call_logs ADD COLUMN input_hash VARCHAR(64) DEFAULT ''"),
("resource_call_logs", "output_hash",
 "ALTER TABLE resource_call_logs ADD COLUMN output_hash VARCHAR(64) DEFAULT ''"),
("resource_call_logs", "source",
 "ALTER TABLE resource_call_logs ADD COLUMN source VARCHAR(32) DEFAULT 'gateway'"),
("resource_call_logs", "parent_correlation_id",
 "ALTER TABLE resource_call_logs ADD COLUMN parent_correlation_id VARCHAR(128) DEFAULT ''"),
```

- [ ] **Step 6：所有网关结果写证据**

在 `invoke_tool` 建立局部函数：

```python
def add_call_log(status, *, result=None, error="", source=caller_id):
    input_digest, input_hash = evidence_digest(params)
    output_digest, output_hash = evidence_digest(result or {"error": error})
    db.add(ResourceCallLog(
        resource_id=resource_id,
        task_id=task_id,
        status=status,
        correlation_id=cid,
        parent_correlation_id=correlation_id or "",
        latency_ms=int((time.perf_counter() - started) * 1000),
        error_message=error[:2000],
        tenant_id=tenant_key,
        user_id=actor_user,
        version=rv.version,
        trace_id=trace_id,
        input_digest=input_digest,
        output_digest=output_digest,
        input_hash=input_hash,
        output_hash=output_hash,
        source=source,
    ))
```

blocked、success、failed 都调用它；`started` 必须在副作用判断之前赋值。

- [ ] **Step 7：增加分页历史 API**

在通配详情路由之前新增：

```python
@router.get("/calls/{rid:path}")
async def list_resource_calls(
    rid: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = Query(""),
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("resource:view")),
):
    resource = await _visible_resource(db, rid, actor)
    q = select(ResourceCallLog).where(
        ResourceCallLog.resource_id == resource.resource_id,
        ResourceCallLog.tenant_id == str(actor.tenant_id),
    )
    if status:
        q = q.where(ResourceCallLog.status == status)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (await db.execute(
        q.order_by(ResourceCallLog.id.desc())
         .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {"items": [call_out(row) for row in rows], "total": total or 0}
```

`call_out` 不返回未脱敏原文，只返回 digest、hash、状态、版本、trace、时间。

- [ ] **Step 8：验证**

Run:

```powershell
.venv\Scripts\python.exe -m unittest `
  tests.test_review_followup_a.ResourceCallEvidenceTest `
  tests.test_review_followup_d1.ResourceAclTest -v
```

Expected: PASS。

- [ ] **Step 9：记录文件清单**

记录 Task 5 全部文件。

## Task 6：Skill 每一步经统一网关

**Files:**
- Modify: `backend/app/services/skill_runtime.py`
- Modify: `backend/app/services/tool_gateway/__init__.py`
- Modify: `backend/app/api/resources.py`
- Modify: `backend/tests/test_tool_gateway.py`
- Modify: `backend/tests/test_review_followup_a.py`

**Interfaces:**
- `async run_skill(manifest, body, *, step_invoker) -> dict`
- `step_invoker(step_id: str, resource_id: str, payload: dict) -> Awaitable[dict]`
- `invoke_tool` 新增仅供内部递归保护的关键字参数 `_depth: int = 0`，返回 `dict`

- [ ] **Step 1：写失败测试**

添加三个用例：

```python
class SkillGatewayTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        self.headers = login_admin(self.client)

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def register(self, manifest, headers=None):
        response = self.client.post(
            "/api/resources/register",
            json={"manifest": manifest},
            headers=headers or self.headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_two_step_skill_uses_previous_real_output_and_logs_each_step(self):
        suffix = uuid.uuid4().hex[:8]
        parse_id = f"demo/parse-{suffix}"
        stats_id = f"demo/stats-{suffix}"
        skill_id = f"demo/skill-{suffix}"
        parent_cid = f"skill-{uuid.uuid4().hex}"
        with stats_service() as base_url:
            self.register(tool_manifest(parse_id, f"{base_url}/v1/parse"))
            self.register(tool_manifest(stats_id, f"{base_url}/v1/stats"))
            skill = tool_manifest(skill_id, f"{base_url}/unused")
            skill.update({
                "resource_type": "skill",
                "interfaces": {"method": "workflow", "auth_type": "none"},
                "skill": {
                    "execution_type": "workflow",
                    "chain": [
                        {
                            "step_id": "s1",
                            "resource_id": parse_id,
                            "input": {"text": {"$ref": "$input.text"}},
                        },
                        {
                            "step_id": "s2",
                            "resource_id": stats_id,
                            "input": {
                                "values": {"$ref": "s1.output.values"},
                                "target_unit": {"$ref": "$input.target_unit"},
                            },
                        },
                    ],
                },
            })
            self.register(skill)
            invoked = self.client.post(
                "/api/resources/invoke",
                json={
                    "resource_id": skill_id,
                    "correlation_id": parent_cid,
                    "body": {
                        "text": "100 cm, 2 m, 500 mm",
                        "target_unit": "m",
                    },
                },
                headers=self.headers,
            )
        self.assertEqual(invoked.status_code, 200, invoked.text)
        result = invoked.json()["body"]["result"]["result"]
        self.assertAlmostEqual(result["mean"], 3.5 / 3)
        for resource_id in (parse_id, stats_id):
            history = self.client.get(
                f"/api/resources/calls/{resource_id}",
                headers=self.headers,
            ).json()
            self.assertEqual(history["items"][0]["source"], "skill_step")
            self.assertEqual(
                history["items"][0]["parent_correlation_id"],
                parent_cid,
            )

    def test_skill_step_cannot_invoke_private_tool_from_other_tenant(self):
        rid = f"demo/private-{uuid.uuid4().hex[:8]}"
        self.register(tool_manifest(rid, "https://example.com/tool"))
        other_headers = create_other_tenant_admin(self.client)
        skill = tool_manifest(f"demo/cross-{uuid.uuid4().hex[:8]}", "https://unused")
        skill.update({
            "resource_type": "skill",
            "interfaces": {"method": "workflow", "auth_type": "none"},
            "skill": {
                "execution_type": "workflow",
                "chain": [{"step_id": "s1", "resource_id": rid, "input": {}}],
            },
        })
        response = self.client.post(
            "/api/resources/register",
            json={"manifest": skill},
            headers=other_headers,
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("skill.chain[0]", response.text)

    def test_skill_cannot_nest_skill(self):
        inner_id = f"demo/inner-{uuid.uuid4().hex[:8]}"
        inner = tool_manifest(inner_id, "https://unused")
        inner.update({
            "resource_type": "skill",
            "interfaces": {"method": "workflow", "auth_type": "none"},
            "skill": {
                "execution_type": "workflow",
                "chain": [{
                    "step_id": "s1",
                    "resource_id": "builtin/exact_match",
                    "input": {},
                }],
            },
        })
        self.register(inner)
        outer = tool_manifest(f"demo/outer-{uuid.uuid4().hex[:8]}", "https://unused")
        outer.update({
            "resource_type": "skill",
            "interfaces": {"method": "workflow", "auth_type": "none"},
            "skill": {
                "execution_type": "workflow",
                "chain": [{"step_id": "s1", "resource_id": inner_id, "input": {}}],
            },
        })
        response = self.client.post(
            "/api/resources/register",
            json={"manifest": outer},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("不允许嵌套", response.text)
```

- [ ] **Step 2：确认失败**

Run:

```powershell
.venv\Scripts\python.exe -m unittest `
  tests.test_review_followup_a.SkillGatewayTest -v
```

Expected: 至少第一例 FAIL，现有 `run_skill` 直接调用 builtin。

- [ ] **Step 3：把 Skill runtime 改为异步回调**

核心循环：

```python
async def run_skill(manifest, body, *, step_invoker):
    # 现有 chain/ref 校验保留
    result_envelope = await step_invoker(step_id, rid, payload)
    response_body = result_envelope.get("body") or {}
    if response_body.get("status") != "success":
        error = response_body.get("error") or {}
        raise SkillStepError(step_id, error.get("code", "SKILL_STEP_FAILED"),
                             error.get("message", "步骤执行失败"), steps_out)
    result = response_result(result_envelope)
```

汇总规则：

```python
scores = [
    float(step["result"]["score"])
    for step in steps_out
    if isinstance(step["result"], dict) and step["result"].get("score") is not None
]
passed_values = [
    bool(step["result"]["passed"])
    for step in steps_out
    if isinstance(step["result"], dict) and "passed" in step["result"]
]
return {
    "score": round(sum(scores) / len(scores), 4) if scores else None,
    "passed": all(passed_values) if passed_values else None,
    "metrics": {"steps": len(steps_out), "execution_type": "workflow"},
    "steps": steps_out,
    "result": steps_out[-1]["result"],
}
```

- [ ] **Step 4：网关提供步骤调用闭包**

Skill 分支：

```python
if _depth >= 1:
    raise RuntimeError("Skill 不允许嵌套调用")

async def invoke_step(step_id, step_resource_id, payload):
    return await invoke_tool(
        db,
        actor=actor,
        resource_id=step_resource_id,
        body=payload,
        correlation_id=f"{cid}:{step_id}",
        parent_trace_id=trace_id,
        continue_trace_id=trace_id,
        task_id=task_id,
        caller_id="skill_step",
        _depth=_depth + 1,
    )

result = await run_skill(manifest, params, step_invoker=invoke_step)
```

在 `_persist_idempotent` 前先 `await db.flush()`，确保步骤日志与父日志同事务。

- [ ] **Step 5：注册时拒绝 Skill 嵌套**

在 `register_resource` 校验每个 chain resource_id：
- 必须对 actor 可见；
- 对应资源必须存在且不是 `resource_type == "skill"`；
- 保存的是冻结 `resource_id`；版本冻结由调用时 `ensure_resource_version` 保证。

错误格式：`skill.chain[1] 引用不可用资源 <resource_id>` 或 `Skill 不允许嵌套 Skill`。

- [ ] **Step 6：更新旧同步单测**

`test_tool_gateway.SkillRefTest` 改为 `unittest.IsolatedAsyncioTestCase`，传入仅用于纯函数测试的异步 invoker：

```python
async def builtin_invoker(step_id, resource_id, payload):
    req = make_envelope("test", resource_id, payload)
    return make_response(req, "success", run_builtin_tool(resource_id, payload))
```

这只是隔离单测的 test double；真实集成证据由 `SkillGatewayTest` 的 HTTP 子进程提供。

- [ ] **Step 7：验证**

Run:

```powershell
.venv\Scripts\python.exe -m unittest `
  tests.test_review_followup_a.SkillGatewayTest `
  tests.test_tool_gateway.SkillRefTest `
  tests.test_review_followup_d2.ExecutableRegisterTest -v
```

Expected: PASS；每个 Skill 子步骤可从调用历史查回。

- [ ] **Step 8：记录文件清单**

记录 Task 6 全部文件。
