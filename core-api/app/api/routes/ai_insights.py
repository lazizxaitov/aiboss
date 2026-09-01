import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.ai_insight_presentation import AIInsightPresentationService
from app.core.auto_business_analytics import AutoAnalyticsRun, AutoBusinessAnalyticsService
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store

router = APIRouter(prefix="/ai/insights")

# The analytics service owns the process-wide execution lock. This registry
# only prevents duplicate background tasks from the same API process.
_MANUAL_ANALYSIS_TASKS: dict[int, asyncio.Task[AutoAnalyticsRun]] = {}
_WIDGET_ANALYSIS_TASKS: dict[int, asyncio.Task[AutoAnalyticsRun | None]] = {}


def _forget_manual_task(store_key: int, task: asyncio.Task[AutoAnalyticsRun]) -> None:
    if _MANUAL_ANALYSIS_TASKS.get(store_key) is task:
        _MANUAL_ANALYSIS_TASKS.pop(store_key, None)
    # Consume failures so asyncio does not emit an unhandled-task warning.
    if not task.cancelled():
        task.exception()


def _forget_widget_task(store_key: int, task: asyncio.Task[AutoAnalyticsRun | None]) -> None:
    if _WIDGET_ANALYSIS_TASKS.get(store_key) is task:
        _WIDGET_ANALYSIS_TASKS.pop(store_key, None)
    if not task.cancelled():
        task.exception()


def _schedule_widget_refresh(store: CoreDataStore) -> bool:
    store_key = id(store)
    existing_task = _WIDGET_ANALYSIS_TASKS.get(store_key)
    if existing_task is not None and not existing_task.done():
        return True
    service = AutoBusinessAnalyticsService(store)
    if not service.widget_needs_refresh():
        return False
    task = asyncio.create_task(service.run_widget_if_needed())
    _WIDGET_ANALYSIS_TASKS[store_key] = task
    task.add_done_callback(lambda completed: _forget_widget_task(store_key, completed))
    return True


@router.get("/status")
def get_automatic_analytics_status(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> dict:
    task = _MANUAL_ANALYSIS_TASKS.get(id(store))
    if task is not None and not task.done():
        return {"status": "analyzing"}
    return AutoBusinessAnalyticsService(store).status().model_dump(mode="json")


@router.get("/dashboard")
async def get_dashboard_insights(store: Annotated[CoreDataStore, Depends(get_core_store)]) -> dict:
    refreshing = _schedule_widget_refresh(store)
    payload = AIInsightPresentationService(store).dashboard()
    payload["refreshing"] = refreshing
    if refreshing and payload.get("status") == "ready":
        payload["message"] = "Обновляем AI-анализ по актуальным данным..."
    return payload


@router.post("/analyze", response_model=AutoAnalyticsRun)
async def run_dashboard_analysis(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> AutoAnalyticsRun:
    """Start the existing business analytics agent without holding the request."""

    store_key = id(store)
    existing_task = _MANUAL_ANALYSIS_TASKS.get(store_key)
    if existing_task is not None and not existing_task.done():
        latest = AutoBusinessAnalyticsService(store).latest()
        return (
            latest
            if latest is not None and latest.status == "running"
            else AutoAnalyticsRun(status="running")
        )

    task = asyncio.create_task(AutoBusinessAnalyticsService(store).run())
    _MANUAL_ANALYSIS_TASKS[store_key] = task
    task.add_done_callback(lambda completed: _forget_manual_task(store_key, completed))
    latest = AutoBusinessAnalyticsService(store).latest()
    return (
        latest
        if latest is not None and latest.status == "running"
        else AutoAnalyticsRun(status="running")
    )


@router.get("/page/{page}")
def get_page_insights(page: str, store: Annotated[CoreDataStore, Depends(get_core_store)]) -> dict:
    return AIInsightPresentationService(store).page(page)


@router.get("/entity/{entity_type}/{entity_id}")
def get_entity_insights(
    entity_type: str,
    entity_id: str,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> dict:
    return AIInsightPresentationService(store).entity(entity_type, entity_id)
