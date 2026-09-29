"""榜单计算：正式资格、cohort、冻结归一化、并列、真实成本。"""
from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    EvalModel,
    EvalResult,
    EvalTask,
    LeaderboardRelease,
    LeaderboardSnapshot,
    LeaderboardWeight,
    ModelCost,
)
from app.utils.jsonutil import dumps, iso, loads


FORMAL_SCORE_OK = frozenset({"ok", "scored", "legacy_unverified", ""})


def is_formal_eligible(task: EvalTask) -> tuple[bool, str]:
    """mock/trial/simulation/非成功不得入正式榜。"""
    if getattr(task, "trial_run", False):
        return False, "trial_run"
    if getattr(task, "simulation", False):
        return False, "simulation"
    if task.status != "success":
        return False, f"status:{task.status}"
    return True, ""


async def task_has_score_errors(db: AsyncSession, task_id: int) -> bool:
    rows = (await db.execute(
        select(EvalResult.score_status, EvalResult.execution_status).where(EvalResult.task_id == task_id)
    )).all()
    if not rows:
        return False
    for score_status, execution_status in rows:
        ss = (score_status or "").lower()
        es = (execution_status or "").lower()
        if ss in {"error", "failed", "invalid"} or es in {"error", "failed"}:
            return True
    return False


def cohort_id_of(task: EvalTask) -> str:
    """同 cohort 才可比较：数据集版本 + 裁判 + 工具版本 + 指标权重。"""
    raw = "|".join([
        str(task.dataset_version_id or task.dataset_id or ""),
        str(task.judge_resource_id or ""),
        str(getattr(task, "tool_version", "") or ""),
        str(getattr(task, "metric_weights_json", "") or "{}"),
        str(task.scene or ""),
    ])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"c-{digest}"


def freeze_normalize(values: list[float | None], scale_lo: float | None = None, scale_hi: float | None = None) -> list[float | None]:
    """缺值保持 null，不填 0。冻结尺度优先；否则用观测到的非空值计算，但不回填缺失。"""
    present = [float(v) for v in values if v is not None]
    if scale_lo is None or scale_hi is None:
        if not present:
            return [None for _ in values]
        lo, hi = min(present), max(present)
    else:
        lo, hi = float(scale_lo), float(scale_hi)
    out: list[float | None] = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        if hi == lo:
            out.append(1.0)
        else:
            out.append(round((float(v) - lo) / (hi - lo), 6))
    return out


def rank_with_ties(items: list[dict], score_key: str = "norm_score") -> list[dict]:
    """同分并列；缺分排后且 rank 用 '—' 语义（rank=None）。"""
    scored = [x for x in items if x.get(score_key) is not None]
    missing = [x for x in items if x.get(score_key) is None]
    scored.sort(key=lambda x: (x.get(score_key) or 0, x.get("pass_rate") or 0), reverse=True)
    rank = 0
    prev = object()
    for i, row in enumerate(scored):
        val = row.get(score_key)
        if val != prev:
            rank = i + 1
            prev = val
        row["rank"] = rank
        row["tied"] = i > 0 and scored[i - 1].get(score_key) == val
    for row in missing:
        row["rank"] = None
        row["tied"] = False
        row["missing_metric"] = True
    return scored + missing


def recalculate_cost(task: EvalTask, cost: ModelCost | None) -> dict[str, float]:
    token_p = cost.token_price_per_1k if cost else 0.002
    lat_p = cost.latency_price_per_sec if cost else 0.01
    gpu_p = cost.gpu_hour_price if cost else 0.0
    tokens = int(getattr(task, "tokens_used", 0) or 0)
    latency_sec = max(int(task.total or 0), 1) * 0.2
    total = tokens / 1000.0 * token_p + latency_sec * lat_p + gpu_p * (latency_sec / 3600.0)
    return {
        "token_price_per_1k": float(token_p),
        "latency_price_per_sec": float(lat_p),
        "gpu_hour_price": float(gpu_p),
        "tokens": float(tokens),
        "latency_sec": float(latency_sec),
        "total_cost": round(total, 6),
    }


