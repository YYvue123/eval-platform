# WP01 对象授权与租户边界 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 ActorContext，按租户 + data_scope（all/own/shared）过滤对象；禁用用户旧 token 失效；敏感导出单独鉴权；伪造 body.tenant_id 不能越权。

**Architecture:** 新增 Tenant 实体与成员关系；业务对象增加 `tenant_id`/`visibility`；`object_policy` 对 list/get/export 强制过滤；`get_current_user` 拒绝 `status!=active`。渐进迁移：默认租户回填，不明归属标 `visibility=isolated`（仅 admin/all 可见）。

**Tech Stack:** FastAPI、SQLAlchemy async、现有 RBAC、unittest 隔离库。

## Global Constraints

- 仅 WP01；不提前做 WP02 网关。
- body/query 中的 `tenant_id` **不得**覆盖会话身份。
- 跨租户 ID 关联 → 404/空列表，不在搜索/导出中泄漏。
- 新权限按 AGENTS.md 六项同步并 `npm run collect-permissions`。
- 测试用隔离 DB；交付 `docs/delivery/WP01.md`。
- 历史对象禁止全部公开；默认回填到 `default` 租户。

## File Map

| 文件 | 职责 |
|---|---|
| `backend/app/models/tenant.py` | Tenant、TenantMembership |
| `backend/app/models/user.py` | `tenant_id`、`status` |
| dataset/model/task/prompt/agent/resource | `tenant_id`、`visibility` |
| `backend/app/services/actor_context.py` | ActorContext 构建 |
| `backend/app/services/object_policy.py` | 可见性过滤、get_visible |
| `backend/app/api/deps.py` | 禁用用户；`require_actor` |
| datasets/tasks/models/agents APIs | 接入过滤 |
| permissions + rbac + loader | `dataset:export_sensitive`；viewer scope=shared |
| `backend/tests/test_tenant_policy.py` | 双租户矩阵 |
| `docs/delivery/WP01.md` | 留痕 |

---

### Task 1: Tenant 模型与 User 字段

- Create: `backend/app/models/tenant.py`
- Modify: `user.py`, `__init__.py`, `database.py` seed/migrate

```python
class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[int] = PK
    code: Mapped[str]  # unique, "default"
    name: Mapped[str]
    status: Mapped[str] = "active"  # active|disabled

class TenantMembership(Base):
    __tablename__ = "tenant_memberships"
    id: Mapped[int] = PK
    tenant_id: Mapped[int]
    user_id: Mapped[int]
    # unique (tenant_id, user_id)
```

User: `tenant_id: int | None`, `status: str = "active"` (`active|disabled`).

Seed: ensure Tenant(code=default)；所有用户无 tenant_id 时挂到 default。

- [ ] Tests: Tenant 可创建；用户默认 active
- [ ] Commit message: `feat(wp01): add tenant models and user status`

### Task 2: ActorContext + object_policy

```python
@dataclass
class ActorContext:
    user_id: int
    username: str
    tenant_id: int
    role_code: str
    data_scope: str  # all|own|shared
    permissions: set[str]
    is_admin: bool

async def build_actor(db, user) -> ActorContext: ...

def apply_object_scope(stmt, model, actor, *, creator_field="creator_id"):
    # tenant_id == actor.tenant_id
    # scope all: + visibility != isolated OR is_admin
    # scope own: creator_id==user OR visibility==shared；排除 isolated unless owner
    # scope shared: visibility==shared only（或 owner）
    ...

async def get_visible_or_404(db, model, obj_id, actor) -> obj: ...
```

Body tenant 忽略辅助：`def resolve_tenant_id(actor, body_tenant) -> int: return actor.tenant_id`

- [ ] 单元测试纯过滤逻辑（可用内存列表模拟）
- [ ] Commit: `feat(wp01): add ActorContext and object_policy`

### Task 3: 业务表 tenant_id/visibility + 迁移回填

对象：Dataset, EvalModel, EvalTask, PromptTemplate, KnowledgeEntry, AgentSession, BatchSnapshot, EvalWorkspace（已有可扩展）。

- ORM 字段：`tenant_id: int | None`, `visibility: str = "private"` (`private|shared|isolated`)
- `init_db` ALTER + backfill SQL：`UPDATE ... SET tenant_id=(SELECT id FROM tenants WHERE code='default') WHERE tenant_id IS NULL`
- 无 creator 的对象：`visibility='isolated'`（或保持 private 仅 all 可见——按计划不明归属隔离：`isolated`）
- 创建路径写入 `tenant_id=actor.tenant_id`, `creator_id=user.id`

### Task 4: deps 禁用用户 + require_actor

```python
if getattr(user, "status", "active") != "active":
    raise HTTPException(401, "用户已禁用")
```

`require_permission` 返回 User；新增 `require_actor(permission)` → ActorContext。

### Task 5: 接入 list/get/export（数据集、任务、模型、Agent、知识）

- list：`apply_object_scope`
- get/export/events：`get_visible_or_404`
- 创建：写 tenant_id；忽略请求体 tenant_id
- 跨租户引用（task.dataset_id 属其他租户）→ 400/404
- 敏感：`security_level in {secret, confidential}` 的 preview/export 需 `dataset:export_sensitive`

### Task 6: 权限与角色

- `permissions.json` + ACTION_NAMES：`export_sensitive`
- RESEARCHER 含 `dataset:export_sensitive`；VIEWER 不含
- viewer `data_scope` 种子改为 `shared`；roles API 允许 `shared`
- 运行 `cd frontend && npm run collect-permissions`

### Task 7: 前端最小暴露

- `/api/auth/me` 或 users/me 返回 `tenant_id`、`status`、`data_scope`
- userStore 保存 tenant_id（若已有 me 接口则扩展）

### Task 8: 验收测试 + 交付

`tests/test_tenant_policy.py`：
- 租户 A 用户看不到租户 B 的 dataset/task（list 空、get 404）
- researcher own：看不到同租户他人 private
- shared 对象可见
- 伪造 body.tenant_id 仍写入本租户
- 禁用用户旧 token → 401
- 敏感导出无权限 → 403

交付：`docs/delivery/WP01.md`，更新 `docs/delivery/STATUS.md` 与 progress ledger。

## Spec coverage

| 规格 | Task |
|---|---|
| ActorContext / 动作+对象授权 | 2–5 |
| 默认租户迁移 / 不明隔离 | 1,3 |
| 跨租户拒绝 | 5,8 |
| 禁用用户 | 4,8 |
| 敏感导出 | 5,6,8 |
| own/shared/all 矩阵 | 2,6,8 |
| 伪造 tenant | 5,8 |
