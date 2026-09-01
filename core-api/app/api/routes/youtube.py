"""Owner-only YouTube connection, mapping and sync controls."""

from typing import Annotated
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.api.routes.auth import _session, _token_from_request
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.integrations.youtube.service import YouTubeMarketingService

router = APIRouter(prefix="/youtube")


def _owner(authorization: str | None, store: CoreDataStore) -> None:
    if _session(_token_from_request(None, authorization), store) is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна"
        )


class YouTubeMappingRequest(BaseModel):
    organization_id: str
    channel_id: str
    display_name: str | None = None


class YouTubeSyncRequest(BaseModel):
    mode: str = "incremental"
    backfill_days: int = Field(default=7, ge=1, le=365)


@router.get("/status")
def youtube_status(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _owner(authorization, store)
    return YouTubeMarketingService(store).status()


@router.post("/connect")
def youtube_connect(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _owner(authorization, store)
    return YouTubeMarketingService(store).connect()


@router.post("/mappings")
def youtube_mapping(
    payload: YouTubeMappingRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _owner(authorization, store)
    return YouTubeMarketingService(store).map_channel(**payload.model_dump())


@router.post("/sync")
def youtube_sync(
    payload: YouTubeSyncRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _owner(authorization, store)
    return YouTubeMarketingService(store).sync(**payload.model_dump())
