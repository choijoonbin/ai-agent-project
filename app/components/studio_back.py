# app/components/candidate_form.py

import os
import json
import html
from typing import Any, Dict, List

import requests
import streamlit as st
import pandas as pd
import altair as alt

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9898/api/v1")


# =======================
# 1) 공통 API 호출 유틸
# =======================

def _get(url: str, *, timeout: int = 30) -> requests.Response:
    resp = requests.get(url, timeout=timeout)
    return resp


def _post(url: str, payload: Dict[str, Any], *, timeout: int = 180) -> requests.Response:
    resp = requests.post(url, json=payload, timeout=timeout)
    return resp


def _post_multipart(url: str, file_field: str, uploaded_file, *, timeout: int = 120) -> requests.Response:
    """
    파일 업로드용 multipart POST 헬퍼.
    - file_field: 백엔드에서 기대하는 필드명 (예: "file")
    - uploaded_file: st.file_uploader 가 반환한 객체
    """
    files = {
        file_field: (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type),
    }
    resp = requests.post(url, files=files, timeout=timeout)
    return resp


# ---------- 인터뷰 워크플로우 ---------- #

def call_interview_api(
    job_title: str,
    candidate_name: str,
    jd_text: str,
    resume_text: str,
    total_questions: int = 5,
    enable_rag: bool = True,
    use_mini: bool = True,
    save_history: bool = True,
) -> Dict[str, Any]:
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

    resp = _post(url, payload, timeout=180)
    if resp.status_code != 200:
        raise RuntimeError(f"API 오류: {resp.status_code} - {resp.text}")
    return resp.json()


def call_rejudge_api(interview_id: int, qa_history: List[Dict[str, Any]]) -> Dict[str, Any]:
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

    resp = _post(url, payload, timeout=180)
    if resp.status_code != 200:
        raise RuntimeError(f"재평가 API 오류: {resp.status_code} - {resp.text}")
    return resp.json()


