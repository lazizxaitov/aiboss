"""Single-use QR pairing for adding a new mobile/web device, plus the
registry of already-paired devices shown in Settings.

Mirrors app/core/telegram_link.py's short-lived token pattern: a token is
created from an authenticated session (Settings → "Мобильные устройства" →
"Добавить устройство"), rendered as a QR code, and consumed exactly once by
whoever scans it and proves they know the owner login/password.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any

from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.entities import AppSetting

DEVICE_LINK_SETTING_KEY = "device:link_tokens:v1"
DEVICE_LINK_TTL_SECONDS = 300
DEVICE_REGISTRY_SETTING_KEY = "device:registry:v1"
_LOCK = Lock()


def hash_token(token: str) -> str:
    """Same hash auth.py uses for its revoked-session list, so a device's
    registry entry and its session-revocation entry are the same value —
    revoking a device never needs the raw session token again."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class DeviceLinkService:
    def __init__(self, store: CoreDataStore) -> None:
        self.store = store

    # --- one-time pairing tokens (the QR code) ---

    def _records(self) -> dict[str, dict[str, Any]]:
        setting = self.store.get_app_setting(DEVICE_LINK_SETTING_KEY)
        value = setting.setting_value if setting else {}
        return dict(value.get("tokens", {})) if isinstance(value, dict) and isinstance(value.get("tokens"), dict) else {}

    def _save(self, records: dict[str, dict[str, Any]]) -> None:
        now = datetime.now(UTC)
        self.store.upsert_app_setting(AppSetting(
            setting_key=DEVICE_LINK_SETTING_KEY,
            setting_value={"tokens": records},
            metadata={"scope": "owner", "kind": "device_link_tokens"},
            created_at=now,
            updated_at=now,
        ))

    def create(self, identity: str) -> dict[str, Any]:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=DEVICE_LINK_TTL_SECONDS)
        with _LOCK:
            records = self._records()
            records[hash_token(token)] = {"identity": identity, "expires_at": expires_at.isoformat(), "used": False}
            self._save(records)
        return {"token": token, "expires_at": expires_at.isoformat()}

    def consume(self, token: str) -> str | None:
        if not token or len(token) > 128:
            return None
        with _LOCK:
            records = self._records()
            key = hash_token(token)
            record = records.get(key)
            if not isinstance(record, dict) or record.get("used"):
                return None
            try:
                expires_at = datetime.fromisoformat(str(record.get("expires_at"))).astimezone(UTC)
            except (TypeError, ValueError):
                return None
            if expires_at <= datetime.now(UTC):
                records.pop(key, None)
                self._save(records)
                return None
            identity = record.get("identity")
            if not isinstance(identity, str) or not identity:
                return None
            record["used"] = True
            self._save(records)
            return identity

    # --- registry of paired devices, for the Settings list + revoke ---

    def _registry(self) -> dict[str, dict[str, Any]]:
        setting = self.store.get_app_setting(DEVICE_REGISTRY_SETTING_KEY)
        value = setting.setting_value if setting else {}
        return dict(value.get("devices", {})) if isinstance(value, dict) and isinstance(value.get("devices"), dict) else {}

    def _save_registry(self, devices: dict[str, dict[str, Any]]) -> None:
        now = datetime.now(UTC)
        self.store.upsert_app_setting(AppSetting(
            setting_key=DEVICE_REGISTRY_SETTING_KEY,
            setting_value={"devices": devices},
            metadata={"scope": "owner", "kind": "device_registry"},
            created_at=now,
            updated_at=now,
        ))

    def register_device(self, *, access_token: str, label: str, user_agent: str) -> str:
        device_id = hash_token(access_token)
        with _LOCK:
            devices = self._registry()
            devices[device_id] = {
                "label": label[:80],
                "user_agent": user_agent[:200],
                "linked_at": datetime.now(UTC).isoformat(),
            }
            self._save_registry(devices)
        return device_id

    def list_devices(self) -> list[dict[str, Any]]:
        devices = self._registry()
        items = [{"device_id": device_id, **info} for device_id, info in devices.items()]
        items.sort(key=lambda item: item.get("linked_at") or "")
        return items

    def forget_device(self, device_id: str) -> bool:
        with _LOCK:
            devices = self._registry()
            if device_id not in devices:
                return False
            devices.pop(device_id, None)
            self._save_registry(devices)
        return True
