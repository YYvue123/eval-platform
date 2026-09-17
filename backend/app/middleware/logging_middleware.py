"""请求日志中间件 - 记录请求详情、响应状态、耗时、异常"""
import time
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.request")


def _safe_header(req: Request, name: str) -> str:
    """安全获取请求头，避免 KeyError"""
    return req.headers.get(name, "-")


async def logging_middleware(request: Request, call_next) -> Response:
    """记录请求、响应及异常"""
    request_id = uuid.uuid4().hex[:12]
    start = time.perf_counter()
    method = request.method
    path = request.url.path
    query = str(request.query_params) if request.query_params else "-"
    client = _safe_header(request, "x-forwarded-for")
    if client == "-" and request.client:
        client = request.client.host
    user_agent = _safe_header(request, "user-agent")
    content_type = _safe_header(request, "content-type")
    content_length = _safe_header(request, "content-length")

    logger.info(
        "[%s] >>> %s %s | query=%s | client=%s | ua=%s | content-type=%s | content-length=%s",
        request_id,
        method,
        path,
        query,
        client,
        user_agent[:80] if user_agent != "-" else "-",
        content_type,
        content_length,
    )

    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception as exc:
        status_code = 500
        logger.exception(
            "[%s] !!! EXCEPTION | %s %s | type=%s | %s",
            request_id,
            method,
            path,
            type(exc).__name__,
            str(exc),
        )
        raise
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        level = logging.INFO if status_code < 400 else (logging.WARNING if status_code < 500 else logging.ERROR)
        logger.log(
            level,
            "[%s] <<< %s %s | status=%s | duration=%.2fms",
            request_id,
            method,
            path,
            status_code,
            duration_ms,
        )


class LoggingMiddleware(BaseHTTPMiddleware):
    """日志中间件（包装为 BaseHTTPMiddleware）"""

    async def dispatch(self, request: Request, call_next) -> Response:
        return await logging_middleware(request, call_next)
