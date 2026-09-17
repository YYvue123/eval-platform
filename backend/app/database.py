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
        PromptTemplate,
        PromptVersion,
        BaseResource,
        ResourceCallLog,
        EvalTask,
        EvalResult,
        QualityReport,
        EvalServiceRequest,
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


async def seed_db():
    from sqlalchemy import select
    from app.models import User, Role
    from app.utils.auth import get_password_hash

    async with async_session() as db:
        await seed_rbac(db)
        await sync_permissions(db)
        await seed_builtin_resources(db)
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
