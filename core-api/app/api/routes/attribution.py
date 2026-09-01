"""Owner-only evidence ingestion and conservative marketing measurement status."""

from typing import Annotated
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.api.routes.auth import _session, _token_from_request
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.core.marketing_attribution import AttributionError, MarketingAttributionService

router = APIRouter(prefix="/marketing/attribution")

def _owner(authorization: str | None, store: CoreDataStore) -> None:
    if _session(_token_from_request(None, authorization), store) is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна")

class AttributionEvidenceRequest(BaseModel):
    organization_id: str
    source_platform: str
    source_entity_type: str
    source_entity_id: str
    target_entity_type: str
    target_entity_id: str
    evidence_type: str
    confidence: str = "confirmed"
    occurred_at: str | None = None
    attribution_window: str | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_content: str | None = None
    utm_term: str | None = None
    click_id_hash: str | None = Field(default=None, min_length=8, max_length=256)
    provenance: str = "first_party"

@router.get("/status")
def attribution_status(store: Annotated[CoreDataStore, Depends(get_core_store)], authorization: Annotated[str | None, Header()] = None) -> dict[str, object]:
    _owner(authorization, store)
    evidence = store.list_source_records("marketing_attribution_evidence")
    outcomes = store.list_source_records("marketing_attributed_outcomes")
    return {"evidence_available": bool(evidence), "confirmed_attribution_available": bool(outcomes), "evidence_count": len(evidence), "attributed_outcome_count": len(outcomes), "message": "Подтверждённая атрибуция доступна" if outcomes else "Атрибуция пока недоступна — нет подтверждённых tracking links."}

@router.post("/evidence")
def ingest_evidence(payload: AttributionEvidenceRequest, store: Annotated[CoreDataStore, Depends(get_core_store)], authorization: Annotated[str | None, Header()] = None) -> dict[str, object]:
    _owner(authorization, store)
    try:
        return MarketingAttributionService(store).ingest(payload.model_dump())
    except AttributionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
