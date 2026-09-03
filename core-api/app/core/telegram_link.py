"""Single-use Telegram account linking tokens."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any

from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.entities import AppSetting

TELEGRAM_LINK_SETTING_KEY = "telegram:link_tokens:v1"
TELEGRAM_LINK_TTL_SECONDS = 600
_LINK_LOCK = Lock()


class TelegramLinkService:
    def __init__(self, store: CoreDataStore) -> None:
        self.store = store

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _records(self) -> dict[str, dict[str, Any]]:
        setting = self.store.get_app_setting(TELEGRAM_LINK_SETTING_KEY)
        value = setting.setting_value if setting else {}
        return dict(value.get("tokens", {})) if isinstance(value, dict) and isinstance(value.get("tokens"), dict) else {}

    def _save(self, records: dict[str, dict[str, Any]]) -> None:
        now = datetime.now(UTC)
        self.store.upsert_app_setting(AppSetting(
            setting_key=TELEGRAM_LINK_SETTING_KEY,
            setting_value={"tokens": records},
            metadata={"scope": "owner", "kind": "telegram_link_tokens"},
            created_at=now,
            updated_at=now,
        ))

    def create(self, identity: str, *, bot_username: str | None = None) -> dict[str, Any]:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=TELEGRAM_LINK_TTL_SECONDS)
        with _LINK_LOCK:
            records = self._records()
            records[self._hash(token)] = {"identity": identity, "expires_at": expires_at.isoformat(), "used": False}
            self._save(records)
        result: dict[str, Any] = {"expires_at": expires_at.isoformat(), "token": token}
        if bot_username:
            result["deep_link"] = f"https://t.me/{bot_username.lstrip('@')}?start={token}"
        return result

    def consume(self, token: str, telegram_chat_id: str) -> str | None:
        if not token or len(token) > 128:
            return None
        with _LINK_LOCK:
            records = self._records()
            key = self._hash(token)
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
            record["telegram_chat_id"] = str(telegram_chat_id)
            self._save(records)
            return identity

    def status(self, identity: str) -> dict[str, Any]:
        from app.core.ai_conversation import AIConversationService

        users = AIConversationService(self.store).telegram_profiles_for_identity(identity)
        return {
            "connected": bool(users),
            "chats": [f"…{user['chat_id'][-4:]}" for user in users],
            "users": users,
        }
