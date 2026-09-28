# L3 预发 / DeepSeek 真实联调证据

日期：2026-09-28  
设计：`docs/superpowers/specs/2026-09-28-l3-deepseek-live-design.md`  
证据：`docs/delivery/evidence/L3-LIVE-DEEPSEEK.json`

## 环境

| 项 | 值 |
|---|---|
| APP_ENV | staging（`backend/.env`，已 gitignore） |
| 模型 API | `https://api.deepseek.com`（OpenAI 兼容） |
| 模型 | `deepseek-flash`、`deepseek-v4-pro` |
| 通道 | https |
| MCP | 本地 `scripts/l3_mcp_echo.py` → `http://127.0.0.1:8765/mcp` |
| 库 | 隔离 `backend/tests/_isolated/l3/l3_live.db` |

密钥仅指纹写入证据（`api_key_fingerprint`），**全文不入库**。

## 结果

全步骤 `ok=true`（见证据 JSON）：

- 直连 Chat Completions ×2
- MCP initialize / tools.list / tools.call
- 平台登录、模型 health、MCP probe、trial 任务 `success`、`/api/ready`

复跑：

```bash
cd backend
# 终端 1（可选，证据脚本会自启）: python scripts/l3_mcp_echo.py
python scripts/l3_run_evidence.py
```

## 安全

- Key 曾在对话中出现，**联调后请在 DeepSeek 控制台轮换**并更新 `.env`。
- 勿把 `.env` 加入提交；CI 已对 tracked `.env` 扫描。

## 未覆盖（仍属 L3/L4 开放项）

- 企业 mTLS 双向证书链路
- 外部第三方托管 MCP（本次为协议真实 HTTP，非公有云 MCP）
- 生产容量压测（L4）
- 媒体多模态 / 全基准套件 live

## 对 M4 的含义

「选定 1 条真实模型 + 1 个 MCP 证据包」已完成。  
**仍不等于**原文全量生产验收；见 `docs/delivery/MILESTONE-M4.md`。
