# WP15 运行手册：发布 / 回滚 / 恢复

## 1. 发布前

1. CI 绿：全量 unittest + 前端 build + SBOM 产物。
2. `APP_ENV=production`，`SECRET_KEY` 非默认且 ≥24 字符。
3. `ADMIN_BOOTSTRAP_PASSWORD` 已轮换（非 `admin123`）；或 admin 已由线下创建。
4. `POST /api/ops/backup`，记录 `path` 与 `sha256`。
5. （可选）金丝雀实例就绪：`GET /api/ready` → 200。

## 2. 滚动 / 金丝雀

1. 拉起新版本（容器或 systemd），仅接入少量流量（建议 ≤5%）。
2. 观察 `GET /api/ready`、`GET /api/metrics`、告警策略。
3. `POST /api/ops/admission/run` `{"level":"basic"}`，确认 `ok` 非 false；完整级另跑 `full`（外部套件可为 `unknown`）。
4. 证据包：`artifact_hash` + `evidence_path` 归档；**不继承**旧版通过状态。
5. 放量至 100%；保留旧版本制品至少一次变更窗口。

## 3. 回滚

1. 上游切回旧版本（Nginx/compose）。
2. 若新版本写入不兼容 schema：**停写**，以备份恢复只读/修复，禁止危险自动 downgrade。
3. 应用回滚不逆转已成功计费/审批流水；需冲正走业务接口。

## 4. 备份恢复演练（AC45）

```bash
# 需 ops:backup
curl -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/ops/restore-drill
```

断言：`hash_match=true`，记录 `rpo_seconds` / `rto_seconds`。演练写入 `backups/restore-drill/`，不覆盖活动库。

真实灾难恢复：停服务 → 用备份覆盖活动 DB 文件 → 启动 → `/api/ready` → 抽查任务/审计。

## 5. 故障注入（AC44）

```bash
# DB 不可用（就绪失败）
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"db_unavailable":true,"reason":"drill"}' http://127.0.0.1:8000/api/ops/fault
curl -i http://127.0.0.1:8000/api/ready   # 期望 503
# 恢复
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"clear":true}' http://127.0.0.1:8000/api/ops/fault
```

证书过期演练：`{"cert_expired":true}`。进程终止/断电：依赖 systemd/容器重启策略 + 任务 lease 回收（WP04）。

## 6. 值班检查清单

- [ ] `/api/live` 200
- [ ] `/api/ready` 200
- [ ] 最近一次 admission 证据已归档
- [ ] 最近一次 backup sha256 已知
- [ ] 无未关闭的 P0 告警
