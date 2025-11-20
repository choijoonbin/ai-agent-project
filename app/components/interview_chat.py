# app/components/interview_chat.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import altair as alt
import pandas as pd
import streamlit as st

from utils.state_manager import get_api_base_url

import requests

API_BASE_URL = get_api_base_url()


# ---------- API 호출 유틸 ---------- #


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


# ---------- 평가 결과 렌더링 ---------- #


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

    top_cols = st.columns([3, 1])
    with top_cols[0]:
        if recommendation:
            st.markdown(f"### 🏁 최종 추천: **{recommendation}**")

    with top_cols[1]:
        # 점수 평균 간단 뱃지
        if scores:
            vals = [v for v in scores.values() if isinstance(v, (int, float))]
            if vals:
                avg = sum(vals) / len(vals)
                st.markdown(
                    f"<div class='metric-pill'>⭐ 평균 점수: <strong>{avg:.1f}</strong></div>",
                    unsafe_allow_html=True,
                )

    if summary:
        st.markdown("#### 요약")
        st.write(summary)

    col_l, col_r = st.columns(2)

    with col_l:
        if strengths:
            st.markdown("#### ✅ 강점")
            for s in strengths:
                st.markdown(f"- {s}")

    with col_r:
        if weaknesses:
            st.markdown("#### ❌ 약점")
            for w in weaknesses:
                st.markdown(f"- {w}")

    # ---------- 점수 차트 ---------- #
    if scores:
        st.markdown("#### 📈 역량별 점수 차트")
        df = pd.DataFrame(
            [{"역량": k, "점수": v} for k, v in scores.items() if isinstance(v, (int, float))]
        )

        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(
                x=alt.X("역량:N", sort="-y"),
                y=alt.Y("점수:Q", scale=alt.Scale(domain=[0, 5])),
                tooltip=["역량", "점수"],
            )
            .properties(height=220)
        )
        st.altair_chart(chart, use_container_width=True)

    with st.expander("LLM 원문 평가 텍스트 보기"):
        st.write(raw_text)


# ---------- 질문/답변 + 후속 질문 트리 ---------- #


@dataclass
class QANode:
    idx: int
    turn: Dict[str, Any]
    children: List["QANode"]


def build_qa_tree(qa_history: List[Dict[str, Any]]) -> List[QANode]:
    nodes: List[QANode] = [QANode(idx=i, turn=t, children=[]) for i, t in enumerate(qa_history)]
    by_idx = {n.idx: n for n in nodes}
    roots: List[QANode] = []

    for n in nodes:
        parent_index = n.turn.get("parent_index")
        if parent_index is None:
            roots.append(n)
        else:
            parent = by_idx.get(parent_index)
            if parent:
                parent.children.append(n)
            else:
                roots.append(n)

    return roots


def render_questions(
    state: dict,
    *,
    interview_id: Optional[int] = None,
    session_prefix: str = "",
    enable_edit: bool = True,
    update_session_state: bool = False,
):
    """
    질문 리스트 + 답변 입력 + 후속 질문 + 재평가 UI (트리형 렌더링).
    """

    st.subheader("💬 인터뷰 세션 (질문 & 답변)")

    qa_history: List[Dict[str, Any]] = state.get("qa_history", [])
    if not qa_history:
        st.info("질문 리스트가 없습니다.")
        return

    roots = build_qa_tree(qa_history)

    progress_placeholder = st.empty()
    updated_qa: List[Dict[str, Any]] = []
    answered_count = 0
    display_counter = {"value": 0}

    def render_node(node: QANode, level: int):
        nonlocal answered_count, updated_qa
        idx = node.idx
        turn = node.turn

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
            header_html = (
                f"<div style='margin-left:{indent_px}px'>"
                f"<strong>{tree_prefix}Q{display_no}. 🔁 {category} {parent_label}</strong>"
                f"</div>"
            )
        else:
            header_html = (
                f"<div style='margin-left:{indent_px}px'>"
                f"<strong>{tree_prefix}Q{display_no}. ({category})</strong>"
                f"</div>"
            )

        with st.container(border=True):
            st.markdown(header_html, unsafe_allow_html=True)

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

            # 후속 질문 생성 버튼
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
                                    followup_q = resp.get("followup_question", "").strip()
                                    if followup_q:
                                        new_turn = {
                                            "interviewer": interviewer,
                                            "question": followup_q,
                                            "answer": "",
                                            "category": category,
                                            "is_followup": True,
                                            "parent_index": idx,
                                        }

                                        # 실행 탭에서라면 세션에 있는 run_tab_state 도 같이 수정
                                        if (
                                            session_prefix.startswith("live_")
                                            and "run_tab_state" in st.session_state
                                            and st.session_state["run_tab_state"] is not None
                                        ):
                                            if "qa_history" not in st.session_state["run_tab_state"]:
                                                st.session_state["run_tab_state"]["qa_history"] = []
                                            st.session_state["run_tab_state"]["qa_history"].append(
                                                new_turn
                                            )
                                            qa_history_local = st.session_state["run_tab_state"][
                                                "qa_history"
                                            ]
                                        else:
                                            qa_history_local = state.get("qa_history", [])
                                            qa_history_local.append(new_turn)

                                        state["qa_history"] = qa_history_local
                                        st.success("후속 질문이 이 질문 아래에 추가되었습니다.")
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"후속 질문 생성 중 오류가 발생했습니다: {e}")

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

            for child in node.children:
                render_node(child, level + 1)

    # 루트 노드부터 렌더링
    for root in roots:
        render_node(root, level=0)

    # 진행률 & 재평가
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
