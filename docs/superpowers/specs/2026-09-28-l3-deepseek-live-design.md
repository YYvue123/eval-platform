# WP L3 预发 / DeepSeek 真实联调 — Design

**Goal:** 在 `APP_ENV=staging` 下用 DeepSeek OpenAI 兼容接口跑通 1 条真实模型链路 + 1 个本地 HTTP MCP 协议端点，产出可复跑证据包；密钥仅存 `backend/.env`（gitignore）。

**非目标:** L4 压测、生产 mTLS 企业证书、宣称全量规格验收通过。

## Approach

1. `.env`：`L3_MODEL_*` + staging 引导密码。
2. `scripts/l3_live_probe.py`：直连 Chat Completions 探测 primary/secondary。
3. `scripts/l3_mcp_echo.py`：本地 JSON-RPC MCP（initialize/tools.list/call）。
4. `scripts/l3_run_evidence.py`：经平台 API 注册模型 → health → trial 任务 → MCP probe → 写 `docs/delivery/evidence/L3-*.json`（脱敏）。
5. 交付：`docs/delivery/L3-LIVE.md`；失败项标 `blocked`/`fail`，不改阈值凑绿。

## Risks

- 模型名若上游不存在 → 证据记 fail，改用探测到的可用 id。
- Key 曾出现在聊天 → 建议联调后轮换。
