# app/components/sidebar.py

from __future__ import annotations

import streamlit as st
from streamlit_option_menu import option_menu


def _ensure_sidebar_state() -> None:
    """사이드바에서 사용하는 공통 세션 키 기본값 세팅."""
    defaults = {
        # 네비게이션 기본 페이지 (코드 값 기준)
        "nav_selected_code": "overview",  # 최초에는 Overview
        # AI 설정 패널 접힘/펼침 상태 (기본: 접힘)
        "sidebar_show_settings": False,
        # 인터뷰 옵션 기본값 (init_app_session_state 에도 있지만 방어용)
        "cfg_enable_rag": True,
        "cfg_use_mini": True,
        "cfg_total_questions": 5,
        "cfg_theme_mode": "시스템 기본",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def render_sidebar() -> None:
    """왼쪽 사이드바 전체 렌더링."""
    _ensure_sidebar_state()

    # -----------------------
    # 1) 네비게이션 메뉴
    # -----------------------
    st.markdown("### 🧭 메뉴")

    labels = ["Overview", "면접 스튜디오", "면접 이력", "인사이트", "설정"]
    codes = ["overview", "studio", "history", "insights", "settings"]
    icons = ["house", "person-badge", "book", "bar-chart", "gear"]

    # 현재 선택된 코드 기준으로 default_index 계산
    current_code = st.session_state.get("nav_selected_code", "overview")
    try:
        default_index = codes.index(current_code)
    except ValueError:
        default_index = 0

    # Shadcn 느낌의 카드 스타일을 입힌 option_menu
    with st.container():
        selected_label: str = option_menu(
            menu_title=None,
            options=labels,
            icons=icons,
            menu_icon="compass",
            default_index=default_index,
            orientation="vertical",
            styles={
                "container": {
                    "padding": "0.75rem 0.2rem",
                    "border-radius": "18px",
                    "background-color": "rgba(15,23,42,0.95)",
                },
                "icon": {"color": "#e5e7eb", "font-size": "1.05rem"},
                "nav-link": {
                    "font-size": "0.95rem",
                    "padding": "0.55rem 0.9rem",
                    "margin": "0.18rem 0.35rem",
                    "border-radius": "999px",
                    "color": "#e5e7eb",
                    "background-color": "transparent",
                },
                "nav-link-selected": {
                    "background-color": "#f97373",  # 선택된 메뉴 색
                    "color": "#111827",
                    "font-weight": "600",
                },
            },
            key="sidebar_nav_menu",
        )

    # 선택된 라벨 → 코드로 변환해서 session_state에 저장
    try:
        selected_index = labels.index(selected_label)
        selected_code = codes[selected_index]
    except ValueError:
        selected_code = "overview"

    st.session_state["nav_selected_code"] = selected_code

    # 네비게이션과 설정 패널 사이 구분선
    st.markdown("---")

    # -----------------------
    # 2) AI Interview 설정 (접었다/펼쳤다)
    # -----------------------
    # 헤더 + 토글 버튼
    col_title, col_btn = st.columns([4, 1])

    with col_title:
        st.markdown("### ⚙️ AI Interview 설정")

    with col_btn:
        # 한 번 클릭에 바로 열리고 닫히도록 세션 상태만 토글
        is_open = st.session_state.get("sidebar_show_settings", False)
        label = "▾" if is_open else "▸"
        if st.button(label, key="sidebar_settings_toggle"):
            st.session_state["sidebar_show_settings"] = not is_open
            st.rerun()

    # 접힌 상태면 여기서 바로 리턴
    if not st.session_state.get("sidebar_show_settings", False):
        return

    # ---- 설정 내용 ----
    st.write("")  # 간격

    # UI 모드
    st.markdown("#### 🎨 UI 모드")
    st.caption("화면 분위기를 선택하세요. (사이드바 & 카드 스타일)")

    ui_mode = st.radio(
        "UI 모드 선택",
        options=["시스템 기본", "라이트", "다크"],
        key="cfg_theme_mode",
        label_visibility="collapsed",
    )

    st.write("")  # 간격

    # 인터뷰 옵션
    st.markdown("#### 🤖 인터뷰 옵션")

    st.checkbox(
        "RAG 활성화",
        key="cfg_enable_rag",
        value=st.session_state.get("cfg_enable_rag", True),
    )

    st.checkbox(
        "경량 모델 사용 (gpt-4o-mini)",
        key="cfg_use_mini",
        value=st.session_state.get("cfg_use_mini", True),
    )

    st.markdown("<span style='font-size:0.8rem;'>초기 생성 질문 개수</span>", unsafe_allow_html=True)

    # ⚠️ 여기서는 value 를 session_state 값으로만 설정하고,
    # 위젯 생성 이후에는 따로 session_state 를 덮어쓰지 않습니다.
    st.slider(
        "질문 개수(초기 생성 개수)",
        min_value=3,
        max_value=10,
        key="cfg_total_questions",
        value=int(st.session_state.get("cfg_total_questions", 5)),
        label_visibility="collapsed",
    )
