# app/main.py

import os
import json
import requests

import streamlit as st
from dotenv import load_dotenv

# app/.env 로드
load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")


# ---------- API 호출 함수들 ---------- #

def call_interview_api(
    job_title: str,
    candidate_name: str,
    jd_text: str,
    resume_text: str,
    total_questions: int = 5,
    enable_rag: bool = True,
    use_mini: bool = True,
    save_history: bool = True,
):
    url = f"{API_BASE_URL}/workflow/interview/run"

    payload = {
        "job_title": job_title,
        "candidate_name": candidate_name,
        "jd_text": jd_text,
        "resume_text": resume_text,
        "total_questions": total_questions,
        "enable_rag": enable_rag,
        "use_mini": use_mini,
        "save_history": save_history,
    }

    response = requests.post(url, json=payload, timeout=180)
    if response.status_code != 200:
        raise RuntimeError(f"API 오류: {response.status_code} - {response.text}")

    return response.json()


def fetch_interview_list(limit: int = 20):
    """면접 이력 목록 조회"""
    url = f"{API_BASE_URL}/interviews/?limit={limit}"
    response = requests.get(url, timeout=30)
    if response.status_code != 200:
        st.error(f"면접 이력 조회 실패: {response.status_code}")
        return []
    return response.json()


def fetch_interview_detail(interview_id: int):
    """특정 면접 이력 상세 조회"""
    url = f"{API_BASE_URL}/interviews/{interview_id}"
    response = requests.get(url, timeout=30)
    if response.status_code != 200:
        st.error(f"면접 이력 상세 조회 실패: {response.status_code}")
        return None
    return response.json()


def call_rejudge_api(interview_id: int, qa_history: list[dict]):
    """수정된 질문/답변을 기반으로 Judge만 재실행"""
    url = f"{API_BASE_URL}/workflow/interview/rejudge"

    enable_rag = st.session_state.get("cfg_enable_rag", True)
    use_mini = st.session_state.get("cfg_use_mini", True)

    payload = {
        "interview_id": interview_id,
        "qa_history": qa_history,
        "enable_rag": enable_rag,
        "use_mini": use_mini,
    }

    response = requests.post(url, json=payload, timeout=180)
    if response.status_code != 200:
        raise RuntimeError(f"재평가 API 오류: {response.status_code} - {response.text}")

    return response.json()


# ---------- 결과 렌더링 유틸 ---------- #

def render_evaluation(state: dict):
    st.subheader("📊 최종 평가 결과")

    evaluation = state.get("evaluation")
    if not evaluation:
        st.info("평가 결과가 없습니다.")
        return

    summary = evaluation.get("summary")
    strengths = evaluation.get("strengths", [])
    weaknesses = evaluation.get("weaknesses", [])
    recommendation = evaluation.get("recommendation")
    scores = evaluation.get("scores", {})
    raw_text = evaluation.get("raw_text")

    if recommendation:
        st.markdown(f"### 🏁 최종 추천: **{recommendation}**")

    if summary:
        st.markdown("#### 요약")
        st.write(summary)

    if strengths:
        st.markdown("#### ✅ 강점")
        for s in strengths:
            st.markdown(f"- {s}")

    if weaknesses:
        st.markdown("#### ❌ 약점")
        for w in weaknesses:
            st.markdown(f"- {w}")

    if scores:
        st.markdown("#### 📈 역량별 점수")
        for label, score in scores.items():
            st.markdown(f"- **{label}**: {score}")

    with st.expander("LLM 원문 평가 텍스트 보기"):
        st.write(raw_text)


