from __future__ import annotations

import math
import uuid
import wave
from pathlib import Path
from collections import deque
from threading import Lock
from typing import Deque, Dict, Any, List, Optional, Tuple

import numpy as np
import streamlit as st
import sys
from streamlit_webrtc import (
    WebRtcMode,
    RTCConfiguration,
    webrtc_streamer,
    AudioProcessorBase,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVER_ROOT = PROJECT_ROOT / "server"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from server.utils.openai_audio import synthesize_speech, transcribe_audio

RECORDINGS_DIR = SERVER_ROOT / "data" / "interview_recordings"
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

RTC_CONFIG = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)


def _init_context() -> Dict[str, Any]:
    """Interview Live 화면에서 사용할 기본 컨텍스트를 반환."""
    default_context = {
        "interview_id": None,
        "application_id": None,
        "candidate_name": "지원자",
        "role": "candidate",
        "origin_nav": "status",
        "current_question": 1,
        "total_questions": 5,
        "question_text": "AI 면접관이 첫 질문을 준비하고 있습니다.",
        "time_limit": 90,
        "transcript": [],
        "last_recording_path": None,
        "last_transcript": "",
    }
    ctx = st.session_state.setdefault("interview_live_context", default_context)

    # default keys 보장
    for key, value in default_context.items():
        ctx.setdefault(key, value)
    return ctx


