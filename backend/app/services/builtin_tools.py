"""内置评测工具：精确匹配 / 包含 / 正则 / 模糊匹配 / 安全正式裁判。"""
from __future__ import annotations

import re
from difflib import SequenceMatcher


def run_builtin_tool(resource_id: str, payload: dict) -> dict:
    if resource_id == "builtin/media_inspect":
        from types import SimpleNamespace
        from app.services.multimodal import media_of, media_summary
        from app.utils.jsonutil import dumps
        media = media_of(SimpleNamespace(extended_content=dumps({"media": payload.get("media", [])})))
        return {"media": media_summary(media), "measurement_scope": "媒体格式、时长、音轨、校验和及抽帧；不进行内容安全评分"}
    prediction = str(payload.get("prediction") or payload.get("output") or "")
    reference = str(payload.get("reference") or payload.get("reference_answer") or "")
    pattern = str(payload.get("pattern") or "")
    if resource_id.endswith("exact_match"):
        passed = prediction.strip() == reference.strip()
        score = 1.0 if passed else 0.0
        return {"score": score, "passed": passed, "metrics": {"accuracy": score}}
    if resource_id.endswith("contains"):
        passed = bool(reference) and reference.strip() in prediction
        score = 1.0 if passed else 0.0
        return {"score": score, "passed": passed, "metrics": {"accuracy": score}}
    if resource_id.endswith("regex"):
        pat = pattern or reference
        try:
            passed = bool(pat) and re.search(pat, prediction, re.S) is not None
        except re.error:
            passed = False
        score = 1.0 if passed else 0.0
        return {"score": score, "passed": passed, "metrics": {"accuracy": score}}
    if resource_id.endswith("fuzzy"):
        score = SequenceMatcher(None, prediction.strip(), reference.strip()).ratio() if (prediction or reference) else 0.0
        passed = score >= float(payload.get("threshold") or 0.6)
        return {"score": round(score, 4), "passed": passed, "metrics": {"fuzzy": round(score, 4)}}

    # —— 安全四类：委托正式 safety_eval ——
    from app.services import safety_eval as se

    sample = payload.get("sample") if isinstance(payload.get("sample"), dict) else {}
    if resource_id == "builtin/safety_protocol":
        from app.services.safety_protocol import rule_score
        return rule_score(prediction, sample)
    if resource_id.endswith("safety_gen_risk"):
        if not sample:
            sample = {"expected_behavior": payload.get("expected_behavior") or "refuse"}
        return se.evaluate("risk", prediction, sample=sample)
    if resource_id.endswith("safety_watermark"):
        return se.evaluate("watermark", prediction, sample=sample, reference=reference)
    if resource_id.endswith("safety_alignment"):
        if reference and "stance" not in sample:
            sample = {**sample, "stance": reference}
        return se.evaluate(
            "alignment",
            prediction,
            sample=sample,
            reference=reference,
            predictions_by_perspective=payload.get("predictions_by_perspective"),
        )
    if resource_id.endswith("safety_hallucination"):
        if reference and "evidence" not in sample:
            sample = {
                **sample,
                "evidence": [{"doc_id": "ref", "text": reference}],
                "claims": sample.get("claims") or [{"subject": "ref", "object": reference, "relation": "is"}],
                "human_gold": sample.get("human_gold") or {"label": "supported"},
            }
        return se.evaluate("hallucination", prediction, sample=sample, reference=reference)
    raise ValueError(f"未知内置工具: {resource_id}")
