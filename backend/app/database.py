from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from app.config import settings

_engine_kw: dict = {"echo": False}
if "sqlite" in (settings.DATABASE_URL or "").lower():
    _engine_kw["poolclass"] = NullPool
    _engine_kw["connect_args"] = {"timeout": 60.0}

engine = create_async_engine(settings.DATABASE_URL, **_engine_kw)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    from sqlalchemy import text
    from app.models import (  # noqa: F401
        User,
        Tenant,
        TenantMembership,
        Notification,
        NotificationRead,
        Role,
        Permission,
        AuditLog,
        Dataset,
        DatasetVersion,
        DatasetItem,
        DataTag,
        DatasetLog,
        EvalModel,
        ModelCallLog,
        ModelMeta,
        ModelVersion,
        ModelAccessConfig,
        ModelAcl,
        ModelHealthSample,
        ModelCost,
        PromptTemplate,
        PromptVersion,
        PromptCallLog,
        PromptTestRun,
        PromptExperiment,
        BaseResource,
        ResourceCallLog,
        ResourceEvent,
        ResourceVersion,
        IdempotencyRecord,
        BatchSnapshot,
        BatchJob,
        BatchShardResult,
        UsageReservation,
        UsageLedger,
        EvalTask,
        EvalResult,
        EvalLineage,
        QualityReport,
        QualityRule,
        QualityIssue,
        EvalServiceRequest,
        TaskTemplate,
        BenchmarkSuite,
        TaskEvent,
        TaskSubtask,
        AlertPolicy,
        EvalWorkspace,
        LeaderboardWeight,
        LeaderboardSnapshot,
        LeaderboardRelease,
        ReportJob,
        KnowledgeEntry,
        AgentSession,
        AgentMessage,
        AgentSuggestion,
        AgentRun,
        AgentEvent,
        AgentApproval,
        AgentDelegation,
        AgentMonitorState,
        KnowledgeCandidate,
        OpsTicket,
        OpsDrillRecord,
        DataAuthorization,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for table, col, sql in [
            ("users", "phone", "ALTER TABLE users ADD COLUMN phone VARCHAR(20) DEFAULT ''"),
            ("users", "email", "ALTER TABLE users ADD COLUMN email VARCHAR(255) DEFAULT ''"),
            ("users", "role", "ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'user'"),
            ("users", "updated_at", "ALTER TABLE users ADD COLUMN updated_at DATETIME"),
            ("users", "role_id", "ALTER TABLE users ADD COLUMN role_id INTEGER"),
            ("users", "avatar", "ALTER TABLE users ADD COLUMN avatar VARCHAR(255)"),
            ("users", "nickname", "ALTER TABLE users ADD COLUMN nickname VARCHAR(50)"),
            ("users", "created_by", "ALTER TABLE users ADD COLUMN created_by INTEGER"),
            ("datasets", "review_comment", "ALTER TABLE datasets ADD COLUMN review_comment TEXT DEFAULT ''"),
            ("eval_tasks", "trial_run", "ALTER TABLE eval_tasks ADD COLUMN trial_run BOOLEAN DEFAULT 0"),
            ("quality_reports", "report_path", "ALTER TABLE quality_reports ADD COLUMN report_path VARCHAR(500) DEFAULT ''"),
            ("quality_reports", "issue_count", "ALTER TABLE quality_reports ADD COLUMN issue_count INTEGER DEFAULT 0"),
            ("eval_models", "current_version_id", "ALTER TABLE eval_models ADD COLUMN current_version_id INTEGER"),
            ("eval_models", "request_template", "ALTER TABLE eval_models ADD COLUMN request_template TEXT DEFAULT ''"),
            ("eval_models", "response_mapping", "ALTER TABLE eval_models ADD COLUMN response_mapping TEXT DEFAULT ''"),
            ("eval_models", "scene_white_list", "ALTER TABLE eval_models ADD COLUMN scene_white_list TEXT DEFAULT '[]'"),
            ("eval_models", "parallel_limit", "ALTER TABLE eval_models ADD COLUMN parallel_limit INTEGER DEFAULT 4"),
            ("eval_models", "support_stream", "ALTER TABLE eval_models ADD COLUMN support_stream BOOLEAN DEFAULT 0"),
            ("eval_models", "probe_interval_sec", "ALTER TABLE eval_models ADD COLUMN probe_interval_sec INTEGER DEFAULT 300"),
            ("eval_models", "consecutive_fail", "ALTER TABLE eval_models ADD COLUMN consecutive_fail INTEGER DEFAULT 0"),
            ("eval_models", "circuit_open_until", "ALTER TABLE eval_models ADD COLUMN circuit_open_until DATETIME"),
            ("eval_tasks", "model_version_id", "ALTER TABLE eval_tasks ADD COLUMN model_version_id INTEGER"),
            ("prompt_templates", "tags", "ALTER TABLE prompt_templates ADD COLUMN tags TEXT DEFAULT '[]'"),
            ("prompt_templates", "constraints", "ALTER TABLE prompt_templates ADD COLUMN constraints TEXT DEFAULT ''"),
            ("prompt_templates", "review_comment", "ALTER TABLE prompt_templates ADD COLUMN review_comment TEXT DEFAULT ''"),
            ("base_resources", "consecutive_fail", "ALTER TABLE base_resources ADD COLUMN consecutive_fail INTEGER DEFAULT 0"),
            ("resource_call_logs", "correlation_id", "ALTER TABLE resource_call_logs ADD COLUMN correlation_id VARCHAR(64) DEFAULT ''"),
            ("eval_tasks", "template_code", "ALTER TABLE eval_tasks ADD COLUMN template_code VARCHAR(80) DEFAULT ''"),
            ("eval_tasks", "priority", "ALTER TABLE eval_tasks ADD COLUMN priority INTEGER DEFAULT 5"),
            ("eval_tasks", "depends_on_id", "ALTER TABLE eval_tasks ADD COLUMN depends_on_id INTEGER"),
            ("eval_tasks", "parent_id", "ALTER TABLE eval_tasks ADD COLUMN parent_id INTEGER"),
            ("eval_tasks", "metric_weights_json", "ALTER TABLE eval_tasks ADD COLUMN metric_weights_json TEXT DEFAULT '{}'"),
            ("eval_tasks", "token_quota", "ALTER TABLE eval_tasks ADD COLUMN token_quota INTEGER DEFAULT 0"),
            ("eval_tasks", "tokens_used", "ALTER TABLE eval_tasks ADD COLUMN tokens_used INTEGER DEFAULT 0"),
            ("eval_tasks", "window_start", "ALTER TABLE eval_tasks ADD COLUMN window_start DATETIME"),
            ("eval_tasks", "window_end", "ALTER TABLE eval_tasks ADD COLUMN window_end DATETIME"),
            ("eval_tasks", "report_path", "ALTER TABLE eval_tasks ADD COLUMN report_path VARCHAR(500) DEFAULT ''"),
            ("eval_tasks", "tool_version", "ALTER TABLE eval_tasks ADD COLUMN tool_version VARCHAR(40) DEFAULT ''"),
            ("eval_service_requests", "quote_mode", "ALTER TABLE eval_service_requests ADD COLUMN quote_mode VARCHAR(20) DEFAULT 'auto'"),
            ("eval_service_requests", "quote_amount", "ALTER TABLE eval_service_requests ADD COLUMN quote_amount FLOAT DEFAULT 0"),
            ("eval_service_requests", "quote_detail_json", "ALTER TABLE eval_service_requests ADD COLUMN quote_detail_json TEXT DEFAULT '{}'"),
            ("eval_service_requests", "workspace_id", "ALTER TABLE eval_service_requests ADD COLUMN workspace_id INTEGER"),
            ("eval_service_requests", "dataset_id", "ALTER TABLE eval_service_requests ADD COLUMN dataset_id INTEGER"),
            ("eval_service_requests", "model_id", "ALTER TABLE eval_service_requests ADD COLUMN model_id INTEGER"),
            ("eval_service_requests", "scene", "ALTER TABLE eval_service_requests ADD COLUMN scene VARCHAR(80) DEFAULT 'chat'"),
            ("eval_service_requests", "gray_version", "ALTER TABLE eval_service_requests ADD COLUMN gray_version VARCHAR(40) DEFAULT ''"),
            ("eval_service_requests", "report_path", "ALTER TABLE eval_service_requests ADD COLUMN report_path VARCHAR(500) DEFAULT ''"),
            ("eval_service_requests", "production_version", "ALTER TABLE eval_service_requests ADD COLUMN production_version VARCHAR(40) DEFAULT 'v1'"),
            ("eval_service_requests", "shadow_json", "ALTER TABLE eval_service_requests ADD COLUMN shadow_json TEXT DEFAULT '{}'"),
            ("eval_service_requests", "quote_version", "ALTER TABLE eval_service_requests ADD COLUMN quote_version VARCHAR(40) DEFAULT ''"),
            ("eval_service_requests", "previous_stable", "ALTER TABLE eval_service_requests ADD COLUMN previous_stable VARCHAR(40) DEFAULT ''"),
            ("eval_service_requests", "delivery_settled", "ALTER TABLE eval_service_requests ADD COLUMN delivery_settled BOOLEAN DEFAULT 0"),
            ("eval_service_requests", "traffic_pct", "ALTER TABLE eval_service_requests ADD COLUMN traffic_pct FLOAT DEFAULT 0"),
            ("eval_service_requests", "shadow_started_at", "ALTER TABLE eval_service_requests ADD COLUMN shadow_started_at DATETIME"),
            ("base_resources", "last_heartbeat", "ALTER TABLE base_resources ADD COLUMN last_heartbeat DATETIME"),
            ("audit_logs", "tenant_id", "ALTER TABLE audit_logs ADD COLUMN tenant_id VARCHAR(64) DEFAULT ''"),
            ("audit_logs", "trace_id", "ALTER TABLE audit_logs ADD COLUMN trace_id VARCHAR(64) DEFAULT ''"),
            ("audit_logs", "parent_trace_id", "ALTER TABLE audit_logs ADD COLUMN parent_trace_id VARCHAR(64) DEFAULT ''"),
            ("eval_results", "finish_reason", "ALTER TABLE eval_results ADD COLUMN finish_reason VARCHAR(32) DEFAULT ''"),
            ("eval_results", "error_code", "ALTER TABLE eval_results ADD COLUMN error_code VARCHAR(64) DEFAULT ''"),
            ("eval_results", "execution_status", "ALTER TABLE eval_results ADD COLUMN execution_status VARCHAR(32) DEFAULT 'legacy_unverified'"),
            ("eval_results", "score_status", "ALTER TABLE eval_results ADD COLUMN score_status VARCHAR(32) DEFAULT 'legacy_unverified'"),
            ("eval_results", "simulation", "ALTER TABLE eval_results ADD COLUMN simulation BOOLEAN DEFAULT 0"),
            ("eval_tasks", "simulation", "ALTER TABLE eval_tasks ADD COLUMN simulation BOOLEAN DEFAULT 0"),
            ("users", "tenant_id", "ALTER TABLE users ADD COLUMN tenant_id INTEGER"),
            ("users", "status", "ALTER TABLE users ADD COLUMN status VARCHAR(20) DEFAULT 'active'"),
            ("datasets", "tenant_id", "ALTER TABLE datasets ADD COLUMN tenant_id INTEGER"),
            ("datasets", "visibility", "ALTER TABLE datasets ADD COLUMN visibility VARCHAR(20) DEFAULT 'private'"),
            ("eval_models", "tenant_id", "ALTER TABLE eval_models ADD COLUMN tenant_id INTEGER"),
            ("eval_models", "visibility", "ALTER TABLE eval_models ADD COLUMN visibility VARCHAR(20) DEFAULT 'private'"),
            ("prompt_templates", "tenant_id", "ALTER TABLE prompt_templates ADD COLUMN tenant_id INTEGER"),
            ("prompt_templates", "visibility", "ALTER TABLE prompt_templates ADD COLUMN visibility VARCHAR(20) DEFAULT 'private'"),
            ("eval_tasks", "tenant_id", "ALTER TABLE eval_tasks ADD COLUMN tenant_id INTEGER"),
            ("eval_tasks", "visibility", "ALTER TABLE eval_tasks ADD COLUMN visibility VARCHAR(20) DEFAULT 'private'"),
            ("knowledge_entries", "tenant_id", "ALTER TABLE knowledge_entries ADD COLUMN tenant_id INTEGER"),
            ("knowledge_entries", "visibility", "ALTER TABLE knowledge_entries ADD COLUMN visibility VARCHAR(20) DEFAULT 'private'"),
            ("agent_sessions", "tenant_id", "ALTER TABLE agent_sessions ADD COLUMN tenant_id INTEGER"),
            ("agent_sessions", "visibility", "ALTER TABLE agent_sessions ADD COLUMN visibility VARCHAR(20) DEFAULT 'private'"),
            ("batch_snapshots", "tenant_id", "ALTER TABLE batch_snapshots ADD COLUMN tenant_id INTEGER"),
            ("batch_snapshots", "visibility", "ALTER TABLE batch_snapshots ADD COLUMN visibility VARCHAR(20) DEFAULT 'private'"),
            ("batch_snapshots", "creator_id", "ALTER TABLE batch_snapshots ADD COLUMN creator_id INTEGER"),
            ("eval_workspaces", "tenant_id", "ALTER TABLE eval_workspaces ADD COLUMN tenant_id INTEGER"),
            ("eval_workspaces", "visibility", "ALTER TABLE eval_workspaces ADD COLUMN visibility VARCHAR(20) DEFAULT 'shared'"),
            ("dataset_versions", "content_checksum", "ALTER TABLE dataset_versions ADD COLUMN content_checksum VARCHAR(64) DEFAULT ''"),
            ("eval_tasks", "lease_owner", "ALTER TABLE eval_tasks ADD COLUMN lease_owner VARCHAR(120) DEFAULT ''"),
            ("eval_tasks", "lease_until", "ALTER TABLE eval_tasks ADD COLUMN lease_until DATETIME"),
            ("eval_tasks", "fencing_token", "ALTER TABLE eval_tasks ADD COLUMN fencing_token INTEGER DEFAULT 0"),
            ("eval_tasks", "cancel_requested", "ALTER TABLE eval_tasks ADD COLUMN cancel_requested BOOLEAN DEFAULT 0"),
            ("eval_tasks", "attempt", "ALTER TABLE eval_tasks ADD COLUMN attempt INTEGER DEFAULT 0"),
            ("batch_jobs", "tokens_reserved", "ALTER TABLE batch_jobs ADD COLUMN tokens_reserved INTEGER DEFAULT 0"),
            ("batch_jobs", "tenant_id", "ALTER TABLE batch_jobs ADD COLUMN tenant_id INTEGER"),
            ("batch_shard_results", "content_hash", "ALTER TABLE batch_shard_results ADD COLUMN content_hash VARCHAR(64) DEFAULT ''"),
            ("batch_shard_results", "immutable", "ALTER TABLE batch_shard_results ADD COLUMN immutable BOOLEAN DEFAULT 1"),
            ("agent_sessions", "active_run_id", "ALTER TABLE agent_sessions ADD COLUMN active_run_id INTEGER"),
            ("agent_sessions", "row_version", "ALTER TABLE agent_sessions ADD COLUMN row_version INTEGER DEFAULT 0"),
            ("knowledge_entries", "source_hash", "ALTER TABLE knowledge_entries ADD COLUMN source_hash VARCHAR(64) DEFAULT ''"),
            ("knowledge_entries", "review_status", "ALTER TABLE knowledge_entries ADD COLUMN review_status VARCHAR(20) DEFAULT 'approved'"),
            ("knowledge_entries", "valid_until", "ALTER TABLE knowledge_entries ADD COLUMN valid_until DATETIME"),
            ("eval_service_requests", "tenant_id", "ALTER TABLE eval_service_requests ADD COLUMN tenant_id INTEGER"),
            ("eval_service_requests", "visibility", "ALTER TABLE eval_service_requests ADD COLUMN visibility VARCHAR(20) DEFAULT 'private'"),
            ("base_resources", "tenant_id", "ALTER TABLE base_resources ADD COLUMN tenant_id INTEGER"),
            ("base_resources", "visibility", "ALTER TABLE base_resources ADD COLUMN visibility VARCHAR(20) DEFAULT 'private'"),
            ("agent_runs", "planner_model_id", "ALTER TABLE agent_runs ADD COLUMN planner_model_id INTEGER"),
            ("agent_sessions", "planner_model_id", "ALTER TABLE agent_sessions ADD COLUMN planner_model_id INTEGER"),
            ("resource_call_logs", "tenant_id", "ALTER TABLE resource_call_logs ADD COLUMN tenant_id VARCHAR(64) DEFAULT ''"),
            ("resource_call_logs", "user_id", "ALTER TABLE resource_call_logs ADD COLUMN user_id INTEGER"),
            ("resource_call_logs", "version", "ALTER TABLE resource_call_logs ADD COLUMN version VARCHAR(32) DEFAULT ''"),
            ("resource_call_logs", "trace_id", "ALTER TABLE resource_call_logs ADD COLUMN trace_id VARCHAR(64) DEFAULT ''"),
            ("resource_call_logs", "input_digest", "ALTER TABLE resource_call_logs ADD COLUMN input_digest TEXT DEFAULT ''"),
            ("resource_call_logs", "output_digest", "ALTER TABLE resource_call_logs ADD COLUMN output_digest TEXT DEFAULT ''"),
            ("resource_call_logs", "input_hash", "ALTER TABLE resource_call_logs ADD COLUMN input_hash VARCHAR(64) DEFAULT ''"),
            ("resource_call_logs", "output_hash", "ALTER TABLE resource_call_logs ADD COLUMN output_hash VARCHAR(64) DEFAULT ''"),
            ("resource_call_logs", "source", "ALTER TABLE resource_call_logs ADD COLUMN source VARCHAR(32) DEFAULT 'gateway'"),
            ("resource_call_logs", "parent_correlation_id", "ALTER TABLE resource_call_logs ADD COLUMN parent_correlation_id VARCHAR(128) DEFAULT ''"),
        ]:
            try:
                r = await conn.execute(text(f"PRAGMA table_info({table})"))
                cols = [row[1] for row in r.fetchall()]
                if col not in cols:
                    await conn.execute(text(sql))
            except Exception:
                pass


async def seed_rbac(db):
    from sqlalchemy import select, text
    from app.models import Role, Permission
    from app.services.permission_loader import load_all_permissions

    r = await db.execute(select(Role).limit(1))
    if r.scalar_one_or_none():
        return
    perms_list = load_all_permissions()
    for resource, action, name in perms_list:
        db.add(Permission(code=f"{resource}:{action}", resource=resource, action=action, name=name))
    await db.flush()
    admin_role = Role(code="admin", name="管理员", data_scope="all")
    researcher_role = Role(code="researcher", name="评测人员", data_scope="own")
    viewer_role = Role(code="viewer", name="访客", data_scope="shared")
    db.add_all([admin_role, researcher_role, viewer_role])
    await db.flush()
    from app.services.rbac import RESEARCHER_PERMISSIONS, VIEWER_PERMISSIONS
    all_perms = await db.execute(select(Permission))
    perm_map = {p.code: p.id for p in all_perms.scalars().all()}
    admin_codes = [f"{r}:{a}" for r, a, _ in perms_list]
    for code in admin_codes:
        if code in perm_map:
            await db.execute(text(
                "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (:rid, :pid)"
            ), {"rid": admin_role.id, "pid": perm_map[code]})
    for code in RESEARCHER_PERMISSIONS:
        if code in perm_map:
            await db.execute(text(
                "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (:rid, :pid)"
            ), {"rid": researcher_role.id, "pid": perm_map[code]})
    for code in VIEWER_PERMISSIONS:
        if code in perm_map:
            await db.execute(text(
                "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (:rid, :pid)"
            ), {"rid": viewer_role.id, "pid": perm_map[code]})
    return True


async def sync_permissions(db):
    from sqlalchemy import select, text
    from app.models import Role, Permission
    from app.services.permission_loader import load_all_permissions

    perms_list = load_all_permissions()
    all_codes = [f"{r}:{a}" for r, a, _ in perms_list]
    existing = await db.execute(select(Permission.code))
    existing_codes = {r[0] for r in existing.all()}
    for resource, action, name in perms_list:
        code = f"{resource}:{action}"
        if code not in existing_codes:
            db.add(Permission(code=code, resource=resource, action=action, name=name))
    await db.flush()
    r = await db.execute(select(Role).where(Role.code == "admin"))
    admin_role = r.scalar_one_or_none()
    if not admin_role:
        return
    all_perms = await db.execute(select(Permission))
    perm_map = {p.code: p.id for p in all_perms.scalars().all()}
    for code in all_codes:
        if code in perm_map:
            await db.execute(text(
                "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (:rid, :pid)"
            ), {"rid": admin_role.id, "pid": perm_map[code]})
    from app.services.rbac import RESEARCHER_PERMISSIONS, VIEWER_PERMISSIONS
    for role_code, codes in (("researcher", RESEARCHER_PERMISSIONS), ("viewer", VIEWER_PERMISSIONS)):
        role = (await db.execute(select(Role).where(Role.code == role_code))).scalar_one_or_none()
        if not role:
            continue
        for code in codes:
            if code in perm_map:
                await db.execute(text(
                    "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (:rid, :pid)"
                ), {"rid": role.id, "pid": perm_map[code]})


async def seed_builtin_resources(db):
    from sqlalchemy import select
    from app.models import BaseResource
    from app.services.builtin_manifests import BUILTIN_MANIFESTS
    from app.utils.jsonutil import dumps

    for mf in BUILTIN_MANIFESTS:
        exists = await db.scalar(select(BaseResource.id).where(BaseResource.resource_id == mf["resource_id"]))
        if exists:
            continue
        db.add(BaseResource(
            resource_id=mf["resource_id"],
            resource_type=mf["resource_type"],
            name=mf["name"],
            version=mf["version"],
            spec_version=str(mf.get("spec_version", "0.6.1")),
            description=mf.get("description", ""),
            status="online",
            builtin=True,
            visibility="shared",
            manifest_json=dumps(mf),
            health_status="online",
        ))
    await db.flush()


async def seed_quality_rules(db):
    from sqlalchemy import select
    from app.models import QualityRule
    from app.services.quality_checker import DEFAULT_RULES
    from app.utils.jsonutil import dumps

    for rule in DEFAULT_RULES:
        exists = await db.scalar(select(QualityRule.id).where(QualityRule.code == rule["code"]))
        if exists:
            continue
        db.add(QualityRule(
            code=rule["code"],
            name=rule["name"],
            category=rule["category"],
            description=rule["description"],
            severity=rule["severity"],
            enabled=rule.get("enabled", True),
            config_json=dumps(rule.get("config") or {}),
        ))
    await db.flush()


async def seed_task_templates(db):
    from sqlalchemy import select
    from app.models import TaskTemplate
    from app.services.task_catalog import catalog_templates
    from app.utils.jsonutil import dumps

    for row in catalog_templates():
        exists = await db.scalar(select(TaskTemplate.id).where(TaskTemplate.code == row["code"]))
        if exists:
            continue
        db.add(TaskTemplate(
            code=row["code"],
            name=row["name"],
            category=row["category"],
            scene=row["scene"],
            industry=row["industry"],
            task_type=row["task_type"],
            judge_resource_id=row["judge_resource_id"],
            metric_weights_json=dumps(row["metric_weights"]),
            default_prompt=row["default_prompt"],
            rubric=row["rubric"],
            description=row["description"],
        ))
    await db.flush()


async def seed_alert_policies(db):
    from sqlalchemy import select
    from app.models import AlertPolicy

    defaults = [
        ("task_failed", "failed", "评测任务失败"),
        ("task_timeout", "timeout", "评测任务超时"),
        ("tool_failed", "tool_failed", "评测工具调用失败"),
        ("resource_short", "resource_short", "评测资源不足"),
        ("callback_error", "callback_error", "状态回传异常"),
    ]
    for code, event_type, title in defaults:
        exists = await db.scalar(select(AlertPolicy.id).where(AlertPolicy.code == code))
        if exists:
            continue
        db.add(AlertPolicy(code=code, event_type=event_type, title=title, enabled=True))
    await db.flush()


async def seed_leaderboard_weights(db):
    from sqlalchemy import select
    from app.models import LeaderboardWeight
    from app.services.task_catalog import CAPABILITIES, INDUSTRIES, SCENES

    defaults = [("overall", "general", 1.0)]
    for code, _ in INDUSTRIES:
        defaults.append(("overall", code, 1.0))
    for code, _ in CAPABILITIES:
        defaults.append(("ability", code, 1.0))
    for code, _ in SCENES:
        defaults.append(("ability", code, 1.0))
        defaults.append(("special", code, 1.0))
    for board, key, w in defaults:
        exists = await db.scalar(
            select(LeaderboardWeight.id).where(LeaderboardWeight.board_type == board, LeaderboardWeight.dim_key == key)
        )
        if exists:
            continue
        db.add(LeaderboardWeight(board_type=board, dim_key=key, weight=w))
    await db.flush()


async def seed_default_workspace(db):
    from sqlalchemy import select
    from app.models import EvalWorkspace, Tenant

    tenant = await db.scalar(select(Tenant).where(Tenant.code == "default"))
    exists = await db.scalar(select(EvalWorkspace.id).where(EvalWorkspace.code == "default"))
    if not exists:
        db.add(EvalWorkspace(
            name="默认工作空间",
            code="default",
            quota_tokens=1000000,
            quota_calls=100000,
            tenant_id=tenant.id if tenant else None,
            visibility="shared",
        ))
        await db.flush()
    elif tenant:
        ws = await db.scalar(select(EvalWorkspace).where(EvalWorkspace.code == "default"))
        if ws and getattr(ws, "tenant_id", None) is None:
            ws.tenant_id = tenant.id
            await db.flush()


async def seed_tenants_and_backfill(db):
    """创建默认租户并把历史对象/用户回填；不明归属标 isolated。"""
    from sqlalchemy import select, text, update
    from app.models import (
        Tenant,
        TenantMembership,
        User,
        Dataset,
        EvalModel,
        PromptTemplate,
        EvalTask,
        KnowledgeEntry,
        AgentSession,
        BatchSnapshot,
        EvalWorkspace,
        Role,
    )

    default = await db.scalar(select(Tenant).where(Tenant.code == "default"))
    if not default:
        default = Tenant(code="default", name="默认租户", status="active")
        db.add(default)
        await db.flush()

    # viewer 角色若仍是 all，收紧为 shared（不强制改已手工调整的）
    viewer = await db.scalar(select(Role).where(Role.code == "viewer"))
    if viewer and (viewer.data_scope or "") == "all":
        viewer.data_scope = "shared"

    users = (await db.execute(select(User))).scalars().all()
    for u in users:
        if getattr(u, "status", None) in (None, ""):
            u.status = "active"
        if getattr(u, "tenant_id", None) is None:
            u.tenant_id = default.id
        mem = await db.scalar(
            select(TenantMembership.id).where(
                TenantMembership.tenant_id == default.id,
                TenantMembership.user_id == u.id,
            )
        )
        if not mem:
            db.add(TenantMembership(tenant_id=default.id, user_id=u.id))
    await db.flush()

    from app.models import EvalServiceRequest, BaseResource

    scoped_models = [
        (Dataset, "datasets"),
        (EvalModel, "eval_models"),
        (PromptTemplate, "prompt_templates"),
        (EvalTask, "eval_tasks"),
        (KnowledgeEntry, "knowledge_entries"),
        (AgentSession, "agent_sessions"),
        (BatchSnapshot, "batch_snapshots"),
        (EvalWorkspace, "eval_workspaces"),
        (EvalServiceRequest, "eval_service_requests"),
        (BaseResource, "base_resources"),
    ]
    for model, _table in scoped_models:
        rows = (await db.execute(select(model))).scalars().all()
        for row in rows:
            if getattr(row, "tenant_id", None) is None:
                row.tenant_id = default.id
            vis = getattr(row, "visibility", None)
            if not vis:
                if model is EvalWorkspace:
                    row.visibility = "shared"
                elif model is BaseResource and getattr(row, "builtin", False):
                    row.visibility = "shared"
                else:
                    row.visibility = "private"
            creator = getattr(row, "creator_id", None)
            owner = getattr(row, "owner_id", None) if hasattr(row, "owner_id") else None
            if model is BaseResource and getattr(row, "builtin", False):
                row.visibility = "shared"
                continue
            if creator is None and owner is None and model is not EvalWorkspace:
                # 不明归属进入隔离，禁止普通范围读取
                if getattr(row, "visibility", "private") == "private" and model is not BatchSnapshot:
                    # 内置数据包等系统对象：标 shared 便于同租户只读
                    if model is Dataset and getattr(row, "data_source", "") == "builtin":
                        row.visibility = "shared"
                    elif model is KnowledgeEntry and not creator:
                        row.visibility = "shared"
                    else:
                        row.visibility = "isolated"
    await db.flush()


async def seed_knowledge(db):
    from sqlalchemy import select
    from app.models import KnowledgeEntry, TaskTemplate
    from app.utils.jsonutil import dumps

    tpls = (await db.execute(select(TaskTemplate).limit(8))).scalars().all()
    for t in tpls:
        exists = await db.scalar(select(KnowledgeEntry.id).where(KnowledgeEntry.ref_type == "template", KnowledgeEntry.ref_id == t.code))
        if exists:
            continue
        db.add(KnowledgeEntry(
            category="template",
            title=t.name,
            content=t.description or t.rubric,
            tags_json=dumps([t.scene, t.industry]),
            ref_type="template",
            ref_id=t.code,
        ))
    await db.flush()


async def seed_db():
    from sqlalchemy import select
    from app.models import User, Role, Tenant
    from app.utils.auth import get_password_hash

    async with async_session() as db:
        await seed_rbac(db)
        await sync_permissions(db)
        await seed_tenants_and_backfill(db)
        await seed_builtin_resources(db)
        await seed_quality_rules(db)
        await seed_task_templates(db)
        from app.api.benchmarks import sync_benchmark_suites
        await sync_benchmark_suites(db)
        await seed_alert_policies(db)
        await seed_leaderboard_weights(db)
        await seed_default_workspace(db)
        await seed_knowledge(db)
        await seed_tenants_and_backfill(db)
        r = await db.execute(select(Role).where(Role.code == "admin"))
        admin_role = r.scalar_one_or_none()
        default_tenant = await db.scalar(select(Tenant).where(Tenant.code == "default"))
        r = await db.execute(select(User).where(User.username == "admin"))
        admin = r.scalar_one_or_none()
        if not admin:
            from app.services.prod_guards import bootstrap_admin_password

            bootstrap_pw = bootstrap_admin_password()
            if bootstrap_pw:
                db.add(User(
                    username="admin",
                    password_hash=get_password_hash(bootstrap_pw),
                    role="admin",
                    role_id=admin_role.id if admin_role else None,
                    email="admin@example.com",
                    tenant_id=default_tenant.id if default_tenant else None,
                    status="active",
                ))
                await db.commit()
            else:
                import logging
                logging.getLogger(__name__).warning(
                    "production: skip default admin seed; set ADMIN_BOOTSTRAP_PASSWORD"
                )
        else:
            if getattr(admin, "role", None) != "admin":
                admin.role = "admin"
            if admin_role and getattr(admin, "role_id", None) is None:
                admin.role_id = admin_role.id
            if getattr(admin, "tenant_id", None) is None and default_tenant:
                admin.tenant_id = default_tenant.id
            if not getattr(admin, "status", None):
                admin.status = "active"
            await db.commit()
        r_roles = await db.execute(select(Role))
        roles_by_code = {ro.code: ro.id for ro in r_roles.scalars().all()}
        r_users = await db.execute(select(User).where(User.role_id.is_(None)))
        for u in r_users.scalars().all():
            code = getattr(u, "role", None) or "viewer"
            if code == "user":
                code = "viewer"
            if code in roles_by_code:
                u.role_id = roles_by_code[code]
        await seed_tenants_and_backfill(db)
        await db.commit()


async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
