"""内置工具 Manifest 与启动种子。"""
from __future__ import annotations

BUILTIN_MANIFESTS = [
    {
        "spec_version": "0.6.1",
        "resource_id": "builtin/exact_match",
        "resource_type": "tool",
        "name": "精确匹配打分",
        "version": "1.0.0",
        "description": "对比模型输出与参考答案是否完全一致。",
        "owner": {"name": "eval-platform", "contact": "platform", "email": "admin@example.com"},
        "capabilities": {
            "input_schema": {"type": "object", "properties": {"prediction": {"type": "string"}, "reference": {"type": "string"}}},
            "output_schema": {"type": "object", "properties": {"score": {"type": "number"}, "passed": {"type": "boolean"}}},
            "call_mode": "sync",
            "idempotent": True,
            "timeout": 10,
            "retryable": True,
        },
        "evaluation_spec": {
            "judge_type": "exact_match",
            "metric_names": ["accuracy"],
            "pass_threshold": {"accuracy": 1.0},
        },
        "interfaces": {"endpoint": "local://builtin/exact_match", "method": "exec", "auth_type": "none"},
    },
    {
        "spec_version": "0.6.1",
        "resource_id": "builtin/contains",
        "resource_type": "tool",
        "name": "包含匹配打分",
        "version": "1.0.0",
        "description": "参考答案作为子串出现在模型输出中即通过。",
        "owner": {"name": "eval-platform", "contact": "platform", "email": "admin@example.com"},
        "capabilities": {
            "input_schema": {"type": "object", "properties": {"prediction": {"type": "string"}, "reference": {"type": "string"}}},
            "output_schema": {"type": "object", "properties": {"score": {"type": "number"}}},
            "call_mode": "sync",
            "idempotent": True,
            "timeout": 10,
        },
        "evaluation_spec": {"judge_type": "contains", "metric_names": ["accuracy"], "pass_threshold": {"accuracy": 1.0}},
        "interfaces": {"endpoint": "local://builtin/contains", "method": "exec", "auth_type": "none"},
    },
    {
        "spec_version": "0.6.1",
        "resource_id": "builtin/regex",
        "resource_type": "tool",
        "name": "正则匹配打分",
        "version": "1.0.0",
        "description": "使用正则表达式判定模型输出是否命中预期模式。",
        "owner": {"name": "eval-platform", "contact": "platform", "email": "admin@example.com"},
        "capabilities": {
            "input_schema": {"type": "object", "properties": {"prediction": {"type": "string"}, "pattern": {"type": "string"}}},
            "output_schema": {"type": "object", "properties": {"score": {"type": "number"}}},
            "call_mode": "sync",
            "idempotent": True,
            "timeout": 10,
        },
        "evaluation_spec": {"judge_type": "regex", "metric_names": ["accuracy"]},
        "interfaces": {"endpoint": "local://builtin/regex", "method": "exec", "auth_type": "none"},
    },
    {
        "spec_version": "0.6.1",
        "resource_id": "builtin/fuzzy",
        "resource_type": "tool",
        "name": "模糊匹配打分",
        "version": "1.0.0",
        "description": "按编辑相似度给模型输出打分。",
        "owner": {"name": "eval-platform", "contact": "platform", "email": "admin@example.com"},
        "capabilities": {
            "input_schema": {"type": "object", "properties": {"prediction": {"type": "string"}, "reference": {"type": "string"}}},
            "output_schema": {"type": "object", "properties": {"score": {"type": "number"}}},
            "call_mode": "sync",
            "idempotent": True,
            "timeout": 10,
        },
        "evaluation_spec": {"judge_type": "fuzzy", "metric_names": ["fuzzy"], "pass_threshold": {"fuzzy": 0.6}},
        "interfaces": {"endpoint": "local://builtin/fuzzy", "method": "exec", "auth_type": "none"},
    },
]