async def latest_success_tasks(
    db: AsyncSession,
    industry: str = "",
    scene: str = "",
    task_types: list[str] | None = None,
    *,
    formal_only: bool = True,
) -> list[EvalTask]:
    q = select(EvalTask).where(EvalTask.status == "success")
    if industry:
        q = q.where(EvalTask.industry == industry)
    if scene:
        q = q.where(EvalTask.scene == scene)
    if task_types:
        q = q.where(EvalTask.task_type.in_(task_types))
    rows = (await db.execute(q.order_by(EvalTask.finished_at.desc()))).scalars().all()
    latest: dict[int, EvalTask] = {}
    excluded = []
    for t in rows:
        ok, reason = is_formal_eligible(t)
        if formal_only and not ok:
            excluded.append({"task_id": t.id, "reason": reason})
            continue
        if formal_only and await task_has_score_errors(db, t.id):
            excluded.append({"task_id": t.id, "reason": "score_error"})
            continue
        if t.model_id not in latest:
            latest[t.model_id] = t
    # stash exclusions on function attribute for callers that want diagnostics
    latest_success_tasks.last_excluded = excluded  # type: ignore[attr-defined]
    return list(latest.values())


async def load_weights(db: AsyncSession, board_type: str) -> dict[str, float]:
    rows = (await db.execute(select(LeaderboardWeight).where(LeaderboardWeight.board_type == board_type))).scalars().all()
    return {r.dim_key: float(r.weight or 0) for r in rows} or {"_": 1.0}


async def load_costs(db: AsyncSession) -> dict[int, ModelCost]:
    rows = (await db.execute(select(ModelCost))).scalars().all()
    return {r.model_id: r for r in rows}


async def _names(db: AsyncSession, tasks: list[EvalTask]) -> dict[int, str]:
    names = {}
    for t in tasks:
        if t.model_id in names:
            continue
        m = await db.get(EvalModel, t.model_id)
        names[t.model_id] = m.name if m else str(t.model_id)
    return names


def _item(t: EvalTask, names: dict[int, str], norm: float | None, extra: dict | None = None) -> dict:
    row = {
        "model_id": t.model_id,
        "model_name": names.get(t.model_id, str(t.model_id)),
        "industry": t.industry,
        "scene": t.scene,
        "avg_score": t.avg_score,
        "pass_rate": t.pass_rate,
        "norm_score": None if norm is None else round(float(norm), 6),
        "task_id": t.id,
        "task_name": t.name,
        "tokens_used": getattr(t, "tokens_used", 0) or 0,
        "updated_at": iso(t.finished_at),
        "cohort_id": cohort_id_of(t),
        "dataset_version_id": t.dataset_version_id,
        "judge_resource_id": t.judge_resource_id,
        "tool_version": getattr(t, "tool_version", "") or "",
        "formal": True,
    }
    if extra:
        row.update(extra)
    return row


async def current_release(db: AsyncSession, board: str) -> LeaderboardRelease | None:
    return await db.scalar(
        select(LeaderboardRelease).where(
            LeaderboardRelease.board_type == board,
            LeaderboardRelease.is_current.is_(True),
            LeaderboardRelease.status == "published",
        )
    )


