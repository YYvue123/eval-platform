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
| `DATABASE_URL` | 默认 SQLite |
| `MTLS_CERT_FILE` / `MTLS_KEY_FILE` / `MTLS_CA_FILE` | 模型通道 `mtls` 时必填 |
| `AUDIT_RETENTION_DAYS` | 普通审计保留，默认 180 |
| `AUDIT_RETENTION_RESTRICTED_DAYS` | 受限租户审计保留，默认 365 |
| `BACKUP_DIR` | SQLite 备份目录 |

## systemd

```bash
sudo cp deploy/eval-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now eval-backend
curl -sf http://127.0.0.1:8000/api/health
```

健康检查：`GET /api/health`。Prometheus：`GET /api/metrics`。手动备份：`POST /api/ops/backup`（需 `ops:backup`）。

## Nginx

```bash
sudo cp deploy/nginx-eval-platform.conf /etc/nginx/sites-available/eval-platform
sudo ln -s /etc/nginx/sites-available/eval-platform /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

`/api/health` 与 `/api/metrics` 随 `/api/` 反代到后端。

## CI 流水线

仓库 `.github/workflows/ci.yml`：编译后端、单测、密钥文件扫描、前端 collect-permissions 与构建。

升级：停服务 → 备份 SQLite（`POST /api/ops/backup` 或拷贝 `eval_platform.db`）→ 更新代码 → 启动 → `curl /api/health`。失败则用备份文件回滚数据库，再回退代码版本。

## 备份与审计

- 备份：复制 SQLite 文件到 `BACKUP_DIR`。
- 清理：`POST /api/ops/purge-audit` 按 180/365 天分别删除普通与 `tenant_id=restricted` 记录。
