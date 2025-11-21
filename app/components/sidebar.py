# app/components/sidebar.py

from __future__ import annotations

import streamlit as st
from streamlit_option_menu import option_menu


def _ensure_sidebar_state() -> None:
    """사이드바에서 사용하는 공통 세션 키 기본값 세팅."""
    defaults = {
        # 네비게이션 기본 페이지 (코드 값 기준)
        # nav_selected_code는 회원 정보에 따라 결정되므로 여기서 초기화하지 않음
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

    # 로그아웃 상태 확인 및 처리
    member_id = st.session_state.get("member_id")
    
    # 로그아웃 상태(member_id가 None)인 경우
    if not member_id:
        # 회원 정보가 없으면 명시적으로 None으로 설정
        st.session_state["member_id"] = None
        st.session_state["member_name"] = None
        st.session_state["member_birth"] = None
        st.session_state["member_role"] = None
        
        # 로그아웃 상태에서는 nav_selected_code를 강제로 "login"으로 설정
        # 이렇게 하면 로그아웃 직후에도 로그인 페이지가 제대로 표시되고 메뉴가 선택됨
        current_nav = st.session_state.get("nav_selected_code")
        if current_nav != "login":
            # 로그인 성공 직후가 아닌 경우에만 (nav_selected_code가 "login"이 아닌 경우)
            if current_nav not in ["manager", "jobs", "status", "studio", "history", "insights"]:
                st.session_state["nav_selected_code"] = "login"

    # -----------------------
    # 1) 네비게이션 메뉴
    # -----------------------
    st.markdown("### 🧭 메뉴")

    role = st.session_state.get("member_role")
    if role == "ADMIN":
        labels = ["관리자 홈", "면접 스튜디오", "면접 이력", "인사이트", "설정", "로그아웃"]
        codes = ["manager", "studio", "history", "insights", "settings", "login"]
        icons = ["shield-lock", "person-badge", "book", "bar-chart", "gear", "box-arrow-left"]
    elif role:  # 지원자
        labels = ["Jobs", "Status", "로그아웃"]
        codes = ["jobs", "status", "login"]
        icons = ["briefcase", "graph-up", "box-arrow-left"]
    else:
        labels = ["로그인"]
        codes = ["login"]
        icons = ["box-arrow-in-right"]
        # 로그아웃 상태에서는 nav_selected_code를 "login"으로 강제 설정
        # (위에서 이미 처리했지만, 여기서도 한 번 더 확인)
        if not st.session_state.get("member_id"):
            st.session_state["nav_selected_code"] = "login"

    # 현재 선택된 코드 기준으로 default_index 계산
    current_code = st.session_state.get("nav_selected_code", codes[0])
    
    # 로그아웃 상태(member_id가 None)에서는 current_code를 강제로 "login"으로 설정
    # 이렇게 하면 option_menu에서 "로그인" 메뉴가 선택된 상태로 표시됨
    if not st.session_state.get("member_id") and "login" in codes:
        current_code = "login"
        st.session_state["nav_selected_code"] = "login"
        # 로그아웃 상태에서는 highlight_code도 "login"으로 확실히 설정
        highlight_code = "login"
    else:
        # 상세 보기 등 메뉴에 없는 코드(job_detail)는 유지하되, 메뉴 하이라이트는 첫 항목 사용
        highlight_code = current_code
        if current_code not in codes:
            if current_code == "job_detail":
                highlight_code = codes[0]
            else:
                current_code = codes[0]
                highlight_code = codes[0]
                st.session_state["nav_selected_code"] = current_code
    
    # default_index 계산
    try:
        default_index = codes.index(highlight_code)
    except ValueError:
        default_index = 0
    
    # 로그아웃 상태에서는 default_index를 확실히 0으로 설정 (codes에 "login"만 있는 경우)
    if not st.session_state.get("member_id") and len(codes) == 1 and codes[0] == "login":
        default_index = 0

    # Shadcn 느낌의 카드 스타일을 입힌 option_menu
    # 로그아웃 상태에서는 option_menu의 key를 동적으로 변경하여 이전 상태를 초기화
    menu_key = "sidebar_nav_menu"
    if not st.session_state.get("member_id"):
        # 로그아웃 상태에서는 key에 접미사를 추가하여 새로운 위젯으로 인식되도록 함
        menu_key = "sidebar_nav_menu_logout"
        # 이전 key가 있으면 삭제
        if "sidebar_nav_menu" in st.session_state:
            del st.session_state["sidebar_nav_menu"]
    
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
            key=menu_key,
        )

    # 선택된 라벨 → 코드로 변환해서 session_state에 저장
    try:
        selected_index = labels.index(selected_label)
        selected_code = codes[selected_index]
    except ValueError:
        selected_code = current_code  # 알 수 없는 경우 기존 값 유지

    # job_detail 같은 내부 코드가 메뉴에 없을 때는 현재 값을 유지
    if current_code not in codes:
        selected_code = current_code

    # 로그아웃 처리: 기존에 로그인된 상태에서 login을 선택한 경우에만 클리어 및 rerun
    if selected_code == "login" and current_code != "login":
        # 로그아웃 처리: 회원 정보 초기화
        st.session_state["member_id"] = None
        st.session_state["member_name"] = None
        st.session_state["member_birth"] = None
        st.session_state["member_role"] = None
        st.session_state["apply_target_id"] = None
        st.session_state["detail_apply_open"] = False
        st.session_state["job_detail_id"] = None
        # 로그인 입력 필드 초기화
        st.session_state["login_user_name"] = ""
        st.session_state["login_user_birth"] = ""
        st.session_state["login_admin_name"] = ""
        st.session_state["login_mode"] = "지원자 로그인"
        # nav_selected_code를 "login"으로 명시적으로 설정
        st.session_state["nav_selected_code"] = "login"
        # option_menu의 상태도 초기화하여 다음 렌더링에서 올바른 default_index가 사용되도록 함
        if "sidebar_nav_menu" in st.session_state:
            del st.session_state["sidebar_nav_menu"]
        st.rerun()
    else:
        # nav_selected_code 업데이트
        # 단, member_id가 설정되어 있고 nav_selected_code가 "manager"나 "jobs"로 설정되어 있으면
        # 로그인 성공 직후일 수 있으므로 덮어쓰지 않음
        if st.session_state.get("member_id") and current_code in ["manager", "jobs"]:
            # 로그인 성공 직후이므로 nav_selected_code를 유지
            pass
        elif selected_code == "login" and not st.session_state.get("member_id"):
            # 로그아웃 상태에서 로그인 메뉴를 선택한 경우 명시적으로 설정
            st.session_state["nav_selected_code"] = "login"
        else:
            st.session_state["nav_selected_code"] = selected_code

    # 네비게이션과 설정 패널 사이 구분선
    st.markdown("---")

    # -----------------------
    # 2) AI Interview 설정 (관리자에게만 노출)
    # -----------------------
    if role == "ADMIN":
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

        st.radio(
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

        st.slider(
            "질문 개수(초기 생성 개수)",
            min_value=3,
            max_value=10,
            key="cfg_total_questions",
            value=int(st.session_state.get("cfg_total_questions", 5)),
            label_visibility="collapsed",
        )
