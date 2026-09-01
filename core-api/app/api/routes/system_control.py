"""Owner-only system controls."""

from __future__ import annotations

from hmac import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from app.api.routes.auth import _current_unlock_pin, _session, _token_from_request
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.core.system_control import SystemControlService

router = APIRouter(prefix="/system")


class ProtectedSystemActionRequest(BaseModel):
    pin: str


def _require_owner(authorization: str | None, store: CoreDataStore):
    session = _session(_token_from_request(None, authorization), store)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна")
    return session


def _require_pin(payload: ProtectedSystemActionRequest, authorization: str | None, store: CoreDataStore) -> None:
    _require_owner(authorization, store)
    expected = _current_unlock_pin(store)
    if expected is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="PIN блокировки не настроен")
    if not compare_digest(payload.pin, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный код блокировки")


@router.post("/lock")
def lock_system(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    _require_owner(authorization, store)
    from app.api.routes.auth import lock_session

    lock_session(store=store, authorization=authorization)
    return {"locked": True}


@router.post("/restart")
def restart_system(
    payload: ProtectedSystemActionRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    _require_pin(payload, authorization, store)
    SystemControlService.restart()
    return {"status": "restarting"}


@router.post("/shutdown")
def shutdown_system(
    payload: ProtectedSystemActionRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    _require_pin(payload, authorization, store)
    SystemControlService.shutdown()
    return {"status": "shutting_down"}
