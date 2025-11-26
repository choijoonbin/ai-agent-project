from __future__ import annotations

import os
from pathlib import Path

from openai import OpenAI

from server.utils.config import get_settings, Settings


def _get_client() -> OpenAI:
    settings: Settings = get_settings()
    api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 가 설정되어 있지 않습니다. .env 를 확인해주세요.")
    return OpenAI(api_key=api_key)


client = _get_client()


def synthesize_speech(text: str, *, voice: str = "alloy") -> bytes:
    """OpenAI TTS (gpt-4o-mini-tts)"""
    response = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice=voice,
        input=text,
    )
    return response.read()


def transcribe_audio(file_path: str | Path) -> str:
    """OpenAI Whisper large-v3 transcription"""
    with open(file_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=audio_file,
            response_format="text",
        )
    return transcript.strip()

