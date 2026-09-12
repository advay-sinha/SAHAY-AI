"""FastAPI application entry point.

One process, PostgreSQL or local SQLite, mock LLM, local assessment runner.
Bound to 0.0.0.0 so a physical phone on the LAN can reach it.

Requires the EXT-001 packages (approved and installed 2026-09-10). The
safety-critical modules it orchestrates (app/ws/fanout.py, app/services/*) are
standard library only, so they are also tested without any of them.
"""

from contextlib import asynccontextmanager

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .adapters.assessment_runner import runner
from .api import router as api_router
from .core import log_redaction
from .core.config import get_settings
from .core.db import dispose_engine
from .core.errors import DomainError
from .workers import assessment as _assessment_worker  # noqa: F401  (binds the job to the runner)
from .schemas.contracts import HealthResponse
from .ws.session import router as ws_router

settings = get_settings()

# Defence in depth for unexpected query data and JWT-shaped log arguments.
log_redaction.install()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Migrations are applied by Alembic, not on startup, so a demo database is
    # reproducible from the seed script.
    yield
    await runner.drain()  # let in-flight assessment cycles finish cleanly
    await dispose_engine()


app = FastAPI(
    title="SAHAY-AI",
    version="0.1.0",
    description=(
        "AI-assisted intake and vulnerability assessment prototype for NHAA 14566. "
        "Assistive prioritisation only: not a clinical, legal or forensic determination. "
        "A human decides every recommended action."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws_router)

_log = logging.getLogger("sahay.api")


@app.exception_handler(DomainError)
async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # FastAPI's default 422 echoes the submitted value back (`input`). For a
    # turn or a rationale that could be victim or case text, so only the field
    # location and a short message are returned.
    errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg", "invalid")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(Exception)
async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
    # Never a stack trace, a secret or case text in a response. The type name
    # alone goes to the server log.
    _log.error("unhandled %s", type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Internal error"})


@app.get("/health", response_model=HealthResponse, tags=["ops"])
async def health() -> HealthResponse:
    """Liveness response without probing or claiming database readiness."""
    from ml.dialogue.scripts import unwritten

    outstanding = unwritten()
    return HealthResponse(
        status="ok",
        app_env="ready",
        llm_provider="ready",
        assessment_runner="ready",
        database="configured",
        fixed_scripts_ready=not outstanding,
        detail={"outstanding_fixed_scripts": sorted(outstanding)},
    )
