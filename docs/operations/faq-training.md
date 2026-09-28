# FAQ 与培训

版本：2026-09-28-wp16

## FAQ

**Q: live 200 但 ready 503？**  
A: 进程在、库或降级标志异常。查 `GET /api/ready` 的 `reason` / `degrade`，勿只看 live。

**Q: 生产登不进 admin123？**  
A: 设计如此。生产须 `ADMIN_BOOTSTRAP_PASSWORD`（非默认）或线下建管理员。

**Q: 准入 overall 为 null？**  
A: 含 `unknown` 项（未跑契约/外部套件）时不得判通过，属预期。

**Q: 恢复演练会覆盖生产库吗？**  
A: 不会。写入 `BACKUP_DIR/restore-drill/`。

**Q: 基准生态还缺什么？**  
A: 见 [benchmark-ecosystem.md](./benchmark-ecosystem.md) 的 TBD，勿自行承诺。

## 新人培训清单（建议 0.5–1 天）

1. 读本目录 README + WP15-runbook。
2. 在预发：`/api/live` `/api/ready` → 备份 → restore-drill → 清除。
3. 创建工单 → 指派自己 → 填写 resolution 关闭。
4. 登记一条数据授权（含 license_spdx + grantor）。
5. 按手册做一次模拟发布回滚并 `POST /ops/drills`。
6. 运营负责人确认签字（线下），在演练 `evidence` 中注明确认人。
