import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


def error_response(
    message: str,
    code: str,
    status_code: int,
    details: list | None = None,
):
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "message": message,
                "code": code,
                "details": details or [],
            }
        },
    )


async def app_exception_handler(
    request: Request,
    exc: AppException,
):
    return error_response(
        message=exc.message,
        code=exc.code,
        status_code=exc.status_code,
        details=exc.details,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    return error_response(
        message="Request validation failed",
        code="VALIDATION_ERROR",
        status_code=422,
        details=[
            {
                "field": ".".join(str(part) for part in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ],
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
):
    return error_response(
        message=str(exc.detail),
        code="HTTP_ERROR",
        status_code=exc.status_code,
    )


async def database_exception_handler(
    request: Request,
    exc: SQLAlchemyError,
):
    logger.exception(
        "Database error while processing %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )

    return error_response(
        message="A database error occurred",
        code="DATABASE_ERROR",
        status_code=500,
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
):
    logger.error(
        "Unhandled exception while processing %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )

    return error_response(
        message="An unexpected error occurred",
        code="INTERNAL_SERVER_ERROR",
        status_code=500,
    )