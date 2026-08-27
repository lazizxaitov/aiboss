"""Structured owner memory shared by web and Telegram conversations."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.entities import AppSetting

SHARED_MEMORY_KEY_PREFIX = "ai_shared_memory:v1:"
MemorySource = Literal["telegram", "dashboard", "system"]


class SharedMemoryType(StrEnum):
    PROFILE = "PROFILE"
    BUSINESS_FACTS = "BUSINESS_FACTS"
    DECISIONS = "DECISIONS"
    GOALS = "GOALS"
    TEMPORARY_CONTEXT = "TEMPORARY_CONTEXT"


class SharedMemoryItem(BaseModel):
    memory_id: str = Field(default_factory=lambda: str(uuid4()))
    memory_type: SharedMemoryType
    memory_key: str
    content: str
    source: MemorySource
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None


class SharedMemoryState(BaseModel):
    owner_id: str
    items: list[SharedMemoryItem] = Field(default_factory=list)


class SharedMemoryService:
    """Persist only explicit, user-owned memory facts outside conversation history."""

    temporary_ttl = timedelta(days=7)

    def __init__(self, store: CoreDataStore) -> None:
        self.store = store

    def load(self, owner_id: str) -> SharedMemoryState:
        setting = self.store.get_app_setting(self._key(owner_id))
        if setting is None or not isinstance(setting.setting_value, dict):
            return SharedMemoryState(owner_id=owner_id)
        try:
            state = SharedMemoryState.model_validate(setting.setting_value)
        except Exception:  # noqa: BLE001 - corrupt memory must not block chat
            return SharedMemoryState(owner_id=owner_id)
        now = datetime.now(UTC)
        active = [item for item in state.items if item.expires_at is None or item.expires_at > now]
        if len(active) != len(state.items):
            state.items = active
            self._save(state)
        return state

    def remember(self, owner_id: str, text: str, source: MemorySource) -> SharedMemoryItem | None:
        parsed = self._parse_explicit_memory(text, source)
        if parsed is None:
            return None
        state = self.load(owner_id)
        now = datetime.now(UTC)
        existing = next(
            (item for item in state.items if item.memory_type == parsed.memory_type and item.memory_key == parsed.memory_key),
            None,
        )
        if existing is not None:
            if existing.content == parsed.content and existing.source == parsed.source:
                return existing
            existing.content = parsed.content
            existing.source = parsed.source
            existing.updated_at = now
            existing.expires_at = parsed.expires_at
            self._save(state)
            return existing
        state.items.append(parsed)
        self._save(state)
        return parsed

    def prompt_context(self, owner_id: str) -> str:
        items = self.load(owner_id).items
        if not items:
            return "SHARED OWNER MEMORY:\nNo saved memory is available."
        lines = ["SHARED OWNER MEMORY:"]
        for item in items:
            lines.append(f"[{item.memory_type.value}] {item.memory_key}: {item.content}")
        return "\n".join(lines)

    def _save(self, state: SharedMemoryState) -> None:
        now = datetime.now(UTC)
        self.store.upsert_app_setting(
            AppSetting(
                setting_key=self._key(state.owner_id),
                setting_value=state.model_dump(mode="json"),
                metadata={"scope": "owner", "kind": "ai_shared_memory", "owner_id": state.owner_id},
                created_at=min((item.created_at for item in state.items), default=now),
                updated_at=now,
            ),
        )

    @staticmethod
    def _key(owner_id: str) -> str:
        return f"{SHARED_MEMORY_KEY_PREFIX}{owner_id}"

    def _parse_explicit_memory(self, text: str, source: MemorySource) -> SharedMemoryItem | None:
        normalized = text.strip()
        lowered = normalized.casefold()
        if not normalized or not any(
            marker in lowered for marker in ("запомни", "сохрани", "это важно", "наша главная организация", "мы решили")
        ):
            return None
        if re.search(r"(парол|токен|api[- ]?key|секрет|credential|bearer|chat[_ -]?id|/tmp/|/var/)", lowered):
            return None

        memory_type = SharedMemoryType.TEMPORARY_CONTEXT
        memory_key = "current_topic"
        if any(word in lowered for word in ("меня зовут", "имя", "язык", "общаться", "предпочтен", "стиль")):
            memory_type, memory_key = SharedMemoryType.PROFILE, "user_preferences"
        elif any(word in lowered for word in ("главная организация", "организация", "продукт", "структур", "правил", "ограничен", "бизнес-факт")):
            memory_type, memory_key = SharedMemoryType.BUSINESS_FACTS, "business_facts"
        elif any(word in lowered for word in ("мы решили", "решили", "отменили", "решение")):
            memory_type, memory_key = SharedMemoryType.DECISIONS, "current_decisions"
        elif any(word in lowered for word in ("цель", "kpi", "задач", "приоритет")):
            memory_type, memory_key = SharedMemoryType.GOALS, "current_goals"

        content = re.sub(r"^(запомни|сохрани|это важно)[: ,\-]*", "", normalized, flags=re.IGNORECASE).strip()
        if not content:
            return None
        now = datetime.now(UTC)
        expires_at = now + self.temporary_ttl if memory_type == SharedMemoryType.TEMPORARY_CONTEXT else None
        return SharedMemoryItem(
            memory_type=memory_type,
            memory_key=memory_key,
            content=content[:1000],
            source=source,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )
