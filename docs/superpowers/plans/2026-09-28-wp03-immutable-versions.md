# WP03 数据/模型/提示词不可变版本 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使数据集修改产生新版本且旧任务内容可复现；任务执行读取冻结的模型访问配置；正式任务拒绝草稿/未质检数据；模型健康与生产明文通道符合验收。

**Architecture:** 数据集写入走「复制出新 DatasetVersion + content_checksum」；`ModelAccessConfig` 存可执行快照并由 runner 优先读取；创建/发布门禁校验 quality+status；prompt 已发布版本禁止原地改。

**Tech Stack:** FastAPI、SQLAlchemy、unittest、现有 datasets/models/prompts/quality/task_runner。

## Global Constraints

- 依赖 WP01 租户/对象策略；不信任客户端伪造 tenant。
- 依赖 WP02：外部裁判仍经 tool_gateway；本包不重做网关。
- Mock/占位不得冒充正式能力；正式任务门禁不可仅 trial 绕过。
- 交付 `docs/delivery/WP03.md`；测试用 `tests/isolated_env.py`。
- **本会话明确不做完**：完整 Vue 改版、标签字典、流式大文件/ZIP 限额深化、.xls 全适配、独立 import job 表、凭证轮换服务。

## File Map

| 路径 | 职责 |
|---|---|
| `models/dataset.py` | `content_checksum`（可选列） |
| `services/dataset_revision.py` | 条目变更 → 新版本 + hash |
| `api/datasets.py` / `api/quality.py` | patch/fix 走 revision；publish 门禁 |
| `api/tasks.py` | 正式任务拒绝 draft/unchecked |
| `models/eval_model.py` / `api/models.py` | AccessConfig 全量冻结（含密钥引用字段） |
| `services/model_client.py` / `task_runner.py` | 执行读 pinned config；health 仅 2xx |
| `services/tls_channel.py` / `config` | 生产禁 plain |
| `api/prompts.py` | published 版本写保护；变量 required |
| `tests/test_version_freeze.py` | 专项验收 |

---

### Task 1: 数据集不可变修订（B06）

- [ ] 新增 `content_checksum` 于 `DatasetVersion`（条目规范 hash：按 item_no 排序的 input/ref/expected）
- [ ] `dataset_revision.apply_item_patch(db, dataset, item_id, changes, actor)`：复制当前版本全部条目 → 新 version → 应用变更 → 更新指针；published → draft + quality unchecked
- [ ] `patch_item` / `quality.handle_issue`（fix/delete）改调 revision，禁止原位改历史 version 行
- [ ] 测试：pin 旧 `version_id` 的条目内容在修订后不变；新版本 content_checksum 不同

### Task 2: 正式任务与发布门禁

- [ ] `create_task`：非 `trial_run` 时拒绝 dataset `status`∉{published} 或 `quality_status`∈{unchecked, failed, check_failed, …异常}
- [ ] `publish_dataset`：要求当前版本 `quality_status`∈{passed, ok, good}（与现有枚举对齐）；否则 400
- [ ] Agent `validate_eval_config` 对齐同一规则

### Task 3: 模型配置冻结（B07）

- [ ] `_sync_access` 写入可执行字段：`api_url/method/auth_type/api_key(或 auth_config.token)/templates/mapping/timeout/retry/channel`
- [ ] `task_runner`：若 `task.model_version_id` 有对应 `ModelAccessConfig`，用其构造调用视图（不读 live EvalModel 可变字段）；无快照则回退 live 并记警告（仅迁移）
- [ ] 更新模型 live 字段后旧 `ModelAccessConfig` 行不变
- [ ] 测试：改 api_url 后旧 version 配置仍指向原 URL

### Task 4: 健康与生产明文（B15 模型侧）

- [ ] `model_client.health_check`：仅 2xx → ok（与 WP02 工具一致）
- [ ] `APP_ENV=production`（或 `settings`）时 `channel_type=plain` 创建/更新/调用拒绝

### Task 5: 提示词冻结与变量必填

- [ ] published 的 `PromptVersion`：禁止原地改 `prompt_content`/`variable_config`（须新版本）
- [ ] `create_task` 有 `prompt_id` 时默认 pin `current_version_id`；正式任务要求 prompt published
- [ ] `render_prompt` / preview：`required` 变量缺失 → 明确错误（正式路径）

### Task 6: 测试与交付

- [ ] `tests/test_version_freeze.py` 覆盖 Task 1–5 要点
- [ ] 全量 `unittest discover` 绿
- [ ] `docs/delivery/WP03.md` + STATUS + progress ledger

## Out of scope（本会话）

- 前端大改、标签体系、ZIP/xls 深化、credential 轮换服务、清洗异步 job 全链路 UI
