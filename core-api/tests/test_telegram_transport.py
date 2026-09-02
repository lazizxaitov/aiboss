from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.api.routes.telegram_ai import TelegramChatResponse
from app.core.ai_media import AITranscription
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


def test_voice_is_downloaded_transcribed_and_sent_to_shared_agent():
    async def execute():
        transport = TelegramTransport(object(), token="secret", transcriber=AsyncMock())
        transport.transcriber.transcribe.return_value = AITranscription("Кто больше продал?", "speech", "speech-model")
        download_response = SimpleNamespace(raise_for_status=lambda: None, content=b"ogg audio")
        async def post(url, **kwargs):
            if url.endswith("/getFile"):
                return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"ok": True, "result": {"file_path": "voice/file.ogg"}})
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"ok": True, "result": None})
        client = SimpleNamespace(
            post=AsyncMock(side_effect=post),
            get=AsyncMock(return_value=download_response),
        )
        with patch("app.core.telegram_transport.AIConversationService") as service_class, patch(
            "app.core.telegram_transport.handle_telegram_chat",
            new=AsyncMock(return_value=TelegramChatResponse(
                conversation_id="conversation-1", assistant_message="Ответ", telegram_message="Ответ",
            )),
        ) as agent:
            service_class.return_value.get_telegram_identity.return_value = "owner"
            await transport._process_update(client, {
                "update_id": 3,
                "message": {"chat": {"id": 10}, "from": {"id": 20}, "voice": {"file_id": "voice-1", "mime_type": "audio/ogg"}},
            })
            request = agent.await_args.args[0]
            assert request.message == "Кто больше продал?"
            assert request.attachments[0]["kind"] == "voice"
            transport.transcriber.transcribe.assert_awaited_once()

    asyncio.run(execute())


def test_photo_is_attached_without_a_telegram_specific_agent():
    async def execute():
        transport = TelegramTransport(object(), token="secret")
        async def post(url, **kwargs):
            if url.endswith("/getFile"):
                return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"ok": True, "result": {"file_path": "photos/image.jpg"}})
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"ok": True, "result": None})
        client = SimpleNamespace(
            post=AsyncMock(side_effect=post),
            get=AsyncMock(return_value=SimpleNamespace(raise_for_status=lambda: None, content=b"jpeg")),
        )
        with patch("app.core.telegram_transport.AIConversationService") as service_class, patch(
            "app.core.telegram_transport.handle_telegram_chat",
            new=AsyncMock(return_value=TelegramChatResponse(
                conversation_id="conversation-2", assistant_message="Ответ", telegram_message="Ответ",
            )),
        ) as agent:
            service_class.return_value.get_telegram_identity.return_value = "owner"
            await transport._process_update(client, {
                "update_id": 4,
                "message": {"chat": {"id": 10}, "from": {"id": 20}, "photo": [
                    {"file_id": "small", "width": 10, "height": 10},
                    {"file_id": "large", "width": 100, "height": 100},
                ]},
            })
            request = agent.await_args.args[0]
            assert request.attachments[0]["telegram_file_id"] == "large"
            assert request.attachments[0]["kind"] == "photo"
            assert not hasattr(transport, "hermes_agent")

    asyncio.run(execute())


def test_outbound_artifact_is_restricted_to_media_directory(tmp_path):
    async def execute():
        artifact_path = tmp_path / "report.pdf"
        artifact_path.write_bytes(b"pdf")
        transport = TelegramTransport(object(), token="secret", media_dir=tmp_path)
        response = SimpleNamespace(raise_for_status=lambda: None)
        client = SimpleNamespace(post=AsyncMock(return_value=response))
        await transport._send_artifact(client, "10", {
            "method": "sendDocument", "path": str(artifact_path), "filename": "report.pdf",
        })
        assert client.post.await_count == 1
        assert client.post.await_args.args[0].endswith("/sendDocument")

    asyncio.run(execute())