def render_questions(
    state: dict,
    *,
    interview_id: int | None = None,
    session_prefix: str = "",
    enable_edit: bool = True,
    update_session_state: bool = False,
):
    """
    질문 리스트 + (선택적으로) 답변 입력 UI + 재평가 버튼.
    - interview_id 가 주어지면 재평가 API 호출 가능.
    - session_prefix 로 각 text_area key를 구분.
    - update_session_state=True 이면 답변 입력 시 세션 상태도 업데이트.
    """
    st.subheader("💬 제안된 인터뷰 질문 리스트")

    qa_history = state.get("qa_history", [])
    if not qa_history:
        st.info("질문 리스트가 없습니다.")
        return

    updated_qa: list[dict] = []

    for i, turn in enumerate(qa_history, start=1):
        category = turn.get("category") or "일반"
        question = turn.get("question")
        answer = turn.get("answer", "")

        with st.container(border=True):
            st.markdown(f"**Q{i}. ({category})** {question}")

            if enable_edit:
                # 사용자가 수정 가능한 답변 입력 영역
                key = f"{session_prefix}_answer_{i}"
                new_answer = st.text_area(
                    "답변 입력 또는 수정",
                    value=answer,
                    key=key,
                    height=80,
                )
                final_answer = new_answer
            else:
                final_answer = answer
                if answer:
                    st.markdown(f"**A{i}.** {answer}")
                else:
                    st.caption("※ 아직 답변이 입력되지 않았습니다.")

            # 재평가용 qa_history 구성
            updated_qa.append(
                {
                    "interviewer": turn.get("interviewer", ""),
                    "question": question,
                    "answer": final_answer,
                    "category": category,
                    "score": turn.get("score"),
                    "notes": turn.get("notes"),
                }
            )

    # 진행률 표시 (몇 개 답변이 채워졌는지) - 업데이트된 답변 기준으로 계산
    answered_count = sum(1 for qa in updated_qa if qa.get("answer", "").strip())
    total = len(updated_qa)
    ratio = answered_count / total if total > 0 else 0
    st.progress(ratio, text=f"답변 완료 {answered_count}/{total}")

    # 재평가 버튼
    if enable_edit and interview_id is not None:
        if st.button(
            "🧠 이 답변들로 재평가 실행",
            use_container_width=True,
            key=f"{session_prefix}_rejudge_btn",
        ):
            with st.spinner("Judge 에이전트가 재평가 중입니다..."):
                try:
                    result = call_rejudge_api(interview_id, updated_qa)
                except Exception as e:
                    st.error(f"재평가 중 오류가 발생했습니다: {e}")
                    return

                new_state = result.get("state", {})
                st.success("재평가가 완료되었습니다!")
                
                # 세션 상태 업데이트 (재평가 결과도 반영)
                if update_session_state and session_prefix.startswith("live_"):
                    if "run_tab_state" in st.session_state:
                        st.session_state["run_tab_state"]["evaluation"] = new_state.get("evaluation")
                        st.session_state["run_tab_state"]["qa_history"] = updated_qa

                # 재평가 결과 바로 아래에 표시
                st.markdown("---")
                st.markdown("### 🔁 재평가 결과")
                render_evaluation(new_state)


# ---------- 개별 화면 렌더링 ---------- #

def render_run_tab():
    """면접 실행 탭"""

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

    # 세션 상태 초기화 (필요한 키들이 없으면 초기화)
    if "run_tab_state" not in st.session_state:
        st.session_state["run_tab_state"] = None
    if "run_tab_interview_id" not in st.session_state:
        st.session_state["run_tab_interview_id"] = None

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
                        total_questions=st.session_state.get("cfg_total_questions", 5),
                        enable_rag=st.session_state.get("cfg_enable_rag", True),
                        use_mini=st.session_state.get("cfg_use_mini", True),
                        save_history=True,
                    )
                except Exception as e:
                    st.error(f"API 호출 중 오류가 발생했습니다: {e}")
                else:
                    state = result.get("state", {})
                    interview_id = result.get("interview_id")
                    
                    # 세션 상태에 결과 저장
                    st.session_state["run_tab_state"] = state
                    st.session_state["run_tab_interview_id"] = interview_id
                    
                    st.success("면접 플로우 실행 완료!")
                    if interview_id is not None:
                        st.info(f"이 면접 이력 ID: {interview_id}")
                        st.session_state["last_interview_id"] = interview_id

    # 세션 상태에 결과가 있으면 항상 표시 (버튼 클릭 여부와 관계없이)
    if st.session_state["run_tab_state"] is not None:
        state = st.session_state["run_tab_state"].copy()  # 복사본 사용
        interview_id = st.session_state["run_tab_interview_id"]
        
        # 답변 입력 시 세션 상태 업데이트 (실시간 반영)
        # st.text_area의 값은 이미 세션 상태에 저장되므로, 
        # render_questions 호출 전에 세션 상태의 qa_history를 업데이트
        if interview_id is not None:
            qa_history = state.get("qa_history", [])
            for i, turn in enumerate(qa_history):
                key = f"live_{interview_id}_answer_{i+1}"
                if key in st.session_state:
                    new_answer = st.session_state[key]
                    # 세션 상태와 state 모두 업데이트
                    if st.session_state["run_tab_state"]["qa_history"][i].get("answer") != new_answer:
                        st.session_state["run_tab_state"]["qa_history"][i]["answer"] = new_answer
                    state["qa_history"][i]["answer"] = new_answer
        
        # 탭으로 결과 표시
        tab1, tab2, tab3 = st.tabs(
            ["📊 평가 결과", "💬 인터뷰 질문 (답변/재평가)", "📦 원시 상태 데이터"]
        )

        with tab1:
            render_evaluation(state)

        with tab2:
            render_questions(
                state,
                interview_id=interview_id,
                session_prefix=f"live_{interview_id}",
                enable_edit=True,
                update_session_state=True,
            )

        with tab3:
            st.json(state)


