"""进程内 Prometheus 文本指标。"""
from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

_lock = Lock()
_started = time.time()
_http_count: dict[tuple[str, str, str], int] = defaultdict(int)
_http_ms: dict[tuple[str, str, str], float] = defaultdict(float)
_invokes = 0
_invoke_fail = 0
_eval_done = 0


def observe_http(method: str, path: str, status: int, duration_ms: float) -> None:
    key = (method.upper(), _norm_path(path), str(status))
    with _lock:
        _http_count[key] += 1
        _http_ms[key] += duration_ms


def observe_model_invoke(ok: bool) -> None:
    global _invokes, _invoke_fail
    with _lock:
        _invokes += 1
        if not ok:
            _invoke_fail += 1


def observe_eval_done() -> None:
    global _eval_done
    with _lock:
        _eval_done += 1


def _norm_path(path: str) -> str:
    parts = []
    for p in (path or "").split("/"):
        if p.isdigit():
            parts.append(":id")
        else:
            parts.append(p)
    return "/".join(parts) or "/"


def render_prometheus() -> str:
    lines = [
        "# HELP eval_platform_up 1 if process is up",
        "# TYPE eval_platform_up gauge",
        "eval_platform_up 1",
        "# HELP eval_platform_uptime_seconds Process uptime",
        "# TYPE eval_platform_uptime_seconds gauge",
        f"eval_platform_uptime_seconds {time.time() - _started:.1f}",
        "# HELP eval_http_requests_total HTTP requests",
        "# TYPE eval_http_requests_total counter",
    ]
    with _lock:
        for (method, path, status), n in sorted(_http_count.items()):
            lines.append(f'eval_http_requests_total{{method="{method}",path="{path}",status="{status}"}} {n}')
        lines.append("# HELP eval_http_request_duration_ms_sum Request duration sum")
        lines.append("# TYPE eval_http_request_duration_ms_sum counter")
        for (method, path, status), ms in sorted(_http_ms.items()):
            lines.append(f'eval_http_request_duration_ms_sum{{method="{method}",path="{path}",status="{status}"}} {ms:.2f}')
        lines.append("# HELP eval_model_invokes_total Model invoke attempts")
        lines.append("# TYPE eval_model_invokes_total counter")
        lines.append(f"eval_model_invokes_total {_invokes}")
        lines.append("# HELP eval_model_invoke_failures_total Model invoke failures")
        lines.append("# TYPE eval_model_invoke_failures_total counter")
        lines.append(f"eval_model_invoke_failures_total {_invoke_fail}")
        lines.append("# HELP eval_tasks_completed_total Finished eval tasks")
        lines.append("# TYPE eval_tasks_completed_total counter")
        lines.append(f"eval_tasks_completed_total {_eval_done}")
    return "\n".join(lines) + "\n"


def snapshot() -> dict:
    with _lock:
        return {
            "uptime_seconds": round(time.time() - _started, 1),
            "http_requests": sum(_http_count.values()),
            "model_invokes": _invokes,
            "model_invoke_failures": _invoke_fail,
            "eval_completed": _eval_done,
        }
