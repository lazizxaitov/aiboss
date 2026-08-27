from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.ai_routing import AIRoutingConfig, AIRoutingResponse, AITaskRouter, get_routing_response, providers_from_registry
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.core.hermes_model_registry import hermes_model_registry

router = APIRouter(prefix="/ai/routing")
providers_router = APIRouter(prefix="/ai")


@router.get("", response_model=AIRoutingResponse)
async def get_ai_routing(store: Annotated[CoreDataStore, Depends(get_core_store)]) -> AIRoutingResponse:
    providers = await hermes_model_registry.get_providers(refresh=True)
    response = get_routing_response(store)
    return response.model_copy(update={"providers": providers_from_registry(providers)})


@providers_router.get("/providers", response_model=list)
async def get_ai_providers() -> list:
    providers = await hermes_model_registry.get_providers(refresh=True)
    return [target.model_dump(mode="json") for target in providers_from_registry(providers)]


@router.put("", response_model=AIRoutingResponse)
async def update_ai_routing(
    config: AIRoutingConfig,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
) -> AIRoutingResponse:
    try:
        await hermes_model_registry.get_providers(refresh=True)
        AITaskRouter(store).save_config(config)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return get_routing_response(store)
