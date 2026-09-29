# 子项目 C：D5 真实数据填充 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** 用受控 HTTP API 脚本按 REAL01–12 写入已确认目标库，失败保留，缺模型标 blocked。

**Architecture:** `tools/real_fill` 只打 FastAPI；单测用 TestClient + isolated_env。活动库须 `--confirm-fingerprint`。

**Tech Stack:** httpx/TestClient、现有 API、stats_service。

## Global Constraints

- 测试不指向 `eval_platform.db`。
- 不直接 INSERT 评分/success。
- 不打印 API Key。
- 不创建 commit。
- REAL11 未满七天不转正；REAL09 不代签专家。

## 文件

| 路径 | 动作 |
|---|---|
| `tools/real_fill/__init__.py` | 新 |
| `tools/real_fill/client.py` | 新：login、request |
| `tools/real_fill/scenarios.py` | 新：REAL01–12 函数 |
| `tools/real_fill/cli.py` | 新 |
| `backend/tests/test_real_fill.py` | 新 |
| `docs/superpowers/evidence/subproject-c.md` | 新 |

---

### Task 1：填充客户端与 REAL01

**Files:** `tools/real_fill/client.py`、`scenarios.py`（real01）、`backend/tests/test_real_fill.py`

**Interfaces:**
- `FillClient.login(username, password) -> None`
- `real01_accounts(client) -> dict`：登录成功；一次无权限动作期望 403。

测试用 TestClient 管理员登录，viewer 调 `POST /api/resources/register` 期望非 200。不写业务库。

记录文件，不 commit。

---

### Task 2：REAL02 数据集

导入 4 条 AI 生成、`source_kind` 在 description 标明「AI 生成确定性题集」的样本；质检若 API 存在则调用。断言 dataset_id、version_id 返回。测试隔离库。

---

### Task 3：REAL04/05 工具与 MCP

启动 stats_service 子进程（复用 `tests.followup_helpers.stats_service`）。经 API register+invoke parse/stats；注册 MCP `http://127.0.0.1:{port}/mcp` 并 probe+call。无效参数断言 failed。证据 ID 写入返回 dict。

---

### Task 4：REAL03/06/07 模型与 Agent/正式评测

读环境 `L3_MODEL_API_URL` 是否非空（**不要把值写入证据**）。空则函数返回 `{result:'blocked', blocking_reason:'missing L3_MODEL_API_URL'}`。有则：注册/使用已有模型健康探测一次；建 Agent 目标「对 demo/parse_ui 或本脚本注册的工具做一次调用」；正式任务小样本 2 条。无 api_url 禁止标 pass。

测试：无 URL 时 blocked（在测试里 delenv）；不调用付费。

---

### Task 5：REAL08–12

- REAL08：两 prompt 版本同一数据集，无模型则 blocked。
- REAL09：跑已有 safety 试评入口若存在，专家签署不调用。
- REAL10：无合格正式结果则不可发布，断言 4xx。
- REAL11：影子窗口不足 → blocked 文案。
- REAL12：调用已有 `POST /api/ops/backup` 与 restore-drill（隔离库）；通知若可触发则记 ID。

---

### Task 6：CLI 与证据

`python -m tools.real_fill --base-url URL --db PATH --confirm-fingerprint HEX --only REAL01,REAL04`

默认 `--only` 不含活动库。证据 `docs/superpowers/evidence/subproject-c.md` 每场景 result/IDs/blocking_reason。

跑 `unittest tests.test_real_fill tests.test_isolation_guard`。不 commit。

对活动库：仅当指纹匹配且用户本会话要求完成 C。先 REAL01/02/04/05（不依赖付费模型）；03/06/07/08 视 .env。
