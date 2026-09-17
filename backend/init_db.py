"""初始化数据库：表结构、RBAC 角色权限、默认用户"""
import asyncio
from app.database import init_db, seed_db


async def main():
    await init_db()
    await seed_db()
    print("数据库初始化完成：表结构、RBAC、默认用户 admin/admin123")


if __name__ == "__main__":
    asyncio.run(main())
