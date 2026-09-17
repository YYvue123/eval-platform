"""统一异常处理"""
import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


def _error_response(status_code: int, message: str, detail=None):
    """统一错误响应格式"""
    body = {"success": False, "code": status_code, "message": message}
    if detail is not None:
        body["detail"] = detail
    return JSONResponse(status_code=status_code, content=body)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """处理 HTTPException（含业务抛出的 400/403/404 等）"""
    msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    logger.warning(
        "HTTPException | path=%s | method=%s | status=%s | detail=%s",
        request.url.path,
        request.method,
        exc.status_code,
        msg,
    )
    return _error_response(exc.status_code, msg)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """处理 Pydantic 校验错误（422）"""
    errors = exc.errors()
    logger.warning(
        "ValidationError | path=%s | method=%s | errors=%s",
        request.url.path,
        request.method,
        errors,
    )
    return _error_response(status.HTTP_422_UNPROCESSABLE_ENTITY, "请求参数校验失败", detail=errors)


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理未捕获的异常，记录完整堆栈，返回 500"""
    logger.exception(
        "Unhandled Exception | path=%s | method=%s | type=%s | error=%s",
        request.url.path,
        request.method,
        type(exc).__name__,
        str(exc),
        exc_info=True,
    )
    return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "服务器内部错误")


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器"""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
