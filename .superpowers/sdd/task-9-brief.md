# Task 9：统一 MCP runner、探测证据与目录快照

Work from E:\eval-platform. Do not create git commits.

## Controller resolutions

- Credentials: `resolve_credential` must only read `credential_ref` from the environment. Do not send Manifest plaintext tokens even if present.
- Gateway MCP errors: `McpError.code` must appear on the response envelope (not always `TOOL_EXEC_FAILED`). Catch `McpError` distinctly if needed so `exc.code` survives.
- `resource_out` stays sync; attach `mcp_catalog` only in the async GET detail handler.
- Registered probe must call `invoke_tool(..., caller_id="mcp_probe")`. Map probe method/params into the invoke body the gateway already understands for MCP.
- Temporary probe tokens stay in memory only; `ResourceCallLog` digest must not contain the token.
- Keep builtin `builtin/mcp_gateway` local JSON-RPC behavior; remote/stdio go through `services.mcp.run_mcp`.
- Delete `backend/app/services/mcp_client.py` and `RemoteMcpClientTest`.
- `parse_measurements` structuredContent is a list; do not wrap in session layer.
- stdio tests need a Windows loop that can spawn subprocesses (same approach as Task 8 tests).
- `GET /mcp/stdio-aliases` already exists; do not duplicate; keep it before path catch-alls.
- Do not implement frontend Tasks 10–13.

## Global constraints

- isolated_env; never eval_platform.db
- no plaintext secrets in logs/DB/responses
- no commits
- no AsyncMock as live MCP evidence

## Plan text

## Task 9：统一 MCP runner、探测证据与目录快照

**Files:**
- Create: `backend/app/services/mcp/catalog.py`
- Create: `backend/app/services/mcp/runner.py`
- Modify: `backend/app/services/mcp/__init__.py`
- Modify: `backend/app/services/skill_runtime.py`
- Delete: `backend/app/services/mcp_client.py`
- Modify: `backend/app/services/tool_gateway/__init__.py`
- Modify: `backend/app/api/resources.py`
- Modify: `backend/tests/test_tool_gateway.py`
- Modify: `backend/tests/test_review_followup_a.py`

**Interfaces:**
- `async run_mcp(manifest: dict, method: str, params: dict, req_id=1) -> McpRunResult`
- `catalog_hash(tools: list[dict]) -> str`
- `persist_catalog(db, resource_id, tools, *, changed, actor) -> dict`

- [ ] **Step 1：写 runner 与 API 失败测试**

新增：

```python
class McpRunnerApiTest(unittest.TestCase):
    def setUp(self):
        self._cm = TestClient(app)
        self.client = self._cm.__enter__()
        self.headers = login_admin(self.client)
        command = [
            str(Path(sys.executable).resolve()),
            "-m", "tools.stats_service.stdio_server",
        ]
        self.old_allowlist = os.environ.get("MCP_STDIO_ALLOWLIST")
        os.environ["MCP_STDIO_ALLOWLIST"] = json.dumps({"stats-local": command})

    def tearDown(self):
        if self.old_allowlist is None:
            os.environ.pop("MCP_STDIO_ALLOWLIST", None)
        else:
            os.environ["MCP_STDIO_ALLOWLIST"] = self.old_allowlist
        self._cm.__exit__(None, None, None)

    def register_mcp(self, rid, interfaces):
        manifest = tool_manifest(rid, "https://unused")
        manifest.update({
            "resource_type": "mcp",
            "interfaces": interfaces,
        })
        response = self.client.post(
            "/api/resources/register",
            json={"manifest": manifest},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.text)

    def probe(self, rid, method, params=None):
        return self.client.post(
            "/api/resources/mcp/probe",
            json={
                "resource_id": rid,
                "method": method,
                "params": params or {},
            },
            headers=self.headers,
        )

    def test_registered_http_mcp_full_flow_and_probe_log(self):
        rid = f"demo/mcp-http-{uuid.uuid4().hex[:8]}"
        with stats_service() as base_url:
            self.register_mcp(rid, {
                "transport": "streamable_http",
                "endpoint": f"{base_url}/mcp",
                "method": "POST",
            })
            initialized = self.probe(rid, "initialize")
            listed = self.probe(rid, "tools/list")
            called = self.probe(rid, "tools/call", {
                "name": "parse_measurements",
                "arguments": {"text": "1 m, 20 cm"},
            })
        self.assertTrue(initialized.json()["ok"])
        self.assertEqual(
            initialized.json()["session"]["protocol_version"],
            "2024-11-05",
        )
        self.assertTrue(initialized.json()["session"]["session_id_present"])
        self.assertEqual(len(listed.json()["result"]["tools"]), 2)
        self.assertTrue(called.json()["ok"])
        history = self.client.get(
            f"/api/resources/calls/{rid}",
            headers=self.headers,
        ).json()
        self.assertGreaterEqual(history["total"], 3)
        self.assertTrue(all(x["source"] == "mcp_probe" for x in history["items"]))

    def test_registered_stdio_mcp_full_flow(self):
        rid = f"demo/mcp-stdio-{uuid.uuid4().hex[:8]}"
        self.register_mcp(rid, {
            "transport": "stdio",
            "command_alias": "stats-local",
        })
        listed = self.probe(rid, "tools/list")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertTrue(listed.json()["ok"])
        self.assertEqual(len(listed.json()["result"]["tools"]), 2)

    def test_tool_is_error_is_not_green(self):
        rid = f"demo/mcp-error-{uuid.uuid4().hex[:8]}"
        with stats_service() as base_url:
            self.register_mcp(rid, {
                "transport": "streamable_http",
                "endpoint": f"{base_url}/mcp",
                "method": "POST",
            })
            response = self.probe(rid, "tools/call", {
                "name": "compute_stats",
                "arguments": {"values": []},
            })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(response.json()["error"]["code"], "MCP_TOOL_ERROR")
        history = self.client.get(
            f"/api/resources/calls/{rid}",
            headers=self.headers,
        ).json()
        self.assertEqual(history["items"][0]["status"], "failed")

    def test_catalog_change_event_marks_detail_stale(self):
        rid = f"demo/mcp-stale-{uuid.uuid4().hex[:8]}"
        with stats_service() as base_url:
            self.register_mcp(rid, {
                "transport": "streamable_http",
                "endpoint": f"{base_url}/mcp",
                "method": "POST",
            })
            listed = self.probe(rid, "tools/list")
            self.assertTrue(listed.json()["ok"])
            changed = self.probe(rid, "tools/call", {
                "name": "parse_measurements",
                "arguments": {
                    "text": "1 m",
                    "_meta": {"announce_list_changed": True},
                },
            })
            self.assertTrue(changed.json()["ok"])
        detail = self.client.get(
            f"/api/resources/{rid}",
            headers=self.headers,
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertTrue(detail.json()["mcp_catalog"]["stale"])
```

