"""OpenAPI / Swagger 文档元数据。"""

API_DESCRIPTION = """
大模型智能评测平台 REST API。

当前仓库是从 llm-manager 抽出的可运行骨架：登录、RBAC、用户、通知、审计与工作台。
评测数据、被测模型、工具底座与批量评测将按接口规范后续接入。

## 认证方式

管理接口（`/api/*`，登录/注册除外）使用登录 JWT：

`Authorization: Bearer <access_token>`
"""

OPENAPI_TAGS = [
    {"name": "认证", "description": "登录与注册"},
    {"name": "工作台", "description": "平台概览"},
    {"name": "用户管理", "description": "用户与个人中心"},
    {"name": "角色管理", "description": "角色与权限"},
    {"name": "通知管理", "description": "系统通知"},
    {"name": "操作审计", "description": "关键操作日志"},
]
