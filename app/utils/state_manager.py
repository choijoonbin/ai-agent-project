# app/utils/state_manager.py

import streamlit as st


def init_app_session_state():
    """
    Streamlit rerun마다 공통 세션 키들을 한 번에 초기화/보정하는 유틸.
    """
    defaults = {
        "cfg_enable_rag": True,
        "cfg_use_mini": True,
        "cfg_total_questions": 5,
        "run_tab_state": None,
        "run_tab_interview_id": None,
        "history_selected_id": None,
        "last_interview_id": None,  # 마지막으로 실행한 인터뷰 ID
        "cfg_theme_mode": "시스템 기본",
    }

    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def apply_theme_css():
    """
    cfg_theme_mode 값에 따라 전체적인 톤 + 사이드바를 살짝 다르게 스타일링.
    """
    mode = st.session_state.get("cfg_theme_mode", "시스템 기본")

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
        tone_css = """
        .sidebar-card {
            background: rgba(15, 23, 42, 0.92);
        }
        """

    full_css = f"<style>{base_css}{tone_css}</style>"
    st.markdown(full_css, unsafe_allow_html=True)
