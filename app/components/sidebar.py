# app/components/sidebar.py

from __future__ import annotations

from importlib import import_module
from typing import Literal, Optional, Callable

import streamlit as st


def _load_option_menu() -> Optional[Callable[..., str]]:
    """
    streamlit-extras 설치 여부와 상관없이 안전하게 option_menu를 로드.
    - 새로 설치 후 앱을 재시작하지 않아도 재시도되도록 매 호출 시 import 시도.
    """
    try:
        module = import_module("streamlit_extras.option_menu")
        return getattr(module, "option_menu")
    except ModuleNotFoundError:
        return None

NavKey = Literal["overview", "studio", "history", "insights", "settings"]


def _nav_label_to_key(label: str) -> NavKey:
    mapping = {
        "Overview": "overview",
        "면접 스튜디오": "studio",
        "면접 이력": "history",
        "인사이트": "insights",
        "설정": "settings",
    }
    return mapping.get(label, "overview")  # fallback


def render_sidebar() -> NavKey:
    """
    좌측 사이드바 전체 렌더링.
    - 상단: streamlit-option-menu 기반 메인 메뉴
    - 하단: ⚙️ AI Interview 설정 (expander로 접기/펼치기, 기본은 접힌 상태)
    """
    # ---- nav 기본값 보정 ----
    if "nav_selected" not in st.session_state:
        st.session_state["nav_selected"] = "studio"

    # ======================
    # 1) 상단 메인 메뉴
    # ======================
    st.markdown("### 🧭 메뉴")

    # 현재 선택 상태를 index로 변환
    nav_order: list[NavKey] = [
        "overview",
        "studio",
        "history",
        "insights",
        "settings",
    ]
    try:
        default_index = nav_order.index(st.session_state["nav_selected"])
    except ValueError:
        default_index = 1  # fallback: studio

    nav_options_display = ["Overview", "면접 스튜디오", "면접 이력", "인사이트", "설정"]
    option_menu = _load_option_menu()

    if option_menu is not None:
        selected_label: str = option_menu(
            menu_title=None,
            options=nav_options_display,
            icons=["house", "person-workspace", "book", "bar-chart-line", "gear"],
            menu_icon="compass",
            default_index=default_index,
            styles={
                "container": {
                    "padding": "0.5rem 0.2rem 0.8rem 0.2rem",
                    "background-color": "rgba(15,23,42,0.0)",
                },
                "icon": {"color": "#e5e7eb", "font-size": "1.0rem"},
                "nav-link": {
                    "font-size": "0.95rem",
                    "padding": "0.45rem 0.75rem",
                    "margin": "0.1rem 0.25rem",
                    "border-radius": "999px",
                    "color": "#e5e7eb",
                    "background-color": "rgba(15,23,42,0.35)",
                },
                "nav-link-selected": {
                    "background-color": "rgba(248, 113, 113, 0.95)",
                    "color": "#0f172a",
                    "font-weight": "600",
                },
            },
            orientation="vertical",
        )
    else:
        # streamlit-extras 미설치 시 기본 radio 로 대체
        selected_label = st.radio(
            "메뉴 선택",
            options=nav_options_display,
            index=default_index,
            label_visibility="collapsed",
            key=None,
        )

    nav_key: NavKey = _nav_label_to_key(selected_label)
    st.session_state["nav_selected"] = nav_key

    # 살짝 구분선
    st.markdown(
        "<hr style='border: 0; border-top: 1px solid rgba(148,163,184,0.35); "
        "margin: 0.8rem 0 0.9rem 0;'/>",
        unsafe_allow_html=True,
    )

    # ======================================
    # 2) ⚙️ AI Interview 설정 (Expander)
    #    - 기본은 접혀 있는 상태(expanded=False)
    #    - 두 번 클릭해야 하는 문제를 없애기 위해
    #      Streamlit 기본 expander + 위젯 key만 사용
    # ======================================

    with st.expander("⚙️ AI Interview 설정", expanded=False):
        # ---- UI 모드 ----
        st.markdown("#### 🎨 UI 모드")
        st.caption("화면 분위기를 선택하세요. (사이드바 & 카드 스타일)")

        # init_app_session_state 에서 기본값을 넣어주고 있으므로
        # 여기서는 value/index 를 명시하지 않고 key 만 사용 → 경고/더블클릭 문제 방지
        st.radio(
            "UI 모드 선택",
            options=["시스템 기본", "라이트", "다크"],
            key="cfg_theme_mode",
            horizontal=False,
            label_visibility="collapsed",
        )

        st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

        # ---- 인터뷰 옵션 ----
        st.markdown("#### 🤖 인터뷰 옵션")

        st.checkbox("RAG 활성화", key="cfg_enable_rag")
        st.checkbox("경량 모델 사용 (gpt-4o-mini)", key="cfg_use_mini")

        st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

        st.markdown("초기 생성 질문 개수")
        # 마찬가지로 key만 사용 (init에서 기본값 이미 세팅)
        st.slider(
            "초기 생성 질문 개수",
            min_value=3,
            max_value=10,
            step=1,
            key="cfg_total_questions",
            label_visibility="collapsed",
        )

    # 최종 nav_key를 main.py에서 사용할 수 있도록 반환
    return nav_key
