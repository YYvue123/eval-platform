# 大模型智能评测平台

从 [llm-manager](https://github.com/YYvue123/LLM-manager) 抽出的可运行骨架，按《第五章项目设计方案》与《工具底座标准接口规范 V0.6.1》落地的多智能体协同智能化大模型评测平台。

默认合作模式为**远程加密访问**（权重不出域）。不部署训练 / GPU / 本地模型服务。Agent **不得**直接改调度或资源主链路，关键操作须经规则校验或人工确认后走工具。

完整规格：`docs/大模型智能评测平台-完整设计与续建规格.md`

## 技术栈

| 层 | 选型 |
| --- | --- |
| 前端 | Vue 3 + Vite + Element Plus + Pinia |
| 后端 | FastAPI + SQLAlchemy + SQLite（可演进 PostgreSQL） |
| 认证 | JWT + RBAC |

## 已实现能力

### 系统与权限

- 登录 / 注册、用户与角色、RBAC、通知、操作审计（含 tenant / trace）
- 权限码同步：前端 `v-if` / `meta.permission`、后端 `require_permission`、`permissions.json`、`permission_loader`、`rbac.py`、`npm run collect-permissions`

### 智能化评测底座

- **评测数据**：导入（Excel/CSV/JSON/JSONL/TXT/ZIP）、预览、版本与 checksum、审核发布、逻辑删除与占用拦截、标签、导出、调用日志
- **数据质量**：可配置规则、问题工单处理、报告归档；不合格数据拦截正式评测（试跑除外）
- **被测模型**：注册、版本、请求模板 / 响应映射、ACL、场景白名单、并发限流、周期健康探测与熔断；通道 HTTPS / mTLS / VPN / 网关 / 明文联调
- **提示词**：模板与版本、变量、审核发布、生成 / 优化、效果测试、调用日志
- **工具底座（V0.6.1）**：Manifest 注册、信封 1.3、网关限流熔断、内置裁判（exact/contains/regex/fuzzy + 四类安全）、Skill 链式 `$ref`、MCP JSON-RPC、HTTP 外部适配、副作用沙箱、`/batch/*` 快照（7 天 GC）、进程内注册发现与心跳剔除

### 评测任务与编排

- **任务引擎**：状态机、优先级队列、依赖编排、子任务分片、事件与告警策略、报告多格式归档（JSON/MD/CSV/Excel/Word/HTML/PDF）
- **任务模板库**：语言 / 语音 / 视觉 / 多模态 + 11 场景 + 14 行业 + 4 类安全（共 33 项）；每项绑定试点数据集 `pack:{模板码}`
- **多智能体编排**：主 Agent 出计划、监控 / 诊断只分析、知识库；创建 / 改配 / 恢复经确认后走工具，不进调度主路径

### 评测应用

- **榜单 2.0**：综合 / 能力 / 专项 / 性价比四类；权重、归一化、快照、雷达与趋势、成本表、导出；异常时展示上次快照
- **评测服务**：自动 / 专家报价、工作空间配额预警、看板、影子测试（只回生产结果）→ 转正 / 回滚、多格式报告交付

### 运行支撑与部署

- 健康检查 `GET /api/health`、进程内 Prometheus `GET /api/metrics`
- SQLite 备份、审计保留清理（普通 180 天 / restricted 365 天）、快照 GC、基础级交付验收
- 任务血缘 `GET /api/tasks/{id}/lineage`（数据集 / 模型 / 提示词 / 工具版本 / checksum / 通道 / trace）
- CI：`.github/workflows/ci.yml`（编译、单测、密钥扫描、前端构建）
- 部署参考：`deploy/`（systemd、Nginx、升级回滚说明）

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

常用环境变量见 `deploy/README.md`（`APP_ENV`、`MTLS_*`、`AUDIT_RETENTION_*`、`BACKUP_DIR` 等）。无接口地址的模型走本地 Mock，便于联调；mTLS 通道需配置证书文件后方可真实调用。

## 仓库结构

```
backend/     FastAPI、RBAC、评测业务、工具底座、Agent、运维 API
frontend/    Vue 控制台
deploy/      systemd、Nginx、部署说明
docs/        完整设计与续建规格
.github/     CI 流水线
```

## 测试

```bash
cd backend
python -m unittest tests.test_eval_flow -v
```

## 权限工作流

新增页面、按钮或 API 时，同步更新 `backend/app/permissions.json`、`permission_loader.py`、`rbac.py`，并运行：

```bash
cd frontend && npm run collect-permissions
```
