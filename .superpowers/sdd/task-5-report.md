# Task 5 实施报告：调用证据、脱敏与历史 API

## Status

完成。调用网关现在为 success、failed、blocked 三类结果保存脱敏证据、完整
JSON 哈希、实际调用耗时与调用来源；历史接口按资源可见性和调用者 tenant 双重
隔离。Critical 复审后经授权将范围最小扩展到 `http_adapter.py`，关闭 HTTP
200 结构化业务错误从响应、日志和证据泄漏的链路。后续复审进一步改为最小信任
模型：普通异常文本一律不公开，仅显式可信 `public_message` 可进入二次净化。
未修改 D1/D2 修复，未访问业务数据库，未创建 commit。

## TDD 记录

### RED

首次运行指定测试时，新测试因 `app.services.redaction` 不存在而失败：

```text
ModuleNotFoundError: No module named 'app.services.redaction'
Ran 3 tests
FAILED (errors=2)
```

加入最小脱敏实现后再次运行，脱敏测试通过，历史路由仍按通配详情路由处理并返回
404，确认历史 API 尚不存在：

```text
GET /api/resources/calls/... status=404
Ran 4 tests
FAILED (failures=1, errors=1)
```

Critical 复审新增本机真实 HTTP 错误服务，返回嵌套
`token/api_key/authorization`。修复前调用响应直接含原值：

```text
AssertionError: 'token-response-secret' unexpectedly found in response_text
Ran 1 test
FAILED (failures=1)
```

随后先增加结构化/字符串化错误净化函数测试，按 TDD 确认函数尚不存在：

```text
ImportError: cannot import name 'safe_error_message'
Ran 1 test
FAILED (errors=1)
```

escaped JSON 复审先增加两个测试：净化函数尚不存在，同时真实 HTTP 路径中的
escaped secret 穿透调用响应：

```text
ImportError: cannot import name 'redact_error_text'
AssertionError: 'escaped-secret' unexpectedly found in response.text
Ran 2 tests
FAILED (failures=1, errors=1)
```

### GREEN

命令：

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest `
  tests.test_review_followup_a.ResourceCallEvidenceTest `
  tests.test_review_followup_a.RedactionTest `
  tests.test_review_followup_d1.ResourceAclTest `
  tests.test_review_followup_d1.HttpSuccessContractTest `
  tests.test_tool_gateway -v
```

结果：

```text
Ran 29 tests in 19.697s
OK
```

共 29 个测试方法通过：Task 5 当前 8 个、D1 资源 ACL 1 个、D1 HTTP
契约 2 个、`test_tool_gateway` 全模块 18 个。代码库中不存在
`tests.test_tool_gateway.HttpAdapterTest`，因此额外运行 D1 的真实适配器契约
类与 `test_tool_gateway` 全模块。Task 5 的 stats 场景启动 Task 4 uvicorn
子进程；Critical 回归使用本机真实 HTTP 服务，新增测试未使用 Mock。

## 数据库兼容迁移

`resource_call_logs` 新增六个字段，并通过 `init_db()` 现有兼容
`(table, column, sql)` 循环迁移：

- `input_digest TEXT DEFAULT ''`
- `output_digest TEXT DEFAULT ''`
- `input_hash VARCHAR(64) DEFAULT ''`
- `output_hash VARCHAR(64) DEFAULT ''`
- `source VARCHAR(32) DEFAULT 'gateway'`
- `parent_correlation_id VARCHAR(128) DEFAULT ''`

## 脱敏历史 API 示例

```http
GET /api/resources/calls/demo/stats_example?page=1&page_size=20&status=success
```

```json
{
  "items": [
    {
      "resource_id": "demo/stats_example",
      "status": "success",
      "input_digest": "{\"token\":{\"configured\":true,\"redacted\":true},\"values\":[{\"unit\":\"m\",\"value\":1}]}",
      "input_hash": "64-character-sha256",
      "output_digest": "{\"count\":1,\"unit\":\"m\"}",
      "output_hash": "64-character-sha256",
      "source": "gateway",
      "parent_correlation_id": ""
    }
  ],
  "total": 1
}
```

接口实际 item 还包含简报指定的 id、耗时、错误、correlation、tenant/user、
version、trace 和 created_at 字段；不返回原始输入输出。

## 文件

简报限定的 7 个代码/测试文件：

- `backend/app/services/redaction.py`
- `backend/app/models/resource.py`
- `backend/app/database.py`
- `backend/app/services/tool_gateway/__init__.py`
- `backend/app/api/resources.py`
- `backend/tests/followup_helpers.py`
- `backend/tests/test_review_followup_a.py`

Critical 复审授权的额外最小文件：

- `backend/app/services/http_adapter.py`

交付报告：`.superpowers/sdd/task-5-report.md`。

## 自审

- history 路由定义在 `/{rid:path}` 通配详情路由之前。
- 私有资源先经过 `_visible_resource`；内置资源日志仍强制匹配调用者 tenant。
- 输入证据基于规范化 params；输出证据基于 result 或 error 对象。
- hash 基于未截断的完整脱敏 JSON，digest 才执行 4000 字符截断。
- `credential_ref` 保留；`credential` 与其他指定秘密键递归脱敏且不修改原对象。
- started 位于副作用判断前；三种日志均写耗时，blocked/failed 不写幂等成功。
- 父 correlation 只取新增显式参数，未误用当前 correlation。
- failed 优先保留异常 `.code`，否则使用 `TOOL_EXEC_FAILED`。
- HTTP 结构化错误先递归脱敏再 JSON 序列化；不直接 f-string 原始 dict/list。
- escaped JSON/Python 文本先尝试安全解析；无法解析时才使用带明确终止边界的
  保守替换，并保留 `;`、`&`、空白后的诊断字段。
- regex 不再是安全边界：gateway 对无 `public_message` 的任意异常只输出稳定
  通用消息和异常类型，不读取或保存原始 `str(exc)`。
- `HttpToolError` 继承 `RuntimeError` 保持异常语义，其可信 `public_message`
  仅来自结构化脱敏结果或固定文案，并由 gateway 再次净化。
- gateway except 在构造响应、日志和 output evidence 前只生成一次
  `safe_message`，三个出口均不再接触异常原文。
- manifest 脱敏复用统一函数；未新增权限码，历史接口复用 `resource:view`。
- IDE 静态诊断为 0；相关 Python 文件编译检查通过。

## 关注点

- 当前依赖组合运行 TestClient 时仍输出既有 Starlette/httpx 弃用警告，不影响
  测试结果。
- SQLite 兼容迁移沿用现有捕获异常策略；生产迁移工具如后续引入，应同步维护这
  六个字段。