def render_history_tab():
    """면접 이력 조회 탭"""

    st.subheader("📚 면접 이력")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🔄 이력 새로고침", use_container_width=True):
            st.rerun()

    with col2:
        st.caption("※ 최신 20건 이력을 조회합니다.")

    interviews = fetch_interview_list(limit=20)
    if not interviews:
        st.info("저장된 면접 이력이 없습니다.")
        return

    for item in interviews:
        interview_id = item["id"]
        title = item["job_title"]
        name = item["candidate_name"]
        created_at = item["created_at"]
        total_questions = item["total_questions"]
        status = item["status"]

        with st.container(border=True):
            st.markdown(f"#### {title} - {name}")
            st.caption(f"🗓 {created_at} | 질문 수: {total_questions} | 상태: {status}")

            col_a, col_b = st.columns([3, 1])

            with col_a:
                jd_preview = item.get("jd_text", "") or ""
                if len(jd_preview) > 250:
                    jd_preview = jd_preview[:250] + "..."
                st.text_area(
                    "JD (요약 보기용)",
                    value=jd_preview,
                    height=80,
                    disabled=True,
                    label_visibility="collapsed",
                    key=f"jd_preview_{interview_id}",  # ← 여기서 key 추가
                )

            with col_b:
                if st.button(
                    "👀 이력 보기",
                    key=f"view_{interview_id}",
                    use_container_width=True,
                ):
                    detail = fetch_interview_detail(interview_id)
                    if detail:
                        # state_json 파싱
                        try:
                            state = json.loads(detail.get("state_json", "{}"))
                        except json.JSONDecodeError:
                            st.error("저장된 state_json을 파싱할 수 없습니다.")
                            continue

                        st.markdown("---")
                        st.markdown(f"### 선택한 이력 (ID: {interview_id})")

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
                            )

                        with tab3:
                            st.json(state)


# ---------- 메인 ---------- #

def main():
    st.set_page_config(
        page_title="AI Interview Agent",
        page_icon="🧑‍💼",
        layout="wide",
    )

    st.title("🧑‍💼 AI Interview Agent (AI 채용 면접관)")
    st.markdown(
        """
        이 앱은 JD(채용공고)와 지원자의 이력서를 기반으로:
        - JD 분석  
        - 이력서 분석  
        - 맞춤형 인터뷰 질문 생성  
        - 최종 평가 리포트 생성  
        - 질문별 답변 입력 후 재평가  
        
        까지 한 번에 수행하는 **AI 기반 면접 보조 에이전트**입니다.
        """
    )

    # 사이드바 설정
    with st.sidebar:
        st.header("⚙️ 설정")
        enable_rag = st.checkbox("RAG 활성화", value=True)
        use_mini = st.checkbox("경량 모델 사용(gpt-4o-mini)", value=True)
        total_questions = st.slider("질문 개수", min_value=3, max_value=10, value=5)

        # 세션에 설정 저장 (run 탭에서 사용)
        st.session_state["cfg_enable_rag"] = enable_rag
        st.session_state["cfg_use_mini"] = use_mini
        st.session_state["cfg_total_questions"] = total_questions

    tab_run, tab_history = st.tabs(["🚀 면접 실행", "📚 면접 이력"])

    with tab_run:
        render_run_tab()

    with tab_history:
        render_history_tab()


if __name__ == "__main__":
    main()
