"""大模型智能评测平台 - FastAPI 主入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from app.api import auth, users, dashboard, notifications, roles, audit
from app.api import datasets, models, prompts, resources, tasks, quality
from app.database import init_db, seed_db
from app.config import settings
from app.exceptions import register_exception_handlers
from app.logging_config import setup_logging
from app.middleware.logging_middleware import LoggingMiddleware
from app.openapi_meta import API_DESCRIPTION, OPENAPI_TAGS

setup_logging(
    level=settings.LOG_LEVEL,
    log_dir=settings.LOG_DIR,
    max_bytes=settings.LOG_MAX_BYTES,
    backup_count=settings.LOG_BACKUP_COUNT,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import logging
    import os
    log = logging.getLogger(__name__)
    log.info("启动中: 创建目录、初始化数据库...")
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.LOG_DIR, exist_ok=True)
    await init_db()
    await seed_db()
    log.info("启动完成: UPLOAD_DIR=%s, LOG_DIR=%s", settings.UPLOAD_DIR, settings.LOG_DIR)
    yield


app = FastAPI(
    title="大模型智能评测平台 API",
    description=API_DESCRIPTION,
    version="0.1.0",
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True, "docExpansion": "list"},
)

register_exception_handlers(app)

app.add_middleware(LoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["工作台"])
app.include_router(users.router, prefix="/api/users", tags=["用户管理"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["通知管理"])
app.include_router(roles.router, prefix="/api/roles", tags=["角色管理"])
app.include_router(audit.router, prefix="/api/audit", tags=["操作审计"])
app.include_router(datasets.router, prefix="/api/datasets", tags=["评测数据"])
app.include_router(models.router, prefix="/api/models", tags=["被测模型"])
app.include_router(prompts.router, prefix="/api/prompts", tags=["提示词工程"])
app.include_router(resources.router, prefix="/api/resources", tags=["工具底座"])
app.include_router(quality.router, prefix="/api/quality", tags=["数据质量"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["评测任务"])
app.include_router(tasks.leaderboard_router, prefix="/api/leaderboard", tags=["模型榜单"])
app.include_router(tasks.service_router, prefix="/api/services", tags=["评测服务"])


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=OPENAPI_TAGS,
    )
    schema["servers"] = [{"url": "/", "description": "当前站点（经 Nginx 反代时与浏览器同源）"}]
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/api/openapi.json", include_in_schema=False)
async def openapi_via_api_proxy():
    return JSONResponse(app.openapi())
