# app/components/history_panel.py

import json
import html

import streamlit as st

from utils.state_manager import init_app_session_state
from utils.api_client import fetch_interview_list, fetch_interview_detail
from components.interview_chat import render_evaluation, render_questions


def render_history_tab():
    """📚 면접 이력 조회 탭"""

    init_app_session_state()

    st.subheader("📚 면접 이력")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🔄 이력 새로고침", use_container_width=True):
            selected_id = st.session_state.get("history_selected_id")
            if selected_id is not None:
                cache_key = f"history_state_{selected_id}"
                if cache_key in st.session_state:
                    del st.session_state[cache_key]
            st.session_state["history_selected_id"] = None
            st.rerun()

    with col2:
        st.caption("※ 최신 20건 이력을 조회합니다.")

    interviews = fetch_interview_list(limit=20)
    if not interviews:
        st.info("저장된 면접 이력이 없습니다.")
        return

    selected_id = st.session_state.get("history_selected_id")

    for item in interviews:
        interview_id = item["id"]
        title = item["job_title"]
        name = item["candidate_name"]
        created_at = item["created_at"]
        total_questions = item["total_questions"]
        status = item["status"]

        cache_key = f"history_state_{interview_id}"

        with st.container(border=True):
            st.markdown(f"#### {title} - {name}")
            st.caption(
                f"🗓 {created_at} | 질문 수(초기): {total_questions} | 상태: {status}"
            )

            col_a, col_b = st.columns([3, 1])

            # ----- JD 영역 ----- #
            with col_a:
                jd_full = item.get("jd_text", "") or ""

                jd_expanded_key = f"history_jd_expanded_{interview_id}"
                if jd_expanded_key not in st.session_state:
                    st.session_state[jd_expanded_key] = False

                is_jd_expanded = st.session_state[jd_expanded_key]

                if is_jd_expanded:
                    display_text = jd_full
                else:
                    if len(jd_full) > 250:
                        display_text = jd_full[:250] + "..."
                    else:
                        display_text = jd_full

                safe_text = html.escape(display_text)
                max_height = "none" if is_jd_expanded else "80px"

                jd_box_html = f"""
                <div style="
                    background-color: rgba(255,255,255,0.02);
                    padding: 10px;
                    border-radius: 6px;
                    border: 1px solid rgba(255,255,255,0.1);
                    max-height: {max_height};
                    overflow-y: auto;
                    font-size: 0.85rem;
                ">
                    <pre style="white-space: pre-wrap; margin: 0;">{safe_text}</pre>
                </div>
                """
                st.markdown(jd_box_html, unsafe_allow_html=True)

                toggle_label = "▲ JD 접기" if is_jd_expanded else "▼ JD 전체 보기"
                if st.button(
                    toggle_label,
                    key=f"jd_toggle_{interview_id}",
                    use_container_width=True,
                ):
                    st.session_state[jd_expanded_key] = not is_jd_expanded
                    st.rerun()

            # ----- 이력 상세 열기 / 닫기 ----- #
            with col_b:
                is_open = selected_id == interview_id
                btn_label = "✖ 닫기" if is_open else "👀 이력 보기"

                if st.button(
                    btn_label,
                    key=f"toggle_{interview_id}",
                    use_container_width=True,
                ):
                    if is_open:
                        st.session_state["history_selected_id"] = None
                        if cache_key in st.session_state:
                            del st.session_state[cache_key]
                    else:
                        prev_id = st.session_state.get("history_selected_id")
                        if prev_id is not None and prev_id != interview_id:
                            prev_cache_key = f"history_state_{prev_id}"
                            if prev_cache_key in st.session_state:
                                del st.session_state[prev_cache_key]

                        st.session_state["history_selected_id"] = interview_id
                    st.rerun()

            # ----- 선택된 카드라면 상세 패널 렌더 ----- #
            if selected_id == interview_id:
                detail = fetch_interview_detail(interview_id)
                if not detail:
                    st.error("선택한 이력 정보를 불러오지 못했습니다.")
                else:
                    if cache_key in st.session_state:
                        state = st.session_state[cache_key]
                    else:
                        try:
                            state = json.loads(detail.get("state_json", "{}"))
                        except json.JSONDecodeError:
                            st.error("저장된 state_json을 파싱할 수 없습니다.")
                            state = {}
                        st.session_state[cache_key] = state

                    st.markdown("---")

                    with st.container(border=True):
                        header_col_left, header_col_right = st.columns([4, 1])

                        with header_col_left:
                            st.markdown(
                                f"##### 📄 선택한 이력 상세 (ID: {interview_id})  \n"
                                f"**{detail.get('job_title', '')} - {detail.get('candidate_name', '')}**"
                            )

                        with header_col_right:
                            if st.button(
                                "✖ 이력 상세 닫기",
                                key=f"close_detail_{interview_id}",
                                use_container_width=True,
                            ):
                                st.session_state["history_selected_id"] = None
                                if cache_key in st.session_state:
                                    del st.session_state[cache_key]
                                st.rerun()

                        tab1, tab2, tab3 = st.tabs(
                            ["📊 평가 결과", "💬 인터뷰 질문 (답변/재평가)", "📦 원시 상태 데이터"]
                        )

                        with tab1:
                            render_evaluation(state)

                        with tab2:
                            render_questions(
                                state,
                                interview_id=interview_id,
                                session_prefix=f"history_{interview_id}",
                                enable_edit=True,
                                update_session_state=False,
                            )

                        with tab3:
                            st.json(state)