async def compute_board(
    db: AsyncSession,
    board: str,
    industry: str = "",
    scene: str = "",
    *,
    cohort_id: str | None = None,
    use_frozen_scale: bool = True,
) -> dict:
    costs = await load_costs(db)
    release = await current_release(db, board) if use_frozen_scale else None
    scale_lo = release.scale_lo if release else None
    scale_hi = release.scale_hi if release else None

    async def _filter_cohort(tasks: list[EvalTask]) -> list[EvalTask]:
        if not tasks:
            return []
        # 默认取最大 cohort；或指定 cohort
        if cohort_id:
            return [t for t in tasks if cohort_id_of(t) == cohort_id]
        counts: dict[str, int] = {}
        for t in tasks:
            counts[cohort_id_of(t)] = counts.get(cohort_id_of(t), 0) + 1
        primary = max(counts, key=counts.get) if counts else ""
        return [t for t in tasks if cohort_id_of(t) == primary]

    excluded = []
    if board == "ability":
        tasks = await _filter_cohort(await latest_success_tasks(db, industry=industry, scene=scene))
        excluded = list(getattr(latest_success_tasks, "last_excluded", []) or [])
        names = await _names(db, tasks)
        raw_scores: list[float | None] = [t.avg_score for t in tasks]
        norms = freeze_normalize(raw_scores, scale_lo, scale_hi)
        items = [_item(t, names, ns, extra={"board": "ability"}) for t, ns in zip(tasks, norms)]
        items = rank_with_ties(items, "norm_score")[:10]
        return _board_out(board, items, release, excluded, scale_lo, scale_hi)

    if board == "special":
        tasks = await _filter_cohort(
            await latest_success_tasks(db, industry=industry, scene=scene, task_types=["scene", "industry", "security"])
        )
        if not tasks:
            tasks = await _filter_cohort(await latest_success_tasks(db, industry=industry, scene=scene))
        excluded = list(getattr(latest_success_tasks, "last_excluded", []) or [])
        names = await _names(db, tasks)
        norms = freeze_normalize([t.avg_score for t in tasks], scale_lo, scale_hi)
        items = [
            _item(t, names, ns, extra={"board": "special", "task_type": t.task_type})
            for t, ns in zip(tasks, norms)
        ]
        return _board_out(board, rank_with_ties(items, "norm_score"), release, excluded, scale_lo, scale_hi)

    if board == "value":
        tasks = await _filter_cohort(await latest_success_tasks(db, industry=industry, scene=scene))
        excluded = list(getattr(latest_success_tasks, "last_excluded", []) or [])
        names = await _names(db, tasks)
        raw = []
        for t in tasks:
            bill = recalculate_cost(t, costs.get(t.model_id))
            value = (t.avg_score or 0) / max(bill["total_cost"], 1e-6)
            raw.append((t, bill, value))
        norms = freeze_normalize([x[2] for x in raw], scale_lo, scale_hi)
        items = []
        for (t, bill, value), ns in zip(raw, norms):
            items.append(_item(
                t, names, ns,
                extra={
                    "board": "value",
                    "cost": bill["total_cost"],
                    "cost_breakdown": bill,
                    "value_score": round(value, 6),
                },
            ))
        return _board_out(board, rank_with_ties(items, "norm_score"), release, excluded, scale_lo, scale_hi)

    # overall
    weights = await load_weights(db, "overall")
    if industry:
        tasks = await _filter_cohort(await latest_success_tasks(db, industry=industry, scene=scene))
        excluded = list(getattr(latest_success_tasks, "last_excluded", []) or [])
        grouped = {t.model_id: [t] for t in tasks}
        names = await _names(db, tasks)
    else:
        all_tasks = await latest_success_by_industry(db)
        excluded = list(getattr(latest_success_tasks, "last_excluded", []) or [])
        # cohort: keep dominant per industry group after formal filter
        filtered = await _filter_cohort(all_tasks)
        grouped = {}
        for t in filtered:
            grouped.setdefault(t.model_id, []).append(t)
        names = await _names(db, filtered)
    items = []
    for mid, ts in grouped.items():
        wsum = 0.0
        acc = 0.0
        for t in ts:
            w = float(weights.get(t.industry, weights.get("_", 1.0)))
            if t.avg_score is None:
                continue
            acc += float(t.avg_score) * w
            wsum += w
        weighted = (acc / wsum) if wsum else None
        t0 = ts[0]
        items.append(_item(
            t0, names, None,
            extra={"board": "overall", "weighted_score": None if weighted is None else round(weighted, 6), "industry_count": len(ts)},
        ))
    norms = freeze_normalize([i.get("weighted_score") for i in items], scale_lo, scale_hi)
    for i, ns in zip(items, norms):
        i["norm_score"] = ns
    return _board_out(board, rank_with_ties(items, "norm_score"), release, excluded, scale_lo, scale_hi)


def _board_out(board, items, release, excluded, scale_lo, scale_hi) -> dict:
    cohort = items[0]["cohort_id"] if items else ""
    return {
        "board": board,
        "items": items,
        "total": len(items),
        "cohort_id": cohort,
        "excluded": excluded[:50],
        "excluded_total": len(excluded),
        "frozen_scale": {"lo": scale_lo, "hi": scale_hi} if scale_lo is not None else None,
        "release_id": release.id if release else None,
        "release_current": bool(release),
    }


async def latest_success_by_industry(db: AsyncSession) -> list[EvalTask]:
    rows = (await db.execute(select(EvalTask).where(EvalTask.status == "success").order_by(EvalTask.finished_at.desc()))).scalars().all()
    seen: set[tuple[int, str]] = set()
    out = []
    excluded = []
    for t in rows:
        ok, reason = is_formal_eligible(t)
        if not ok:
            excluded.append({"task_id": t.id, "reason": reason})
            continue
        if await task_has_score_errors(db, t.id):
            excluded.append({"task_id": t.id, "reason": "score_error"})
            continue
        key = (t.model_id, t.industry or "general")
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    latest_success_tasks.last_excluded = excluded  # type: ignore[attr-defined]
    return out


