"""权限加载：从配置文件 + 前端扫描结果自动合并"""
import json
from pathlib import Path

ACTION_NAMES = {
    "workspace": "企业工作空间管理",
    "credential": "接入密钥管理",
    "list": "列表",
    "view": "详情",
    "view_mine": "我的",
    "create": "创建",
    "edit": "编辑",
    "delete": "删除",
    "export": "导出",
    "export_sensitive": "敏感导出",
    "invoke": "调用",
    "publish": "发布",
    "audit": "审核",
    "confirm": "确认",
    "backup": "备份",
    "admit": "准入",
    "ticket": "工单",
    "run": "执行",
}

RESOURCE_NAMES = {
    "dashboard": "工作台",
    "user": "用户管理",
    "notification": "通知",
    "role": "权限管理",
    "audit": "操作审计",
    "dataset": "评测数据",
    "model": "被测模型",
    "prompt": "提示词",
    "resource": "工具底座",
    "quality": "数据质量",
    "task": "评测任务",
    "leaderboard": "模型榜单",
    "service": "评测服务",
    "agent": "编排Agent",
    "ops": "运行支撑",
}


def _base_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def load_all_permissions() -> list[tuple[str, str, str]]:
    base = _base_dir()
    result_map = {}

    config_path = base / "permissions.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            for p in data.get("permissions", []):
                r, a, n = p.get("resource"), p.get("action"), p.get("name")
                if r and a:
                    code = f"{r}:{a}"
                    result_map[code] = (r, a, n or _auto_name(r, a))
        except Exception:
            pass

    discovered_path = base / "permissions.discovered.json"
    if discovered_path.exists():
        try:
            codes = json.loads(discovered_path.read_text(encoding="utf-8"))
            if isinstance(codes, list):
                for code in codes:
                    if isinstance(code, str) and ":" in code and code not in result_map:
                        r, _, a = code.partition(":")
                        result_map[code] = (r, a, _auto_name(r, a))
        except Exception:
            pass

    return [(r, a, n) for _, (r, a, n) in sorted(result_map.items())]


def _auto_name(resource: str, action: str) -> str:
    rn = RESOURCE_NAMES.get(resource, resource)
    an = ACTION_NAMES.get(action, action)
    return f"{rn}{an}"
