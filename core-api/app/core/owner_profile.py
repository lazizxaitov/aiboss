"""Persistent owner profile used as AI context."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.entities import AppSetting

OWNER_PROFILE_KEY_PREFIX = "owner_profile:v1:"


class OwnerProfile(BaseModel):
    name: str = Field(default="", max_length=200)
    about: str = Field(default="", max_length=5000)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OwnerProfileService:
    def __init__(self, store: CoreDataStore) -> None:
        self.store = store

    def load(self, owner_id: str) -> OwnerProfile:
        setting = self.store.get_app_setting(self._key(owner_id))
        if setting is None or not isinstance(setting.setting_value, dict):
            return OwnerProfile()
        try:
            return OwnerProfile.model_validate(setting.setting_value)
        except Exception:  # noqa: BLE001 - invalid profile must not block AI
            return OwnerProfile()

    def save(self, owner_id: str, *, name: str, about: str) -> OwnerProfile:
        profile = OwnerProfile(name=name.strip(), about=about.strip(), updated_at=datetime.now(UTC))
        now = datetime.now(UTC)
        self.store.upsert_app_setting(AppSetting(
            setting_key=self._key(owner_id),
            setting_value=profile.model_dump(mode="json"),
            metadata={"scope": "owner", "kind": "owner_profile", "owner_id": owner_id},
            created_at=now,
            updated_at=now,
        ))
        return profile

    @staticmethod
    def _key(owner_id: str) -> str:
        return f"{OWNER_PROFILE_KEY_PREFIX}{owner_id}"
