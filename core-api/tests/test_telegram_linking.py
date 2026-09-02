from datetime import UTC, datetime, timedelta

from app.core.ai_conversation import AIConversationChannel, AIConversationService
from app.core.data_layer.service import InMemoryCoreDataLayer
from app.core.telegram_link import TelegramLinkService


def test_link_token_is_single_use_and_binds_server_identity():
    store = InMemoryCoreDataLayer()
    links = TelegramLinkService(store)
    token = links.create("owner")['token']

    assert links.consume(token, "telegram-chat") == "owner"
    assert links.consume(token, "other-chat") is None

    conversation = AIConversationService(store).resolve_or_create_conversation(
        source_channel=AIConversationChannel.TELEGRAM,
        user_id="owner",
        telegram_chat_id="telegram-chat",
    )
    assert conversation.user_id == "owner"


def test_expired_link_token_is_rejected():
    store = InMemoryCoreDataLayer()
    links = TelegramLinkService(store)
    records = links._records()
    records[links._hash("expired")] = {
        "identity": "owner",
        "expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        "used": False,
    }
    links._save(records)

    assert links.consume("expired", "telegram-chat") is None
