"""Owner authentication endpoints."""

from hashlib import sha256
from hmac import compare_digest, new
from time import time
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from app.core.config import settings
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.entities import AppSetting
from app.core.data_layer.factory import get_core_store
from app.core.owner_profile import OwnerProfileService

router = APIRouter(prefix="/auth")


class LoginRequest(BaseModel):
    login: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "owner"


class ChangePasswordRequest(BaseModel):
    login: str
    current_password: str
    new_password: str


class UnlockRequest(BaseModel):
    pin: str


class UnlockPinRequest(BaseModel):
    pin: str


class AutoLockSettingsRequest(BaseModel):
    timeout_minutes: int


class OwnerProfileRequest(BaseModel):
    name: str = ""
    about: str = ""


@dataclass
class _SessionState:
    login: str
    locked: bool = False
    last_activity_at: float = 0
    locked_at: float | None = None


_SESSIONS: dict[str, _SessionState] = {}
_SESSIONS_LOCK = Lock()
_UNLOCK_PIN: str | None = None
UNLOCK_PIN_SETTING_KEY = "auth:owner_unlock_pin:v1"
AUTO_LOCK_SETTING_KEY = "auth:auto_lock_timeout:v1"
DEFAULT_AUTO_LOCK_MINUTES = 5
REVOKED_SESSIONS_SETTING_KEY = "auth:revoked_sessions:v1"


def _token_for(login: str) -> str:
    issued_at = str(int(time()))
    payload = f"{login}:{issued_at}"
    signature = new(settings.auth_secret.encode(), payload.encode(), sha256).hexdigest()
    token = f"{payload}:{signature}"
    with _SESSIONS_LOCK:
        _SESSIONS[token] = _SessionState(login=login, last_activity_at=time())
    return token


def _session(token: str, store: CoreDataStore | None = None) -> _SessionState | None:
    parts = token.split(":")
    if len(parts) != 3 or not settings.owner_login:
        return None
    login_name, issued_at, signature = parts
    payload = f"{login_name}:{issued_at}"
    expected = new(settings.auth_secret.encode(), payload.encode(), sha256).hexdigest()
    if not compare_digest(login_name, settings.owner_login) or not compare_digest(signature, expected):
        return None
    if store is not None:
        setting = store.get_app_setting(REVOKED_SESSIONS_SETTING_KEY)
        revoked = setting.setting_value.get("tokens", []) if setting and isinstance(setting.setting_value, dict) else []
        if isinstance(revoked, list) and sha256(token.encode()).hexdigest() in revoked:
            return None
    with _SESSIONS_LOCK:
        session = _SESSIONS.get(token)
        if session is None:
            session = _SessionState(login=login_name, last_activity_at=time())
            _SESSIONS[token] = session
        return session


def _revoke_session_by_hash(store: CoreDataStore, token_hash: str) -> None:
    setting = store.get_app_setting(REVOKED_SESSIONS_SETTING_KEY)
    revoked = setting.setting_value.get("tokens", []) if setting and isinstance(setting.setting_value, dict) else []
    tokens = [item for item in revoked if isinstance(item, str)] if isinstance(revoked, list) else []
    if token_hash not in tokens:
        tokens.append(token_hash)
    now = datetime.now(UTC)
    store.upsert_app_setting(AppSetting(
        setting_key=REVOKED_SESSIONS_SETTING_KEY,
        setting_value={"tokens": tokens[-500:]},
        metadata={"scope": "owner", "kind": "revoked_sessions"},
        created_at=now,
        updated_at=now,
    ))


def _revoke_session(store: CoreDataStore, token: str) -> None:
    _revoke_session_by_hash(store, sha256(token.encode()).hexdigest())


