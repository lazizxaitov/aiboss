"""Voice-to-text for the hold-to-record composer (mobile Action button, and
any other client that wants to send a recorded clip as a chat message)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.routes.auth import _session, _token_from_request
from app.core.ai_media import TranscriptionService
from app.core.data_layer.contracts import CoreDataStore
from app.core.data_layer.factory import get_core_store

router = APIRouter(prefix="/ai")

MAX_VOICE_MESSAGE_BYTES = 15 * 1024 * 1024


class TranscribeResponse(BaseModel):
    text: str


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_voice_message(
    store: Annotated[CoreDataStore, Depends(get_core_store)],
    audio: Annotated[UploadFile, File()],
    authorization: str | None = Header(default=None),
) -> TranscribeResponse:
    if _session(_token_from_request(None, authorization), store) is None:
        raise HTTPException(status_code=401, detail="Сессия недействительна")
    content = await audio.read()
    if not content:
        raise HTTPException(status_code=422, detail="Пустая запись")
    if len(content) > MAX_VOICE_MESSAGE_BYTES:
        raise HTTPException(status_code=413, detail="Голосовое сообщение слишком большое")
    suffix = Path(audio.filename or "voice.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix) as handle:
        handle.write(content)
        handle.flush()
        try:
            result = await TranscriptionService().transcribe(
                Path(handle.name),
                filename=audio.filename or f"voice{suffix}",
                mime_type=audio.content_type or "audio/webm",
            )
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
    return TranscribeResponse(text=result.text)
