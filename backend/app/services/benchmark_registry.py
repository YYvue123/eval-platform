"""基准框架：指标注册、套件 readiness、MUT 工具隔离、不可观测指标。"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

# —— 指标注册表 ——
METRIC_REGISTRY: dict[str, dict[str, Any]] = {
    "completion_rate": {"name": "任务完成率", "type": "score", "observable": True},
    "satisfaction": {"name": "效果满意度", "type": "score", "observable": True},
    "resource_efficiency": {"name": "资源消耗效率", "type": "score", "observable": True},
    "exact_match": {"name": "精确匹配", "type": "score", "observable": True},
    "fuzzy_match": {"name": "模糊匹配", "type": "score", "observable": True},
    "citation": {"name": "依据引用", "type": "score", "observable": True},
    "code_pass": {"name": "用例通过率", "type": "score", "observable": True},
    "trajectory_quality": {"name": "轨迹质量", "type": "score", "observable": False},  # 默认不可观测
    "internal_state": {"name": "内部状态正确性", "type": "score", "observable": False},
    "domain_knowledge": {"name": "行业知识适配", "type": "score", "observable": True},
}

# 平台管理工具：MUT / 被测 Agent 禁止
PLATFORM_ADMIN_TOOLS = frozenset({
    "create_task",
    "enqueue_task",
    "cancel_task",
    "retry_task",
    "user_admin",
    "role_admin",
    "tenant_admin",
    "resource_register",
    "offline_resource",
    "publish_dataset",
    "publish_prompt",
    "promote_service",
})

MUT_ALLOWED_TOOLS = frozenset({
    "search_knowledge",
    "http_fetch_fixture",
    "cart_get",
    "order_draft_set",
})

# 输入模态 schema（ready 必须满足）
INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "text": {
        "type": "object",
        "required": ["input"],
        "properties": {"input": {"type": "string"}, "reference": {"type": "string"}},
        "media": False,
    },
    "table": {
        "type": "object",
        "required": ["table"],
        "properties": {
            "table": {"type": "object"},
            "question": {"type": "string"},
            "reference": {"type": "string"},
        },
        "media": False,
    },
    "code": {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string"},
            "tests": {"type": "array"},
            "reference": {"type": "string"},
        },
        "media": False,
        "host_exec_forbidden": True,
    },
    "rag": {
        "type": "object",
        "required": ["question", "contexts"],
        "properties": {
            "question": {"type": "string"},
            "contexts": {"type": "array"},
            "reference": {"type": "string"},
        },
        "media": False,
    },
    "media": {
        "type": "object",
        "required": ["media_uri", "media_type"],
        "properties": {
            "media_uri": {"type": "string"},
            "media_type": {"enum": ["image", "audio", "video"]},
            "transcript": {"type": "string"},
        },
        "media": True,
        "forbid_string_only_media": True,
    },
    "mut": {
        "type": "object",
        "required": ["goal", "initial_state", "expected_final_state"],
        "properties": {
            "goal": {"type": "string"},
            "initial_state": {"type": "object"},
            "expected_final_state": {"type": "object"},
            "allowed_tools": {"type": "array"},
        },
        "media": False,
    },
}


def _suite_base(**extra: Any) -> dict[str, Any]:
    base = {
        "license": "internal-eval",
        "calibration_report": "accepted-for-internal-ready",
        "has_real_inputs": True,
        "has_oracle": True,
        "code_host_exec": False,
        "mut_isolated": True,
        "string_only_media": False,
        "readiness_target": "ready",
    }
    base.update(extra)
    return base


def default_suites() -> list[dict[str, Any]]:
    """WP11 全量：文本/媒体/MUT/金融政务 + 其余行业保持 draft。"""
    return [
        {
            "code": "bench.chat",
            "name": "智能对话（文本）",
            "category": "text",
            "template_code": "scene.chat",
            "metrics": ["completion_rate", "satisfaction", "exact_match"],
            "input_modality": "text",
            "oracle_type": "reference",
            **_suite_base(),
        },
        {
            "code": "bench.table",
            "name": "表格分析",
            "category": "text",
            "template_code": "scene.table",
            "metrics": ["completion_rate", "exact_match"],
            "input_modality": "table",
            "oracle_type": "reference",
            **_suite_base(),
        },
        {
            "code": "bench.writing",
            "name": "文本写作",
            "category": "text",
            "template_code": "scene.writing",
            "metrics": ["satisfaction", "fuzzy_match"],
            "input_modality": "text",
            "oracle_type": "human",
            **_suite_base(),
        },
        {
            "code": "bench.rag",
            "name": "RAG 检索增强",
            "category": "text",
            "template_code": "scene.rag",
            "metrics": ["citation", "exact_match", "satisfaction"],
            "input_modality": "rag",
            "oracle_type": "reference",
            **_suite_base(),
        },
        {
            "code": "bench.code",
            "name": "代码应用",
            "category": "text",
            "template_code": "scene.code",
            "metrics": ["code_pass", "completion_rate"],
            "input_modality": "code",
            "oracle_type": "unit_tests",
            **_suite_base(),
        },
        {
            "code": "bench.finance",
            "name": "金融行业包",
            "category": "industry",
            "template_code": "industry.finance",
            "metrics": ["domain_knowledge", "completion_rate"],
            "input_modality": "text",
            "oracle_type": "reference",
            **_suite_base(),
        },
        {
            "code": "bench.gov",
            "name": "政务行业包",
            "category": "industry",
            "template_code": "industry.gov",
            "metrics": ["domain_knowledge", "completion_rate"],
            "input_modality": "text",
            "oracle_type": "reference",
            **_suite_base(),
        },
        {
            "code": "bench.media.video",
            "name": "媒体多模态（真实 fixture）",
            "category": "media",
            "template_code": "scene.video",
            "metrics": ["satisfaction", "trajectory_quality"],
            "input_modality": "media",
            "oracle_type": "human",
            **_suite_base(),
        },
        {
            "code": "bench.mut.episode",
            "name": "被测 Agent Episode",
            "category": "mut",
            "template_code": "scene.agent",
            "metrics": ["completion_rate", "trajectory_quality", "internal_state"],
            "input_modality": "mut",
            "oracle_type": "final_state",
            **_suite_base(),
        },
        # 其余行业骨架：无金标 → draft
        {
            "code": "bench.healthcare",
            "name": "医疗行业包（骨架）",
            "category": "industry",
            "template_code": "industry.healthcare",
            "metrics": ["domain_knowledge"],
            "input_modality": "text",
            "oracle_type": "reference",
            **_suite_base(
                has_real_inputs=False,
                has_oracle=False,
                calibration_report="",
                license="tbd",
                readiness_target="draft",
            ),
        },
    ]


def metric_out(code: str) -> dict:
    m = METRIC_REGISTRY.get(code) or {"name": code, "type": "score", "observable": True}
    return {
        "code": code,
        "name": m["name"],
        "type": m.get("type") or "score",
        "observable": bool(m.get("observable", True)),
        "status": "ok" if m.get("observable", True) else "not_observable",
    }


def assert_mut_tool_allowed(tool_name: str) -> None:
    if tool_name in PLATFORM_ADMIN_TOOLS:
        raise PermissionError(f"mut_forbidden_platform_tool:{tool_name}")


def validate_sample_against_schema(modality: str, sample: dict) -> list[str]:
    schema = INPUT_SCHEMAS.get(modality) or INPUT_SCHEMAS["text"]
    errors: list[str] = []
    if schema.get("forbid_string_only_media") or schema.get("media"):
        if sample.get("media_as_string") or (
            isinstance(sample.get("media"), str) and not sample.get("media_uri")
        ):
            errors.append("media_must_not_be_string_description")
        if schema.get("media") and not sample.get("media_uri"):
            errors.append("media_uri_required")
    for key in schema.get("required") or []:
        if key not in sample or sample.get(key) in (None, ""):
            errors.append(f"missing:{key}")
    if schema.get("host_exec_forbidden") and sample.get("execute_on_host"):
        errors.append("code_must_not_execute_on_host")
    return errors


def compute_readiness(suite: dict) -> dict:
    """根据门禁计算 readiness；缺资源 → draft/blocked，不得静默 ready。"""
    blockers: list[str] = []
    warnings: list[str] = []

    for m in suite.get("metrics") or []:
        if m not in METRIC_REGISTRY:
            blockers.append(f"unknown_metric:{m}")
        elif not METRIC_REGISTRY[m].get("observable", True):
            warnings.append(f"not_observable:{m}")

    modality = suite.get("input_modality") or "text"
    if modality not in INPUT_SCHEMAS:
        blockers.append(f"unknown_modality:{modality}")

    if not suite.get("has_real_inputs"):
        blockers.append("missing_real_inputs")
    if not suite.get("has_oracle"):
        blockers.append("missing_oracle_or_human_gold")
    if not (suite.get("license") or "").strip() or suite.get("license") == "tbd":
        blockers.append("license_unset")
    if not (suite.get("calibration_report") or "").strip():
        warnings.append("calibration_pending")

    if suite.get("code_host_exec"):
        blockers.append("code_host_exec_forbidden")
    if suite.get("string_only_media"):
        blockers.append("media_string_description_forbidden")
    if not suite.get("mut_isolated", True) and suite.get("category") == "mut":
        blockers.append("mut_not_isolated_from_platform_tools")

    # 若声明 ready 目标且有 pack，则叠加 pack 资源检查
    try:
        from app.services import benchmark_packs as packs

        if suite.get("code") in packs.PACK_INDEX and suite.get("readiness_target") == "ready":
            blockers.extend(packs.assert_pack_ready_resources(suite["code"]))
            # 媒体包：再跑 adapter
            if suite.get("category") == "media":
                from app.services import media_adapter

                pack = packs.load_pack(suite["code"])
                for s in pack.get("samples") or []:
                    errors = media_adapter.validate_media_sample(s)
                    blockers.extend(errors)
    except Exception as exc:  # noqa: BLE001 — readiness 不得因导入失败静默 ready
        blockers.append(f"pack_check_error:{exc}")

    # 去重保持顺序
    seen = set()
    uniq = []
    for b in blockers:
        if b not in seen:
            seen.add(b)
            uniq.append(b)
    blockers = uniq

    if blockers:
        if suite.get("readiness_target") == "ready":
            status = "blocked"
        else:
            status = "draft"
    else:
        status = "ready" if suite.get("readiness_target") == "ready" else "draft"

    return {
        "status": status,
        "blockers": blockers,
        "warnings": warnings,
        "metrics": [metric_out(m) for m in (suite.get("metrics") or [])],
        "input_schema": deepcopy(INPUT_SCHEMAS.get(modality, {})),
    }


def suite_public_view(suite: dict, readiness: dict | None = None) -> dict:
    r = readiness or compute_readiness(suite)
    return {
        "code": suite["code"],
        "name": suite["name"],
        "category": suite.get("category"),
        "template_code": suite.get("template_code"),
        "input_modality": suite.get("input_modality"),
        "oracle_type": suite.get("oracle_type"),
        "license": suite.get("license"),
        "readiness": r["status"],
        "blockers": r["blockers"],
        "warnings": r["warnings"],
        "metrics": r["metrics"],
        "input_schema": r["input_schema"],
        "mut_isolated": bool(suite.get("mut_isolated", True)),
        "code_host_exec": bool(suite.get("code_host_exec")),
    }
