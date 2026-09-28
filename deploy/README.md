# 部署与运行

默认通道为远程加密评测。不部署训练、GPU 或本地模型服务。Agent 不进入任务调度主路径。

## 目录

- 后端：`/opt/eval-platform/backend`
- 前端构建产物：`/opt/eval-platform/frontend/dist`
- SQLite：`backend/eval_platform.db`
- 备份目录：`backend/backups`（可用环境变量 `BACKUP_DIR` 覆盖）
- 日志：`backend/logs`

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `APP_ENV` | `dev` / `production` |
| `SECRET_KEY` | **生产必填且不得使用示例默认值**（≥24 字符） |
| `ADMIN_BOOTSTRAP_PASSWORD` | 生产首次引导 admin 密码；禁止 `admin123` |
| `DATABASE_URL` | 默认 SQLite |
| `MTLS_CERT_FILE` / `MTLS_KEY_FILE` / `MTLS_CA_FILE` | 模型通道 `mtls` 时必填 |
| `AUDIT_RETENTION_DAYS` | 普通审计保留，默认 180 |
| `AUDIT_RETENTION_RESTRICTED_DAYS` | 受限租户审计保留，默认 365 |
| `BACKUP_DIR` | SQLite 备份目录 |

生产启动会校验 `SECRET_KEY`；未设置安全引导密码时不会写入默认 `admin/admin123`。

## 探针

| 路径 | 含义 |
| --- | --- |
| `GET /api/live` | 进程存活（不查库） |
| `GET /api/ready` | 就绪：降级标志 + DB；失败 503 |
| `GET /api/health` | 兼容旧探针，含 DB 检查，失败 503 |
| `GET /api/metrics` | Prometheus 文本 |

## systemd

```bash
sudo cp deploy/eval-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now eval-backend
curl -sf http://127.0.0.1:8000/api/live
curl -sf http://127.0.0.1:8000/api/ready
```

手动备份：`POST /api/ops/backup`（需 `ops:backup`）。恢复演练：`POST /api/ops/restore-drill`（隔离目录，不覆盖活动库）。

## 容器与金丝雀

```bash
export SECRET_KEY='…' ADMIN_BOOTSTRAP_PASSWORD='…'
docker compose -f deploy/docker-compose.yml up -d --build
# 金丝雀实例（可选）
docker compose -f deploy/docker-compose.yml --profile canary up -d backend-canary
```

流量切分建议：Nginx `split_clients` 或上游权重将约 5% 打到 `:8001`，观察 `/api/ready` 与准入报告后再滚动。

蓝绿：保留旧容器/旧 systemd unit，新版本探针绿后再切 upstream；失败切回旧 upstream，**不**自动 downgrade 已写新数据。

## Nginx

```bash
sudo cp deploy/nginx-eval-platform.conf /etc/nginx/sites-available/eval-platform
sudo ln -s /etc/nginx/sites-available/eval-platform /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

`/api/live`、`/api/ready`、`/api/health` 与 `/api/metrics` 随探针路径反代。

## CI 流水线

仓库 `.github/workflows/ci.yml`：编译后端、**全量** unittest、密钥扫描、SBOM（`deploy/generate_sbom.py`）、前端 collect-permissions 与构建。

升级：停写（可选）→ `POST /api/ops/backup` → 更新代码/镜像 → 启动 → `curl /api/ready` → `POST /api/ops/admission/run`。失败则用备份文件回滚数据库，再回退代码版本。详见 `docs/operations/WP15-runbook.md`。

## 备份与审计

- 备份：复制 SQLite 文件到 `BACKUP_DIR`（含 sha256）。
- 恢复演练：拷贝到 `BACKUP_DIR/restore-drill/`，返回实测 `rpo_seconds` / `rto_seconds`。
- 清理：`POST /api/ops/purge-audit` 按 180/365 天分别删除普通与 `tenant_id=restricted` 记录。
- 故障注入：`POST /api/ops/fault`（进程内标志，可 clear）。
