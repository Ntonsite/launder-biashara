"""One error envelope for every failure: {"error": {"code", "message", "details"}, "detail": message}.

`detail` is kept for clients that already read FastAPI's default shape.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("launder.errors")

STATUS_CODES = {400: "BAD_REQUEST", 401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED",
                409: "CONFLICT", 422: "VALIDATION_ERROR", 429: "RATE_LIMITED"}


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None, headers: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details, self.headers = status, code, message, details, headers


def not_found(what: str) -> AppError:
    return AppError(404, "NOT_FOUND", f"{what} not found")


def _body(code: str, message: str, details=None, request: Request | None = None) -> dict:
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    if request is not None and getattr(request.state, "request_id", None):
        error["request_id"] = request.state.request_id
    return {"error": error, "detail": message}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return JSONResponse(_body(exc.code, exc.message, exc.details, request), status_code=exc.status, headers=exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(_body(STATUS_CODES.get(exc.status_code, "ERROR"), message, None, request),
                            status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        fields = [{"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(_body("VALIDATION_ERROR", "Some fields are invalid", fields, request), status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("unhandled_error", extra={"path": request.url.path})
        return JSONResponse(_body("INTERNAL_ERROR", "Something went wrong. Please try again.", None, request), status_code=500)
