"""GoalSpec、澄清缺口与计划 canonical hash。"""
from __future__ import annotations

import hashlib
import json
from typing import Any


GOAL_SPEC_VERSION = "1.0"


def build_goal_spec(
    *,
    requirement: str,
    scene: str,
    industry: str,
    objective: str = "",
    token_budget: int = 0,
    success_criteria: list[str] | None = None,
) -> dict:
    return {
        "schema_version": GOAL_SPEC_VERSION,
        "requirement": (requirement or "").strip(),
        "scene": scene or "chat",
        "industry": industry or "general",
        "objective": (objective or requirement or "").strip()[:500],
        "token_budget": int(token_budget or 0),
        "success_criteria": success_criteria or ["plan_ready", "approval_consumed_once"],
    }


def clarification_gaps(goal: dict, plan: dict) -> list[dict]:
    """缺模型/目标/预算时返回澄清项（确定性规则）。"""
    gaps: list[dict] = []
    if not (goal.get("objective") or "").strip():
        gaps.append({"field": "objective", "question": "请补充评测目标/成功标准", "severity": "high"})
    if not plan.get("model_id"):
        gaps.append({"field": "model_id", "question": "缺少可用被测模型，请指定或注册模型", "severity": "high"})
    if not plan.get("dataset_id"):
        gaps.append({"field": "dataset_id", "question": "缺少匹配场景的数据集", "severity": "high"})
    if int(goal.get("token_budget") or 0) <= 0 and not plan.get("trial_run"):
        gaps.append({"field": "token_budget", "question": "正式评测请给出 token 预算（或改为 trial_run）", "severity": "medium"})
    if plan.get("resource_gaps"):
        for g in plan["resource_gaps"]:
            gaps.append({"field": "resource", "question": g, "severity": "high"})
    return gaps


def plan_fingerprint_fields(plan: dict) -> dict[str, Any]:
    """参与审批 hash 的冻结字段（不含密钥）。"""
    return {
        "name": plan.get("name"),
        "requirement": plan.get("requirement"),
        "scene": plan.get("scene"),
        "industry": plan.get("industry"),
        "task_type": plan.get("task_type"),
        "template_code": plan.get("template_code"),
        "judge_resource_id": plan.get("judge_resource_id"),
        "dataset_id": plan.get("dataset_id"),
        "dataset_version_id": plan.get("dataset_version_id"),
        "model_id": plan.get("model_id"),
        "model_version_id": plan.get("model_version_id"),
        "trial_run": bool(plan.get("trial_run")),
        "token_budget": int(plan.get("token_budget") or 0),
        "goal_objective": (plan.get("goal_spec") or {}).get("objective"),
    }


def canonical_plan_hash(plan: dict) -> str:
    body = plan_fingerprint_fields(plan)
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def plans_semantically_equal(a: dict, b: dict) -> bool:
    return canonical_plan_hash(a) == canonical_plan_hash(b)
