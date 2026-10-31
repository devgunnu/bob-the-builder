"""API error shape (G1): every error body is {"error", "provider"?, "detail"?}."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        error: str,
        *,
        provider: str | None = None,
        detail: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(error)
        self.status = status
        self.error = error
        self.provider = provider
        self.detail = detail
        self.headers = headers

    def body(self) -> dict[str, Any]:
        body: dict[str, Any] = {"error": self.error}
        if self.provider is not None:
            body["provider"] = self.provider
        if self.detail is not None:
            body["detail"] = self.detail
        return body


async def orchestrator_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """PreconditionFailed (412) and JobRunning (409) carry `.status_code` and `.body`."""
    status = int(getattr(exc, "status_code", 500))
    body = getattr(exc, "body", None) or {"error": str(exc)}
    return JSONResponse(body, status_code=status)


async def runner_busy_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"error": "too many running jobs", "detail": str(exc) or None}, status_code=429)


def not_found(what: str = "not found") -> ApiError:
    return ApiError(404, what)


async def api_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return JSONResponse(exc.body(), status_code=exc.status, headers=exc.headers)


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    detail = [{"loc": list(err.get("loc", ())), "msg": err.get("msg", "")} for err in exc.errors()]
    return JSONResponse({"error": "invalid request", "detail": detail}, status_code=422)
