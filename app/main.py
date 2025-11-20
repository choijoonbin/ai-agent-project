# app/main.py

import base64
import os
import sys
from io import BytesIO
from pathlib import Path

# ⚠️ 반드시 import 전에 경로를 추가해야 합니다
APP_DIR = Path(__file__).parent.resolve()
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import streamlit as st
from dotenv import load_dotenv
from PIL import Image

# 모듈 import (경로가 추가된 후)
from utils.state_manager import init_app_session_state, apply_theme_css
from components.sidebar import render_sidebar
from components.candidate_form import render_run_tab
from components.history_panel import render_history_tab

# app/.env 로드
load_dotenv()


@st.cache_data(show_spinner=False)
def _render_header_process_image(
    path: str,
    *,
    max_height: int = 280,
) -> None:
    """상단 hero 영역에 들어가는 프로세스 다이어그램 이미지 렌더링 (선택 사용)."""
    image = Image.open(path)
    width, height = image.size
    scaling = max_height / height
    new_size = (int(width * scaling), max_height)
    resized = image.resize(new_size, Image.LANCZOS)

    buffer = BytesIO()
    resized.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")

    img_html = f"""
    <div class="hero-image-wrapper" style="max-width:520px; margin-left:0;">
        <img
            src="data:image/png;base64,{encoded}"
            style="width:100%; max-height:{max_height}px; object-fit:contain; display:block; margin:0;"
        />
    </div>
    """
    st.markdown(img_html, unsafe_allow_html=True)


def main():
    st.set_page_config(
        page_title="AI Interview Agent",
        page_icon="🧑‍💼",
        layout="wide",
    )

    # 공통 세션키 초기화 & 테마 CSS 적용
    init_app_session_state()
    apply_theme_css()

    st.title("🧑‍💼 AI Interview Agent (AI 채용 면접관)")
    st.markdown(
        """
        이 앱은 JD(채용공고)와 지원자의 이력서를 기반으로:
        - JD 분석  
        - 이력서 분석  
        - 맞춤형 인터뷰 질문 생성  
        - 후속질문을 포함한 인터뷰 세션 관리  
        - 최종 평가 리포트 생성  
        - 질문별 답변 입력 후 재평가  
        
        까지 한 번에 수행하는 **AI 기반 면접 보조 에이전트**입니다.
        """
    )

    # (원하면 상단 프로세스 이미지 활성화)
    # hero_col, spacer_col = st.columns([0.9, 3.4])
    # with hero_col:
    #     _render_header_process_image("images/process.png", max_height=176)
    # with spacer_col:
    #     st.empty()

    # ---------- 사이드바 ---------- #
    with st.sidebar:
        render_sidebar()

    # ---------- 본문 탭 ---------- #
    tab_run, tab_history = st.tabs(["🚀 면접 실행", "📚 면접 이력"])

    with tab_run:
        render_run_tab()

    with tab_history:
        render_history_tab()


if __name__ == "__main__":
    main()
