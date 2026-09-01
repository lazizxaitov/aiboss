"""FastAPI application entrypoint."""

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from logging import INFO, Formatter, StreamHandler, getLogger

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.api.routes.auth import _session
from app.core.auto_business_analytics import AutoBusinessAnalyticsService
from app.core.config import settings
from app.core.data_layer.factory import get_core_store
from app.integrations.smartup.bootstrap import bootstrap_smartup_organizations_from_env
from app.integrations.smartup.live_sync import SmartUpLiveSyncService

logger = getLogger(__name__)


async def _run_startup_auto_analysis(store) -> None:
    """Refresh AI insights once from already materialized Core data."""

    try:
        await AutoBusinessAnalyticsService(store).run_startup_if_needed()
    except asyncio.CancelledError:
        raise
    except Exception as error:  # noqa: BLE001 - analytics must not affect readiness
        logger.exception("AI_ANALYTICS_RUN_FAILED stage=startup error=%s", str(error)[:300])


def configure_application_logging() -> None:
    """Enable application INFO logs on the process stream used by Uvicorn."""

    application_logger = getLogger("app")
    application_logger.setLevel(INFO)
    application_logger.propagate = False
    if any(getattr(handler, "_aiboss_application_handler", False) for handler in application_logger.handlers):
        return

    handler = StreamHandler(sys.stderr)
    handler._aiboss_application_handler = True
    handler.setLevel(INFO)
    handler.setFormatter(Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    application_logger.addHandler(handler)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own application startup and shutdown for SmartUp runtime services."""

    configure_application_logging()
    logger.info("AIBOSS_APPLICATION_LOGGING_READY")
    store = get_core_store()
    result = bootstrap_smartup_organizations_from_env(store)
    if result.organizations:
        logger.info("SmartUp organizations bootstrapped: %s", len(result.organizations))
    live_sync = SmartUpLiveSyncService(store)
    live_sync.start()
    app.state.smartup_live_sync = live_sync
    auto_analysis_task = asyncio.create_task(_run_startup_auto_analysis(store))
    app.state.auto_analysis_task = auto_analysis_task
    yield
    auto_analysis_task.cancel()
    try:
        await auto_analysis_task
    except asyncio.CancelledError:
        pass
    live_sync.stop()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def enforce_web_session_lock(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path
    public = {f"{settings.api_v1_prefix}/auth/login", f"{settings.api_v1_prefix}/auth/verify", f"{settings.api_v1_prefix}/auth/me", f"{settings.api_v1_prefix}/auth/unlock", f"{settings.api_v1_prefix}/auth/lock", f"{settings.api_v1_prefix}/auth/logout", f"{settings.api_v1_prefix}/health"}
    if path.startswith(settings.api_v1_prefix) and path not in public:
        authorization = request.headers.get("authorization", "")
        token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
        session = _session(token, get_core_store())
        if session is None:
            return JSONResponse({"detail": "Сессия недействительна"}, status_code=401)
        if session.locked:
            return JSONResponse({"detail": "SESSION_LOCKED"}, status_code=423)
    return await call_next(request)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/")
def root() -> dict[str, str]:
    """Return service metadata."""

    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }
