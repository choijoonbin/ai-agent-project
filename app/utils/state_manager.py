# app/utils/state_manager.py

import streamlit as st


def init_app_session_state() -> None:
    """
    Streamlit rerun마다 공통 세션 키들을 한 번에 초기화/보정하는 유틸.
    - 각 탭/화면에서 중복으로 if "xxx" not in ... 체크하던 코드들을 모아둠.
    """
    defaults = {
        # 인터뷰 옵션
        "cfg_enable_rag": True,
        "cfg_use_mini": True,
        "cfg_total_questions": 5,

        # UI 모드
        "cfg_theme_mode": "시스템 기본",

        # 네비게이션 (사이드바 상단 메뉴)
        "nav_selected": "Studio",

        # 실행 중 인터뷰 상태
        "run_tab_state": None,
        "run_tab_interview_id": None,
        "last_interview_id": None,

        # 히스토리 화면
        "history_selected_id": None,

        # 사이드바 설정 접기/펼치기
        "sidebar_settings_open": True,
    }

    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def apply_theme_css() -> None:
    """
    cfg_theme_mode 값에 따라 전체적인 톤 + 사이드바를 스타일링.
    실제로는 <style> 태그 하나만 주입하고, 내용은 화면에 노출되지 않도록 한다.
    """
    mode = st.session_state.get("cfg_theme_mode", "시스템 기본")

    # 🔹 공통 CSS
    base_css = """
    /* 사이드바 전체 래퍼 */
    [data-testid="stSidebar"] {
        background: radial-gradient(circle at top left, rgba(96, 165, 250, 0.28), transparent),
                    radial-gradient(circle at bottom right, rgba(236, 72, 153, 0.2), transparent);
        backdrop-filter: blur(14px);
        border-right: 1px solid rgba(148, 163, 184, 0.35);
    }

    /* 사이드바 내부 패딩 정리 */
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 1.2rem;
    }

    /* 사이드바 안의 카드 스타일 */
    .sidebar-card {
        border-radius: 12px;
        padding: 0.9rem 0.85rem;
        margin-bottom: 0.9rem;
        border: 1px solid rgba(148, 163, 184, 0.45);
        background: rgba(15, 23, 42, 0.90);
    }

    .sidebar-card h4 {
        font-size: 0.9rem;
        margin-bottom: 0.6rem;
    }

    /* 슬라이더 라벨 조금 압축 */
    .sidebar-small-label {
        font-size: 0.8rem;
        opacity: 0.85;
        margin-bottom: 0.2rem;
    }

    .hero-image-wrapper {
        margin-top: -0.5rem;
        margin-left: -2.2rem;
    }
    """

    # 🔹 모드별 추가 CSS
    if mode == "라이트":
        tone_css = """
        [data-testid="stSidebar"] {
            background: radial-gradient(circle at top left, rgba(59, 130, 246, 0.08), transparent),
                        radial-gradient(circle at bottom right, rgba(236, 72, 153, 0.06), transparent);
            backdrop-filter: blur(10px);
        }
        .sidebar-card {
            background: rgba(248, 250, 252, 0.94);
            border-color: rgba(148, 163, 184, 0.55);
        }
        .sidebar-card h4 {
            color: #0f172a;
        }
        """
    elif mode == "다크":
        tone_css = """
        [data-testid="stSidebar"] {
            background: radial-gradient(circle at top left, rgba(56, 189, 248, 0.22), transparent),
                        radial-gradient(circle at bottom right, rgba(139, 92, 246, 0.25), transparent);
        }
        .sidebar-card {
            background: rgba(15, 23, 42, 0.96);
            border-color: rgba(148, 163, 184, 0.60);
        }
        """
    else:
        # 시스템 기본
        tone_css = """
        .sidebar-card {
            background: rgba(15, 23, 42, 0.92);
        }
        """

    full_css = f"<style>{base_css}{tone_css}</style>"
    st.markdown(full_css, unsafe_allow_html=True)
