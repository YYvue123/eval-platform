"""OpenAPI / Swagger 文档元数据。"""

API_DESCRIPTION = """
大模型智能评测平台 REST API。

覆盖登录与 RBAC，以及评测数据、被测模型、提示词、数据质量、工具底座、批量评测任务、榜单与评测服务。
工具底座遵循《标准接口规范 V0.6.1》的 Manifest 注册与统一消息信封。

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
    {"name": "评测数据", "description": "数据集导入、版本与导出"},
    {"name": "被测模型", "description": "模型注册、健康检查与推理调用"},
    {"name": "提示词工程", "description": "评测提示词模板与版本"},
    {"name": "工具底座", "description": "Manifest 注册、发现与信封调用"},
    {"name": "数据质量", "description": "数据集质量检测报告"},
    {"name": "评测任务", "description": "批量评测执行与结果"},
    {"name": "模型榜单", "description": "按最新成功任务聚合排名"},
    {"name": "评测服务", "description": "评测需求受理与交付"},
]
