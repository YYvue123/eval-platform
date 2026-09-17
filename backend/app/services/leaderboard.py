"""榜单计算：最近一次完整结果、归一化、四类榜、快照。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EvalModel, EvalTask, LeaderboardSnapshot, LeaderboardWeight, ModelCost
from app.utils.jsonutil import dumps, iso


def normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0 for _ in values]
    return [round((v - lo) / (hi - lo), 6) for v in values]


async def latest_success_tasks(db: AsyncSession, industry: str = "", scene: str = "", task_types: list[str] | None = None) -> list[EvalTask]:
    q = select(EvalTask).where(EvalTask.status == "success")
    if industry:
        q = q.where(EvalTask.industry == industry)
    if scene:
        q = q.where(EvalTask.scene == scene)
    if task_types:
        q = q.where(EvalTask.task_type.in_(task_types))
    rows = (await db.execute(q.order_by(EvalTask.finished_at.desc()))).scalars().all()
    latest: dict[int, EvalTask] = {}
    for t in rows:
        if t.model_id not in latest:
            latest[t.model_id] = t
    return list(latest.values())


async def load_weights(db: AsyncSession, board_type: str) -> dict[str, float]:
    rows = (await db.execute(select(LeaderboardWeight).where(LeaderboardWeight.board_type == board_type))).scalars().all()
    return {r.dim_key: float(r.weight or 0) for r in rows} or {"_": 1.0}


async def load_costs(db: AsyncSession) -> dict[int, ModelCost]:
    rows = (await db.execute(select(ModelCost))).scalars().all()
    return {r.model_id: r for r in rows}


def _cost_of(task: EvalTask, cost: ModelCost | None) -> float:
    token_p = cost.token_price_per_1k if cost else 0.002
    lat_p = cost.latency_price_per_sec if cost else 0.01
    gpu_p = cost.gpu_hour_price if cost else 0.0
    tokens = int(getattr(task, "tokens_used", 0) or 0)
    # 用进度耗时近似时延：无逐条均值时按 0.2s * total
    latency_sec = max(int(task.total or 0), 1) * 0.2
    return tokens / 1000.0 * token_p + latency_sec * lat_p + gpu_p * (latency_sec / 3600.0)


async def _names(db: AsyncSession, tasks: list[EvalTask]) -> dict[int, str]:
    names = {}
    for t in tasks:
        if t.model_id in names:
            continue
        m = await db.get(EvalModel, t.model_id)
        names[t.model_id] = m.name if m else str(t.model_id)
    return names


def _rank(items: list[dict], score_key: str) -> list[dict]:
    items.sort(key=lambda x: (x.get(score_key) or 0, x.get("pass_rate") or 0), reverse=True)
    for i, row in enumerate(items, start=1):
        row["rank"] = i
    return items


async def compute_board(db: AsyncSession, board: str, industry: str = "", scene: str = "") -> dict:
    costs = await load_costs(db)
    if board == "ability":
        tasks = await latest_success_tasks(db, industry=industry, scene=scene)
        names = await _names(db, tasks)
        scores = [t.avg_score for t in tasks]
        norms = normalize(scores)
        items = []
        for t, ns in zip(tasks, norms):
            items.append(_item(t, names, ns, extra={"board": "ability"}))
        items = _rank(items, "norm_score")[:10]
        return {"board": "ability", "items": items, "total": len(items)}

    if board == "special":
        tasks = await latest_success_tasks(db, industry=industry, scene=scene, task_types=["scene", "industry", "security"])
        if not tasks:
            tasks = await latest_success_tasks(db, industry=industry, scene=scene)
        names = await _names(db, tasks)
        scores = [t.avg_score for t in tasks]
        norms = normalize(scores)
        items = [_item(t, names, ns, extra={"board": "special", "task_type": t.task_type}) for t, ns in zip(tasks, norms)]
        return {"board": "special", "items": _rank(items, "norm_score"), "total": len(items)}

    if board == "value":
        tasks = await latest_success_tasks(db, industry=industry, scene=scene)
        names = await _names(db, tasks)
        raw = []
        for t in tasks:
            cost = _cost_of(t, costs.get(t.model_id))
            value = (t.avg_score or 0) / max(cost, 1e-6)
            raw.append((t, cost, value))
        norms = normalize([x[2] for x in raw])
        items = []
        for (t, cost, value), ns in zip(raw, norms):
            items.append(_item(t, names, ns, extra={"board": "value", "cost": round(cost, 6), "value_score": round(value, 6)}))
        return {"board": "value", "items": _rank(items, "norm_score"), "total": len(items)}

    # overall：分行业加权
    tasks = await latest_success_tasks(db, industry=industry, scene=scene)
    weights = await load_weights(db, "overall")
    names = await _names(db, tasks)
    by_model: dict[int, list[EvalTask]] = {}
    if industry:
        grouped = {t.model_id: [t] for t in tasks}
    else:
        all_tasks = await latest_success_by_industry(db)
        grouped = {}
        for t in all_tasks:
            grouped.setdefault(t.model_id, []).append(t)
        names = await _names(db, all_tasks)
    items = []
    for mid, ts in grouped.items():
        wsum = 0.0
        acc = 0.0
        for t in ts:
            w = float(weights.get(t.industry, weights.get("_", 1.0)))
            acc += (t.avg_score or 0) * w
            wsum += w
        weighted = acc / wsum if wsum else 0
        t0 = ts[0]
        items.append(_item(t0, names, weighted, extra={"board": "overall", "weighted_score": round(weighted, 6), "industry_count": len(ts)}))
    norms = normalize([i["weighted_score"] for i in items])
    for i, ns in zip(items, norms):
        i["norm_score"] = ns
    return {"board": "overall", "items": _rank(items, "norm_score"), "total": len(items)}


async def latest_success_by_industry(db: AsyncSession) -> list[EvalTask]:
    rows = (await db.execute(select(EvalTask).where(EvalTask.status == "success").order_by(EvalTask.finished_at.desc()))).scalars().all()
    seen: set[tuple[int, str]] = set()
    out = []
    for t in rows:
        key = (t.model_id, t.industry or "general")
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def _item(t: EvalTask, names: dict[int, str], norm: float, extra: dict | None = None) -> dict:
    row = {
        "model_id": t.model_id,
        "model_name": names.get(t.model_id, str(t.model_id)),
        "industry": t.industry,
        "scene": t.scene,
        "avg_score": t.avg_score,
        "pass_rate": t.pass_rate,
        "norm_score": round(float(norm or 0), 6),
        "task_id": t.id,
        "task_name": t.name,
        "tokens_used": getattr(t, "tokens_used", 0) or 0,
        "updated_at": iso(t.finished_at),
    }
    if extra:
        row.update(extra)
    return row


async def radar_payload(db: AsyncSession, model_ids: list[int]) -> dict:
    ids = model_ids[:5]
    rows = (await db.execute(
        select(EvalTask).where(EvalTask.status == "success", EvalTask.model_id.in_(ids)).order_by(EvalTask.finished_at.desc())
    )).scalars().all()
    latest: dict[tuple[int, str], EvalTask] = {}
    for t in rows:
        key = (t.model_id, t.scene or "chat")
        if key not in latest:
            latest[key] = t
    scenes = sorted({k[1] for k in latest})
    names = {}
    for mid in ids:
        m = await db.get(EvalModel, mid)
        names[mid] = m.name if m else str(mid)
    series = []
    for mid in ids:
        series.append({
            "model_id": mid,
            "model_name": names.get(mid, str(mid)),
            "values": [float((latest.get((mid, sc)).avg_score if latest.get((mid, sc)) else 0) or 0) for sc in scenes],
        })
    return {"scenes": scenes, "series": series}


async def save_snapshot(db: AsyncSession, board: str, payload: dict, status: str = "ok") -> LeaderboardSnapshot:
    snap = LeaderboardSnapshot(board_type=board, payload_json=dumps(payload), status=status)
    db.add(snap)
    await db.flush()
    return snap


async def last_snapshot(db: AsyncSession, board: str) -> LeaderboardSnapshot | None:
    return (await db.execute(
        select(LeaderboardSnapshot).where(LeaderboardSnapshot.board_type == board).order_by(LeaderboardSnapshot.id.desc()).limit(1)
    )).scalars().first()