- [ ] **Step 2：实现 transport 工厂与 runner**

```python
def transport_from_manifest(manifest):
    interfaces = manifest.get("interfaces") or {}
    if interfaces.get("transport", "streamable_http") == "stdio":
        return StdioTransport(
            str(interfaces.get("command_alias") or ""),
            timeout=timeout,
        )
    return HttpTransport(
        endpoint,
        auth_token=resolve_credential(interfaces),
        timeout=timeout,
        channel=str(interfaces.get("channel") or "https"),
        manifest=manifest,
    )
```

`run_mcp` 每次创建会话，`try/finally close()`：
- `initialize`：仅 `open()`；
- `tools/list`：open 后聚合分页；
- `tools/call`：open 后调用；
- 其他方法：open 后通过 session 的 `request(method, params)`；
- 返回 dataclass：

```python
@dataclass
class McpRunResult:
    result: dict
    protocol_version: str
    server_info: dict
    session_id_present: bool
    notifications: list[dict]
    catalog_changed: bool
```

- [ ] **Step 3：替换旧运行路径**

`skill_runtime.py` 删除远程 MCP 实现和 `mcp_client` imports，只保留：
- Skill 工作流函数；
- 内置 `builtin/mcp_gateway` 的本地行为（如继续保留）；
- 非内置 MCP 调用委托 `services.mcp.run_mcp`。

`tool_gateway` 的 MCP 分支：

```python
run = await run_mcp(manifest, method, rpc_params, req_id=req_id)
result = run.result
```

任何 `McpError` 必须由通用异常分支记为 failed；响应 error code 使用 `exc.code`，不能统一覆盖成 `TOOL_EXEC_FAILED`：

```python
code = getattr(exc, "code", "TOOL_EXEC_FAILED")
```

- [ ] **Step 4：实现目录 hash 与事件**

```python
def catalog_hash(tools):
    canonical = json.dumps(
        sorted(tools, key=lambda x: x.get("name", "")),
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
```

`persist_catalog` 查询该资源最后一个 `mcp.catalog` 事件：
- 成功 list 写 `mcp.catalog`，payload 只有 hash、count、tool_names、tenant_id；
- hash 改变或 session 收到 list_changed，另写 `mcp.catalog_changed`；
- 不保存工具 schema 中可能出现的 secret default。

`resource_out` 为 MCP 资源追加：

```python
"mcp_catalog": {
    "hash": latest_hash,
    "count": count,
    "observed_at": iso(event.created_at),
    "stale": latest_changed_id > latest_catalog_id,
}
```

由于 `resource_out` 当前是同步函数，目录摘要应由详情接口异步查询后附加，不要在 serializer 内查询数据库。

- [ ] **Step 5：probe 归一与落库**

`McpProbeBody` 增加：

```python
transport: str = "streamable_http"
command_alias: str = ""
```

临时探测：
- HTTP 可传 endpoint/token（token 只在内存使用）；
- stdio 只传 command_alias；
- 两类来源继续互斥。

返回：

```python
{
  "ok": error is None,
  "mode": mode,
  "target": target,
  "transport": transport,
  "probed_at": "2026-09-29T01:00:00Z",
  "session": {
    "protocol_version": run.protocol_version,
    "server_info": run.server_info,
    "session_id_present": run.session_id_present,
  },
  "error": error.as_dict() if error else None,
  "result": run.result if run else None,
  "notifications": run.notifications if run else [],
}
```

已注册资源 probe 调用 `invoke_tool` 时显式传 `caller_id="mcp_probe"`，从而自动落证据。临时探测手动写 `ResourceCallLog(resource_id=f"adhoc-mcp:{host_or_alias}", source="mcp_probe")`，digest 不能包含 token。

- [ ] **Step 6：移除旧 AsyncMock 测试**

删除 `test_tool_gateway.RemoteMcpClientTest` 和 `backend/app/services/mcp_client.py`。保留/更新 builtin MCP 用例；真实协议覆盖由 Task 7–9 子进程测试提供。

- [ ] **Step 7：验证 MCP 后端**

Run:

```powershell
.venv\Scripts\python.exe -m unittest `
  tests.test_review_followup_a.McpHttpTransportTest `
  tests.test_review_followup_a.McpStdioTransportTest `
  tests.test_review_followup_a.McpRunnerApiTest `
  tests.test_tool_gateway.McpSkillApiTest -v
```

Expected: 全部 PASS；HTTP、SSE、恢复、stdio 都使用真实子进程。

- [ ] **Step 8：记录文件清单**

记录 Task 9 全部文件。