def _token_from_request(token: str | None, authorization: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return token or ""


def _stored_unlock_pin(store: CoreDataStore) -> str | None:
    setting = store.get_app_setting(UNLOCK_PIN_SETTING_KEY)
    if setting is None or not isinstance(setting.setting_value, dict):
        return None
    value = setting.setting_value.get("pin")
    return value if isinstance(value, str) and len(value) == 4 and value.isdigit() else None


def _current_unlock_pin(store: CoreDataStore) -> str | None:
    global _UNLOCK_PIN
    if _UNLOCK_PIN is None:
        _UNLOCK_PIN = _stored_unlock_pin(store)
    return _UNLOCK_PIN


def _auto_lock_minutes(store: CoreDataStore) -> int:
    setting = store.get_app_setting(AUTO_LOCK_SETTING_KEY)
    if setting is None or not isinstance(setting.setting_value, dict):
        return DEFAULT_AUTO_LOCK_MINUTES
    value = setting.setting_value.get("timeout_minutes")
    return value if isinstance(value, int) and 1 <= value <= 1440 else DEFAULT_AUTO_LOCK_MINUTES


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    if not settings.owner_login or not settings.owner_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Владелец не настроен. Укажите OWNER_LOGIN и OWNER_PASSWORD.",
        )
    if not compare_digest(payload.login, settings.owner_login) or not compare_digest(
        payload.password, settings.owner_password
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль")
    return LoginResponse(access_token=_token_for(payload.login))


@router.post("/password")
def change_password(payload: ChangePasswordRequest) -> dict[str, bool]:
    if not settings.owner_login or not settings.owner_password:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Владелец не настроен")
    if not compare_digest(payload.login, settings.owner_login) or not compare_digest(
        payload.current_password, settings.owner_password
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Текущий пароль указан неверно")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Новый пароль должен содержать минимум 8 символов")
    settings.owner_password = payload.new_password
    return {"updated": True}


@router.get("/verify")
def verify(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    token: str = Query(...),
) -> dict[str, bool]:
    return {"valid": _session(token, store) is not None}


@router.get("/me")
def me(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    session = _session(_token_from_request(token, authorization), store)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна")
    return {
        "authenticated": True,
        "locked": session.locked,
        "unlock_pin_configured": _current_unlock_pin(store) is not None,
        "user": {"login": session.login},
    }


@router.get("/lock-settings")
def get_lock_settings(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, int]:
    if _session(_token_from_request(token, authorization), store) is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна")
    return {"timeout_minutes": _auto_lock_minutes(store)}


@router.put("/lock-settings")
def update_lock_settings(
    payload: AutoLockSettingsRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, int]:
    if _session(_token_from_request(token, authorization), store) is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна")
    if not 1 <= payload.timeout_minutes <= 1440:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Время должно быть от 1 до 1440 минут")
    now = datetime.now(UTC)
    store.upsert_app_setting(AppSetting(
        setting_key=AUTO_LOCK_SETTING_KEY,
        setting_value={"timeout_minutes": payload.timeout_minutes},
        metadata={"scope": "owner", "kind": "auto_lock"},
        created_at=now,
        updated_at=now,
    ))
    return {"timeout_minutes": payload.timeout_minutes}


@router.get("/profile")
def get_profile(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    session = _session(_token_from_request(token, authorization), store)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна")
    return OwnerProfileService(store).load(session.login).model_dump(mode="json")


@router.put("/profile")
def update_profile(
    payload: OwnerProfileRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    session = _session(_token_from_request(token, authorization), store)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна")
    profile = OwnerProfileService(store).save(session.login, name=payload.name, about=payload.about)
    return profile.model_dump(mode="json")


@router.post("/unlock-pin")
def set_unlock_pin(
    payload: UnlockPinRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    session = _session(_token_from_request(token, authorization), store)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна")
    if len(payload.pin) != 4 or not payload.pin.isdigit():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="PIN должен содержать ровно 4 цифры")
    global _UNLOCK_PIN
    with _SESSIONS_LOCK:
        _UNLOCK_PIN = payload.pin
    now = datetime.now(UTC)
    store.upsert_app_setting(AppSetting(
        setting_key=UNLOCK_PIN_SETTING_KEY,
        setting_value={"pin": payload.pin},
        metadata={"scope": "owner", "kind": "unlock_pin"},
        created_at=now,
        updated_at=now,
    ))
    return {"configured": True}


@router.post("/lock")
def lock_session(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    session = _session(_token_from_request(token, authorization), store)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна")
    with _SESSIONS_LOCK:
        session.locked = True
        session.locked_at = time()
    return {"locked": True}


@router.post("/unlock")
def unlock_session(
    payload: UnlockRequest,
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    session = _session(_token_from_request(token, authorization), store)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна")
    unlock_pin = _current_unlock_pin(store)
    if unlock_pin is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="PIN разблокировки не настроен. Создайте его в профиле.")
    if not compare_digest(payload.pin, unlock_pin):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный PIN")
    with _SESSIONS_LOCK:
        session.locked = False
        session.locked_at = None
        session.last_activity_at = time()
    return {"locked": False}


@router.post("/logout")
def logout_session(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    resolved = _token_from_request(token, authorization)
    with _SESSIONS_LOCK:
        _SESSIONS.pop(resolved, None)
    if resolved:
        _revoke_session(store, resolved)
    return {"logged_out": True}
