"""影子/灰度路由：双路评估与转正门禁（不信任客户端分数）。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


TRAFFIC_PCT_DEFAULT = 0.05
EVIDENCE_DAYS = 7
SCORE_DRIFT_MAX = 0.10
LATENCY_DRIFT_MAX = 0.20
CORR_MIN = 0.90


def _server_scores(payload: dict | None) -> dict[str, Any]:
    """只接受服务端观测字段；忽略 client_score。"""
    p = payload or {}
    return {
        "score": float(p.get("score") if p.get("score") is not None else p.get("server_score") or 0),
        "latency_ms": float(p.get("latency_ms") or 0),
        "samples": list(p.get("samples") or []),
        "failed": bool(p.get("failed")),
        "client_score": p.get("client_score"),
    }


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = min(len(xs), len(ys))
    if n < 2:
        return None
    xs, ys = xs[:n], ys[:n]
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denx = sum((x - mx) ** 2 for x in xs) ** 0.5
    deny = sum((y - my) ** 2 for y in ys) ** 0.5
    if denx == 0 or deny == 0:
        return None
    return num / (denx * deny)


def evaluate_shadow(
    production: dict | None,
    candidate: dict | None,
    *,
    traffic_pct: float = TRAFFIC_PCT_DEFAULT,
    started_at: datetime | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    四门禁：
    1) 单项分数漂移 >10% 不得转正
    2) 样本相关性不足
    3) 常量分数 → inconclusive
    4) 仅有客户端伪造分数 → 无效
    始终 returned=production（candidate 失败不影响生产）。
    """
    prod = _server_scores(production)
    cand = _server_scores(candidate)
    gates: list[dict[str, Any]] = []
    now = now or datetime.utcnow()

    # Gate: forged client score
    if candidate and candidate.get("client_score") is not None and candidate.get("score") is None and candidate.get("server_score") is None:
        gates.append({"code": "client_score_rejected", "ok": False, "detail": "伪造客户端 score 无效"})
    else:
        gates.append({"code": "client_score_rejected", "ok": True, "detail": "ok"})

    # Gate: candidate failure isolation
    cand_failed = bool(cand["failed"])
    gates.append({
        "code": "candidate_isolated",
        "ok": True,
        "detail": "candidate_failed_ignored" if cand_failed else "candidate_ok",
    })

    # Gate: constant scores inconclusive
    psamples = [float(x) for x in prod["samples"]] if prod["samples"] else []
    csamples = [float(x) for x in cand["samples"]] if cand["samples"] else []
    const_p = len(psamples) >= 2 and len(set(psamples)) == 1
    const_c = len(csamples) >= 2 and len(set(csamples)) == 1
    inconclusive = const_p or const_c
    gates.append({
        "code": "constant_score",
        "ok": not inconclusive,
        "detail": "inconclusive" if inconclusive else "ok",
    })

    # Gate: score drift
    ps, cs = prod["score"], cand["score"]
    if cand_failed:
        drift = None
        drift_ok = False
        gates.append({"code": "score_drift", "ok": False, "detail": "candidate_failed"})
    elif ps == 0 and cs == 0:
        drift = 0.0
        drift_ok = True
        gates.append({"code": "score_drift", "ok": True, "detail": "0"})
    else:
        drift = abs(cs - ps) / ps if ps else (1.0 if cs else 0.0)
        drift_ok = drift <= SCORE_DRIFT_MAX
        gates.append({"code": "score_drift", "ok": drift_ok, "detail": round(drift, 4)})

    # Gate: correlation
    corr = pearson(psamples, csamples) if psamples and csamples else None
    if corr is None:
        # 无成对样本时用延迟差作为弱门禁
        pl, cl = prod["latency_ms"], cand["latency_ms"]
        lat_diff = abs(cl - pl) / pl if pl else (0.0 if cl == 0 else 1.0)
        corr_ok = lat_diff <= LATENCY_DRIFT_MAX and not cand_failed
        gates.append({"code": "correlation", "ok": corr_ok, "detail": f"latency_proxy:{round(lat_diff, 4)}"})
    else:
        corr_ok = corr >= CORR_MIN
        gates.append({"code": "correlation", "ok": corr_ok, "detail": round(corr, 4)})

    evidence_days = 0.0
    if started_at:
        evidence_days = max((now - started_at).total_seconds() / 86400.0, 0.0)
    # 证据窗在转正时复核；shadow 记录仅保存天数与起始点
    gates.append({
        "code": "evidence_window",
        "ok": True,
        "detail": f"pending_check:{evidence_days:.2f}d/{EVIDENCE_DAYS}d",
        "deferred": True,
    })

    traffic = float(traffic_pct if traffic_pct is not None else TRAFFIC_PCT_DEFAULT)
    if traffic <= 0:
        traffic = TRAFFIC_PCT_DEFAULT

    # promotable 不含证据窗（deferred）
    core_ok = all(g["ok"] for g in gates if not g.get("deferred")) and not inconclusive and not cand_failed
    status = "inconclusive" if inconclusive else ("ready" if core_ok else "blocked")

    return {
        "production": {"score": ps, "latency_ms": prod["latency_ms"], "failed": False},
        "candidate": {"score": cs, "latency_ms": cand["latency_ms"], "failed": cand_failed},
        "score_diff_rate": None if drift is None else round(float(drift), 4),
        "correlation": None if corr is None else round(corr, 4),
        "gates": gates,
        "promotable": core_ok,
        "status": status,
        "stable": core_ok,
        "returned": "production",
        "traffic_pct": traffic,
        "evidence_days": round(evidence_days, 4),
        "evidence_required_days": EVIDENCE_DAYS,
    }


def can_promote(shadow: dict[str, Any], *, started_at: datetime | None = None, now: datetime | None = None) -> tuple[bool, str]:
    if not shadow:
        return False, "missing_shadow_evidence"
    if shadow.get("status") == "inconclusive":
        return False, "inconclusive_constant_scores"
    if not shadow.get("promotable"):
        bad = [g["code"] for g in (shadow.get("gates") or []) if not g.get("ok") and not g.get("deferred")]
        return False, "gates_failed:" + ",".join(bad or ["unknown"])
    now = now or datetime.utcnow()
    if not started_at:
        return False, "evidence_window_missing_start"
    days = max((now - started_at).total_seconds() / 86400.0, 0.0)
    if days < EVIDENCE_DAYS:
        return False, f"evidence_window_insufficient:{days:.2f}d"
    traffic = float(shadow.get("traffic_pct") or 0)
    if traffic <= 0:
        return False, "traffic_not_enabled"
    return True, ""
