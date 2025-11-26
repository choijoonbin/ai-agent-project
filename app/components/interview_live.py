from __future__ import annotations

import math
import time
import uuid
import wave
import requests
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

from server.utils.openai_audio import transcribe_audio

RECORDINGS_DIR = SERVER_ROOT / "data" / "interview_recordings"
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

RTC_CONFIG = RTCConfiguration(
    {
        "iceServers": [
            {"urls": ["stun:stun.l.google.com:19302"]},
            {"urls": ["stun:stun1.l.google.com:19302"]},
            {"urls": ["stun:stun2.l.google.com:19302"]},
        ]
    }
)

# Backend API URL
BACKEND_URL = "http://localhost:9898"


# ========== API Helper Functions ========== #

def _start_interview_session(application_id: int, candidate_name: str, job_title: str, 
                             jd_text: str, resume_text: str, total_questions: int = 5) -> Dict[str, Any]:
    """면접 세션 시작 API 호출"""
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/v1/interview-live/start",
            json={
                "application_id": application_id,
                "candidate_name": candidate_name,
                "job_title": job_title,
                "jd_text": jd_text,
                "resume_text": resume_text,
                "total_questions": total_questions,
                "enable_rag": True,
            },
            timeout=180,  # 3분으로 증가 (JD/Resume 분석 + 질문 생성)
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        st.error("면접 준비 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.")
        return {}
    except requests.exceptions.RequestException as e:
        st.error(f"면접 시작 중 오류 발생: {e}")
        return {}


def _submit_answer(session_id: str, answer: str, retry: int = 2) -> Dict[str, Any]:
    """답변 제출 및 다음 질문 받기 API 호출 (재시도 포함)"""
    last_error = None
    
    for attempt in range(retry + 1):
        try:
            response = requests.post(
                f"{BACKEND_URL}/api/v1/interview-live/submit-answer",
                json={
                    "session_id": session_id,
                    "answer": answer,
                },
                timeout=60,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError as e:
            last_error = e
            if attempt < retry:
                st.warning(f"서버 연결 실패. 재시도 중... ({attempt + 1}/{retry})")
                time.sleep(1)
            continue
        except requests.exceptions.Timeout as e:
            last_error = e
            st.error("서버 응답 시간 초과. 네트워크 상태를 확인해주세요.")
            return {}
        except requests.exceptions.RequestException as e:
            last_error = e
            break
    
    st.error(f"답변 제출 실패: {last_error}")
    st.caption("💡 백엔드 서버가 실행 중인지 확인해주세요 (http://localhost:9898)")
    return {}


def _end_interview(session_id: str) -> Dict[str, Any]:
    """면접 종료 API 호출"""
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/v1/interview-live/end",
            json={"session_id": session_id},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError as e:
        st.error("서버에 연결할 수 없습니다. 백엔드 서버가 실행 중인지 확인해주세요.")
        return {}
    except requests.exceptions.Timeout:
        st.error("서버 응답 시간 초과. 평가 생성에 시간이 걸리고 있습니다.")
        return {}
    except requests.exceptions.RequestException as e:
        st.error(f"면접 종료 중 오류 발생: {e}")
        return {}


def _init_context() -> Dict[str, Any]:
    """Interview Live 화면에서 사용할 기본 컨텍스트를 반환."""
    default_context = {
        "session_id": None,  # 백엔드 면접 세션 ID
        "interview_id": None,
        "application_id": None,
        "candidate_name": "지원자",
        "job_title": "",
        "jd_text": "",
        "resume_text": "",
        "role": "candidate",
        "origin_nav": "status",
        "current_question": 0,
        "total_questions": 5,
        "question_text": "AI 면접관이 첫 질문을 준비하고 있습니다.",
        "question_category": "일반",
        "time_limit": 90,
        "transcript": [],
        "last_recording_path": None,
        "last_transcript": "",
        "interview_started": False,  # 실제 면접 시작 여부
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
            # 면접 세션 시작 - 백엔드 API 호출
            if not ctx.get("application_id"):
                st.error("지원서 정보가 없습니다. 면접을 시작할 수 없습니다.")
                return
            
            with st.spinner("면접을 준비하고 있습니다... (첫 질문을 생성 중)"):
                result = _start_interview_session(
                    application_id=ctx["application_id"],
                    candidate_name=ctx["candidate_name"],
                    job_title=ctx.get("job_title", ""),
                    jd_text=ctx.get("jd_text", ""),
                    resume_text=ctx.get("resume_text", ""),
                    total_questions=ctx["total_questions"],
                )
            
            if result and "session_id" in result:
                # 세션 정보 저장
                ctx["session_id"] = result["session_id"]
                ctx["question_text"] = result["first_question"]
                ctx["question_category"] = result.get("question_category", "일반")
                ctx["current_question"] = result["current_question_num"]
                ctx["total_questions"] = result["total_questions"]
                ctx["interview_started"] = True
                
                st.session_state["interview_live_started"] = True
                st.success(f"✅ 면접이 시작되었습니다! (세션 ID: {result['session_id'][:8]}...)")
                st.rerun()
            else:
                st.error("면접 시작에 실패했습니다. 백엔드 서버 상태를 확인해주세요.")


def _render_timer_html(seconds: int) -> str:
    """타이머 HTML 렌더링 (정적)"""
    minutes = math.floor(seconds / 60)
    remain = seconds % 60
    return f"<h3 style='text-align: right; color: #38bdf8; margin:0;'>⏱ {minutes:02d}:{remain:02d}</h3>"


def _render_countdown_timer(time_limit: int, key: str = "timer") -> None:
    """실시간 카운트다운 타이머 렌더링"""
    # 타이머 시작 시간 초기화
    timer_key = f"timer_start_{key}"
    if timer_key not in st.session_state:
        st.session_state[timer_key] = time.time()
    
    # 경과 시간 계산
    elapsed = int(time.time() - st.session_state[timer_key])
    remaining = max(time_limit - elapsed, 0)
    
    minutes = remaining // 60
    seconds = remaining % 60
    
    # 색상: 시간에 따라 변경
    if remaining > 30:
        color = "#38bdf8"  # 파란색
    elif remaining > 10:
        color = "#fbbf24"  # 노란색
    else:
        color = "#f87171"  # 빨간색
    
    st.markdown(
        f"<h3 style='text-align: right; color: {color}; margin:0;'>⏱ {minutes:02d}:{seconds:02d}</h3>",
        unsafe_allow_html=True
    )


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
        """
        오디오 프레임 수신 및 버퍼 저장
        - WebRTC가 기본적으로 호출하는 메서드
        """
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
            return frame

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
    """
    AudioProcessor Factory 함수
    - 싱글톤 패턴: 기존 인스턴스가 있으면 재사용
    """
    print(f"🏭 [DEBUG] create_audio_processor() 호출됨")
    
    # 기존 인스턴스가 있으면 재사용
    existing_instance = InterviewAudioProcessor.get_instance()
    if existing_instance:
        print(f"♻️ [DEBUG] 기존 인스턴스 재사용: {id(existing_instance)}")
        return existing_instance
    
    # 없으면 새로 생성
    print(f"✨ [DEBUG] 새 인스턴스 생성")
    return InterviewAudioProcessor()


def render_interview_live_page() -> None:
    """AI 면접 실시간 화면 렌더링."""
    ctx = _init_context()
    started = st.session_state.get("interview_live_started", False)
    
    # 타이머 자동 업데이트를 위한 주기적 새로고침 (면접 진행 중일 때만)
    if started and ctx.get("interview_started"):
        # 5초마다 타이머 업데이트
        if "last_timer_update" not in st.session_state:
            st.session_state.last_timer_update = time.time()
        
        time_since_update = time.time() - st.session_state.last_timer_update
        if time_since_update >= 5.0:
            st.session_state.last_timer_update = time.time()
            time.sleep(0.1)
            st.rerun()

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
            # 확인 다이얼로그
            if not st.session_state.get("confirm_exit", False):
                st.session_state["confirm_exit"] = True
                st.warning("⚠️ 정말 면접을 종료하시겠습니까? 진행 중인 답변은 저장되지 않습니다.")
                
                confirm_cols = st.columns([1, 1])
                with confirm_cols[0]:
                    if st.button("✅ 네, 종료합니다", type="primary", use_container_width=True):
                        # 면접 세션이 있으면 중간 저장 시도
                        if ctx.get("session_id") and ctx.get("interview_started"):
                            try:
                                result = _end_interview(ctx["session_id"])
                                if result and "interview_id" in result:
                                    st.success(f"부분 답변이 저장되었습니다. (ID: {result['interview_id']})")
                            except:
                                pass  # 실패해도 종료는 진행
                        
                        st.session_state["interview_live_started"] = False
                        st.session_state["confirm_exit"] = False
                        st.session_state["nav_selected_code"] = origin
                        st.rerun()
                with confirm_cols[1]:
                    if st.button("❌ 취소", type="secondary", use_container_width=True):
                        st.session_state["confirm_exit"] = False
                        st.rerun()
                st.stop()
            else:
                st.session_state["confirm_exit"] = False

    with header_cols[1]:
        current = max(ctx["current_question"], 0)
        total = max(ctx["total_questions"], 1)
        progress_val = current / total if current > 0 else 0.0
        st.progress(progress_val, text=f"진행률: {current}/{total} 질문")
        
        if current > 0:
            question_preview = ctx.get("question_text", "")[:50] + "..." if len(ctx.get("question_text", "")) > 50 else ctx.get("question_text", "")
            st.metric("현재 질문", f"Q{current:02d}", question_preview)
        else:
            st.info("면접을 시작하려면 '면접 시작하기' 버튼을 눌러주세요.")

    with header_cols[2]:
        # 면접 진행 중일 때만 실시간 타이머 표시
        if ctx.get("interview_started"):
            _render_countdown_timer(ctx.get("time_limit", 90), key=f"q{ctx['current_question']}")
        else:
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
                    <p style="margin:0;font-weight:600;color:#67e8f9;">
                        현재 질문 
                        <span style="background:rgba(45,212,191,0.2);padding:2px 8px;border-radius:4px;font-size:0.8rem;margin-left:8px;">
                            {category}
                        </span>
                    </p>
                    <p style="margin:4px 0 0;color:#e0f2fe;font-size:1rem;">{question}</p>
                </div>
            </div>
            """.format(
                question=ctx.get("question_text", "면접을 시작하면 질문이 표시됩니다."),
                category=ctx.get("question_category", "일반")
            ),
            unsafe_allow_html=True,
        )

    # WebRTC 변수를 블록 바깥에 선언 (스코프 문제 해결)
    webrtc_key = f"candidate-stream-{ctx.get('session_id', 'default')}"
    webrtc_ctx = None
    connection_ready = False
    
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
            key=webrtc_key,
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
        elif webrtc_ctx and hasattr(webrtc_ctx, 'state'):
            # WebRTC 연결 상태 세부 확인
            state = webrtc_ctx.state
            if hasattr(state, 'signalling_state'):
                st.warning(f"⚠️ WebRTC 연결 중... (상태: {state.signalling_state})")
                st.caption("💡 연결이 오래 걸리면 'STOP' 버튼을 누르고 'START'를 다시 눌러주세요.")
            else:
                st.info("연결 대기 중입니다. 브라우저 접근 권한을 허용해주세요.")
            st.caption("💡 팁: 브라우저 주소창 왼쪽의 아이콘을 클릭해 마이크 권한을 '허용'으로 설정하세요.")
        else:
            st.warning("⚠️ WebRTC 준비 중입니다. 'START' 버튼을 눌러 연결을 시작해주세요.")
            st.caption("💡 첫 연결 시 시간이 걸릴 수 있습니다. 'STOP' 후 'START'를 다시 눌러보세요.")

    st.markdown("---")

    # 실시간 STT
    st.subheader("📝 실시간 답변 기록 (STT)")
    st.caption("👂 AI가 사용자의 답변을 인식하고 있습니다.")

    transcript_placeholder = st.empty()
    transcript_text = "\n".join(ctx.get("transcript") or ["(아직 음성이 입력되지 않았습니다.)"])
    transcript_placeholder.code(transcript_text, language="text")

    st.markdown(
        "<p style='color:#f87171;'>* 답변이 완료되면 '녹음 저장 및 STT' 버튼을 눌러주세요. (버튼이 반응하지 않으면 한 번 더 클릭해주세요)</p>",
        unsafe_allow_html=True,
    )

    st.markdown("#### 🎙️ 답변 녹음 / STT")
    col_rec, col_tts = st.columns([1, 1])
    with col_rec:
        record_disabled = not connection_ready
        
        # 버튼 클릭 처리
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
                            st.success(f"✅ STT 완료: {text[:100]}..." if len(text) > 100 else f"✅ STT 완료: {text}")
                            
                            # 백엔드로 답변 제출
                            if ctx.get("session_id") and ctx.get("interview_started"):
                                with st.spinner("답변을 제출하고 다음 질문을 준비 중..."):
                                    result = _submit_answer(ctx["session_id"], text)
                                
                                if result and "status" in result:
                                    if result["status"] == "continue":
                                        # 다음 질문으로 진행
                                        ctx["question_text"] = result["next_question"]
                                        ctx["question_category"] = result.get("question_category", "일반")
                                        ctx["current_question"] = result["current_question_num"]
                                        st.success(f"✅ Q{ctx['current_question']}: {ctx['question_text'][:50]}...")
                                        st.rerun()
                                    elif result["status"] == "finished":
                                        # 면접 종료
                                        st.success("🎉 모든 질문이 완료되었습니다!")
                                        ctx["interview_started"] = False
                                        
                                        # 평가 결과 표시
                                        if "evaluation" in result:
                                            st.json(result["evaluation"])
                                        
                                        # 면접 종료 처리
                                        end_result = _end_interview(ctx["session_id"])
                                        if end_result and "interview_id" in end_result:
                                            ctx["interview_id"] = end_result["interview_id"]
                                            st.info(f"면접 결과가 저장되었습니다. (ID: {end_result['interview_id']})")
                                else:
                                    st.warning("답변 제출에 실패했습니다. 다시 시도해주세요.")
                        except Exception as exc:
                            st.error(f"STT 변환 중 오류: {exc}")

    with col_tts:
        if st.button("🔊 AI 질문 음성 재생", use_container_width=True):
            with st.spinner("음성을 생성하고 있습니다..."):
                try:
                    question_text = ctx.get("question_text", "질문이 없습니다.")
                    print(f"🔊 [DEBUG] TTS 버튼 클릭: {question_text[:50]}...")
                    
                    # 백엔드 API 호출
                    response = requests.post(
                        f"{BACKEND_URL}/api/v1/interview-live/tts",
                        json={"text": question_text},
                        timeout=30
                    )
                    response.raise_for_status()
                    
                    audio_bytes = response.content
                    print(f"✅ [DEBUG] TTS 응답 수신: {len(audio_bytes)} bytes")
                    
                    # gTTS는 MP3 포맷으로 출력
                    st.audio(audio_bytes, format="audio/mp3")
                    st.success("✅ TTS 음성 재생 완료")
                except requests.exceptions.Timeout:
                    st.error("TTS 생성 시간이 초과되었습니다. 다시 시도해주세요.")
                except requests.exceptions.ConnectionError:
                    st.error("백엔드 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.")
                except Exception as exc:
                    st.error(f"TTS 실행 중 오류: {exc}")
                    print(f"❌ [DEBUG] TTS 오류: {exc}")

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

