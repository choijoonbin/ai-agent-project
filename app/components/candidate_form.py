# app/components/candidate_form.py

import streamlit as st

from utils.state_manager import init_app_session_state
from utils.api_client import call_interview_api
from components.interview_chat import render_evaluation, render_questions


def render_run_tab():
    """🚀 면접 실행 탭"""

    init_app_session_state()

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("📝 기본 정보 & JD")

        job_title = st.text_input("채용 포지션명", value="백엔드 개발자")
        candidate_name = st.text_input("지원자 이름", value="홍길동")

        jd_text = st.text_area(
            "채용 공고 (JD) 텍스트",
            height=260,
            placeholder="채용 공고 내용을 여기에 붙여넣으세요.",
        )

    with col_right:
        st.subheader("📄 이력서 내용")

        resume_text = st.text_area(
            "이력서 텍스트",
            height=320,
            placeholder="지원자의 이력서 내용을 텍스트로 붙여넣으세요.",
        )

    if st.button("🚀 AI 면접 에이전트 실행", use_container_width=True):
        if not jd_text.strip() or not resume_text.strip():
            st.error("JD와 이력서 내용을 모두 입력해주세요.")
        else:
            with st.spinner("AI 면접 에이전트가 분석 중입니다..."):
                try:
                    result = call_interview_api(
                        job_title=job_title,
                        candidate_name=candidate_name,
                        jd_text=jd_text,
                        resume_text=resume_text,
                        total_questions=st.session_state.get(
                            "cfg_total_questions", 5
                        ),
                        enable_rag=st.session_state.get("cfg_enable_rag", True),
                        use_mini=st.session_state.get("cfg_use_mini", True),
                        save_history=True,
                    )
                except Exception as e:
                    st.error(f"API 호출 중 오류가 발생했습니다: {e}")
                else:
                    st.session_state["run_tab_state"] = result.get("state", {})
                    st.session_state["run_tab_interview_id"] = result.get(
                        "interview_id"
                    )

                    st.success("면접 플로우 실행 완료!")
                    if st.session_state["run_tab_interview_id"] is not None:
                        st.info(
                            f"이 면접 이력 ID: {st.session_state['run_tab_interview_id']}"
                        )
                        st.session_state["last_interview_id"] = st.session_state[
                            "run_tab_interview_id"
                        ]

    if st.session_state["run_tab_state"] is not None:
        state = st.session_state["run_tab_state"]
        interview_id = st.session_state["run_tab_interview_id"]

        tab_options = [
            "📊 평가 결과",
            "💬 인터뷰 질문 (답변/재평가)",
            "📦 원시 상태 데이터",
        ]
        tab_key = f"run_result_tab_{interview_id or 'none'}"

        if tab_key not in st.session_state:
            st.session_state[tab_key] = tab_options[0]

        st.markdown(
            """
        <style>
        .stRadio > div {
            display: flex;
            gap: 8px;
        }
        .stRadio > div > label {
            flex: 1;
            text-align: center;
            padding: 8px 4px;
            border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.15);
            cursor: pointer;
        }
        </style>
        """,
            unsafe_allow_html=True,
        )

        selected_tab = st.radio(
            "결과 보기",
            options=tab_options,
            key=tab_key,
            horizontal=True,
            label_visibility="collapsed",
        )

        if selected_tab == "📊 평가 결과":
            render_evaluation(state)
        elif selected_tab == "💬 인터뷰 질문 (답변/재평가)":
            render_questions(
                state,
                interview_id=interview_id,
                session_prefix=f"live_{interview_id}",
                enable_edit=True,
                update_session_state=True,
            )
        else:
            st.json(state)
