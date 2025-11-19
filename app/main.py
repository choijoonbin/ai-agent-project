# app/main.py

import os
import json
import requests

import streamlit as st
from dotenv import load_dotenv

# app/.env 로드
load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9898/api/v1")


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


def call_followup_api(
    interview_id: int,
    question: str,
    answer: str,
    category: str | None = None,
):
    """특정 질문/답변에 대한 후속 질문(재질문) 생성"""
    url = f"{API_BASE_URL}/workflow/interview/followup"

    payload = {
        "interview_id": interview_id,
        "question": question,
        "answer": answer,
        "category": category,
        "use_mini": True,
    }

    response = requests.post(url, json=payload, timeout=120)
    if response.status_code != 200:
        raise RuntimeError(
            f"후속 질문 API 오류: {response.status_code} - {response.text}"
        )

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
        # 👇 여기서 오타였던 markmarkdown 을 markdown 으로 수정
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
    질문 리스트 + 답변 입력 + 후속 질문 + 재평가 UI (트리형 렌더링).

    - qa_history 는 평면 리스트지만,
      화면에서는 "부모 질문 → 그 아래 들여쓰기된 후속질문들" 형태로 표시.
    - 인터랙션(답변, 후속질문 생성, 재평가)은 기존과 동일하게 동작.
    """
    st.subheader("💬 인터뷰 세션 (질문 & 답변)")

    qa_history = state.get("qa_history", [])
    if not qa_history:
        st.info("질문 리스트가 없습니다.")
        return

    # ---------- 1) 트리 구조 구성 (parent_index 기준) ---------- #
    nodes: list[dict] = []
    for idx, turn in enumerate(qa_history):
        nodes.append({"idx": idx, "turn": turn, "children": []})

    by_idx = {n["idx"]: n for n in nodes}
    roots: list[dict] = []

    for n in nodes:
        parent_index = n["turn"].get("parent_index")
        if parent_index is None:
            roots.append(n)
        else:
            parent = by_idx.get(parent_index)
            if parent:
                parent["children"].append(n)
            else:
                # 부모가 없으면 루트로 취급 (방어 코드)
                roots.append(n)

    # ---------- 2) 렌더링 준비 ---------- #
    progress_placeholder = st.empty()
    updated_qa: list[dict] = []
    answered_count = 0

    display_counter = {"value": 0}  # Q 번호(화면상 Q1, Q2, ...)

    # ---------- 3) 재귀 렌더링 함수 ---------- #
    def render_node(node: dict, level: int):
        nonlocal answered_count, updated_qa

        idx = node["idx"]
        turn = node["turn"]

        display_counter["value"] += 1
        display_no = display_counter["value"]

        question = turn.get("question", "")
        answer = turn.get("answer", "")

        category = turn.get("category") or "일반"
        interviewer = turn.get("interviewer", "") or "Interviewer"

        is_followup = bool(turn.get("is_followup", False))
        parent_index = turn.get("parent_index")

        # 들여쓰기(레벨별 좌측 마진) – 질문 헤더에만 적용
        indent_px = level * 24

        with st.container(border=True):
            # ---- 헤더 (Qn + 카테고리 + 후속표시) ---- #
            if is_followup:
                parent_label = (
                    f"(Q{(parent_index or 0) + 1}의 후속 질문)"
                    if parent_index is not None
                    else "(후속 질문)"
                )
                header_html = (
                    f"<div style='margin-left:{indent_px}px'>"
                    f"<strong>Q{display_no}. 🔁 {category} {parent_label}</strong>"
                    f"</div>"
                )
            else:
                header_html = (
                    f"<div style='margin-left:{indent_px}px'>"
                    f"<strong>Q{display_no}. ({category})</strong>"
                    f"</div>"
                )

            st.markdown(header_html, unsafe_allow_html=True)

            # ---- 질문/답변 2열 레이아웃 ---- #
            q_col, _, a_col = st.columns([3, 0.2, 3])

            with q_col:
                st.markdown(f"👨‍💼 **{interviewer}**")
                st.markdown(f"> {question}")

            if enable_edit:
                with a_col:
                    st.markdown("🙋‍♂ **Candidate**")

                    key = f"{session_prefix}_answer_{idx}"
                    if key not in st.session_state:
                        st.session_state[key] = answer or ""

                    _ = st.text_area(
                        "답변 입력 또는 수정",
                        key=key,
                        height=100,
                        label_visibility="collapsed",
                    )
                    final_answer = st.session_state[key]
            else:
                with a_col:
                    st.markdown("🙋‍♂ **Candidate**")
                    final_answer = answer
                    if answer:
                        st.markdown(f"> {answer}")
                    else:
                        st.caption("※ 아직 답변이 입력되지 않았습니다.")

            if final_answer and final_answer.strip():
                answered_count += 1

            # ---- 후속 질문 생성 버튼 ---- #
            if enable_edit and interview_id is not None:
                st.markdown("")
                col_f1, col_f2 = st.columns([1.5, 3.5])
                with col_f1:
                    if st.button(
                        "↪️ 이 질문에 대한 후속 질문 생성",
                        key=f"{session_prefix}_followup_btn_{idx}",
                        use_container_width=True,
                    ):
                        if not final_answer.strip():
                            st.warning("먼저 이 질문에 대한 답변을 입력해주세요.")
                        else:
                            with st.spinner("후속 질문 생성 중..."):
                                try:
                                    resp = call_followup_api(
                                        interview_id=interview_id,
                                        question=question,
                                        answer=final_answer,
                                        category=category,
                                    )
                                    followup_q = (
                                        resp.get("followup_question", "").strip()
                                    )
                                    if followup_q:
                                        new_turn = {
                                            "interviewer": interviewer,
                                            "question": followup_q,
                                            "answer": "",
                                            "category": category,
                                            "is_followup": True,
                                            "parent_index": idx,
                                        }

                                        # run_tab_state & state 양쪽에 반영
                                        if (
                                            session_prefix.startswith("live_")
                                            and "run_tab_state" in st.session_state
                                            and st.session_state["run_tab_state"] is not None
                                        ):
                                            # 실행 중인 세션의 qa_history 에만 한 번 append
                                            st.session_state["run_tab_state"]["qa_history"].append(
                                                new_turn
                                            )
                                            qa_history = st.session_state["run_tab_state"]["qa_history"]
                                        else:
                                            # 이력 탭에서 보는 경우 등은 현재 state 의 qa_history 에만 append
                                            qa_history = state.get("qa_history", [])
                                            qa_history.append(new_turn)

                                        # 화면에서 사용하는 state 도 동일 리스트를 바라보게 동기화
                                        state["qa_history"] = qa_history

                                        st.success("후속 질문이 이 질문 아래에 추가되었습니다.")
                                        st.rerun()
                                except Exception as e:
                                    st.error(
                                        f"후속 질문 생성 중 오류가 발생했습니다: {e}"
                                    )

                with col_f2:
                    st.caption("※ 후속 질문은 이 질문 아래에 트리 구조로 표시됩니다.")

            # ---- 재평가용 updated_qa 리스트에 추가 ---- #
            updated_qa.append(
                {
                    "interviewer": interviewer,
                    "question": question,
                    "answer": final_answer,
                    "category": category,
                    "score": turn.get("score"),
                    "notes": turn.get("notes"),
                    "is_followup": is_followup,
                    "parent_index": parent_index,
                }
            )

            # ---- 자식 노드(후속질문들) 재귀 렌더링 ---- #
            for child in node["children"]:
                render_node(child, level + 1)

    # ---------- 4) 루트 노드부터 전체 트리 렌더링 ---------- #
    # roots 는 원래 인덱스 순서대로 들어 있으므로, 전체 흐름도 시간 순서를 대략 유지합니다.
    for root in roots:
        render_node(root, level=0)

    # ---------- 5) 진행률 & 재평가 버튼 ---------- #
    total = len(updated_qa)
    ratio = answered_count / total if total > 0 else 0
    progress_placeholder.progress(ratio, text=f"답변 완료 {answered_count}/{total}")

    if enable_edit and interview_id is not None:
        st.markdown("---")
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

                if update_session_state and session_prefix.startswith("live_"):
                    if "run_tab_state" in st.session_state:
                        st.session_state["run_tab_state"]["evaluation"] = new_state.get(
                            "evaluation"
                        )
                        st.session_state["run_tab_state"]["qa_history"] = new_state.get(
                            "qa_history", updated_qa
                        )

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

        # 서브 탭 상태를 라디오로 관리 (기본: 평가 결과)
        tab_options = [
            "📊 평가 결과",
            "💬 인터뷰 질문 (답변/재평가)",
            "📦 원시 상태 데이터",
        ]
        tab_key = f"run_result_tab_{interview_id or 'none'}"

        if tab_key not in st.session_state:
            st.session_state[tab_key] = tab_options[0]

        # 탭 스타일 라디오 (한 번 클릭으로 전환, 상태 유지)
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


def render_history_tab():
    """면접 이력 조회 탭"""

    st.subheader("📚 면접 이력")

    # 어떤 이력을 펼쳐서 보고 있는지 저장 (없으면 None)
    if "history_selected_id" not in st.session_state:
        st.session_state["history_selected_id"] = None

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🔄 이력 새로고침", use_container_width=True):
            st.session_state["history_selected_id"] = None
            st.rerun()

    with col2:
        st.caption("※ 최신 20건 이력을 조회합니다.")

    interviews = fetch_interview_list(limit=20)
    if not interviews:
        st.info("저장된 면접 이력이 없습니다.")
        return

    selected_id = st.session_state.get("history_selected_id")

    # 이력 카드 목록
    for item in interviews:
        interview_id = item["id"]
        title = item["job_title"]
        name = item["candidate_name"]
        created_at = item["created_at"]
        total_questions = item["total_questions"]
        status = item["status"]

        with st.container(border=True):
            # --- 카드 헤더 영역 --- #
            st.markdown(f"#### {title} - {name}")
            st.caption(f"🗓 {created_at} | 질문 수(초기): {total_questions} | 상태: {status}")

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
                    key=f"jd_preview_{interview_id}",
                )

            with col_b:
                # 이미 열려 있으면 버튼 라벨을 "닫기"로
                is_open = selected_id == interview_id
                btn_label = "✖ 닫기" if is_open else "👀 이력 보기"

                if st.button(
                    btn_label,
                    key=f"toggle_{interview_id}",
                    use_container_width=True,
                ):
                    # 같은 걸 다시 누르면 접기, 다른 걸 누르면 그걸로 교체
                    if is_open:
                        st.session_state["history_selected_id"] = None
                    else:
                        st.session_state["history_selected_id"] = interview_id
                    st.rerun()

            # --- 선택된 카드라면, 바로 아래에 상세 패널 렌더 --- #
            if selected_id == interview_id:
                detail = fetch_interview_detail(interview_id)
                if not detail:
                    st.error("선택한 이력 정보를 불러오지 못했습니다.")
                else:
                    try:
                        state = json.loads(detail.get("state_json", "{}"))
                    except json.JSONDecodeError:
                        st.error("저장된 state_json을 파싱할 수 없습니다.")
                        state = {}

                    st.markdown("---")
                    st.markdown(
                        f"##### 📄 선택한 이력 상세 (ID: {interview_id})  \n"
                        f"**{detail.get('job_title', '')} - {detail.get('candidate_name', '')}**"
                    )

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
        - 후속질문을 포함한 인터뷰 세션 관리  
        - 최종 평가 리포트 생성  
        - 질문별 답변 입력 후 재평가  
        
        까지 한 번에 수행하는 **AI 기반 면접 보조 에이전트**입니다.
        """
    )

    with st.sidebar:
        st.header("⚙️ 설정")
        enable_rag = st.checkbox("RAG 활성화", value=True)
        use_mini = st.checkbox("경량 모델 사용(gpt-4o-mini)", value=True)
        total_questions = st.slider(
            "질문 개수(초기 생성 개수)", min_value=3, max_value=10, value=5
        )

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
