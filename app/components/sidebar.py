# app/components/sidebar.py

import streamlit as st


NAV_ITEMS = {
    "Overview": "🏠 Overview",
    "Studio": "🧑‍💼 면접 스튜디오",
    "History": "📚 면접 이력",
    "Insights": "📊 인사이트",
    "Settings": "⚙️ 설정",
}


def render_sidebar() -> None:
    # --- 상단 네비게이션 ---
    st.markdown("### 🧭 메뉴")

    st.radio(
        "메인 메뉴",
        options=list(NAV_ITEMS.keys()),
        format_func=lambda k: NAV_ITEMS[k],
        key="nav_selected",
        label_visibility="collapsed",
    )

    st.markdown("---")

    # --- AI Interview 설정 (접기/펼치기) ---
    col_title, col_toggle = st.columns([4, 1])
    with col_title:
        st.markdown("### ⚙️ AI Interview 설정")
    with col_toggle:
        is_open = st.session_state.get("sidebar_settings_open", True)
        icon = "▲" if is_open else "▼"
        if st.button(icon, key="sidebar_settings_toggle"):
            st.session_state["sidebar_settings_open"] = not is_open

    if not st.session_state.get("sidebar_settings_open", True):
        return

    # --- UI 모드 카드 ---
    with st.container():
        st.markdown("<div class='sidebar-card'>", unsafe_allow_html=True)
        st.markdown("#### 🎨 UI 모드")
        st.caption("화면 분위기를 선택하세요. (사이드바 & 카드 스타일)")

        st.radio(
            "UI 모드 선택",
            options=["시스템 기본", "라이트", "다크"],
            key="cfg_theme_mode",
            horizontal=False,
            label_visibility="collapsed",
        )

        st.markdown("</div>", unsafe_allow_html=True)

    # --- 인터뷰 옵션 카드 ---
    with st.container():
        st.markdown("<div class='sidebar-card'>", unsafe_allow_html=True)
        st.markdown("#### 🤖 인터뷰 옵션")

        st.checkbox("RAG 활성화", key="cfg_enable_rag")
        st.checkbox("경량 모델 사용 (gpt-4o-mini)", key="cfg_use_mini")

        st.markdown(
            "<div class='sidebar-small-label'>초기 생성 질문 개수</div>",
            unsafe_allow_html=True,
        )

        # ⚠️ value 를 주지 않고 key만 사용 → 세션 기본값으로 경고 제거
        st.slider(
            "질문 개수(초기 생성 개수)",
            min_value=3,
            max_value=10,
            key="cfg_total_questions",
            label_visibility="collapsed",
        )

        st.markdown("</div>", unsafe_allow_html=True)
