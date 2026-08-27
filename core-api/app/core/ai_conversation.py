"""Shared AI conversation state for web and Telegram channels."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.entities import AppSetting
from app.core.organization_context import OrganizationContextService
from app.core.owner_profile import OwnerProfileService

AI_CONVERSATION_INDEX_KEY = "ai_conversations:index:v1"
AI_CONVERSATION_KEY_PREFIX = "ai_conversations:conversation:v1:"


class AIConversationChannel(StrEnum):
    """Supported source channels."""

    WEB = "web"
    TELEGRAM = "telegram"


class AIConversationTargetChannel(StrEnum):
    """Hermes target channel hints."""

    REPLY_WEB = "reply_web"
    REPLY_TELEGRAM = "reply_telegram"
    REPLY_BOTH = "reply_both"


class AIConversationMessage(BaseModel):
    """A single message in a shared AI conversation."""

    message_id: str = Field(default_factory=lambda: str(uuid4()))
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]]
    source_channel: AIConversationChannel
    target_channel: AIConversationTargetChannel | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class AIConversationState(BaseModel):
    """Persisted conversation state shared across channels."""

    conversation_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str | None = None
    organization_id: UUID | None = None
    period: str | None = None
    messages: list[AIConversationMessage] = Field(default_factory=list)
    resolved_entities: list[dict[str, str]] = Field(default_factory=list)
    source_channel: AIConversationChannel = AIConversationChannel.WEB
    target_channel: AIConversationTargetChannel | None = None
    telegram_chat_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AIConversationIndex(BaseModel):
    """Lookup index for shared conversations."""

    active_by_identity: dict[str, str] = Field(default_factory=dict)
    telegram_chat_to_identity: dict[str, str] = Field(default_factory=dict)


@dataclass(slots=True)
class AIConversationService:
    """Persist and resolve shared AI conversation state."""

    store: CoreDataStore

    def get_index(self) -> AIConversationIndex:
        setting = self.store.get_app_setting(AI_CONVERSATION_INDEX_KEY)
        if setting is None:
            return AIConversationIndex()
        return self._deserialize_index(setting)

    def save_index(self, index: AIConversationIndex) -> AIConversationIndex:
        now = datetime.now(UTC)
        self.store.upsert_app_setting(
            AppSetting(
                setting_key=AI_CONVERSATION_INDEX_KEY,
                setting_value=index.model_dump(mode="json"),
                metadata={"scope": "global", "kind": "ai_conversation_index"},
                created_at=now,
                updated_at=now,
            ),
        )
        return index

    def get_conversation(self, conversation_id: str) -> AIConversationState | None:
        setting = self.store.get_app_setting(self._conversation_key(conversation_id))
        if setting is None:
            return None
        return self._deserialize_state(setting)

    def save_conversation(self, conversation: AIConversationState) -> AIConversationState:
        normalized = conversation.model_copy(update={"updated_at": datetime.now(UTC)})
        if normalized.created_at > normalized.updated_at:
            normalized.created_at = normalized.updated_at
        now = normalized.updated_at
        self.store.upsert_app_setting(
            AppSetting(
                setting_key=self._conversation_key(normalized.conversation_id),
                setting_value=normalized.model_dump(mode="json"),
                metadata={
                    "scope": "global",
                    "kind": "ai_conversation",
                    "conversation_id": normalized.conversation_id,
                    "user_id": normalized.user_id,
                },
                created_at=normalized.created_at,
                updated_at=now,
            ),
        )
        return normalized

    def link_telegram_chat(self, telegram_chat_id: str, identity: str) -> AIConversationIndex:
        index = self.get_index()
        index.telegram_chat_to_identity[str(telegram_chat_id)] = identity
        return self.save_index(index)

    def resolve_identity(
        self,
        *,
        user_id: str | None = None,
        telegram_chat_id: str | None = None,
        organization_id: UUID | None = None,
        period: str | None = None,
    ) -> str:
        index = self.get_index()
        if telegram_chat_id:
            mapped_identity = index.telegram_chat_to_identity.get(str(telegram_chat_id))
            if mapped_identity:
                return mapped_identity
        if user_id:
            return user_id
        context = OrganizationContextService(self.store).get_context()
        organization_value = organization_id or self._context_organization_id(context)
        period_value = period or self._context_period_value(context)
        if organization_value is None:
            return f"context:all:{period_value}"
        return f"context:{organization_value}:{period_value}"

    def resolve_or_create_conversation(
        self,
        *,
        source_channel: AIConversationChannel,
        user_id: str | None = None,
        telegram_chat_id: str | None = None,
        organization_id: UUID | None = None,
        period: str | None = None,
        conversation_id: str | None = None,
    ) -> AIConversationState:
        if conversation_id:
            existing = self.get_conversation(conversation_id)
            if existing is not None:
                return self._update_context(
                    existing,
                    source_channel=source_channel,
                    telegram_chat_id=telegram_chat_id,
                    organization_id=organization_id,
                    period=period,
                    user_id=user_id,
                )
        identity = self.resolve_identity(
            user_id=user_id,
            telegram_chat_id=telegram_chat_id,
            organization_id=organization_id,
            period=period,
        )
        index = self.get_index()
        channel_identity = f"{source_channel.value}:{identity}"
        # An explicit new ID is authoritative. Never fall back to the identity's
        # active conversation, otherwise a new web chat can inherit old history.
        if conversation_id is None:
            conversation_id = index.active_by_identity.get(channel_identity)
            if conversation_id:
                conversation = self.get_conversation(conversation_id)
                if conversation is not None:
                    return self._update_context(
                        conversation,
                        source_channel=source_channel,
                        telegram_chat_id=telegram_chat_id,
                        organization_id=organization_id,
                        period=period,
                        user_id=user_id,
                    )

        context = OrganizationContextService(self.store).get_context()
        resolved_organization_id = organization_id or self._context_organization_id(context)
        resolved_period = period or self._context_period_value(context)
        conversation = AIConversationState(
            conversation_id=conversation_id or str(uuid4()),
            user_id=user_id or identity,
            organization_id=resolved_organization_id,
            period=resolved_period,
            source_channel=source_channel,
            telegram_chat_id=telegram_chat_id,
        )
        index.active_by_identity[channel_identity] = conversation.conversation_id
        if telegram_chat_id:
            index.telegram_chat_to_identity[str(telegram_chat_id)] = identity
        self.save_index(index)
        return self.save_conversation(conversation)

    def sync_incoming_messages(
        self,
        conversation: AIConversationState,
        messages: list[dict[str, Any]],
        *,
        source_channel: AIConversationChannel,
        target_channel: AIConversationTargetChannel | None = None,
    ) -> AIConversationState:
        incoming = [message for message in messages if message.get("role") != "system"]
        existing_count = len(conversation.messages)
        if existing_count < len(incoming):
            for message in incoming[existing_count:]:
                role = message.get("role")
                content = message.get("content")
                if role not in {"user", "assistant", "tool"}:
                    continue
                conversation.messages.append(
                    AIConversationMessage(
                        role=role,
                        content=content if isinstance(content, str) or isinstance(content, list) else str(content),
                        source_channel=source_channel,
                        target_channel=target_channel,
                    ),
                )
        conversation.source_channel = source_channel
        conversation.target_channel = target_channel or conversation.target_channel
        conversation.updated_at = datetime.now(UTC)
        return self.save_conversation(conversation)

    def append_message(
        self,
        conversation: AIConversationState,
        *,
        role: Literal["system", "user", "assistant", "tool"],
        content: str | list[dict[str, Any]],
        source_channel: AIConversationChannel,
        target_channel: AIConversationTargetChannel | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AIConversationState:
        conversation.messages.append(
            AIConversationMessage(
                role=role,
                content=content,
                source_channel=source_channel,
                target_channel=target_channel,
                metadata=metadata or {},
            ),
        )
        conversation.source_channel = source_channel
        conversation.target_channel = target_channel or conversation.target_channel
        conversation.updated_at = datetime.now(UTC)
        return self.save_conversation(conversation)

    def update_context(
        self,
        conversation: AIConversationState,
        *,
        organization_id: UUID | None = None,
        period: str | None = None,
        source_channel: AIConversationChannel | None = None,
        telegram_chat_id: str | None = None,
        user_id: str | None = None,
    ) -> AIConversationState:
        if organization_id is not None:
            conversation.organization_id = organization_id
        if period is not None:
            conversation.period = period
        if source_channel is not None:
            conversation.source_channel = source_channel
        if telegram_chat_id is not None:
            conversation.telegram_chat_id = telegram_chat_id
        if user_id is not None:
            conversation.user_id = user_id
        conversation.updated_at = datetime.now(UTC)
        return self.save_conversation(conversation)

    def build_system_prompt(self, conversation: AIConversationState) -> str:
        context_service = OrganizationContextService(self.store)
        context = context_service.get_context()
        organization_ids = [str(item) for item in context.organization_context.organization_ids]
        organization_text = ", ".join(organization_ids) if organization_ids else "all"
        period_text = context.period_context.preset.value
        if context.period_context.date_from and context.period_context.date_to:
            period_text = (
                f"{period_text} ({context.period_context.date_from.isoformat()}.."
                f"{context.period_context.date_to.isoformat()})"
            )
        profile_context = self._owner_profile_context(conversation.user_id or "owner")
        entity_context = ""
        if conversation.resolved_entities:
            entity_context = (
                "Resolved business entities from this conversation (reuse their IDs for follow-up requests): "
                + ", ".join(
                    f"{item.get('type')}={item.get('id')} ({item.get('display_name')})"
                    for item in conversation.resolved_entities[-10:]
                )
                + ".\n"
            )
        return (
            "Ты AI-ассистент AI Business OS.\n"
            "Работай только с текущим диалогом пользователя и доступными данными AI Business OS.\n"
            "Не продолжай темы из других чатов или каналов. Не упоминай Telegram, файлы или другие сессии, если пользователь сам не спрашивает о них.\n"
            "Use ONLY the provided business data tools when the user asks about revenue, orders, sales, top products, "
            "business comparisons, organizations, current attention, or dashboard actions.\n"
            "For a named business entity, first use search_entities, then pass the resolved canonical ID to the next data tool. "
            "If search returns multiple matches, ask the user to choose and do not guess. Reuse resolved entity context for pronouns in follow-up questions.\n"
            "Do not request or reveal SQL, PostgreSQL, raw SmartUp payloads, terminal/file/system access, or secrets.\n"
            "If the user does not specify organization or period, rely on the current AI Business OS context.\n"
            "If the user explicitly asks to answer in the web chat or Telegram, respect that delivery target.\n"
            "Use the same Hermes tools regardless of whether the message came from web or Telegram.\n"
            "If the user asks for a file or a document, return it as a fenced code block in the form "
            "```file name=\"report.txt\" type=\"text/plain\"\n<content>\n``` so the UI can offer a download.\n"
            "Answer in the user's language and keep the answer grounded in tool results.\n"
            f"Current organization context: {organization_text}.\n"
            f"Current period context: {period_text}.\n"
            f"{profile_context}"
            f"{entity_context}"
            f"Conversation id: {conversation.conversation_id}."
        )

    def remember_entities(self, conversation: AIConversationState, entities: list[dict[str, str]]) -> AIConversationState:
        """Persist only safe type/id/display-name resolution context for follow-ups."""
        existing = {(item.get("type"), item.get("id")): item for item in conversation.resolved_entities}
        for entity in entities:
            entity_type = str(entity.get("type") or "")
            entity_id = str(entity.get("id") or "")
            display_name = str(entity.get("display_name") or "")
            if entity_type and entity_id and display_name:
                existing[(entity_type, entity_id)] = {
                    "type": entity_type,
                    "id": entity_id,
                    "display_name": display_name,
                }
        conversation.resolved_entities = list(existing.values())[-20:]
        return self.save_conversation(conversation)

    def _owner_profile_context(self, owner_id: str) -> str:
        profile = OwnerProfileService(self.store).load(owner_id)
        parts: list[str] = []
        if profile.name:
            parts.append(f"Owner name: {profile.name}")
        if profile.about:
            parts.append(f"Owner preferences and background: {profile.about}")
        return ("Owner profile context: " + " | ".join(parts) + ".\n") if parts else ""

    def build_hermes_messages(
        self,
        conversation: AIConversationState,
        current_user_message: str | list[dict[str, Any]],
        *,
        source_channel: AIConversationChannel,
        target_channel: AIConversationTargetChannel | None = None,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.build_system_prompt(conversation)}]
        for message in conversation.messages:
            messages.append(
                {
                    "role": message.role,
                    "content": message.content,
                },
            )
        messages.append(
            {
                "role": "user",
                "content": current_user_message,
                "metadata": {
                    "source_channel": source_channel.value,
                    "target_channel": target_channel.value if target_channel else None,
                },
            },
        )
        return messages

    def infer_target_channel(self, text: str | None) -> AIConversationTargetChannel | None:
        if not text:
            return None
        normalized = text.lower()
        if "reply_both" in normalized or "и в веб, и в telegram" in normalized or "и в телеграм, и в веб" in normalized:
            return AIConversationTargetChannel.REPLY_BOTH
        if "ответь в веб-чате" in normalized or "в веб-чате" in normalized or "в веб чате" in normalized:
            return AIConversationTargetChannel.REPLY_WEB
        if "отправь это в telegram" in normalized or "отправь в telegram" in normalized or "в telegram" in normalized or "в телеграм" in normalized:
            return AIConversationTargetChannel.REPLY_TELEGRAM
        return None

    def conversation_history(self, conversation: AIConversationState) -> list[dict[str, Any]]:
        return [
            {
                "message_id": message.message_id,
                "role": message.role,
                "content": message.content,
                "source_channel": message.source_channel.value,
                "target_channel": message.target_channel.value if message.target_channel else None,
                "created_at": message.created_at.isoformat(),
                "metadata": message.metadata,
            }
            for message in conversation.messages
        ]

    def _conversation_key(self, conversation_id: str) -> str:
        return f"{AI_CONVERSATION_KEY_PREFIX}{conversation_id}"

    def _deserialize_index(self, setting: AppSetting) -> AIConversationIndex:
        value = setting.setting_value or {}
        if not isinstance(value, dict):
            return AIConversationIndex()
        try:
            return AIConversationIndex.model_validate(value)
        except Exception:  # noqa: BLE001 - keep safe defaults for corrupt settings
            return AIConversationIndex()

    def _deserialize_state(self, setting: AppSetting) -> AIConversationState:
        value = setting.setting_value or {}
        if not isinstance(value, dict):
            return AIConversationState()
        try:
            return AIConversationState.model_validate(value)
        except Exception:  # noqa: BLE001 - keep safe defaults for corrupt settings
            return AIConversationState()

    def _context_organization_id(self, context) -> UUID | None:
        organization_ids = list(context.organization_context.organization_ids)
        return organization_ids[0] if len(organization_ids) == 1 else None

    def _context_period_value(self, context) -> str:
        period = context.period_context.preset.value
        if context.period_context.date_from and context.period_context.date_to:
            return (
                f"{period}:{context.period_context.date_from.isoformat()}.."
                f"{context.period_context.date_to.isoformat()}"
            )
        return period

    def _update_context(
        self,
        conversation: AIConversationState,
        *,
        source_channel: AIConversationChannel,
        telegram_chat_id: str | None = None,
        organization_id: UUID | None = None,
        period: str | None = None,
        user_id: str | None = None,
    ) -> AIConversationState:
        return self.update_context(
            conversation,
            source_channel=source_channel,
            telegram_chat_id=telegram_chat_id,
            organization_id=organization_id,
            period=period,
            user_id=user_id,
        )
