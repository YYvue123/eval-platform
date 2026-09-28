# 大模型智能评测平台

按《第五章项目设计方案》与《工具底座标准接口规范 V0.6.1》落地的多智能体协同智能化大模型评测平台。

默认合作模式为**远程加密访问**（权重不出域）。不部署训练 / GPU / 本地模型服务。Agent **不得**直接改调度或资源主链路，关键操作须经规则校验或人工确认后走工具。

| 文档 | 用途 |
| --- | --- |
| `docs/implementation-plan-2026-09-28/` | 核查与研发设计包（差距、工作包、验收） |
| `docs/delivery/STATUS.md` | WP00–WP16 交付追踪（追加，不覆写原始差距矩阵） |
| `docs/delivery/MILESTONE-M4.md` | M4 收口：已交付 vs 待 L3/L4 |
| `docs/operations/` | 值班/变更/发布回滚/FAQ/基准生态 TBD |
| `CONTRIBUTING.md` / `LICENSE` / `docs/licenses/` | 贡献与许可 |

旧文 `docs/大模型智能评测平台-完整设计与续建规格.md` 中部分「现状」已过时，以设计包与交付报告为准。

## 技术栈

| 层 | 选型 |
| --- | --- |
| 前端 | Vue 3 + Vite + Element Plus + Pinia |
| 后端 | FastAPI + SQLAlchemy + SQLite（可演进 PostgreSQL） |
| 认证 | JWT + RBAC |

## 能力摘要（工程交付）

- **系统**：登录、用户角色、RBAC、通知、审计（tenant/trace）；权限六件套见 `AGENTS.md`
- **数据/模型/提示词/质量**：版本冻结、正式门禁、质量工单、通道策略（生产禁 plain）
- **工具底座**：信封 1.3、tool_gateway、幂等、MCP/Skill/`$ref`、副作用策略、batch 快照
- **任务**：claim/lease/fencing、worker、取消重试、预算、多格式报告
- **Agent**：GoalSpec/审批/委派/监控诊断/知识候选（不进调度主路径）
- **基准/安全/榜单/服务**：套件 readiness、安全评测、可比榜单、影子灰度与幂等结算
- **运行支撑**：`/api/live` `/api/ready`、AdmissionRunner、备份恢复演练、故障注入、工单/授权/演练留痕、Docker/SBOM/CI

**未宣称**：真实生产压测达标、全行业题库、集群中间件默认就绪——见 `MILESTONE-M4.md`。

## 本地开发

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
python init_db.py
python run.py    # http://localhost:8000

cd frontend
npm install
npm run dev      # http://localhost:5173，/api 代理到后端
```

开发默认账号 **`admin` / `admin123`**（登录后改密）。  
`APP_ENV=production` 时必须配置非默认 `SECRET_KEY`，并用 `ADMIN_BOOTSTRAP_PASSWORD`（禁止 `admin123`）引导管理员。

环境变量与探针见 `deploy/README.md`。运维步骤见 `docs/operations/WP15-runbook.md`。

## 仓库结构

```
backend/      FastAPI、评测业务、工具底座、Agent、运维 API
frontend/     Vue 控制台
deploy/       systemd、Nginx、Dockerfile、compose、SBOM
docs/         设计包、delivery、operations、licenses
.github/      CI（全量 unittest + 前端构建 + SBOM）
```

## 测试

```bash
cd backend
python -m unittest discover -s tests
# 测试使用 tests/isolated_env.py，不触碰业务库

cd frontend
npm run build
```

## 权限工作流

见 `AGENTS.md`：新增页面/按钮/API 时同步 `permissions.json`、loader、rbac，并 `npm run collect-permissions`。
