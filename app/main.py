# app/main.py

import base64
import os
import sys
from io import BytesIO
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from PIL import Image

# 경로 설정 (components, utils import 위함)
APP_DIR = Path(__file__).parent.resolve()
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from utils.state_manager import init_app_session_state, apply_theme_css
from components.sidebar import render_sidebar
from components.candidate_form import render_studio_page
from components.history_panel import render_history_tab
from components.overview import render_overview_page
from components.insights import render_insights_page  # ✅ 새로 추가

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


def _render_settings_page() -> None:
    st.title("⚙️ 시스템 설정")
    st.write("추후, API 상태 / 버전 정보 / 디버그 옵션 등을 제공할 수 있습니다.")
    st.info("현재는 플레이스홀더 페이지입니다.")


def main() -> None:
    st.set_page_config(
        page_title="AI Interview Agent",
        page_icon="🧑‍💼",
        layout="wide",
    )

    # 공통 세션키 초기화 & 테마 CSS 적용
    init_app_session_state()
    apply_theme_css()

    # ---------- 사이드바 ---------- #
    with st.sidebar:
        render_sidebar()

    # ---------- 본문: 네비게이션에 따라 분기 ---------- #
    current_page = st.session_state.get("nav_selected", "Studio")

    if current_page == "Overview":
        render_overview_page()
    elif current_page == "Studio":
        render_studio_page()
    elif current_page == "History":
        render_history_tab()
    elif current_page == "Insights":
        render_insights_page()
    else:
        _render_settings_page()


if __name__ == "__main__":
    main()
