# app/utils/state_manager.py

import streamlit as st


def init_app_session_state() -> None:
    """
    Streamlit rerun 마다 공통 세션 키들을 한 번에 초기화/보정하는 유틸.

    - 기존에 여기저기 흩어져 있던 if "xxx" not in ... 체크를 한 곳으로 모음
    - 기본값만 세팅하고, 나머지는 각 컴포넌트에서 그대로 사용
    """
    defaults = {
        # 인터뷰 옵션
        "cfg_enable_rag": True,
        "cfg_use_mini": True,
        "cfg_total_questions": 5,
        "cfg_theme_mode": "시스템 기본",

        # Studio 실행 결과
        "run_tab_state": None,
        "run_tab_interview_id": None,

        # History 선택/캐시
        "history_selected_id": None,
        "last_interview_id": None,

        # Navigation (사이드바 상단 메뉴)
        "nav_selected": "Studio",

        # 사이드바 - AI 설정 패널 펼침 여부
        "sidebar_ai_settings_open": True,

        # Insights 결과 캐시
        "insights_result": None,
    }

    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def apply_theme_css() -> None:
    """
    전체 앱 공통 스타일 주입.

    - 사이드바 배경/카드 스타일
    - 본문 카드/헤더 스타일
    - 모바일(좁은 화면) 대응 약간 보정
    """
    mode = st.session_state.get("cfg_theme_mode", "시스템 기본")

    # 공통 CSS
    base_css = """
    /* 전체 폰트/배경 약간 정리 */
    html, body, [data-testid="stAppViewContainer"] {
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    /* 메인 컨테이너 폭 약간 넓게 */
    [data-testid="block-container"] {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
        max-width: 1180px;
    }

    /* 공통 섹션 카드 */
    .main-section-card {
        padding: 1.1rem 1.0rem;
        border-radius: 14px;
        border: 1px solid rgba(148, 163, 184, 0.45);
        background: rgba(15, 23, 42, 0.90);
        margin-bottom: 1.1rem;
    }

    .main-section-card.light-mode {
        background: rgba(248, 250, 252, 0.96);
    }

    .section-title {
        font-size: 1.05rem;
        font-weight: 600;
        margin-bottom: 0.4rem;
    }

    .section-subtitle {
        font-size: 0.85rem;
        opacity: 0.8;
        margin-bottom: 0.6rem;
    }

    /* 사이드바 전체 래퍼 */
    [data-testid="stSidebar"] {
        backdrop-filter: blur(14px);
        border-right: 1px solid rgba(148, 163, 184, 0.35);
    }

    /* 사이드바 내부 패딩 정리 */
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 1.2rem;
    }

    /* 사이드바 카드 스타일 */
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

    .sidebar-small-label {
        font-size: 0.8rem;
        opacity: 0.85;
        margin-bottom: 0.2rem;
    }

    /* 네비게이션 라디오를 탭처럼 보이게 */
    .nav-radio > div {
        display: flex;
        gap: 6px;
        flex-wrap: wrap;
    }

    .nav-radio > div > label {
        flex: 1 1 48%;
        text-align: center;
        padding: 6px 4px;
        border-radius: 999px;
        border: 1px solid rgba(148, 163, 184, 0.4);
        font-size: 0.80rem;
        cursor: pointer;
        white-space: nowrap;
    }

    .hero-image-wrapper {
        margin-top: -0.5rem;
        margin-left: -2.2rem;
    }

    /* 모바일/좁은 화면 대응 */
    @media (max-width: 900px) {
        [data-testid="block-container"] {
            padding-left: 0.9rem;
            padding-right: 0.9rem;
        }
        .nav-radio > div > label {
            flex: 1 1 100%;
        }
    }
    """

    # 모드별 톤
    if mode == "라이트":
        tone_css = """
        [data-testid="stSidebar"] {
            background: radial-gradient(circle at top left, rgba(59, 130, 246, 0.10), transparent),
                        radial-gradient(circle at bottom right, rgba(236, 72, 153, 0.08), transparent);
        }
        .sidebar-card {
            background: rgba(248, 250, 252, 0.96);
            border-color: rgba(148, 163, 184, 0.55);
        }
        .sidebar-card h4 {
            color: #0f172a;
        }
        .main-section-card {
            background: rgba(248, 250, 252, 0.96);
            border-color: rgba(148, 163, 184, 0.55);
        }
        """
    elif mode == "다크":
        tone_css = """
        [data-testid="stSidebar"] {
            background: radial-gradient(circle at top left, rgba(56, 189, 248, 0.24), transparent),
                        radial-gradient(circle at bottom right, rgba(139, 92, 246, 0.28), transparent);
        }
        .sidebar-card {
            background: rgba(15, 23, 42, 0.96);
            border-color: rgba(148, 163, 184, 0.60);
        }
        """
    else:
        # 시스템 기본
        tone_css = """
        [data-testid="stSidebar"] {
            background: radial-gradient(circle at top left, rgba(96, 165, 250, 0.22), transparent),
                        radial-gradient(circle at bottom right, rgba(236, 72, 153, 0.18), transparent);
        }
        .sidebar-card {
            background: rgba(15, 23, 42, 0.92);
        }
        """

    full_css = f"<style>{base_css}{tone_css}</style>"
    st.markdown(full_css, unsafe_allow_html=True)
