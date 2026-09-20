"""
Speech-to-text for uploaded audio and video.

Transcription needs a real engine. This module uses `faster-whisper` when it is installed
(CPU-friendly, free, runs locally) and otherwise says plainly that transcription is
unavailable. It never returns placeholder text: the previous implementation returned a
hardcoded "distributed architecture" transcript for every file, which then flowed into
competency and question generation as if it were the lecture.

When transcription is unavailable the media is still stored and playable; the
administrator can paste a transcript, and the analysis stages run on that.
"""

import asyncio
import os
import tempfile
from typing import Optional, Protocol

from app.core.config import settings
from app.ingestion.errors import IngestionError, TranscriptionUnavailable


class Transcriber(Protocol):
    name: str

    async def transcribe(self, data: bytes, extension: str) -> str: ...


class FasterWhisperTranscriber:
    name = "faster-whisper"

    def __init__(self, model_size: str):
        self.model_size = model_size
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    def _run(self, data: bytes, extension: str) -> str:
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, f"media.{extension}")
            with open(path, "wb") as handle:
                handle.write(data)
            segments, _info = self._load().transcribe(path, vad_filter=True)
            return "\n\n".join(segment.text.strip() for segment in segments if segment.text.strip())

    async def transcribe(self, data: bytes, extension: str) -> str:
        try:
            return await asyncio.to_thread(self._run, data, extension)
        except Exception as exc:
            raise IngestionError(f"Transcription failed: {exc}", code="transcription_failed") from exc


_override: Optional[Transcriber] = None


def set_transcriber_override(transcriber: Optional[Transcriber]) -> None:
    global _override
    _override = transcriber


def get_transcriber() -> Transcriber:
    if _override is not None:
        return _override
    try:
        import faster_whisper  # noqa: F401
    except ImportError as exc:
        raise TranscriptionUnavailable(
            "No speech-to-text engine is installed (install faster-whisper). "
            "You can paste a transcript instead."
        ) from exc
    return FasterWhisperTranscriber(settings.whisper_model)


def transcription_available() -> bool:
    try:
        get_transcriber()
        return True
    except TranscriptionUnavailable:
        return False
