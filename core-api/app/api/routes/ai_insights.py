from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.ai_insight_presentation import AIInsightPresentationService
from app.core.auto_business_analytics import AutoBusinessAnalyticsService
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store

router = APIRouter(prefix="/ai/insights")


@router.get("/status")
def get_automatic_analytics_status(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> dict:
    return AutoBusinessAnalyticsService(store).status().model_dump(mode="json")


@router.get("/dashboard")
def get_dashboard_insights(store: Annotated[CoreDataStore, Depends(get_core_store)]) -> dict:
    return AIInsightPresentationService(store).dashboard()


@router.get("/page/{page}")
def get_page_insights(page: str, store: Annotated[CoreDataStore, Depends(get_core_store)]) -> dict:
    return AIInsightPresentationService(store).page(page)


@router.get("/entity/{entity_type}/{entity_id}")
def get_entity_insights(entity_type: str, entity_id: str, store: Annotated[CoreDataStore, Depends(get_core_store)]) -> dict:
    return AIInsightPresentationService(store).entity(entity_type, entity_id)
