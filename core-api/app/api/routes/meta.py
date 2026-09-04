"""Owner-only Meta marketing connection and sync controls."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.api.routes.auth import _session, _token_from_request
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.integrations.meta.service import MetaMarketingService

router = APIRouter(prefix="/meta")


def _owner(authorization: str | None, store: CoreDataStore) -> None:
    if _session(_token_from_request(None, authorization), store) is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна"
        )


class MetaMappingRequest(BaseModel):
    organization_id: str
    resource_type: str
    external_id: str
    display_name: str | None = None


class MetaCredentialsRequest(BaseModel):
    # Every field is optional and independent: the owner can fill in just an
    # access token (a Meta System User token needs nothing else), or the
    # full App ID/App Secret/Redirect URI trio for the OAuth flow. Sending ""
    # for a field clears it; omitting a field leaves it untouched.
    app_id: str | None = None
    app_secret: str | None = None
    redirect_uri: str | None = None
    access_token: str | None = None


class MetaSyncRequest(BaseModel):
    mode: str = "incremental"
    backfill_days: int = Field(default=7, ge=1, le=365)


@router.get("/status")
def meta_status(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _owner(authorization, store)
    return MetaMarketingService(store).status()


@router.post("/connect")
def meta_connect(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _owner(authorization, store)
    return MetaMarketingService(store).connect()


@router.post("/credentials")
def meta_save_credentials(
    payload: MetaCredentialsRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _owner(authorization, store)
    return {"credentials": MetaMarketingService(store).save_credentials(**payload.model_dump())}


@router.post("/mappings")
def meta_mapping(
    payload: MetaMappingRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _owner(authorization, store)
    try:
        return MetaMarketingService(store).map_resource(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/sync")
def meta_sync(
    payload: MetaSyncRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _owner(authorization, store)
    try:
        return MetaMarketingService(store).sync(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
