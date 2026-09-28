# UX 浏览器烟雾（Playwright）

日期：2026-09-28

> 隔离后端 + Vite；**不等于** UX01–16 全绿。仅关闭本文件列出的可自动化子集。

## 环境

| 项 | 值 |
|---|---|
| 前端 | `http://127.0.0.1:5173`（`npx vite --host 127.0.0.1 --port 5173`） |
| 后端 | `http://127.0.0.1:8000`，库 `backend/tests/_isolated/e2e/e2e.db` |
| 账号 | `admin` / `admin123`（仅开发/隔离；生产禁用） |

```powershell
# 后端（新终端）
cd backend
$iso = Join-Path (Get-Location) "tests\_isolated\e2e"
New-Item -ItemType Directory -Force -Path $iso,"$iso\uploads","$iso\logs","$iso\backups" | Out-Null
$db = ((Join-Path $iso "e2e.db") -replace '\\','/')
$env:DATABASE_URL = "sqlite+aiosqlite:///$db"
$env:UPLOAD_DIR = "$iso\uploads"; $env:LOG_DIR = "$iso\logs"; $env:BACKUP_DIR = "$iso\backups"
python init_db.py
python -c "import uvicorn; uvicorn.run('app.main:app', host='127.0.0.1', port=8000, reload=False)"

# 前端（新终端）
cd frontend
npx vite --host 127.0.0.1 --port 5173

# 测试
cd frontend
npm run test:e2e
```

## 本轮结果

| 套件 | 结果 | 证据 |
|---|---|---|
| Playwright chromium ×7 | **7 passed**（~14s） | `ux-smoke-playwright.txt` / `ux-smoke-playwright.json` |

| 用例 | 对应 UX | 结果 |
|---|---|---|
| 登录离开 /login | 登录可达 | pass |
| Dashboard 工作台 | UX13 子集 | pass |
| Tasks 列表 | UX09 浅层 | pass |
| Models 无 Mock 文案 | No-Mock UI | pass |
| Safety 页/复核入口 | UX12 浅层 | pass |
| EvalServices 页 | U4 可达 | pass |
| MCP registered/remote 互斥 UI | UX05 UI | pass |

## 仍 not_run / blocked

UX01–04、UX06–11（除 UX05 UI）、UX12 完整复核提交、UX13–16 全页明暗/窄屏/真实模型 Agent 循环——未在本烟雾覆盖。

## 入口

- `frontend/package.json` → `npm run test:e2e`
- `frontend/playwright.config.mjs`
- `frontend/e2e/*.spec.mjs`
