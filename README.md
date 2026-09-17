# 大模型智能评测平台

从 [llm-manager](https://github.com/YYvue123/LLM-manager) 抽出的可运行骨架，并按《第五章项目设计方案》与《工具底座标准接口规范 V0.6.1》落地评测主链路。

当前能力：登录与 RBAC、评测数据（导入/版本/导出）、数据质量检测、被测模型注册与 OpenAI 兼容调用、提示词模板、工具底座 Manifest 注册与信封调用、批量评测任务、榜单与评测服务单。

未接入（需真实基础设施）：mTLS/VPN 通道落地、外部 MCP/Agent 运行时、离线 Eval Kit、多智能体自动编排的 LLM 规划。无接口地址的模型会走本地 Mock，便于联调。

## 技术栈

前端 Vue 3 + Vite + Element Plus；后端 FastAPI + SQLite；认证 JWT。

## 本地开发

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux: source .venv/bin/activate
pip install -r requirements.txt
python init_db.py
python run.py    # http://localhost:8000

cd frontend
npm install
npm run dev      # http://localhost:5173，/api 代理到后端
```

默认账号 **`admin` / `admin123`**，登录后立刻改密码。

后续将按《第五章项目设计方案》和《工具底座标准接口规范 V0.6.1》补齐全部设计能力。给后续开发/AI 的**完整规格**见：

`docs/大模型智能评测平台-完整设计与续建规格.md`

## 仓库结构

```
backend/     FastAPI、RBAC、评测业务与工具底座
frontend/    Vue 控制台
deploy/      systemd、Nginx 参考配置
```

## 权限

新增页面、按钮或 API 时，同步更新 `backend/app/permissions.json`、`permission_loader.py`、`rbac.py`，并运行：

```bash
cd frontend && npm run collect-permissions
```