def _render_preflight_steps(ctx: Dict[str, Any]) -> None:
    st.title("AI 면접을 시작하기 전에…")
    st.caption("원활한 면접 진행을 위해 아래 단계를 확인해주세요.")

    steps = [
        ("Step 1", "카메라 / 마이크 연결 테스트"),
        ("Step 2", "면접 규칙 확인 (제한 시간, 재시도 불가 등)"),
        ("Step 3", "조용한 환경에서 진행 준비"),
    ]

    cols = st.columns(len(steps))
    for col, (title, desc) in zip(cols, steps):
        with col:
            st.markdown(
                f"""
                <div style="
                    border:1px solid rgba(148,163,184,0.4);
                    border-radius:12px;
                    padding:16px;
                    background:rgba(15,23,42,0.75);
                    min-height:150px;
                ">
                    <p style="font-weight:700;color:#f9fafb;font-size:1.05rem;margin-bottom:6px;">{title}</p>
                    <p style="color:#cbd5f5;font-size:0.9rem;line-height:1.4;">{desc}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")
    button_cols = st.columns([1, 1])
    with button_cols[0]:
        if st.button("↩️ 이전 화면", type="secondary", use_container_width=True):
            origin = ctx.get("origin_nav", "status")
            st.session_state["interview_live_started"] = False
            st.session_state["nav_selected_code"] = origin
            st.rerun()
    with button_cols[1]:
        if st.button("✅ 면접 시작하기", type="primary", use_container_width=True):
            st.session_state["interview_live_started"] = True
            st.rerun()


def _render_timer_html(seconds: int) -> str:
    minutes = math.floor(seconds / 60)
    remain = seconds % 60
    return f"<h3 style='text-align: right; color: #38bdf8; margin:0;'>⏱ {minutes:02d}:{remain:02d}</h3>"


class InterviewAudioProcessor(AudioProcessorBase):
    """웹캠에서 수신한 오디오 프레임을 버퍼에 적재하고 필요 시 추출."""

    # 클래스 레벨에서 인스턴스 추적
    _instance: Optional["InterviewAudioProcessor"] = None

    def __init__(self) -> None:
        super().__init__()  # 부모 클래스 초기화 명시
        self._buffer: Deque[np.ndarray] = deque(maxlen=1600)
        self._sample_rate: Optional[int] = None
        self._channels: Optional[int] = None
        self._lock = Lock()
        self._frame_count = 0  # 디버깅용 카운터
        InterviewAudioProcessor._instance = self
        print(f"🔧 [DEBUG] InterviewAudioProcessor 인스턴스 생성됨: {id(self)}")

    def recv(self, frame):
        """오디오 프레임 수신 및 버퍼 저장"""
        try:
            self._sample_rate = frame.sample_rate
            # PyAV AudioLayout에서 채널 수 가져오기
            if hasattr(frame.layout, 'channels'):
                self._channels = frame.layout.channels
            elif hasattr(frame.layout, 'nb_channels'):
                self._channels = frame.layout.nb_channels
            else:
                # 기본값: 스테레오
                self._channels = 2
                
            arr = frame.to_ndarray()
            with self._lock:
                self._buffer.append(arr.copy())
                self._frame_count += 1
                # 처음 10개 프레임은 로그 출력
                if self._frame_count <= 10:
                    print(f"🎤 [DEBUG] 프레임 수신됨 #{self._frame_count}: shape={arr.shape}, rate={self._sample_rate}, channels={self._channels}")
            return frame
        except Exception as e:
            print(f"❌ [DEBUG] recv() 오류: {e}")
            import traceback
            traceback.print_exc()
            raise

    def dump_audio(self) -> Tuple[List[np.ndarray], int, int]:
        """버퍼의 오디오 데이터를 추출하고 프레임 카운트도 반환"""
        with self._lock:
            if not self._buffer:
                return [], 0, self._frame_count
            arrays = list(self._buffer)
            self._buffer.clear()
            frame_count = self._frame_count
            self._frame_count = 0  # 카운터 리셋
        if not self._sample_rate:
            return [], 0, frame_count
        print(f"📤 [DEBUG] dump_audio() 호출됨: {len(arrays)}개 청크, {frame_count}개 프레임")
        return arrays, self._sample_rate, frame_count

    @classmethod
    def get_instance(cls) -> Optional["InterviewAudioProcessor"]:
        """현재 활성화된 프로세서 인스턴스 반환"""
        return cls._instance


def create_audio_processor():
    """AudioProcessor Factory 함수"""
    print(f"🏭 [DEBUG] create_audio_processor() 호출됨")
    return InterviewAudioProcessor()


def render_interview_live_page() -> None:
    """AI 면접 실시간 화면 렌더링."""
    ctx = _init_context()
    started = st.session_state.get("interview_live_started", False)

    st.markdown(
        """
        <style>
        .interview-frame {
            border:1px solid rgba(148,163,184,0.35);
            border-radius:16px;
            padding:16px;
            background:rgba(15,23,42,0.92);
            min-height:320px;
            display:flex;
            flex-direction:column;
            gap:12px;
            position:relative;
        }
        .interview-frame.ai::after {
            content:"AI 면접관";
            position:absolute;
            top:12px;
            right:12px;
            font-size:0.8rem;
            color:#67e8f9;
            letter-spacing:0.05em;
        }
        .interview-frame.candidate::after {
            content:"지원자";
            position:absolute;
            top:12px;
            right:12px;
            font-size:0.8rem;
            color:#fbcfe8;
            letter-spacing:0.05em;
        }
        .webrtc-placeholder {
            flex:1;
            border-radius:12px;
            background:rgba(15,23,42,0.8);
            border:1px dashed rgba(148,163,184,0.5);
            display:flex;
            align-items:center;
            justify-content:center;
            color:#cbd5f5;
            font-size:0.95rem;
            text-align:center;
            padding:12px;
        }
        .ai-active {
            box-shadow:0 0 25px rgba(45,212,191,0.35);
            border-color:rgba(45,212,191,0.6) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if not started:
        _render_preflight_steps(ctx)
        return

    st.title("AI 모의 면접 대시보드")

    # 상단 제어 바
    header_cols = st.columns([1.1, 2.0, 0.9])
    with header_cols[0]:
        origin = ctx.get("origin_nav", "status")
        if st.button("🔴 면접 종료", type="secondary", use_container_width=True):
            st.session_state["interview_live_started"] = False
            st.session_state["nav_selected_code"] = origin
            st.rerun()

    with header_cols[1]:
        progress_val = ctx["current_question"] / max(ctx["total_questions"], 1)
        st.progress(progress_val, text=f"진행률: {ctx['current_question']}/{ctx['total_questions']} 질문")
        st.metric("현재 질문", f"Q{ctx['current_question']:02d}", ctx.get("question_text", ""))

    with header_cols[2]:
        st.markdown(_render_timer_html(ctx.get("time_limit", 90)), unsafe_allow_html=True)

    st.markdown("---")

    # 듀얼 뷰
    video_cols = st.columns([1.2, 0.05, 1.2])
    with video_cols[0]:
        st.subheader("🤖 AI 면접관")
        st.markdown(
            """
            <div class="interview-frame ai ai-active">
                <div class="webrtc-placeholder">
                    WebRTC 컴포넌트 자리<br/>
                    (AI 아바타 스트림 / TTS 출력)
                </div>
                <div style="margin-top:8px;">
                    <p style="margin:0;font-weight:600;color:#67e8f9;">현재 질문</p>
                    <p style="margin:4px 0 0;color:#e0f2fe;font-size:1rem;">{question}</p>
                </div>
            </div>
            """.format(question=ctx.get("question_text", "")),
            unsafe_allow_html=True,
        )

    with video_cols[2]:
        st.subheader("👤 지원자")
        st.markdown(
            """
            <div class="interview-frame candidate">
                <div class="webrtc-placeholder">
                    지원자 카메라/마이크 연결 중...
                </div>
                <p style="text-align:center;color:#cbd5f5;margin:8px 0 0;font-size:0.9rem;">
                    * 본인의 자세, 표정, 시선을 확인하며 답변을 진행해주세요.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        webrtc_ctx = webrtc_streamer(
            key="candidate-stream",
            mode=WebRtcMode.SENDRECV,
            rtc_configuration=RTC_CONFIG,
            media_stream_constraints={
                "video": {"width": 640, "height": 480},
                "audio": {
                    "echoCancellation": True,
                    "noiseSuppression": True,
                    "autoGainControl": True,
                }
            },
            async_processing=True,
            audio_processor_factory=create_audio_processor,  # Factory 함수 사용
        )

        connection_ready = bool(webrtc_ctx and webrtc_ctx.state.playing)
        if connection_ready:
            st.success("✅ 카메라/마이크 연결이 확인되었습니다.")
            # 프로세서 상태 확인
            processor = InterviewAudioProcessor.get_instance()
            if processor:
                st.info(f"🎤 오디오 프로세서 활성화됨 (현재 버퍼: {len(processor._buffer)}개 프레임)")
            else:
                st.warning("⚠️ 오디오 프로세서가 초기화되지 않았습니다. 몇 초 기다린 후 말씀해주세요.")
        else:
            st.info("연결 대기 중입니다. 브라우저 접근 권한을 허용해주세요.")
            st.caption("💡 팁: 브라우저 주소창 왼쪽의 아이콘을 클릭해 마이크 권한을 '허용'으로 설정하세요.")

    st.markdown("---")

    # 실시간 STT
    st.subheader("📝 실시간 답변 기록 (STT)")
    st.caption("👂 AI가 사용자의 답변을 인식하고 있습니다.")

    transcript_placeholder = st.empty()
    transcript_text = "\n".join(ctx.get("transcript") or ["(아직 음성이 입력되지 않았습니다.)"])
    transcript_placeholder.code(transcript_text, language="text")

    st.markdown(
        "<p style='color:#f87171;'>* 답변이 완료되면 '녹음 저장 및 STT' 버튼을 눌러주세요.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("#### 🎙️ 답변 녹음 / STT")
    col_rec, col_tts = st.columns([1, 1])
    with col_rec:
        record_disabled = not connection_ready
        if st.button("💾 녹음 저장 및 STT", use_container_width=True, disabled=record_disabled):
            # webrtc_ctx에서 audio_processor 가져오기
            processor = None
            if hasattr(webrtc_ctx, "audio_processor"):
                processor = webrtc_ctx.audio_processor
                print(f"🔍 [DEBUG] webrtc_ctx.audio_processor: {processor}, type={type(processor)}")
            
            # webrtc_ctx에 없으면 클래스 레벨 인스턴스 사용
            if not processor:
                processor = InterviewAudioProcessor.get_instance()
                print(f"🔍 [DEBUG] InterviewAudioProcessor.get_instance(): {processor}, type={type(processor)}")
            
            if not isinstance(processor, InterviewAudioProcessor):
                st.error("⚠️ 오디오 프로세서를 찾을 수 없습니다.")
                st.info(f"디버그: webrtc_ctx 타입={type(webrtc_ctx)}, processor={processor}")
                st.caption("페이지를 새로고침하고, 'Start' 버튼을 누른 후 몇 초 기다린 후 다시 시도해주세요.")
            else:
                chunks, sample_rate, frame_count = processor.dump_audio()
                st.info(f"🔍 디버그: 수신된 프레임 수={frame_count}, 버퍼 청크={len(chunks)}, 샘플레이트={sample_rate}")
                
                if not chunks or not sample_rate:
                    st.warning(f"수신된 오디오 데이터가 없습니다. 몇 초간 말한 후 다시 시도해주세요. (프레임 카운트: {frame_count})")
                    if frame_count == 0:
                        st.error("⚠️ 오디오 프레임이 전혀 수신되지 않았습니다.")
                        st.caption("🔧 **디버깅 힌트:**")
                        st.caption("1. 터미널에 `🏭 [DEBUG] create_audio_processor() 호출됨` 메시지가 있는지 확인")
                        st.caption("2. 터미널에 `🎤 [DEBUG] 프레임 수신됨` 메시지가 있는지 확인")
                        st.caption("3. 브라우저 콘솔(F12)에서 WebRTC 관련 오류 메시지 확인")
                else:
                    try:
                        file_path = _save_audio_chunks(chunks, sample_rate)
                    except ValueError as exc:
                        st.error(f"녹음 파일 저장 중 오류: {exc}")
                    else:
                        ctx["last_recording_path"] = str(file_path)
                        st.success(f"✅ 녹음 파일 저장: {file_path.name} (프레임 {frame_count}개, 청크 {len(chunks)}개)")
                        try:
                            text = transcribe_audio(file_path)
                            ctx["last_transcript"] = text
                            ctx.setdefault("transcript", []).append(text or "(인식 실패)")
                            transcript_placeholder.code("\n".join(ctx["transcript"]), language="text")
                            st.success("STT 결과가 업데이트되었습니다.")
                        except Exception as exc:
                            st.error(f"STT 변환 중 오류: {exc}")

    with col_tts:
        if st.button("🔊 AI 질문 음성 재생", use_container_width=True):
            try:
                audio_bytes = synthesize_speech(ctx.get("question_text", "질문이 없습니다."))
                # gTTS는 MP3 포맷으로 출력
                st.audio(audio_bytes, format="audio/mp3")
                st.success("✅ TTS 음성 재생 완료")
            except Exception as exc:
                st.error(f"TTS 실행 중 오류: {exc}")

    action_cols = st.columns([1, 1])
    with action_cols[0]:
        st.button("⏸️ 일시 정지", use_container_width=True, disabled=True)
    with action_cols[1]:
        st.button("다음 질문으로 이동 >>", type="primary", use_container_width=True, disabled=True)


def _save_audio_chunks(chunks: List[np.ndarray], sample_rate: int) -> Path:
    """AudioProcessor에서 추출한 numpy 배열 리스트를 WAV 파일로 저장."""
    if not chunks or not sample_rate:
        raise ValueError("오디오 버퍼가 비어 있거나 샘플레이트를 알 수 없습니다.")

    channels = chunks[0].shape[0]
    total_samples = sum(chunk.shape[1] for chunk in chunks)
    if total_samples < sample_rate * 0.5:
        raise ValueError("녹음 길이가 너무 짧습니다. 최소 0.5초 이상 말한 뒤 다시 시도해주세요.")

    audio_ndarray = np.concatenate(chunks, axis=1)
    audio_ndarray = audio_ndarray.transpose()
    audio_ndarray = np.clip(audio_ndarray, -32768, 32767).astype(np.int16)

    file_path = RECORDINGS_DIR / f"{uuid.uuid4().hex}.wav"
    with wave.open(str(file_path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_ndarray.tobytes())

    return file_path

