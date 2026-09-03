"""QR pairing for mobile/web devices: create a code in Settings, scan it
from a phone browser at /m/pair, and the phone gets its own owner session —
listed and individually revocable, the same pattern as Telegram accounts."""

from __future__ import annotations

import re
from hmac import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.routes.auth import (
    LoginResponse,
    _revoke_session_by_hash,
    _session,
    _token_for,
    _token_from_request,
)
from app.core.config import settings
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store
from app.core.device_link import DeviceLinkService
from app.core.rate_limit import client_key, enforce_rate_limit, record_failure, record_success

try:
    import segno
except ImportError:  # pragma: no cover - optional dependency, see telegram_ai.py
    segno = None  # type: ignore[assignment]

router = APIRouter(prefix="/device")

_ORIGIN_PATTERN = re.compile(r"^https?://[A-Za-z0-9.\-]+(?::\d{1,5})?$")


def _require_owner(authorization: str | None, store: CoreDataStore):
    session = _session(_token_from_request(None, authorization), store)
    if session is None:
        raise HTTPException(status_code=401, detail="Сессия недействительна")
    return session


class DeviceLinkCreateRequest(BaseModel):
    origin: str = Field(min_length=1, max_length=200)


class DeviceLinkResponse(BaseModel):
    token: str | None = None
    deep_link: str | None = None
    qr_data_uri: str | None = None
    expires_at: str | None = None


class DeviceInfo(BaseModel):
    device_id: str
    label: str
    user_agent: str | None = None
    linked_at: str | None = None


class DeviceListResponse(BaseModel):
    devices: list[DeviceInfo] = Field(default_factory=list)


class DeviceDisconnectRequest(BaseModel):
    device_id: str = Field(min_length=1)


class DevicePairRequest(BaseModel):
    token: str = Field(min_length=1, max_length=256)
    login: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)
    device_label: str | None = Field(default=None, max_length=80)
    # A stable id the phone generates once and stores locally (localStorage),
    # so re-pairing the SAME physical device (session expired, PWA
    # reinstalled, cookie cleared) updates its existing registry entry
    # instead of appending a new "ghost" device every time.
    device_id: str | None = Field(default=None, max_length=64)


@router.post("/link/create", response_model=DeviceLinkResponse)
def create_device_link(
    request: DeviceLinkCreateRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: str | None = Header(default=None),
) -> DeviceLinkResponse:
    session = _require_owner(authorization, store)
    if not _ORIGIN_PATTERN.match(request.origin):
        raise HTTPException(status_code=422, detail="Некорректный адрес системы")
    result = DeviceLinkService(store).create(session.login)
    # Prefer the configured public origin over whatever the browser sent.
    # The desktop app always renders Settings from a loopback address
    # (127.0.0.1 or similar) even when the server is reachable from the
    # network at a real domain — a QR built from that loopback origin can
    # never be reached by a phone scanning it. request.origin is still used
    # as a fallback for setups with no configured public_app_origin (e.g.
    # opening Settings directly from a browser on the real address already
    # works fine as-is).
    origin = (settings.public_app_origin or request.origin).rstrip("/")
    deep_link = f"{origin}/m/pair?token={result['token']}"
    qr_data_uri = None
    if segno is not None:
        try:
            qr_data_uri = segno.make(deep_link, error="m").svg_data_uri(scale=6, border=2)
        except Exception:  # noqa: BLE001 - a broken QR image must never break pairing
            qr_data_uri = None
    return DeviceLinkResponse(
        token=result["token"],
        deep_link=deep_link,
        qr_data_uri=qr_data_uri,
        expires_at=result["expires_at"],
    )


@router.get("/link/list", response_model=DeviceListResponse)
def list_devices(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: str | None = Header(default=None),
) -> DeviceListResponse:
    _require_owner(authorization, store)
    return DeviceListResponse(devices=[DeviceInfo(**item) for item in DeviceLinkService(store).list_devices()])


@router.post("/link/disconnect", response_model=DeviceListResponse)
def disconnect_device(
    request: DeviceDisconnectRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    authorization: str | None = Header(default=None),
) -> DeviceListResponse:
    _require_owner(authorization, store)
    service = DeviceLinkService(store)
    token_hash = service.forget_device(request.device_id)
    if token_hash is None:
        raise HTTPException(status_code=404, detail="Устройство не найдено")
    _revoke_session_by_hash(store, token_hash)
    return DeviceListResponse(devices=[DeviceInfo(**item) for item in service.list_devices()])


@router.post("/pair", response_model=LoginResponse)
def pair_device(
    request: DevicePairRequest,
    request_ctx: Request,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    user_agent: str | None = Header(default=None),
) -> LoginResponse:
    """Called from the public /m/pair page after the phone scans the QR.

    Three things must all check out, same layering as the Telegram Mini App
    flow: the owner login/password (typed on the phone), and the one-time
    pairing token from the QR — neither one alone is enough.
    """

    key = client_key("device_pair", request_ctx)
    enforce_rate_limit(key)
    if not settings.owner_login or not settings.owner_password:
        raise HTTPException(status_code=503, detail="Владелец не настроен")
    if not compare_digest(request.login, settings.owner_login) or not compare_digest(
        request.password, settings.owner_password
    ):
        record_failure(key)
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    identity = DeviceLinkService(store).consume(request.token)
    if identity is None:
        record_failure(key)
        raise HTTPException(status_code=410, detail="QR-код недействителен или уже истёк")
    record_success(key)
    access_token = _token_for(identity)
    DeviceLinkService(store).register_device(
        access_token=access_token,
        label=request.device_label or "Мобильное устройство",
        user_agent=user_agent or "",
        device_id=request.device_id,
    )
    return LoginResponse(access_token=access_token)
