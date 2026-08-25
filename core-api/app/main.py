"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from logging import getLogger

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.data_layer.factory import get_core_store
from app.core.data_layer.migrations import SmartUpCanonicalV2FoundationService
from app.integrations.smartup.bootstrap import bootstrap_smartup_organizations_from_env

logger = getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own application startup and shutdown for SmartUp runtime services."""

    store = get_core_store()
    result = bootstrap_smartup_organizations_from_env(store)
    if result.organizations:
        logger.info("SmartUp organizations bootstrapped: %s", len(result.organizations))
    canonical_reports = SmartUpCanonicalV2FoundationService(store).backfill_all()
    logger.info(
        "Canonical V2 materialized during startup: %s phase reports",
        len(canonical_reports),
    )
    yield


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
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/")
def root() -> dict[str, str]:
    """Return service metadata."""

    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }
