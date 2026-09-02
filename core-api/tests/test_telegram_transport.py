from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.telegram_transport import TelegramTransport, split_telegram_text


def test_long_messages_are_split_at_telegram_limit():
    assert split_telegram_text("x" * 9000, limit=4096) == ["x" * 4096, "x" * 4096, "x" * 808]


def test_unlinked_chat_is_not_sent_to_ai_application():
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True, "result": []}

    async def execute():
        transport = TelegramTransport(object(), token="secret")
        client = SimpleNamespace(post=AsyncMock(return_value=FakeResponse()))
        with patch("app.core.telegram_transport.AIConversationService") as service_class:
            service_class.return_value.get_telegram_identity.return_value = None
            await transport._process_update(client, {
                "update_id": 1,
                "message": {
                    "chat": {"id": 10},
                    "from": {"id": 20},
                    "text": "Кто больше всех продал?",
                },
            })
            assert service_class.return_value.get_telegram_identity.called
            assert not client.post.await_args_list[1:]  # no AI request/send after the access check

    asyncio.run(execute())


def test_duplicate_update_is_processed_once():
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True, "result": []}

    async def execute():
        transport = TelegramTransport(object(), token="secret")
        client = SimpleNamespace(post=AsyncMock(return_value=FakeResponse()))
        with patch("app.core.telegram_transport.AIConversationService") as service_class:
            service_class.return_value.get_telegram_identity.return_value = None
            update = {
                "update_id": 2,
                "message": {"chat": {"id": 10}, "from": {"id": 20}, "text": "Привет"},
            }
            await transport._process_update(client, update)
            first_call_count = client.post.await_count
            await transport._process_update(client, update)
            assert client.post.await_count == first_call_count

    asyncio.run(execute())
