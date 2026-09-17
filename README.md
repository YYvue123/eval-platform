# 大模型智能评测平台

从 [llm-manager](https://github.com/YYvue123/LLM-manager) 抽出的可运行骨架，用于建设独立的评测平台。当前只包含登录、RBAC、用户、通知、审计和工作台，**不含** TinyLLaVA 训练、GPU 调度和本机 serving。

后续将按《第五章项目设计方案》和《工具底座标准接口规范 V0.6.1》接入评测数据、被测模型、工具底座与批量评测。

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

## 仓库结构

```
backend/     FastAPI、RBAC、用户与审计
frontend/    Vue 控制台骨架
deploy/      systemd、Nginx 参考配置
```

## 权限

新增页面、按钮或 API 时，同步更新 `backend/app/permissions.json`、`permission_loader.py`、`rbac.py`，并运行：

```bash
cd frontend && npm run collect-permissions
```
