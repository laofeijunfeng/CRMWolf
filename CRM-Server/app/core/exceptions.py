from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
import logging
from uuid import uuid4

from app.core.logging import get_logger, log_with_fields

logger = get_logger(__name__)


class AppException(Exception):
    def __init__(
        self,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail: str = "Internal server error",
        error_code: str = "INTERNAL_ERROR"
    ):
        self.status_code = status_code
        self.detail = detail
        self.error_code = error_code
        super().__init__(detail)


class ValidationException(AppException):
    def __init__(self, detail: str = "Validation failed"):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
            error_code="VALIDATION_ERROR"
        )


class NotFoundException(AppException):
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            error_code="NOT_FOUND"
        )


class ConflictException(AppException):
    def __init__(self, detail: str = "Resource already exists"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            error_code="CONFLICT"
        )


class ForbiddenException(AppException):
    def __init__(self, detail: str = "Access forbidden"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            error_code="FORBIDDEN"
        )


class UnauthorizedException(AppException):
    def __init__(self, detail: str = "Unauthorized"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code="UNAUTHORIZED"
        )


def _is_customer_profile_path(request: Request) -> bool:
    path = request.url.path.rstrip("/")
    return "/v1/customers/" in path and "/profile" in path


def _profile_request_id(request: Request) -> str:
    request_id = request.headers.get("X-Request-ID") or request.headers.get("x-request-id")
    return request_id.strip() if request_id and request_id.strip() else f"req_profile_{uuid4().hex}"


def _profile_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "request_id": _profile_request_id(request),
            "data": None,
            "error": {"code": code, "message": message, "details": details},
        },
    )


def _profile_http_error_code(status_code: int) -> str:
    return {
        status.HTTP_400_BAD_REQUEST: "PROFILE_SCHEMA_INVALID",
        status.HTTP_401_UNAUTHORIZED: "PROFILE_UNAUTHORIZED",
        status.HTTP_403_FORBIDDEN: "PROFILE_FORBIDDEN",
        status.HTTP_404_NOT_FOUND: "PROFILE_NOT_FOUND",
        status.HTTP_409_CONFLICT: "PROFILE_REFRESH_IN_PROGRESS",
        status.HTTP_422_UNPROCESSABLE_ENTITY: "PROFILE_SCHEMA_INVALID",
    }.get(status_code, "PROFILE_INTERNAL_ERROR")


async def http_exception_handler(request: Request, exc: HTTPException):
    if not _is_customer_profile_path(request):
        content = {"detail": exc.detail}
        return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    code = str(detail.get("code") or _profile_http_error_code(exc.status_code))
    message = str(detail.get("message") or detail.get("detail") or exc.detail or "请求失败")
    raw_details = detail.get("details")
    details = raw_details if isinstance(raw_details, dict) else None
    return _profile_response(
        request,
        status_code=exc.status_code,
        code=code,
        message=message,
        details=details,
    )


async def app_exception_handler(request: Request, exc: AppException):
    log_with_fields(
        logger, logging.ERROR,
        f"业务异常: {exc.error_code} - {exc.detail}",
        path=str(request.url.path),
        error_code=exc.error_code,
        status_code=exc.status_code
    )
    if _is_customer_profile_path(request):
        return _profile_response(
            request,
            status_code=exc.status_code,
            code=exc.error_code,
            message=exc.detail,
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.error_code,
            "detail": exc.detail,
            "path": str(request.url)
        }
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    log_with_fields(
        logger, logging.ERROR,
        "请求参数验证失败",
        path=str(request.url.path),
        method=request.method,
        errors=[{"field": " -> ".join(str(loc) for loc in e["loc"]), "msg": e["msg"]} for e in exc.errors()]
    )

    errors = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"]
        })

    if _is_customer_profile_path(request):
        return _profile_response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="PROFILE_SCHEMA_INVALID",
            message="请求参数验证失败",
            details={"fields": errors},
        )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error_code": "VALIDATION_ERROR",
            "detail": "请求参数验证失败",
            "errors": errors,
            "path": str(request.url)
        }
    )


async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    log_with_fields(
        logger, logging.ERROR,
        "数据验证失败",
        path=str(request.url.path),
        errors=[{"field": " -> ".join(str(loc) for loc in e["loc"]), "msg": e["msg"]} for e in exc.errors()]
    )

    errors = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"]
        })

    if _is_customer_profile_path(request):
        return _profile_response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="PROFILE_SCHEMA_INVALID",
            message="数据验证失败",
            details={"fields": errors},
        )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error_code": "VALIDATION_ERROR",
            "detail": "数据验证失败",
            "errors": errors,
            "path": str(request.url)
        }
    )


async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.error(
        "数据库错误",
        exc_info=True,
        extra={"extra_fields": {
            "path": str(request.url.path),
            "method": request.method,
            "error_type": type(exc).__name__
        }}
    )
    if _is_customer_profile_path(request):
        return _profile_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="PROFILE_DATA_UNAVAILABLE",
            message="客户档案数据暂时不可用",
        )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error_code": "DATABASE_ERROR",
            "detail": "数据库操作失败",
            "path": str(request.url)
        }
    )


async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(
        f"未处理异常: {type(exc).__name__}",
        exc_info=True,
        extra={"extra_fields": {
            "path": str(request.url.path),
            "method": request.method,
            "error_type": type(exc).__name__,
            "message": str(exc)
        }}
    )
    if _is_customer_profile_path(request):
        return _profile_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="PROFILE_INTERNAL_ERROR",
            message="客户档案服务暂时不可用",
        )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error_code": "INTERNAL_ERROR",
            "detail": "服务器内部错误",
            "path": str(request.url)
        }
    )
