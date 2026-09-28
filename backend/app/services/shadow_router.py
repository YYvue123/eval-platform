"""影子/灰度路由：双路评估与转正门禁（不信任客户端分数）。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


TRAFFIC_PCT_DEFAULT = 0.05
EVIDENCE_DAYS = 7
SCORE_DRIFT_MAX = 0.10
LATENCY_DRIFT_MAX = 0.20
CORR_MIN = 0.90


def _reject_client_observation(payload: dict | None, label: str) -> str | None:
    """请求体携带的 score/samples 一律视为不可信，除非 source=server_persisted。"""
    if not payload:
        return None
    if payload.get("source") == "server_persisted" and payload.get("observation_id"):
        return None
    dirty = any(
        k in payload and payload.get(k) is not None
        for k in ("score", "server_score", "samples", "latency_ms", "client_score")
    )
    if dirty:
        return f"{label}_client_observation_rejected"
    return None


def _server_scores(payload: dict | None) -> dict[str, Any]:
    p = payload or {}
    if p.get("source") != "server_persisted" or not p.get("observation_id"):
        return {
            "score": None,
            "latency_ms": None,
            "samples": [],
            "failed": bool(p.get("failed")),
            "trusted": False,
        }
    return {
        "score": float(p["score"]) if p.get("score") is not None else None,
        "latency_ms": float(p["latency_ms"]) if p.get("latency_ms") is not None else None,
        "samples": list(p.get("samples") or []),
        "failed": bool(p.get("failed")),
        "trusted": True,
        "observation_id": p.get("observation_id"),
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
    evidence_pair_count: int = 0,
) -> dict[str, Any]:
    """
    四门禁 + 拒绝客户端观测。
    始终 returned=production（candidate 失败不影响生产）。
    """
    gates: list[dict[str, Any]] = []
    now = now or datetime.utcnow()

    for label, payload in (("production", production), ("candidate", candidate)):
        reason = _reject_client_observation(payload, label)
        if reason:
            gates.append({"code": "client_observation_rejected", "ok": False, "detail": reason})
            return {
                "returned": "production",
                "promotable": False,
                "status": "rejected",
                "gates": gates,
                "traffic_pct": traffic_pct,
                "score_diff_rate": None,
                "detail": reason,
            }

    prod = _server_scores(production)
    cand = _server_scores(candidate)

    if not prod["trusted"] or not cand["trusted"]:
        gates.append(
            {
                "code": "server_observation_required",
                "ok": False,
                "detail": "缺少服务端持久化观测（observation_id + source=server_persisted）",
            }
        )
        return {
            "returned": "production",
            "promotable": False,
            "status": "insufficient_evidence",
            "gates": gates,
            "traffic_pct": traffic_pct,
            "score_diff_rate": None,
        }

    gates.append({"code": "client_observation_rejected", "ok": True, "detail": "ok"})

    cand_failed = bool(cand["failed"])
    gates.append(
        {
            "code": "candidate_isolated",
            "ok": True,
            "detail": "candidate_failed_ignored" if cand_failed else "candidate_ok",
        }
    )

    psamples = [float(x) for x in prod["samples"]] if prod["samples"] else []
    csamples = [float(x) for x in cand["samples"]] if cand["samples"] else []
    const_p = len(psamples) >= 2 and len(set(psamples)) == 1
    const_c = len(csamples) >= 2 and len(set(csamples)) == 1
    if const_p or const_c:
        gates.append({"code": "constant_inconclusive", "ok": False, "detail": "常量分数 inconclusive"})
        status = "inconclusive"
    else:
        gates.append({"code": "constant_inconclusive", "ok": True, "detail": "ok"})
        status = "evaluated"

    score_diff_rate = None
    if prod["score"] is not None and cand["score"] is not None and abs(prod["score"]) > 1e-9:
        score_diff_rate = abs(cand["score"] - prod["score"]) / abs(prod["score"])
    drift_ok = score_diff_rate is not None and score_diff_rate <= SCORE_DRIFT_MAX
    gates.append(
        {
            "code": "score_drift",
            "ok": drift_ok,
            "detail": f"diff_rate={score_diff_rate}",
        }
    )

    corr = pearson(psamples, csamples) if psamples and csamples else None
    corr_ok = corr is not None and corr >= CORR_MIN
    gates.append({"code": "correlation", "ok": bool(corr_ok), "detail": f"pearson={corr}"})

    # 证据窗：需要 started_at 满 EVIDENCE_DAYS 且至少有成对观测计数
    window_ok = False
    if started_at:
        elapsed = (now - started_at).total_seconds()
        window_ok = elapsed >= EVIDENCE_DAYS * 86400 and evidence_pair_count >= 2
    gates.append(
        {
            "code": "evidence_window",
            "ok": window_ok,
            "detail": f"pairs={evidence_pair_count} days_required={EVIDENCE_DAYS}",
        }
    )

    promotable = (
        status != "inconclusive"
        and all(g["ok"] for g in gates if g["code"] != "candidate_isolated")
        and not cand_failed
    )

    return {
        "returned": "production",
        "promotable": promotable,
        "status": status if promotable or status == "inconclusive" else "blocked",
        "gates": gates,
        "traffic_pct": traffic_pct,
        "score_diff_rate": score_diff_rate,
        "pearson": corr,
        "evidence_pair_count": evidence_pair_count,
    }


def can_promote(shadow: dict | None, *, started_at: datetime | None = None, now: datetime | None = None) -> tuple[bool, str]:
    s = shadow or {}
    if not s:
        return False, "no_shadow_evidence"
    if s.get("status") in {"rejected", "insufficient_evidence", "inconclusive"}:
        return False, f"status:{s.get('status')}"
    if not s.get("promotable"):
        bad = [g["code"] for g in (s.get("gates") or []) if not g.get("ok")]
        return False, "gates:" + ",".join(bad or ["not_promotable"])
    now = now or datetime.utcnow()
    if started_at and (now - started_at) < timedelta(days=EVIDENCE_DAYS):
        days = (now - started_at).total_seconds() / 86400
        return False, f"evidence_window_insufficient:{days:.2f}d"
    if int(s.get("evidence_pair_count") or 0) < 2:
        return False, "evidence_pairs_insufficient"
    return True, "ok"


def make_server_observation(
    *,
    observation_id: str,
    score: float,
    latency_ms: float,
    samples: list[float],
    failed: bool = False,
) -> dict[str, Any]:
    return {
        "source": "server_persisted",
        "observation_id": observation_id,
        "score": score,
        "latency_ms": latency_ms,
        "samples": samples,
        "failed": failed,
    }
