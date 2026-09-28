"""Validate the delivered design files, not the production implementation."""
from pathlib import Path
from copy import deepcopy
import ast
import json
import re
import runpy

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def load(name):
    return json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))


def main():
    checks = []
    for path in (ROOT / "contracts").glob("*.schema.json"):
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))
        checks.append(f"schema-valid:{path.name}")
    for name in ("agent-plan", "tool-result"):
        validator = Draft202012Validator(load(name + ".schema.json"), format_checker=FormatChecker())
        validator.validate(load(name + ".example.json"))
        checks.append(f"example-valid:{name}")

    validator = Draft202012Validator(load("agent-plan.schema.json"), format_checker=FormatChecker())
    for label, modify in [
        ("negative-budget", lambda p: p["budget"].update(max_total_tokens=-1)),
        ("unregistered-node-kind", lambda p: p["nodes"][0].update(kind="arbitrary_shell")),
        ("extra-credential-field", lambda p: p.update(api_key="test-only")),
        ("bad-resource-hash", lambda p: p["resources"][0].update(content_hash="invalid")),
    ]:
        plan = deepcopy(load("agent-plan.example.json"))
        modify(plan)
        assert list(validator.iter_errors(plan)), label
        checks.append(f"negative-rejected:{label}")

    plan = load("agent-plan.example.json")
    resources = {r["key"]: r for r in plan["resources"]}
    nodes = {n["node_id"]: n for n in plan["nodes"]}
    assert len(resources) == len(plan["resources"])
    assert len(nodes) == len(plan["nodes"])
    visited, active = set(), set()

    def visit(key):
        assert key in nodes and key not in active, "unknown reference or cycle"
        if key in visited:
            return
        active.add(key)
        for dependency in nodes[key]["depends_on"]:
            visit(dependency)
        active.remove(key)
        visited.add(key)

    for node in plan["nodes"]:
        visit(node["node_id"])
        if node["kind"] == "evaluation":
            for field, kind in [("dataset_key", "dataset"), ("model_key", "model"), ("judge_key", "judge"), ("benchmark_key", "benchmark")]:
                assert resources[node["config"][field]]["kind"] == kind
        for ref in node["config"].get("input_nodes", []):
            assert ref in nodes and ref in node["depends_on"]
    checks.append("example-references-and-dag-valid")

    for path in ROOT.glob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if not target.startswith(("http:", "https:", "#")):
                assert (path.parent / target.split("#", 1)[0]).exists(), (path.name, target)
    checks.append("markdown-local-links-valid")

    app = REPO / "backend" / "app"
    paths = list(app.rglob("*.py"))
    for path in paths:
        ast.parse(path.read_text(encoding="utf-8-sig"))
    checks.append(f"backend-ast:{len(paths)}")
    builtin = runpy.run_path(str(app / "services" / "builtin_tools.py"))["run_builtin_tool"]
    findings = {
        "watermark_empty_prediction": builtin("builtin/safety_watermark", {"prediction": "", "reference": "AIGC"}),
        "hallucination_empty_prediction": builtin("builtin/safety_hallucination", {"prediction": "", "reference": "北京"}),
    }
    result = {"design_checks": checks, "current_code_probes": findings,
              "scope": "Design validation and pure-function probes only; no integration tests or production database access."}
    (ROOT / "verification" / "design-validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
