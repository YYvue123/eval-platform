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
        BaseResource,
        ResourceCallLog,
        ResourceEvent,
        BatchSnapshot,
        BatchJob,
        BatchShardResult,
        EvalTask,
        EvalResult,
        EvalLineage,
        QualityReport,
        QualityRule,
        QualityIssue,
        EvalServiceRequest,
        TaskTemplate,
        TaskEvent,
        TaskSubtask,
        AlertPolicy,
        EvalWorkspace,
        LeaderboardWeight,
        LeaderboardSnapshot,
        KnowledgeEntry,
        AgentSession,
        AgentMessage,
        AgentSuggestion,
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
            ("base_resources", "last_heartbeat", "ALTER TABLE base_resources ADD COLUMN last_heartbeat DATETIME"),
            ("audit_logs", "tenant_id", "ALTER TABLE audit_logs ADD COLUMN tenant_id VARCHAR(64) DEFAULT ''"),
            ("audit_logs", "trace_id", "ALTER TABLE audit_logs ADD COLUMN trace_id VARCHAR(64) DEFAULT ''"),
            ("audit_logs", "parent_trace_id", "ALTER TABLE audit_logs ADD COLUMN parent_trace_id VARCHAR(64) DEFAULT ''"),
            ("eval_results", "finish_reason", "ALTER TABLE eval_results ADD COLUMN finish_reason VARCHAR(32) DEFAULT ''"),
            ("eval_results", "error_code", "ALTER TABLE eval_results ADD COLUMN error_code VARCHAR(64) DEFAULT ''"),
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
    viewer_role = Role(code="viewer", name="访客", data_scope="all")
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
    from app.models import EvalWorkspace

    exists = await db.scalar(select(EvalWorkspace.id).where(EvalWorkspace.code == "default"))
    if not exists:
        db.add(EvalWorkspace(name="默认工作空间", code="default", quota_tokens=1000000, quota_calls=100000))
        await db.flush()


async def seed_knowledge(db):
    from sqlalchemy import select
    from app.models import KnowledgeEntry, TaskTemplate
    from app.utils.jsonutil import dumps

    if not await db.scalar(select(KnowledgeEntry.id).limit(1)):
        db.add(KnowledgeEntry(
            category="exception",
            title="任务失败不自动恢复",
            content="诊断 Agent 只给建议，需人工确认后通过工具重跑，禁止直接改队列。",
            tags_json=dumps(["failed", "retry"]),
        ))
        db.add(KnowledgeEntry(
            category="profile",
            title="内置裁判画像",
            content="exact_match/contains/fuzzy 与四类安全启发式裁判可直接编排。",
            tags_json=dumps(["tool", "judge"]),
        ))
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
    from app.models import User, Role
    from app.utils.auth import get_password_hash

    async with async_session() as db:
        await seed_rbac(db)
        await sync_permissions(db)
        await seed_builtin_resources(db)
        await seed_quality_rules(db)
        await seed_task_templates(db)
        from app.services.eval_packs import seed_eval_packs
        await seed_eval_packs(db)
        await seed_alert_policies(db)
        await seed_leaderboard_weights(db)
        await seed_default_workspace(db)
        await seed_knowledge(db)
        r = await db.execute(select(Role).where(Role.code == "admin"))
        admin_role = r.scalar_one_or_none()
        r = await db.execute(select(User).where(User.username == "admin"))
        admin = r.scalar_one_or_none()
        if not admin:
            db.add(User(
                username="admin",
                password_hash=get_password_hash("admin123"),
                role="admin",
                role_id=admin_role.id if admin_role else None,
                email="admin@example.com",
            ))
            await db.commit()
        else:
            if getattr(admin, "role", None) != "admin":
                admin.role = "admin"
            if admin_role and getattr(admin, "role_id", None) is None:
                admin.role_id = admin_role.id
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
            await db.commit()


async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
