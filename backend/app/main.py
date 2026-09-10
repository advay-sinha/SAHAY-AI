"""FastAPI application entry point.

Local MVP: one process, SQLite, mock LLM, local assessment runner.
Bound to 0.0.0.0 so a physical phone on the LAN can reach it.

Requires the EXT-001 packages (approved and installed 2026-09-10). The
safety-critical modules it orchestrates (app/ws/fanout.py, app/services/*) are
standard library only, so they are also tested without any of them.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router as api_router
from .core import log_redaction
from .core.config import get_settings
from .schemas.contracts import HealthResponse
from .ws.session import router as ws_router

settings = get_settings()

# Before any request is served: the WebSocket handshake URL carries the JWT by
# contract, and uvicorn would otherwise write it into the log.
log_redaction.install()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Migrations are applied by Alembic, not on startup, so a demo database is
    # reproducible from the seed script.
    yield


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


@app.get("/health", response_model=HealthResponse, tags=["ops"])
async def health() -> HealthResponse:
    """Liveness and configuration check for the P0 gate."""
    from ml.dialogue.scripts import unwritten

    outstanding = unwritten()
    return HealthResponse(
        status="ok",
        app_env=settings.APP_ENV,
        llm_provider=settings.LLM_PROVIDER,
        assessment_runner=settings.ASSESSMENT_RUNNER,
        database=settings.DATABASE_URL.split("///")[-1],
        fixed_scripts_ready=not outstanding,
        detail={"outstanding_fixed_scripts": sorted(outstanding)},
    )
