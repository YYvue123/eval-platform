"""Task-derived leaderboard: one protocol per comparison, no inferred cross-tool scores."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from statistics import mean

from sqlalchemy import select

from app.models import Dataset, DatasetItem, EvalModel, EvalResult, EvalTask, ModelCost, ModelMeta, ModelVersion, LeaderboardPolicy, LeaderboardReview
from app.services.leaderboard import cohort_id_of, is_formal_eligible
from app.services.object_policy import apply_object_scope
from app.services.task_catalog import industry_options, scene_options
from app.services.evaluation_labels import judge_name
from app.utils.jsonutil import iso
from app.utils.jsonutil import loads

# Only these built-in judges have an established [0, 1], higher-is-better score contract.
UNIT_JUDGES = {"builtin/exact_match", "builtin/contains", "builtin/regex", "builtin/fuzzy"}


def measured_results(rows):
    return [r for r in rows if not r.simulation and r.execution_status == "ok"
            and r.score_status == "scored" and r.score is not None and math.isfinite(r.score)]


def summarize_results(rows, labels, expected):
    valid = measured_results(rows)
    dimensions = {}
    for label, item_ids in expected.items():
        samples = [r for r in valid if r.item_id in item_ids]
        # Partial coverage is reported, but never promoted to a comparable dimension score.
        complete = bool(item_ids) and {r.item_id for r in samples} == item_ids
        dimensions[label] = {"score": mean(r.score for r in samples) if complete else None,
                             "count": len(samples), "expected": len(item_ids)}
    latencies = sorted(r.latency_ms for r in valid if r.latency_ms > 0)
    return {
        "score": mean(r.score for r in valid) if valid else None,
        "pass_rate": mean(bool(r.passed) for r in valid) if valid else None,
        "sample_count": len(valid), "dimensions": dimensions,
        "latency_ms": mean(latencies) if len(latencies) == len(valid) and latencies else None,
        "p95_latency_ms": latencies[max(0, math.ceil(len(latencies) * .95) - 1)] if len(latencies) == len(valid) and latencies else None,
        "total_latency_sec": sum(latencies) / 1000 if len(latencies) == len(valid) and latencies else None,
    }


def category_of(task, dataset, model):
    if 'K12' in dataset.name.upper() or 'k12' in loads(dataset.tags, []):
        return 'k12'
    if task.industry == 'finance':
        return 'finance'
    if task.task_type == 'security':
        return 'safety'
    modal = (model.support_modal or '').lower()
    return 'video' if 'video' in modal else 'audio' if 'audio' in modal else 'vision' if any(v in modal for v in ['image', 'vision']) else 'language'


def apply_scores(items, dimensions, weights, board, metric, unit):
    effective = {d: float(weights.get(d, 1)) for d in dimensions}
    for row in items:
        row['raw_score'] = row['score']
        values = row['dimensions']
        if unit and sum(effective.values()) > 0 and all(values[d]['score'] is not None for d,w in effective.items() if w > 0):
            row['score'] = sum(values[d]['score'] * w for d,w in effective.items() if w > 0) / sum(effective.values())
        row['cost_per_sample'] = row['cost'] / row['sample_count'] if row.get('cost') is not None and row['sample_count'] else None
        row['value_score'] = row['score'] / row['cost_per_sample'] if unit and row.get('cost_per_sample') and row['cost_per_sample'] > 0 else None
        row['ranking_score'] = (values.get(metric, {}).get('score') if board == 'ability' else row['value_score'] if board == 'value' else row['score']) if unit else None
    items.sort(key=lambda r: (r['ranking_score'] is None, -(r['ranking_score'] or 0), r['key']))
    previous, rank = None, 0
    for i,row in enumerate(items):
        score = row['ranking_score']
        if score is not None and score != previous:
            rank = i + 1
        row['rank'] = rank if score is not None else None
        previous = score
    return effective


async def insights(db, actor, *, cohort_id="", industry="", scene="", as_of=None, since=None,
                   board='overall', metric='', model_ids=None, version_id=None, category=''):
    query = apply_object_scope(select(EvalTask), EvalTask, actor)
    if industry:
        query = query.where(EvalTask.industry == industry)
    if scene:
        query = query.where(EvalTask.scene == scene)
    if as_of:
        query = query.where(EvalTask.finished_at <= as_of)
    if since:
        query = query.where(EvalTask.finished_at >= since)
    tasks = list((await db.scalars(query.order_by(EvalTask.finished_at.desc(), EvalTask.id.desc()))).all())
    all_results = defaultdict(list)
    if tasks:
        for r in (await db.scalars(select(EvalResult).where(EvalResult.task_id.in_([t.id for t in tasks])))).all():
            all_results[r.task_id].append(r)
    datasets = {d.id: d for d in (await db.scalars(apply_object_scope(select(Dataset), Dataset, actor))).all()}
    models = {m.id: m for m in (await db.scalars(apply_object_scope(select(EvalModel), EvalModel, actor))).all()}
    expected_versions = defaultdict(lambda: defaultdict(set))
    version_ids = {t.dataset_version_id for t in tasks if t.dataset_version_id}
    if version_ids:
        for item in (await db.scalars(select(DatasetItem).where(DatasetItem.version_id.in_(version_ids), DatasetItem.status == "active"))).all():
            expected_versions[item.version_id][item.data_label or "未分类"].add(item.id)
    reviews = {r.task_id:r for r in (await db.scalars(select(LeaderboardReview).where(LeaderboardReview.tenant_id == actor.tenant_id))).all()}
    eligible, excluded, pending = [], Counter(), []
    categories = Counter()
    for t in tasks:
        if t.model_id not in models or t.dataset_id not in datasets:
            continue
        cat = category_of(t, datasets[t.dataset_id], models[t.model_id])
        ok, reason = is_formal_eligible(t)
        if not ok:
            excluded[reason] += 1
            continue
        rows = all_results[t.id]
        valid = measured_results(rows)
        expected = set().union(*expected_versions[t.dataset_version_id].values()) if expected_versions[t.dataset_version_id] else set()
        if not expected or len(rows) != len(expected) or len(valid) != len(rows) or {r.item_id for r in valid} != expected:
            excluded["未完整实测或评分未验证"] += 1
            continue
        categories[cat] += 1
        if category and category != cat:
            continue
        if board == 'special' and t.task_type not in {'scene','industry','security'} and t.industry in {'','general'} and cat != 'k12':
            continue
        review = reviews.get(t.id)
        if review and review.status in {'pending', 'excluded'}:
            excluded['异常待复核' if review.status == 'pending' else '复核排除'] += 1
            if review.status == 'pending':
                pending.append({'task_id':t.id, 'cohort_id':cohort_id_of(t)})
            continue
        eligible.append(t)
    groups = defaultdict(list)
    for t in eligible:
        groups[cohort_id_of(t)].append(t)
    options = []
    for cid, members in groups.items():
        t = members[0]
        options.append({"id": cid, "label": f"{datasets[t.dataset_id].name} · {judge_name(t.judge_resource_id)}",
                        "count": len({(r.model_id, r.model_version_id) for r in members}), "runs": len(members),
                        "dataset_version_id": t.dataset_version_id, "judge": t.judge_resource_id,
                        "tool_version": t.tool_version, "scene": t.scene, "industry": t.industry,
                        "prompt_version_id": t.prompt_version_id, "updated_at": iso(t.finished_at)})
        options[-1]['category'] = category_of(t,datasets[t.dataset_id],models[t.model_id])
        options[-1]['dataset_name'] = datasets[t.dataset_id].name
        options[-1]['judge_name'] = judge_name(t.judge_resource_id)
    options.sort(key=lambda c: c["updated_at"] or "", reverse=True)
    options.sort(key=lambda c: -c["count"])
    active = cohort_id or (options[0]["id"] if options else "")
    members = groups.get(active, [])
    latest = {}
    for t in members:
        if model_ids and t.model_id not in model_ids:
            continue
        if version_id is not None and t.model_version_id != version_id:
            continue
        latest.setdefault((t.model_id, t.model_version_id), t)
    metadata = {m.model_id: m for m in (await db.scalars(select(ModelMeta).where(ModelMeta.model_id.in_(list(models))))).all()} if models else {}
    prices = {c.model_id: c for c in (await db.scalars(select(ModelCost).where(ModelCost.model_id.in_(list(models))))).all()} if models else {}
    versions = {v.id: v.version_code for v in (await db.scalars(select(ModelVersion).where(ModelVersion.model_id.in_(list(models))))).all()} if models else {}
    items, history = [], []
    for (mid, version), t in latest.items():
        model = models[mid]
        summary = summarize_results(all_results[t.id], None, expected_versions[t.dataset_version_id])
        bill = prices.get(mid)
        latency = summary["total_latency_sec"]
        # Explicit prices only; no invented fallback prices or time estimates.
        cost = (t.tokens_used / 1000 * bill.token_price_per_1k + latency * bill.latency_price_per_sec
                + latency / 3600 * bill.gpu_hour_price) if bill and latency is not None and t.tokens_used > 0 else None
        meta = metadata.get(mid)
        items.append({**summary, "key": f"{mid}:{version or 'live'}", "model_id": mid,
                      "model_version_id": version, "model_name": model.name,
                      "version": versions.get(version, "未冻结版本"), "parameter_scale": model.parameter_scale,
                      "company": meta.company_name if meta else "", "source_type": {"open_source": "open", "open": "open", "closed": "closed", "closed_source": "closed"}.get(meta.source_type if meta else "", ""),
                      "modal": model.support_modal, "description": model.description,
                      "demo_alias": "[演示配置]" in model.name, "task_id": t.id, "task_name": t.name,
                      "tokens": t.tokens_used or None, "cost": round(cost, 6) if cost is not None else None,
                      "updated_at": iso(t.finished_at)})
    items.sort(key=lambda r: (-(r["score"] if r["score"] is not None else -math.inf), r["key"]))
    previous, rank = None, 0
    for i, row in enumerate(items):
        if row["score"] != previous:
            rank = i + 1
        row["rank"] = rank
        previous = row["score"]
    for t in reversed(members):
        history.append({"key": f"{t.model_id}:{t.model_version_id or 'live'}", "task_id": t.id,
                        "at": iso(t.finished_at), "score": mean(r.score for r in measured_results(all_results[t.id]))})
    first = members[0] if members else None
    dimensions = sorted(expected_versions[first.dataset_version_id]) if first else []
    unit = bool(first and first.judge_resource_id in UNIT_JUDGES
                and all(0 <= r.score <= 1 for t in members for r in measured_results(all_results[t.id])))
    if not unit:
        for row in items:
            row["rank"] = None
    policy = await db.scalar(select(LeaderboardPolicy).where(LeaderboardPolicy.tenant_id == actor.tenant_id, LeaderboardPolicy.cohort_id == active))
    selected_metric = metric or (dimensions[0] if dimensions else '')
    weights = apply_scores(items, dimensions, loads(policy.weights_json, {}) if policy else {}, board, selected_metric, unit)
    if board == 'ability':
        items = items[:10]
    item_keys = {row['key'] for row in items}
    history = [point for point in history if point['key'] in item_keys]
    for point in history:
        task = next(t for t in members if t.id == point['task_id'])
        summary = summarize_results(all_results[task.id], None, expected_versions[task.dataset_version_id])
        if board == 'ability':
            point['score'] = summary['dimensions'].get(selected_metric, {}).get('score')
        elif unit and sum(weights.values()) > 0:
            point['score'] = sum(summary['dimensions'][d]['score'] * w for d,w in weights.items()) / sum(weights.values())
    profiles = {}
    for t in eligible:
        if model_ids and t.model_id not in model_ids:
            continue
        if version_id is not None and t.model_version_id != version_id:
            continue
        key = f"{t.model_id}:{t.model_version_id or 'live'}"
        meta = metadata.get(t.model_id)
        profile = profiles.setdefault(key, {"key": key, "model_name": models[t.model_id].name,
            'company':meta.company_name if meta else '',
            'source_type':{'open_source':'open','open':'open','closed':'closed','closed_source':'closed'}.get(meta.source_type if meta else '', ''), 'cells': {}})
        cid = cohort_id_of(t)
        if cid not in profile["cells"]:
            profile["cells"][cid] = {"score": mean(r.score for r in measured_results(all_results[t.id])),
                                      "samples": len(all_results[t.id]), "task_id": t.id}
    return {"cohort_id": active, "cohorts": options, "items": items, "history": history,
            "profiles": list(profiles.values()), "industries": industry_options(), "scenes": scene_options(),
            "board":board, "metric":selected_metric, "weights":weights, "category":category,
            "model_options":[{'id':m.id,'name':m.name} for m in models.values()],
            "version_options":[{'id':v.id,'code':v.version_code,'model_id':v.model_id} for v in (await db.scalars(select(ModelVersion).where(ModelVersion.model_id.in_(list(models))))).all()] if models else [],
            "categories":dict(categories), "pending_review_total":sum(p['cohort_id']==active for p in pending),
            "filter_context":{'industry':industry,'scene':scene,'since':iso(since),'as_of':iso(as_of),'model_ids':model_ids,'version_id':version_id,'category':category},
            "dimensions": dimensions, "scale": {"min": 0, "max": 1, "unit": "比例"} if unit else None,
            "excluded": dict(excluded), "excluded_total": sum(excluded.values()),
            "overview": {"models": len({t.model_id for t in eligible}), "protocols": len(groups),
                         "runs": len(eligible), "samples": sum(len(all_results[t.id]) for t in eligible)},
            "as_of": iso(as_of), "rules": "仅比较同数据版本、裁判、工具版本、提示词版本、权重、行业及场景的完整实测结果。维度来自数据集标签；不代表通用能力认证。成本是实测用量按配置单价计算的估算。"}
