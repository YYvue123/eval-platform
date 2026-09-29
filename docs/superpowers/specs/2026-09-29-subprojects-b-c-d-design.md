# 子项目 B / C / D 设计

日期：2026-09-29。承接 `2026-09-29-review-followup-roadmap-design.md`。A 已验收。用户要求用 subagent 连续完成 B→C→D。不创建 git commit，除非用户另行指示。

## 共同约束

- 测试一律 `from tests import isolated_env`；禁止指向 `backend/eval_platform.db`。
- 后端：`E:\eval-platform\backend`，解释器 `.venv\Scripts\python.exe`，`unittest`。
- 产品文案不写 Mock/假成功/API 未开放等研发口号。
- 明文密钥不进日志、清单、截图、证据。
- 权限新动作走 AGENTS.md 全套；本三子项目默认不新增权限码。
- `trial_run` 表示真实小规模试跑，不是 Mock，清理时默认保留。

## B. D4 业务库 Mock 清理

### 目标

plan/apply/verify CLI；SQLite Backup API（含 WAL checkpoint）；结构化标志与衍生链处理；停止 seed 回灌示例业务记录。

### 架构

独立包 `tools/cleanup_mock/`，只通过解析后的 SQLite 文件路径操作，不经 FastAPI。默认子命令 `plan` 只写 JSON 清单到 `--out`，不改库。

目标指纹：`sha256(文件字节) + "|" + resolve() 绝对路径` 再 sha256，输出 `sha256:<hex>`。清单 `manifest_hash` 为去掉该字段后的 canonical JSON（`sort_keys=True`、无空白差）的 sha256。

分类（禁止 `LIKE '%mock%'`）：

- 删除：`eval_results.simulation=1`；其 `task_id` 若任务 `simulation=1` 则任务及 `eval_lineages` / `task_events` / `task_subtasks` / `report_jobs` 随链删除。
- 删除：`agent_runs.provider='mock'` 及其 `agent_events` / `agent_messages`。
- 下游：引用已删 `task_id` 的 `leaderboard_snapshots` 行、`idempotency_records` 中绑定这些 task 的键，删除或作废；不手填分数。
- 保留：RBAC、租户、用户、quality_rules、task_templates、benchmark_suites、builtin resources 定义、`trial_run=1 AND simulation=0` 的任务。
- `score_status=legacy_unverified` 且 `simulation=0`：隔离标记写入清单 `action=archive`（结果行加/保留 simulation 不洗白；本轮实现为写入 `eval_results.simulation=1` 不采用——那会洗成假删除依据）。改为清单 `action=isolate`：设置一个已有列或 JSON 字段 `metrics_json` 内 `_isolated_unverified=true` **禁止**。最简：isolate 行不删，清单列出，verify 要求正式榜 `is_formal_eligible` 仍排除它们（已有逻辑）。本轮 apply **不删除** legacy_unverified 且非 simulation 的结果。

apply 拒绝：指纹不符、manifest_hash 不符、存在 `eval_tasks.status IN ('running','queued','leased','cancelling')`、未提供 `--confirm-fingerprint`。apply 先 Backup API 到 `--backup-dir`。

verify：`PRAGMA integrity_check`、`foreign_key_check`；`eval_results.simulation` 与 `eval_tasks.simulation` 与 `agent_runs.provider='mock'` 计数为 0。

防回灌：`seed_db` 不再调用 `seed_eval_packs`；`seed_knowledge` 不再插入那两条示例知识（模板引用条目可留，属配置）。`seed_eval_packs` 函数保留供显式调用。测试若需要 packs 自己调用。

业务库 apply：仅当操作员传入与当前 `DATABASE_URL` 解析路径一致的 `--db` 与指纹。自动化验收在 `tests/_isolated/` 内对**拷贝**执行 plan/apply/verify；另可选对活动库只跑 `plan` 产出清单。活动库 apply 由 CLI 支持，证据优先记录隔离拷贝上的成功 apply；若对活动库执行 apply，必须先 Backup API 且把指纹写入证据。

### 验收

DATA01：plan 不写库；hash 失配 apply 拒绝；恢复实测（backup→临时文件 hash 一致）；结构标志清零。  
DATA02：重启 seed 后无 `pack:*` 新数据集（空库 init 后 datasets 不含 pack 名）；测试无法指向业务库。

## C. D5 真实数据填充

### 目标

受控脚本经 **HTTP API / TaskService** 写入**已确认目标库**。禁止单测当填充器，禁止直接 INSERT 评分。

### 架构

`tools/real_fill/`：登录 → 按 REAL01–12 调用现有 API。目标由 `REAL_FILL_BASE_URL` + 目标库指纹文件确认。脚本内所有测试用 `isolated_env` + TestClient，不填业务库。

对活动库填充：显式 `--confirm-fingerprint`。缺模型/预算的场景 `blocked` 写入 `docs/superpowers/evidence/subproject-c.md`，不得编造成功。

REAL04/05 复用 `tools/stats_service`（A 已有）。REAL03/06/07/08 读 `.env` 的 `L3_MODEL_*` 引用名，不打印 Key。不可用则 blocked。REAL11 未满七天不得转正。REAL09 专家签署不由脚本代签。

### 验收

证据 JSON：case_id、result、task/run/trace、断言。失败保留。刷新页面能看到同一 ID。

## D. D3 全站 24 页

### 目标

公共六态 + URL 筛选/分页 + 禁止 catch 空数组 + 去口号 + 各页相对 `02-frontend-spec.md` 的缺口补齐。不改框架。

### 架构

- `frontend/src/utils/asyncState.js`：`idle|loading|empty|uncreated|error|forbidden|success`。
- `frontend/src/components/PageAsyncState.vue`：六态展示（原因+下一步）。
- `frontend/src/utils/listQuery.js`：筛选/页码读写 `route.query`。
- `frontend/src/utils/request.js`：`skipErrorToast` 配置；轮询静默。
- 无权限：路由进入 `NotFound` 且 `reason=forbidden`，不再静默改到首页（Dashboard `denied` 可保留为次要提示，主路径走 403 页）。
- `ResourcePicker` 服务端翻页加载更多，禁止 30 条当全量。
- Agents：去掉 Mock 口号；规划模型不默认第一条。
- Models：产品提示改为「未配置 api_url 时无法探测或试调用」，`verify:ux-static` 对 Models 的 Mock 句改为匹配新文案（更新脚本断言）。

页面按计划分批改，每批 `test:unit` + `verify:ux-static`。证据 `docs/superpowers/evidence/subproject-d.md`。

## 执行顺序

B 全部过闸 → C（可 blocked 个别 REAL）→ D。D 不依赖 C 的真实业务数据即可改交互；最终截图若业务库仍空，空态本身即验收。