def _safety(rid: str, name: str, desc: str, judge: str, metrics: list[str]) -> dict:
    return {
        "spec_version": "0.6.1",
        "resource_id": rid,
        "resource_type": "tool",
        "name": name,
        "version": "1.0.0",
        "description": desc,
        "demo_only": True,
        "owner": {"name": "eval-platform", "contact": "platform", "email": "admin@example.com"},
        "capabilities": {
            "input_schema": {"type": "object", "properties": {"prediction": {"type": "string"}, "reference": {"type": "string"}}},
            "output_schema": {"type": "object", "properties": {"score": {"type": "number"}, "passed": {"type": "boolean"}}},
            "call_mode": "sync",
            "idempotent": True,
            "timeout": 10,
        },
        "evaluation_spec": {"judge_type": judge, "metric_names": metrics},
        "interfaces": {"endpoint": f"local://{rid}", "method": "exec", "auth_type": "none"},
    }


BUILTIN_MANIFESTS.extend([
    _safety("builtin/safety_gen_risk", "生成合成内容风险裁判", "有害性/拒绝率启发式裁判。", "rule_based", ["harmfulness", "refusal_rate"]),
    _safety("builtin/safety_watermark", "标识合规裁判", "检测显式 AIGC 标识或水印关键词。", "rule_based", ["integrity", "parseable"]),
    _safety("builtin/safety_alignment", "价值对齐裁判", "对照参考立场做稳定性打分。", "rule_based", ["stance_stability"]),
    _safety("builtin/safety_hallucination", "幻觉裁判", "对象-属性-关系一致性启发式。", "rule_based", ["object_hallucination", "relation_hallucination"]),
    {
        "spec_version": "0.6.1",
        "resource_id": "builtin/skill_dual_judge",
        "resource_type": "skill",
        "name": "双裁判技能包",
        "version": "1.0.0",
        "description": "按优先级链式调用 exact_match 与 fuzzy。",
        "owner": {"name": "eval-platform", "contact": "platform", "email": "admin@example.com"},
        "capabilities": {
            "input_schema": {"type": "object", "properties": {"prediction": {"type": "string"}, "reference": {"type": "string"}}},
            "output_schema": {"type": "object", "properties": {"score": {"type": "number"}, "passed": {"type": "boolean"}}},
            "call_mode": "sync",
            "idempotent": True,
            "timeout": 20,
        },
        "evaluation_spec": {"judge_type": "custom", "metric_names": ["chain_score"], "pass_threshold": {"chain_score": 0.5}},
        "interfaces": {"endpoint": "local://builtin/skill_dual_judge", "method": "exec", "auth_type": "none"},
        "skill": {
            "execution_type": "workflow",
            "priority": 10,
            "chain": [
                {
                    "step_id": "exact",
                    "resource_id": "builtin/exact_match",
                    "input": {
                        "prediction": {"$ref": "$input.prediction"},
                        "reference": {"$ref": "$input.reference"},
                    },
                },
                {
                    "step_id": "fuzzy",
                    "resource_id": "builtin/fuzzy",
                    "input": {
                        "prediction": {"$ref": "$input.prediction"},
                        "reference": {"$ref": "$input.reference"},
                    },
                },
            ],
        },
    },
    {
        "spec_version": "0.6.1",
        "resource_id": "builtin/mcp_gateway",
        "resource_type": "mcp",
        "name": "内置 MCP 网关",
        "version": "1.0.0",
        "description": "JSON-RPC initialize/tools.list/tools.call，本地或远程 endpoint。",
        "owner": {"name": "eval-platform", "contact": "platform", "email": "admin@example.com"},
        "capabilities": {
            "input_schema": {"type": "object", "properties": {"method": {"type": "string"}, "params": {"type": "object"}}},
            "output_schema": {"type": "object"},
            "call_mode": "sync",
            "idempotent": True,
            "timeout": 30,
        },
        "interfaces": {"endpoint": "local://builtin/mcp_gateway", "method": "exec", "auth_type": "none"},
    },
])
