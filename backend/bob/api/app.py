"""FastAPI app (G1). Run locally: `backend/run.sh` (uvicorn on :8000, Vite proxies /api)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from bob.api.auth import check_auth_config
from bob.api.deps import settings
from bob.api.errors import (
    ApiError,
    api_error_handler,
    orchestrator_error_handler,
    runner_busy_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from bob.api.routes import router
from bob.core.runner import RunnerBusy
from bob.orchestrator import JobRunning, PreconditionFailed

DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def create_app() -> FastAPI:
    check_auth_config()
    app = FastAPI(title="Bob API", docs_url="/api/docs", openapi_url="/api/openapi.json")
    origins = list(DEV_ORIGINS)
    if settings.public_url:
        origins.append(settings.public_url.rstrip("/"))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
    )
    # No GZip middleware: it buffers the SSE stream.
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(PreconditionFailed, orchestrator_error_handler)
    app.add_exception_handler(JobRunning, orchestrator_error_handler)
    app.add_exception_handler(RunnerBusy, runner_busy_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
    app.include_router(router, prefix="/api")
    return app


app = create_app()
