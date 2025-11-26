from __future__ import annotations

import io
from pathlib import Path

from gtts import gTTS
from faster_whisper import WhisperModel

# Whisper 모델 로드 (최초 1회만)
_whisper_model = None


def _get_whisper_model():
    """Whisper 모델을 로드 (lazy loading)"""
    global _whisper_model
    if _whisper_model is None:
        print("🔄 [INFO] Faster-Whisper large-v3 모델 로딩 중...")
        # device: "cpu" 또는 "cuda", compute_type: "int8" (CPU용)
        _whisper_model = WhisperModel("large-v3", device="cpu", compute_type="int8")
        print("✅ [INFO] Faster-Whisper large-v3 모델 로드 완료")
    return _whisper_model


def synthesize_speech(text: str, *, lang: str = "ko") -> bytes:
    """Google TTS (gTTS) - 무료, API 키 불필요"""
    print(f"🔊 [INFO] TTS 생성 중: {text[:50]}..." if len(text) > 50 else f"🔊 [INFO] TTS 생성 중: {text}")
    
    # gTTS 객체 생성
    tts = gTTS(text=text, lang=lang, slow=False)
    
    # 메모리 버퍼에 저장
    audio_buffer = io.BytesIO()
    tts.write_to_fp(audio_buffer)
    audio_buffer.seek(0)
    
    audio_bytes = audio_buffer.read()
    print(f"✅ [INFO] TTS 생성 완료: {len(audio_bytes)} bytes")
    return audio_bytes


def transcribe_audio(file_path: str | Path) -> str:
    """로컬 Faster-Whisper large-v3 transcription (API 키 불필요)"""
    model = _get_whisper_model()
    segments, info = model.transcribe(str(file_path), language="ko", beam_size=5)
    
    # 세그먼트를 하나의 텍스트로 결합
    text_parts = []
    for segment in segments:
        text_parts.append(segment.text)
    
    result = " ".join(text_parts).strip()
    print(f"📝 [INFO] STT 완료: {result[:100]}..." if len(result) > 100 else f"📝 [INFO] STT 완료: {result}")
    return result