def call_followup_api(
    interview_id: int,
    question: str,
    answer: str,
    category: str | None = None,
) -> Dict[str, Any]:
    """특정 질문/답변에 대한 후속 질문(재질문) 생성"""
    url = f"{API_BASE_URL}/workflow/interview/followup"

    payload = {
        "interview_id": interview_id,
        "question": question,
        "answer": answer,
        "category": category,
        "use_mini": True,
    }

    resp = _post(url, payload, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(
            f"후속 질문 API 오류: {resp.status_code} - {resp.text}"
        )
    return resp.json()


# ---------- JD / 이력서 파일 라이브러리 & 업로드 ---------- #

def fetch_jd_list() -> List[Dict[str, Any]]:
    url = f"{API_BASE_URL}/files/jd"
    resp = _get(url, timeout=15)
    if resp.status_code != 200:
        st.error(f"JD 파일 목록 조회 실패: {resp.status_code}")
        return []
    return resp.json()


def fetch_resume_list() -> List[Dict[str, Any]]:
    url = f"{API_BASE_URL}/files/resume"
    resp = _get(url, timeout=15)
    if resp.status_code != 200:
        st.error(f"이력서 파일 목록 조회 실패: {resp.status_code}")
        return []
    return resp.json()


def fetch_jd_content(file_id: str) -> str:
    url = f"{API_BASE_URL}/files/jd/{file_id}"
    resp = _get(url, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"JD 내용 조회 실패: {resp.status_code} - {resp.text}")
    data = resp.json()
    return data.get("content", "")


def fetch_resume_content(file_id: str) -> str:
    url = f"{API_BASE_URL}/files/resume/{file_id}"
    resp = _get(url, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"이력서 내용 조회 실패: {resp.status_code} - {resp.text}")
    data = resp.json()
    return data.get("content", "")


def upload_jd_file(uploaded_file) -> None:
    """
    JD 파일 업로드.
    예상 백엔드 엔드포인트:
        POST /api/v1/files/jd/upload
        - multipart/form-data, 필드명 "file"
        - 응답: {"id": "...", "filename": "..."} 형식 가정
    """
    if uploaded_file is None:
        st.warning("업로드할 JD 파일을 선택해 주세요.")
        return

    url = f"{API_BASE_URL}/files/jd/upload"
    try:
        resp = _post_multipart(url, "file", uploaded_file, timeout=120)
    except Exception as e:
        st.error(f"JD 업로드 중 오류가 발생했습니다: {e}")
        return

    if resp.status_code != 200:
        st.error(f"JD 업로드 실패: {resp.status_code} - {resp.text}")
        return

    st.success("JD 파일이 업로드되었습니다. 목록을 갱신했습니다.")


def upload_resume_file(uploaded_file) -> None:
    """
    이력서 파일 업로드.
    예상 백엔드 엔드포인트:
        POST /api/v1/files/resume/upload
        - multipart/form-data, 필드명 "file"
    """
    if uploaded_file is None:
        st.warning("업로드할 이력서 파일을 선택해 주세요.")
        return

    url = f"{API_BASE_URL}/files/resume/upload"
    try:
        resp = _post_multipart(url, "file", uploaded_file, timeout=120)
    except Exception as e:
        st.error(f"이력서 업로드 중 오류가 발생했습니다: {e}")
        return

    if resp.status_code != 200:
        st.error(f"이력서 업로드 실패: {resp.status_code} - {resp.text}")
        return

    st.success("이력서 파일이 업로드되었습니다. 목록을 갱신했습니다.")


def _render_file_library(file_type: str) -> None:
    """
    JD / 이력서 파일 라이브러리 렌더링.
    - file_type: "jd" | "resume"
    - 선택 시 studio_{jd,resume}_text 세션 키에 내용을 채워넣음.
    """
    if file_type == "jd":
        files = fetch_jd_list()
        text_key = "studio_jd_text"
        title = "채용공고 파일 목록"
    else:
        files = fetch_resume_list()
        text_key = "studio_resume_text"
        title = "이력서 파일 목록"

    st.markdown(f"**📁 {title}**")

    if not files:
        st.caption("지정된 폴더에 사용 가능한 파일이 없습니다. (docx/pdf/md/txt)")
        return

    # 2열 카드 레이아웃
    cols = st.columns(2)
    for idx, item in enumerate(files):
        col = cols[idx % 2]
        with col:
            display = (
                item.get("display_name")
                or item.get("filename")
                or item.get("id")
            )
            ext = item.get("ext", "")
            label = f"📄 {display} ({ext})"
            if st.button(
                label,
                key=f"{file_type}_file_{item.get('id')}",
                use_container_width=True,
            ):
                try:
                    if file_type == "jd":
                        content = fetch_jd_content(item["id"])
                    else:
                        content = fetch_resume_content(item["id"])
                    pending_key = f"{text_key}_pending"
                    st.session_state[pending_key] = content
                    st.success("선택한 파일 내용이 텍스트 영역에 채워졌습니다. 잠시 후 입력창이 갱신됩니다.")
                    st.rerun()
                except Exception as e:
                    st.error(f"파일 내용을 불러오지 못했습니다: {e}")


# ==========================
# 2) 평가 결과 렌더링 (차트)
# ==========================

def render_evaluation(state: Dict[str, Any]) -> None:
    """최종 평가 결과를 인사이트 스타일로 개선된 UI로 렌더링"""
    
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

    # ------------------------
    # 1) 상단 추천 결과 카드
    # ------------------------
    if recommendation:
        with st.container(border=True):
            st.subheader("🏁 최종 추천", divider='blue')
            # 추천 결과에 따른 색상 구분 (순서 중요: "No Hire"를 먼저 체크)
            recommendation_upper = recommendation.upper()
            if "NO HIRE" in recommendation_upper:
                rec_color = "#ef4444"  # 빨간색
            elif "STRONG HIRE" in recommendation_upper or "HIRE" in recommendation_upper:
                rec_color = "#10b981"  # 초록색
            else:
                rec_color = "#6366f1"  # 보라색
            
            st.markdown(
                f"""
                <div style="padding: 16px; background: {rec_color}20; border-radius: 8px; border-left: 4px solid {rec_color}; margin-top: 16px; margin-bottom: 8px;">
                    <p style="margin: 0; font-size: 16px; font-weight: 600; color: {rec_color}; line-height: 1.6;">
                        {recommendation}
                    </p>
                </div>
                """,
                unsafe_allow_html=True
            )

    st.markdown("---")

    # ------------------------
    # 2) 요약, 강점, 약점 카드 (3개 나란히, 높이 300px 고정)
    # ------------------------
    col_summary, col_strength, col_weakness = st.columns(3)

    with col_summary:
        if summary:
            st.markdown("#### 📝 평가 요약")
            # HTML 이스케이프 처리
            summary_escaped = html.escape(summary)
            st.markdown(
                f"""
                <div style="border: 1px solid rgba(250, 250, 250, 0.2); border-radius: 0.5rem; padding: 0; height: 300px; display: flex; flex-direction: column;">
                    <div style="height: 300px; overflow-y: auto; padding: 16px; flex: 1; font-size: 16px; line-height: 1.6;">
                        {summary_escaped}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.markdown("#### 📝 평가 요약")
            st.markdown(
                """
                <div style="border: 1px solid rgba(250, 250, 250, 0.2); border-radius: 0.5rem; padding: 0; height: 300px; display: flex; flex-direction: column;">
                    <div style="height: 300px; overflow-y: auto; padding: 16px; flex: 1; display: flex; align-items: center; justify-content: center; color: #666;">
                        평가 요약이 없습니다.
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

    with col_strength:
        if strengths:
            st.markdown("#### ✅ 강점")
            # HTML 이스케이프 처리 및 내용 생성
            content_html = ""
            for s in strengths:
                s_escaped = html.escape(s)
                content_html += f'<div style="padding: 8px 0; font-size: 16px; border-left: 3px solid #10b981; padding-left: 12px; margin-bottom: 8px;">• {s_escaped}</div>'
            
            st.markdown(
                f"""
                <div style="border: 1px solid rgba(250, 250, 250, 0.2); border-radius: 0.5rem; padding: 0; height: 300px; display: flex; flex-direction: column;">
                    <div style="height: 300px; overflow-y: auto; padding: 16px; flex: 1;">
                        {content_html}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.markdown("#### ✅ 강점")
            st.markdown(
                """
                <div style="border: 1px solid rgba(250, 250, 250, 0.2); border-radius: 0.5rem; padding: 0; height: 300px; display: flex; flex-direction: column;">
                    <div style="height: 300px; overflow-y: auto; padding: 16px; flex: 1; display: flex; align-items: center; justify-content: center; color: #666;">
                        강점이 없습니다.
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

    with col_weakness:
        if weaknesses:
            st.markdown("#### ❌ 약점")
            # HTML 이스케이프 처리 및 내용 생성
            content_html = ""
            for w in weaknesses:
                w_escaped = html.escape(w)
                content_html += f'<div style="padding: 8px 0; font-size: 16px; border-left: 3px solid #ef4444; padding-left: 12px; margin-bottom: 8px;">• {w_escaped}</div>'
            
            st.markdown(
                f"""
                <div style="border: 1px solid rgba(250, 250, 250, 0.2); border-radius: 0.5rem; padding: 0; height: 300px; display: flex; flex-direction: column;">
                    <div style="height: 300px; overflow-y: auto; padding: 16px; flex: 1;">
                        {content_html}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.markdown("#### ❌ 약점")
            st.markdown(
                """
                <div style="border: 1px solid rgba(250, 250, 250, 0.2); border-radius: 0.5rem; padding: 0; height: 300px; display: flex; flex-direction: column;">
                    <div style="height: 300px; overflow-y: auto; padding: 16px; flex: 1; display: flex; align-items: center; justify-content: center; color: #666;">
                        약점이 없습니다.
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

    st.markdown("---")

    # ------------------------
    # 3) 역량별 점수 분포 차트 (하단에 위치)
    # ------------------------
    if scores:
        # 평균 점수 계산
        avg_score = sum(scores.values()) / len(scores) if scores else 0.0
        
        with st.container(border=True):
            st.subheader(f"📈 역량별 점수 분포 (평균: {avg_score:.1f}점)", divider='blue')
            
            # Altair 차트 개선 (인사이트 스타일)
            df = pd.DataFrame(
                [{"역량": k, "점수": float(v)} for k, v in scores.items()]
            )

            chart = (
                alt.Chart(df)
                .mark_bar(color="#4c78a8", cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                .encode(
                    x=alt.X(
                        "역량:N", 
                        axis=alt.Axis(labelAngle=-45, title=None, labelLimit=100)
                    ),
                    y=alt.Y(
                        "점수:Q",
                        scale=alt.Scale(domain=[0, 5], nice=False),
                        axis=alt.Axis(
                            values=[0, 1, 2, 3, 4, 5],
                            title="점수 (만점: 5점)",
                            grid=True
                        )
                    ),
                    tooltip=["역량", alt.Tooltip("점수", format=".1f")],
                )
                .properties(height=350)
            )

            st.altair_chart(chart, use_container_width=True)

    # ------------------------
    # 3) 원문 평가 텍스트 (Expander)
    # ------------------------
    if raw_text:
        with st.expander("📄 LLM 원문 평가 텍스트 보기", expanded=False):
            st.markdown(
                f"""
                <div style="padding: 12px; background: rgba(250, 250, 250, 0.05); border-radius: 8px; font-size: 14px; line-height: 1.6;">
                    {raw_text}
                </div>
                """,
                unsafe_allow_html=True
            )


# ===================================
# 3) 인터뷰 질문/답변 + 후속질문(트리형)
# ===================================

def render_questions(
    state: Dict[str, Any],
    *,
    interview_id: int | None = None,
    session_prefix: str = "",
    enable_edit: bool = True,
    update_session_state: bool = False,
) -> None:
    """
    질문 리스트 + 답변 입력 + 후속 질문 + 재평가 UI (트리형 렌더링).

    - qa_history 는 평면 리스트지만,
      화면에서는 "부모 질문 → 그 아래 들여쓰기된 후속질문들" 형태로 표시.
    """
    st.subheader("💬 인터뷰 세션 (질문 & 답변)")

    qa_history = state.get("qa_history", [])
    if not qa_history:
        st.info("질문 리스트가 없습니다.")
        return

    # ---------- 1) 트리 구조 구성 (parent_index 기준) ---------- #
    nodes: List[Dict[str, Any]] = []
    for idx, turn in enumerate(qa_history):
        nodes.append({"idx": idx, "turn": turn, "children": []})

    by_idx = {n["idx"]: n for n in nodes}
    roots: List[Dict[str, Any]] = []

    for n in nodes:
        parent_index = n["turn"].get("parent_index")
        if parent_index is None:
            roots.append(n)
        else:
            parent = by_idx.get(parent_index)
            if parent:
                parent["children"].append(n)
            else:
                roots.append(n)

    # ---------- 2) 렌더링 준비 ---------- #
    progress_placeholder = st.empty()
    updated_qa: List[Dict[str, Any]] = []
    answered_count = 0

    display_counter = {"value": 0}  # Q 번호(화면상 Q1, Q2, ...)

    # ---------- 3) 재귀 렌더링 함수 ---------- #
    def render_node(node: Dict[str, Any], level: int) -> None:
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

        indent_px = level * 24
        if level <= 0:
            tree_prefix = ""
        else:
            tree_prefix = "└" + "─" * (2 * level - 1) + " "

        if is_followup:
            if parent_index is not None:
                parent_label = f"(Q{(parent_index or 0) + 1}의 후속 질문)"
            else:
                parent_label = "(후속 질문)"
            badge_html = f"<span class='shad-badge'>{category}</span>"
            header_html = (
                f"<div style='margin-left:{indent_px}px'>"
                f"<strong>{tree_prefix}Q{display_no}. 🔁 {badge_html} {parent_label}</strong>"
                f"</div>"
            )
        else:
            badge_html = f"<span class='shad-badge'>{category}</span>"
            header_html = (
                f"<div style='margin-left:{indent_px}px'>"
                f"<strong>{tree_prefix}Q{display_no}. {badge_html}</strong>"
                f"</div>"
            )

        with st.container(border=True):
            st.markdown(header_html, unsafe_allow_html=True)
            st.markdown("<hr class='shad-hr' />", unsafe_allow_html=True)

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

                                        if (
                                            session_prefix.startswith("live_")
                                            and "run_tab_state" in st.session_state
                                            and st.session_state["run_tab_state"]
                                            is not None
                                        ):
                                            if (
                                                "qa_history"
                                                not in st.session_state["run_tab_state"]
                                            ):
                                                st.session_state["run_tab_state"][
                                                    "qa_history"
                                                ] = []

                                            st.session_state["run_tab_state"][
                                                "qa_history"
                                            ].append(new_turn)
                                            qa_hist = st.session_state["run_tab_state"][
                                                "qa_history"
                                            ]
                                        else:
                                            qa_hist = state.get("qa_history", [])
                                            qa_hist.append(new_turn)

                                        state["qa_history"] = qa_hist
                                        st.success(
                                            "후속 질문이 이 질문 아래에 추가되었습니다."
                                        )
                                except Exception as e:
                                    st.error(
                                        f"후속 질문 생성 중 오류가 발생했습니다: {e}"
                                    )

                with col_f2:
                    st.caption("※ 후속 질문은 이 질문 아래에 트리 구조로 표시됩니다.")

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

            for child in node["children"]:
                render_node(child, level + 1)

    # ---------- 4) 루트 노드부터 전체 트리 렌더링 ---------- #
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


# ==========================
# 4) Studio Stepper + 페이지
# ==========================

def _render_studio_stepper() -> None:
    """상단에 4단계 Stepper를 그려주는 작은 유틸."""
    current = int(st.session_state.get("studio_step", 1))

    steps = [
        (1, "JD / 이력서 선택"),
        (2, "AI 분석 & 질문 생성"),
        (3, "인터뷰 진행"),
        (4, "평가 & 인사이트"),
    ]

    # 간단한 CSS + columns 로 Stepper 표현
    st.markdown(
        """
        <style>
        .stepper-container {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 1.2rem;
        }
        .stepper-step {
            display: flex;
            flex-direction: column;
            align-items: center;
            font-size: 0.8rem;
            min-width: 80px;
        }
        .stepper-circle {
            width: 26px;
            height: 26px;
            border-radius: 999px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.8rem;
            font-weight: 600;
            border: 2px solid rgba(148,163,184,0.6);
            background: rgba(15,23,42,0.9);
            color: #e5e7eb;
        }
        .stepper-circle-active {
            background: linear-gradient(135deg, #f97373, #fb923c);
            border-color: rgba(248,250,252,0.9);
            color: #111827;
        }
        .stepper-line {
            flex: 1;
            height: 2px;
            background: linear-gradient(90deg, rgba(148,163,184,0.5), rgba(55,65,81,0.3));
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    html = ['<div class="stepper-container">']
    for i, (num, label) in enumerate(steps):
        active_class = " stepper-circle-active" if num == current else ""
        html.append('<div class="stepper-step">')
        html.append(f'<div class="stepper-circle{active_class}">{num}</div>')
        html.append(f'<div style="margin-top:4px; text-align:center;">{label}</div>')
        html.append("</div>")
        if i < len(steps) - 1:
            html.append('<div class="stepper-line"></div>')
    html.append("</div>")

    st.markdown("".join(html), unsafe_allow_html=True)


def render_studio_page() -> None:
    """사이드바에서 'Studio' 선택 시 렌더링되는 메인 화면."""

    st.title("🧑‍💼 Interview Studio")

    # Shadcn 느낌의 카드/배지 스타일을 간단히 적용
    st.markdown(
        """
        <style>
        .shad-card {
            background: #0f172a;
            border: 1px solid rgba(148, 163, 184, 0.25);
            border-radius: 14px;
            padding: 16px 16px 12px 16px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 16px;
        }
        .shad-badge {
            display: inline-flex;
            align-items: center;
            padding: 2px 8px;
            border-radius: 999px;
            background: rgba(59,130,246,0.12);
            color: #bfdbfe;
            font-size: 0.75rem;
            font-weight: 600;
            border: 1px solid rgba(59,130,246,0.25);
        }
        .shad-hr {
            height: 1px;
            border: 0;
            background: linear-gradient(90deg, rgba(148,163,184,0.4), rgba(148,163,184,0.1));
            margin: 12px 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Stepper (기본 1단계)
    if "studio_step" not in st.session_state:
        st.session_state["studio_step"] = 1
    _render_studio_stepper()

    # 파일 선택으로 미리 저장된 텍스트가 있으면 위젯 생성 전에 주입
    for base_key in ("studio_jd_text", "studio_resume_text"):
        pending_key = f"{base_key}_pending"
        if pending_key in st.session_state:
            st.session_state[base_key] = st.session_state[pending_key]
            del st.session_state[pending_key]

    col_left, col_right = st.columns(2)

    # ---------- Step 1: JD / 이력서 입력 + 라이브러리 + 업로드 ---------- #
    with col_left:
        st.markdown('<div class="shad-card">', unsafe_allow_html=True)
        st.subheader("📝 채용 공고 (JD)")

        jd_text = st.text_area(
            "채용 공고 (JD) 텍스트",
            key="studio_jd_text",
            height=260,
            placeholder="채용 공고 내용을 여기에 붙여넣거나, 아래 라이브러리/업로드를 사용하세요.",
        )

        with st.expander("📁 채용공고 파일 라이브러리에서 불러오기"):
            _render_file_library("jd")

        st.caption("파일 업로드 (docx/pdf/md/txt 지원)")
        jd_upload = st.file_uploader(
            "JD 파일 업로드",
            type=["docx", "pdf", "md", "txt"],
            key="jd_file_uploader",
            label_visibility="collapsed",
        )
        if st.button("⬆️ JD 파일 업로드", use_container_width=True):
            upload_jd_file(jd_upload)
            # 업로드 후 라이브러리 자동 갱신을 위해 rerun
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with col_right:
        st.markdown('<div class="shad-card">', unsafe_allow_html=True)
        st.subheader("📄 이력서 내용")

        resume_text = st.text_area(
            "이력서 텍스트",
            key="studio_resume_text",
            height=260,
            placeholder="지원자의 이력서 내용을 텍스트로 붙여넣거나, 아래 라이브러리/업로드를 사용하세요.",
        )

        with st.expander("📁 이력서 파일 라이브러리에서 불러오기"):
            _render_file_library("resume")

        st.caption("파일 업로드 (docx/pdf/md/txt 지원)")
        resume_upload = st.file_uploader(
            "이력서 파일 업로드",
            type=["docx", "pdf", "md", "txt"],
            key="resume_file_uploader",
            label_visibility="collapsed",
        )
        if st.button("⬆️ 이력서 파일 업로드", use_container_width=True):
            upload_resume_file(resume_upload)
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")

    # ---------- 인터뷰 실행 버튼 ---------- #
    st.markdown('<div class="shad-card">', unsafe_allow_html=True)
    job_title = st.text_input("채용 포지션명", value="백엔드 개발자", key="studio_job_title")
    candidate_name = st.text_input("지원자 이름", value="홍길동", key="studio_candidate_name")

    if st.button("🚀 AI 면접 에이전트 실행", use_container_width=True):
        if not jd_text.strip() or not resume_text.strip():
            st.error("JD와 이력서 내용을 모두 입력하거나 파일에서 불러와 주세요.")
        else:
            # Step 2 로 전환
            st.session_state["studio_step"] = 2
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
                    st.session_state["run_tab_state"] = result.get("state", {})
                    st.session_state["run_tab_interview_id"] = result.get("interview_id")

                    # 질문 생성까지 완료 → Step 3
                    st.session_state["studio_step"] = 3

                    st.success("면접 플로우 실행 완료!")
                    if st.session_state["run_tab_interview_id"] is not None:
                        st.info(
                            f"이 면접 이력 ID: {st.session_state['run_tab_interview_id']}"
                        )
                        st.session_state["last_interview_id"] = st.session_state[
                            "run_tab_interview_id"
                        ]
    st.markdown("</div>", unsafe_allow_html=True)

    # ---------- 실행된 결과 보여주기 ---------- #
    if st.session_state.get("run_tab_state") is not None:
        state = st.session_state["run_tab_state"]
        interview_id = st.session_state.get("run_tab_interview_id")

        tab_options = [
            "📊 평가 결과",
            "💬 인터뷰 질문 (답변/재평가)",
            "📦 원시 상태 데이터",
        ]
        tab_key = f"run_result_tab_{interview_id or 'none'}"

        if tab_key not in st.session_state:
            st.session_state[tab_key] = tab_options[0]

        st.markdown("")
        selected_tab = st.radio(
            "결과 보기",
            options=tab_options,
            key=tab_key,
            horizontal=True,
            label_visibility="collapsed",
        )

        # 탭 선택에 따라 Stepper 단계도 자연스럽게 이동
        if selected_tab == "📊 평가 결과":
            st.session_state["studio_step"] = 4
        else:
            st.session_state["studio_step"] = 3

        st.markdown('<div class="shad-card">', unsafe_allow_html=True)

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

        st.markdown("</div>", unsafe_allow_html=True)
