"""Telegram Bot API transport for the shared AI Business OS application layer."""

from __future__ import annotations

import asyncio
import fcntl
import logging
from collections import deque
from pathlib import Path
from time import monotonic
from typing import Any

import httpx

from app.api.routes.telegram_ai import (
    TelegramChatRequest,
    TelegramChatResponse,
    handle_telegram_chat,
)
from app.core.ai_conversation import AIConversationService
from app.core.config import settings
from app.core.data_layer.contracts import CoreDataStore

logger = logging.getLogger(__name__)

TELEGRAM_MAX_MESSAGE_LENGTH = 4096
TELEGRAM_LOCK_PATH = Path("/tmp/aiboss-telegram-transport.lock")


class TelegramTransport:
    """Single-process long poller that delegates every message to AI Business OS."""

    def __init__(
        self,
        store: CoreDataStore,
        *,
        token: str,
        poll_timeout_seconds: int = 25,
        request_timeout_seconds: float = 35.0,
    ) -> None:
        self.store = store
        self.token = token
        self.poll_timeout_seconds = max(1, poll_timeout_seconds)
        self.request_timeout_seconds = max(5.0, request_timeout_seconds)
        self._stop = asyncio.Event()
        self._offset: int | None = None
        self._processed: deque[int] = deque(maxlen=2048)
        self._processed_set: set[int] = set()
        self._lock_file = None

    @property
    def api_url(self) -> str:
        return f"https://api.telegram.org/bot{self.token}"

    def stop(self) -> None:
        self._stop.set()

    def _acquire_process_lock(self) -> bool:
        self._lock_file = TELEGRAM_LOCK_PATH.open("a+")
        try:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._lock_file.close()
            self._lock_file = None
            return False
        return True

    def _release_process_lock(self) -> None:
        if self._lock_file is None:
            return
        try:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            self._lock_file.close()
            self._lock_file = None

    async def _call(self, client: httpx.AsyncClient, method: str, payload: dict[str, Any]) -> Any:
        response = await client.post(
            f"{self.api_url}/{method}",
            json=payload,
            timeout=self.request_timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram API {method} failed")
        return body.get("result")

    async def _send_text(
        self,
        client: httpx.AsyncClient,
        chat_id: str,
        text: str,
        options: list[dict[str, str]] | None = None,
    ) -> None:
        chunks = split_telegram_text(text)
        keyboard = (
            {
                "inline_keyboard": [[
                    {"text": item["label"], "callback_data": item["command"]}
                    for item in options
                ]],
            }
            if options
            else None
        )
        for index, chunk in enumerate(chunks):
            payload: dict[str, Any] = {"chat_id": chat_id, "text": chunk}
            if keyboard is not None and index == len(chunks) - 1:
                payload["reply_markup"] = keyboard
            try:
                await self._call(client, "sendMessage", payload)
            except Exception:
                if "reply_markup" not in payload:
                    raise
                payload.pop("reply_markup", None)
                await self._call(client, "sendMessage", payload)
        logger.info("TELEGRAM_SEND_SUCCESS telegram_chat_id=%s chunks=%s", chat_id, len(chunks))

    async def _typing_loop(self, client: httpx.AsyncClient, chat_id: str) -> None:
        while not self._stop.is_set():
            try:
                await self._call(
                    client,
                    "sendChatAction",
                    {"chat_id": chat_id, "action": "typing"},
                )
            except Exception as error:  # noqa: BLE001 - typing must never block the answer
                logger.info("TELEGRAM_TRANSPORT_ERROR stage=typing error_type=%s", type(error).__name__)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=4.0)
            except TimeoutError:
                continue

    def _already_processed(self, update_id: int) -> bool:
        return update_id in self._processed_set

    def _mark_processed(self, update_id: int) -> None:
        if len(self._processed) == self._processed.maxlen:
            self._processed_set.discard(self._processed[0])
        self._processed.append(update_id)
        self._processed_set.add(update_id)

    async def _process_update(self, client: httpx.AsyncClient, update: dict[str, Any]) -> None:
        update_id = update.get("update_id")
        if not isinstance(update_id, int) or self._already_processed(update_id):
            return
        self._mark_processed(update_id)

        message = update.get("message")
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            callback_message = callback.get("message") or {}
            message = callback_message
            text = callback.get("data") if isinstance(callback.get("data"), str) else ""
            callback_id = callback.get("id")
            if isinstance(callback_id, str):
                try:
                    await self._call(
                        client,
                        "answerCallbackQuery",
                        {"callback_query_id": callback_id},
                    )
                except Exception:
                    pass
        else:
            text = message.get("text") if isinstance(message, dict) else ""
        if not isinstance(message, dict) or not isinstance(text, str) or not text.strip():
            return
        chat = message.get("chat")
        sender = message.get("from")
        if not isinstance(chat, dict) or not isinstance(sender, dict):
            return
        chat_id = str(chat.get("id") or "")
        telegram_user_id = str(sender.get("id") or "")
        if not chat_id or not telegram_user_id:
            return
        conversation_service = AIConversationService(self.store)
        linked_identity = conversation_service.get_telegram_identity(chat_id)
        if not linked_identity:
            await self._send_text(
                client,
                chat_id,
                (
                    "Этот Telegram-чат ещё не подключён к AI Business OS. "
                    "Сначала подключите его в настройках системы."
                ),
            )
            return

        logger.info(
            "TELEGRAM_AI_REQUEST update_id=%s telegram_chat_id=%s telegram_user_id=%s",
            update_id,
            chat_id,
            telegram_user_id,
        )
        started = monotonic()
        typing_task = asyncio.create_task(self._typing_loop(client, chat_id))
        try:
            result: TelegramChatResponse = await handle_telegram_chat(
                TelegramChatRequest(
                    telegram_chat_id=chat_id,
                    user_id=linked_identity,
                    message=text.strip(),
                ),
                self.store,
            )
            await self._send_text(
                client,
                chat_id,
                result.telegram_message,
                [option.model_dump() for option in result.options] or None,
            )
            logger.info(
                "TELEGRAM_AI_RESPONSE update_id=%s telegram_chat_id=%s conversation_id=%s "
                "elapsed_ms=%.2f provider_id=%s model_id=%s",
                update_id,
                chat_id,
                result.conversation_id,
                (monotonic() - started) * 1000,
                result.provider_id,
                result.model_id,
            )
        except Exception as error:  # noqa: BLE001 - one update must not stop the poller
            logger.info(
                "TELEGRAM_TRANSPORT_ERROR update_id=%s telegram_chat_id=%s error_type=%s",
                update_id,
                chat_id,
                type(error).__name__,
            )
            try:
                await self._send_text(
                    client,
                    chat_id,
                    "Не удалось обработать запрос. Попробуйте ещё раз позже.",
                )
            except Exception:
                pass
        finally:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

    async def run(self) -> None:
        if not self._acquire_process_lock():
            logger.info("TELEGRAM_TRANSPORT_ERROR stage=lock reason=another_poller_is_running")
            return
        logger.info("TELEGRAM_TRANSPORT_START poll_timeout_seconds=%s", self.poll_timeout_seconds)
        backoff = 1.0
        try:
            async with httpx.AsyncClient() as client:
                while not self._stop.is_set():
                    try:
                        payload: dict[str, Any] = {
                            "timeout": self.poll_timeout_seconds,
                            "allowed_updates": ["message", "callback_query"],
                        }
                        if self._offset is not None:
                            payload["offset"] = self._offset
                        updates = await self._call(client, "getUpdates", payload)
                        backoff = 1.0
                        for update in updates if isinstance(updates, list) else []:
                            if isinstance(update, dict):
                                update_id = update.get("update_id")
                                if isinstance(update_id, int):
                                    self._offset = max(self._offset or update_id, update_id + 1)
                                    logger.info("TELEGRAM_UPDATE_RECEIVED update_id=%s", update_id)
                                await self._process_update(client, update)
                    except asyncio.CancelledError:
                        raise
                    except Exception as error:  # noqa: BLE001 - retry Telegram/network failures
                        logger.info(
                            "TELEGRAM_TRANSPORT_ERROR stage=poll error_type=%s",
                            type(error).__name__,
                        )
                        try:
                            await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                        except TimeoutError:
                            backoff = min(backoff * 2, 30.0)
        finally:
            self._release_process_lock()


def split_telegram_text(text: str, limit: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> list[str]:
    """Split a Telegram answer without exceeding Bot API message limits."""

    normalized = text.strip() or "Ответ не содержит текста."
    return [normalized[index : index + limit] for index in range(0, len(normalized), limit)]


async def run_telegram_transport(store: CoreDataStore) -> None:
    """Run the configured transport; a missing token disables it cleanly."""

    if not settings.telegram_transport_enabled or not settings.telegram_bot_token:
        return
    await TelegramTransport(
        store,
        token=settings.telegram_bot_token,
        poll_timeout_seconds=settings.telegram_poll_timeout_seconds,
        request_timeout_seconds=settings.telegram_request_timeout_seconds,
    ).run()
