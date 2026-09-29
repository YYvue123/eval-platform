# Task B4 报告：apply 守卫与事务删除

## Review Assessment

**Approved**

只读复核 `tools/cleanup_mock/apply.py` 与 `ApplyTests`。守卫（空 confirm / fingerprint / manifest_hash / busy status）在备份与删除之前；成功路径先 `consistent_backup` 再事务内按 `DELETE_ORDER` 仅删 `plan.actions` 的 pk；无 `LIKE '%mock%'`；trial 行保留。独立复跑 `tests.test_cleanup_mock -v`：**Ran 12 tests in 0.915s OK**。无 Critical / Important。实现代码未改。

### Strengths

- 拒绝路径顺序正确：`confirm_fingerprint` 空值 → 当前文件指纹 vs confirm 与 `plan.target.fingerprint` → 重算 `manifest_hash` → 仅当 `eval_tasks.status` 存在时扫描 `running/queued/leased/cancelling`（`apply.py:37-64`）。hash/指纹失败发生在 `connect` 之前，不会备份或删行。
- 成功路径先 `consistent_backup` 到 `backup_dir/{stem}.pre-apply.db`，再 `BEGIN`/`DELETE`/`commit`，异常 `rollback`（`apply.py:66-91`）。
- 表名白名单 `KNOWN_TABLES`；pk 经 `int()` 与绑定参数 `IN (?)`，不是拼接删除条件。删除顺序与计划一致（events/messages → results/lineages/子表 → tasks → runs）。
- `ApplyTests` 覆盖计划用例并补了 fingerprint / 空 confirm / busy（busy 打在 trial 任务 `id=2` 上，证明是全表扫描而非仅待删 pk）。成功用例用 SQL 断言保留 `id=2` 与 `eval_results.id=11`，未假造 `verify_clean`。

### Issues

#### Critical (Must Fix)

无。

#### Important (Should Fix)

无。

#### Minor (Nice to Have)

1. **未校验 `action=="delete"`**  
   - File: `tools/cleanup_mock/apply.py:72-87`  
   - 清单里凡白名单表+pk 都会删。当前 inventory 只发 `delete`，本任务可接受；设计里的 `isolate` 若日后入清单且未改 apply，会被误删。  
   - 建议：非 `delete` 跳过或 `ValueError`。

2. **成功用例未打开备份核对其仍含被删行**  
   - File: `backend/tests/test_cleanup_mock.py:250-266`  
   - 只断言 `backup_dir` 存在且返回含 `backup`。代码路径已先 backup，恢复闭环属 Task 8/DATA01。

3. **`deleted` 可能含未真正删除的 pk**  
   - File: `tools/cleanup_mock/apply.py:84-97`  
   - 表不在库中会 `continue`，返回值仍累加这些 pk。

4. **未知表在 backup 之后才拒绝**  
   - File: `tools/cleanup_mock/apply.py:71-75`  
   - 库不变，但会多一份 backup。可把 actions 校验提前到 backup 前。

5. **busy 仅测 `running`**；`queued`/`leased`/`cancelling` 靠同一 `IN` 元组，无单独用例。

### Recommendations

- Task 5/7 接入 isolate 或 CLI 前加上 `action=="delete"`。
- 同目录重复 apply 会覆盖 `{stem}.pre-apply.db`；CLI 可用时间戳文件名。

### Assessment

**Ready to merge?** Yes（本任务无 commit；**Approved**，可进 Task 5）

**Reasoning:** 计划中的守卫、先备份、仅删 plan pk、保留 trial、事务回滚均已落地且 12 项测试通过。剩余为前向兼容与测试加强，不阻断。

---

## 状态

**DONE** — `tests.test_cleanup_mock` 12 项 unittest 全部通过；未 commit；未写入 `backend/eval_platform.db`。

## RED

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock -v
```

**关键输出：**

```
ERROR: test_apply_deletes_simulation_keeps_trial
ERROR: test_apply_rejects_busy_status
ERROR: test_apply_rejects_missing_confirm
ERROR: test_apply_rejects_wrong_fingerprint
ERROR: test_apply_rejects_wrong_hash
ModuleNotFoundError: No module named 'tools.cleanup_mock.apply'
Ran 12 tests in 0.263s
FAILED (errors=5)
```

**失败原因：** `ApplyTests` 已引用 `tools.cleanup_mock.apply.apply_plan`，模块尚未创建（TDD 预期 RED）。Task 1–3 的 7 项仍为 ok。

## GREEN

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock -v
```

**结果：** `Ran 12 tests in 0.912s` — **OK**

| 用例 | 说明 |
| --- | --- |
| Task 1 ×4、Task 2 ×1、Task 3 ×2 | 保持通过 |
| `test_apply_rejects_wrong_hash` | `manifest_hash` 改为 `deadbeef` 时 `ValueError` 含 `manifest`；`eval_results` 仍为 2 行 |
| `test_apply_rejects_wrong_fingerprint` | 错误 `confirm_fingerprint` 时 `ValueError` 含 `fingerprint`；任务行数不变 |
| `test_apply_rejects_missing_confirm` | 空字符串 confirm 时 `ValueError` 含 `confirm` |
| `test_apply_rejects_busy_status` | `eval_tasks.status=running` 时拒绝；simulation 任务仍在 |
| `test_apply_deletes_simulation_keeps_trial` | 先 backup 到 `backup_dir`；删 simulation 任务/结果/lineage 与 mock run/events；保留 `id=2` 的 trial 任务及 `eval_results.id=11`。未调用尚未存在的 `verify_clean`，用 SQL 断言 |

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `tools/cleanup_mock/apply.py` | 新建：`apply_plan(db_path, plan, *, confirm_fingerprint, backup_dir) -> dict` |
| `backend/tests/test_cleanup_mock.py` | 追加 `ApplyTests`；保留 Task 1–3 测试 |

未改动简报外文件；未创建 commit。未创建 `verify.py`（按 brief：缺则用 SQL）。

## 实现要点

- 守卫顺序：空 confirm → 当前指纹 vs confirm 与 plan.target.fingerprint → 重算 `manifest_hash` → 若存在 `eval_tasks.status` 则拒绝 `running/queued/leased/cancelling`。
- 通过后：`consistent_backup` 到 `backup_dir/{stem}.pre-apply.db`，再事务内按 `DELETE_ORDER` 仅删 `plan.actions` 的 pk（白名单表）。
- 删除顺序：`agent_events` → `agent_messages` → `eval_results` → `eval_lineages` → `task_events` → `task_subtasks` → `report_jobs` → `eval_tasks` → `agent_runs`。
- 不使用 `LIKE '%mock%'`；trial 任务不在 actions 中故保留。
- 返回 `{"backup": consistent_backup 结果, "deleted": 动作条数}`。

## 自审

- [x] TDD：先测后码；RED 为 `ModuleNotFoundError`。
- [x] hash / fingerprint / confirm / busy status 拒绝且不删行。
- [x] 成功路径先 backup 再事务删除；保留 trial。
- [x] 测试从 `backend/` 运行；未 git commit；未写 `backend/eval_platform.db`。

## 关注点

1. **busy 是全表扫描：** 任意 `eval_tasks` 处于 running/queued/leased/cancelling 即拒绝，不限于待删 pk。
2. **`verify_clean` 延后：** 成功用例用 SQL 断言；Task 5 再接 `verify.py`。
3. **未知表名：** actions 中表不在 `KNOWN_TABLES` 时 `ValueError`（计划外防护）。
