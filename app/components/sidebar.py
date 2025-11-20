# app/components/sidebar.py

import streamlit as st


def render_sidebar():
    """
    사이드바 전체 렌더링.
    - 상단에 'AI Interview 설정' 헤더 + 접기/펼치기 토글 버튼
    - 펼쳐진 상태에서만 UI 모드 / 인터뷰 옵션 카드 보여줌
    """

    # 접기/펼치기 상태 기본값
    if "sidebar_settings_open" not in st.session_state:
        st.session_state["sidebar_settings_open"] = True

    is_open = st.session_state["sidebar_settings_open"]

    # --- 헤더 + 토글 버튼 행 --- #
    header_col, toggle_col = st.columns([4, 1])

    with header_col:
        st.markdown("### ⚙️ AI Interview 설정")

    with toggle_col:
        # 펼쳐져 있으면 ▲, 접혀 있으면 ▼ 느낌으로
        toggle_label = "▲" if is_open else "▼"
        if st.button(
            toggle_label,
            key="sidebar_toggle_btn",
            help="설정 접기 / 펼치기",
        ):
            st.session_state["sidebar_settings_open"] = not is_open
            # 버튼 클릭 후 바로 상태 반영되도록 재실행
            st.rerun()

    # 접혀 있으면 여기서 종료 (헤더만 보이게)
    if not st.session_state["sidebar_settings_open"]:
        return

    # -------------------------
    # 아래부터는 '펼쳐진 상태'에서만 보이는 내용
    # -------------------------

    # --- UI 모드 카드 --- #
    with st.container():
        st.markdown("<div class='sidebar-card'>", unsafe_allow_html=True)
        st.markdown("#### 🎨 UI 모드")
        st.caption("화면 분위기를 선택하세요. (사이드바 & 카드 스타일)")

        current_mode = st.session_state.get("cfg_theme_mode", "시스템 기본")

        st.radio(
            "UI 모드 선택",
            options=["시스템 기본", "라이트", "다크"],
            index=["시스템 기본", "라이트", "다크"].index(current_mode),
            key="cfg_theme_mode",
            horizontal=False,
            label_visibility="collapsed",
        )
        st.markdown("</div>", unsafe_allow_html=True)

    # --- 인터뷰 / RAG 옵션 카드 --- #
    with st.container():
        st.markdown("<div class='sidebar-card'>", unsafe_allow_html=True)
        st.markdown("#### 🤖 인터뷰 옵션")

        st.checkbox(
            "RAG 활성화",
            key="cfg_enable_rag",
        )
        st.checkbox(
            "경량 모델 사용 (gpt-4o-mini)",
            key="cfg_use_mini",
        )

        st.markdown(
            "<div class='sidebar-small-label'>초기 생성 질문 개수</div>",
            unsafe_allow_html=True,
        )
        st.slider(
            "질문 개수(초기 생성 개수)",
            min_value=3,
            max_value=10,
            value=st.session_state.get("cfg_total_questions", 5),
            key="cfg_total_questions",
            label_visibility="collapsed",
        )

        st.markdown("</div>", unsafe_allow_html=True)