async def radar_payload(db: AsyncSession, model_ids: list[int]) -> dict:
    ids = model_ids[:5]
    q = select(EvalTask).where(EvalTask.status == "success", EvalTask.model_id.in_(ids)).order_by(EvalTask.finished_at.desc())
    rows = (await db.execute(q)).scalars().all()
    latest: dict[tuple[int, str], EvalTask] = {}
    for t in rows:
        ok, _ = is_formal_eligible(t)
        if not ok:
            continue
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
        values = []
        for sc in scenes:
            t = latest.get((mid, sc))
            values.append(None if not t or t.avg_score is None else float(t.avg_score))
        series.append({"model_id": mid, "model_name": names.get(mid, str(mid)), "values": values})
    return {"scenes": scenes, "series": series, "missing_as_null": True}


async def save_snapshot(db: AsyncSession, board: str, payload: dict, status: str = "ok") -> LeaderboardSnapshot:
    snap = LeaderboardSnapshot(board_type=board, payload_json=dumps(payload), status=status)
    db.add(snap)
    await db.flush()
    return snap


async def last_snapshot(db: AsyncSession, board: str) -> LeaderboardSnapshot | None:
    return (await db.execute(
        select(LeaderboardSnapshot).where(LeaderboardSnapshot.board_type == board).order_by(LeaderboardSnapshot.id.desc()).limit(1)
    )).scalars().first()


async def publish_release(db: AsyncSession, board: str, note: str = "") -> LeaderboardRelease:
    payload = await compute_board(db, board, use_frozen_scale=False)
    items = payload.get("items") or []
    present = [i["avg_score"] for i in items if i.get("avg_score") is not None]
    if payload["board"] == "overall":
        present = [i["weighted_score"] for i in items if i.get("weighted_score") is not None]
    elif payload["board"] == "value":
        present = [i["value_score"] for i in items if i.get("value_score") is not None]
    if not items or not present:
        raise ValueError("no_qualifying_formal_result")
    lo = min(present)
    hi = max(present)
    # 用冻结尺度重算
    payload2 = await compute_board(db, board, use_frozen_scale=False)
    # 手动注入尺度
    if lo is not None:
        for i, ns in zip(payload2["items"], freeze_normalize(
            [i.get("weighted_score") if board == "overall" else (i.get("value_score") if board == "value" else i.get("avg_score")) for i in payload2["items"]],
            lo, hi,
        )):
            i["norm_score"] = ns
        payload2["items"] = rank_with_ties(payload2["items"], "norm_score")
        payload2["frozen_scale"] = {"lo": lo, "hi": hi}

    snap = await save_snapshot(db, board, payload2)
    prev = await current_release(db, board)
    if prev:
        prev.is_current = False
    rel = LeaderboardRelease(
        board_type=board,
        cohort_id=payload2.get("cohort_id") or "",
        snapshot_id=snap.id,
        payload_json=dumps(payload2),
        scale_lo=lo,
        scale_hi=hi,
        status="published",
        is_current=True,
        previous_release_id=prev.id if prev else None,
        note=note or "publish",
    )
    db.add(rel)
    await db.flush()
    payload2["release_id"] = rel.id
    rel.payload_json = dumps(payload2)
    await db.flush()
    return rel


async def rollback_release(db: AsyncSession, board: str) -> LeaderboardRelease:
    cur = await current_release(db, board)
    if not cur:
        raise ValueError("no_current_release")
    # 不可变：只撤回指针
    cur.is_current = False
    cur.status = "withdrawn"
    prev = None
    if cur.previous_release_id:
        prev = await db.get(LeaderboardRelease, cur.previous_release_id)
    if prev and prev.status != "withdrawn":
        # 恢复上一合格发布；若已被标 withdrawn 仍可展示为 current（历史快照内容不变）
        prev.is_current = True
        prev.status = "published"
        await db.flush()
        return prev
    # 无上一发布：保持无 current，调用方读快照兜底
    await db.flush()
    raise ValueError("no_previous_qualified_release")


def release_out(rel: LeaderboardRelease) -> dict[str, Any]:
    return {
        "id": rel.id,
        "board_type": rel.board_type,
        "cohort_id": rel.cohort_id,
        "snapshot_id": rel.snapshot_id,
        "scale_lo": rel.scale_lo,
        "scale_hi": rel.scale_hi,
        "status": rel.status,
        "is_current": rel.is_current,
        "previous_release_id": rel.previous_release_id,
        "note": rel.note,
        "created_at": iso(rel.created_at),
        "payload": loads(rel.payload_json, {}),
    }
