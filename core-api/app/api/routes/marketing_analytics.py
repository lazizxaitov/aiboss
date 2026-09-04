"""Owner-only Marketing Analytics endpoint: Instagram/YouTube/Meta-ads
aggregates plus AI commentary for the Marketing Analytics dashboard page."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.api.routes.auth import _session, _token_from_request
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.core.marketing_analytics import MarketingAnalyticsService
from app.core.marketing_insights import generate_marketing_commentary

router = APIRouter(prefix="/marketing")


def _owner(authorization: str | None, store: CoreDataStore) -> None:
    if _session(_token_from_request(None, authorization), store) is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна"
        )


@router.get("/analytics")
async def marketing_analytics(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    organization_id: Annotated[str | None, Query()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _owner(authorization, store)
    payload = MarketingAnalyticsService(store).build(organization_id)
    payload["ai_commentary"] = await generate_marketing_commentary(payload)
    return payload
