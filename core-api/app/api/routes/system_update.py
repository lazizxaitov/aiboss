"""Owner-only system update endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.routes.auth import _session, _token_from_request
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.core.system_update import SystemUpdateService

router = APIRouter(prefix="/system/update")


def require_owner(authorization: str | None, store: CoreDataStore) -> None:
    if _session(_token_from_request(None, authorization), store) is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна")


@router.get("/status")
def update_status(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    require_owner(authorization, store)
    try:
        return SystemUpdateService(store).status()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Не удалось проверить обновления: {exc}") from exc


@router.post("/install")
def install_update(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    require_owner(authorization, store)
    return SystemUpdateService(store).start_install().model_dump(mode="json")


@router.get("/jobs/{job_id}")
def update_job(
    job_id: str,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    require_owner(authorization, store)
    job = SystemUpdateService(store).get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Задача обновления не найдена")
    return job.model_dump(mode="json")


@router.get("/latest")
def latest_update_job(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: str | None = Header(default=None),
) -> dict[str, object] | None:
    """The most recent update attempt (running, succeeded, failed, or rolled
    back), so Settings can show what happened even after a reload — an
    update restarts the backend itself, wiping any in-page state."""

    require_owner(authorization, store)
    job = SystemUpdateService(store).get_latest_job()
    return job.model_dump(mode="json") if job else None
