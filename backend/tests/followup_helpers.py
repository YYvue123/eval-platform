from __future__ import annotations

from tests import isolated_env  # noqa: F401

import asyncio
import contextlib
import os
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

from sqlalchemy import select


def login_admin(client) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    if response.status_code != 200:
        raise AssertionError(response.text)
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_tenant_admin_header(client, prefix: str) -> dict[str, str]:
    from app.database import async_session
    from app.models import Role, Tenant, TenantMembership, User
    from app.utils.auth import get_password_hash

    username = f"{prefix}-{uuid.uuid4().hex[:8]}"
    password = "Test1234!"

    async def create_user() -> None:
        async with async_session() as db:
            tenant = Tenant(
                code=f"{prefix}-{uuid.uuid4().hex[:8]}",
                name=prefix,
                status="active",
            )
            db.add(tenant)
            await db.flush()
            role = await db.scalar(select(Role).where(Role.code == "admin"))
            user = User(
                username=username,
                password_hash=get_password_hash(password),
                role="admin",
                role_id=role.id if role else None,
                tenant_id=tenant.id,
                status="active",
            )
            db.add(user)
            await db.flush()
            db.add(TenantMembership(tenant_id=tenant.id, user_id=user.id))
            await db.commit()

    asyncio.run(create_user())
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    if response.status_code != 200:
        raise AssertionError(response.text)
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_other_tenant_admin(client) -> dict[str, str]:
    return create_tenant_admin_header(client, "other")


def tool_manifest(rid: str, endpoint: str, **overrides) -> dict:
    manifest = {
        "spec_version": "0.6.1",
        "resource_id": rid,
        "resource_type": "tool",
        "name": "followup stats tool",
        "description": "Task 5 real HTTP fixture",
        "version": "1.0.0",
        "owner": {"name": "test", "contact": "test", "email": "test@example.com"},
        "capabilities": {
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "call_mode": "sync",
            "idempotent": True,
            "timeout": 10,
            "side_effects": "none",
        },
        "interfaces": {
            "endpoint": endpoint,
            "method": "POST",
            "auth_type": "none",
            "egress_allowlist": ["127.0.0.1", "localhost"],
        },
    }
    manifest.update(overrides)
    return manifest


@contextlib.contextmanager
def stats_service():
    root = Path(__file__).resolve().parents[2]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    env.pop("DATABASE_URL", None)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "tools.stats_service.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    health = f"http://127.0.0.1:{port}/health"
    deadline = time.monotonic() + 10
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("stats service exited before health check")
            try:
                with urllib.request.urlopen(health, timeout=0.5) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("stats service health check timed out")
        yield f"http://127.0.0.1:{port}"
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
