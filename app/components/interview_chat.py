# app/components/interview_chat.py

import streamlit as st

from utils.api_client import call_rejudge_api, call_followup_api


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
    질문 리스트 + 답변 입력 + 후속 질문 + 재평가 UI (트리형 렌더링).
    """
    st.subheader("💬 인터뷰 세션 (질문 & 답변)")

    qa_history = state.get("qa_history", [])
    if not qa_history:
        st.info("질문 리스트가 없습니다.")
        return

    # ---------- 1) 트리 구조 구성 ---------- #
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
                roots.append(n)

    progress_placeholder = st.empty()
    updated_qa: list[dict] = []
    answered_count = 0
    display_counter = {"value": 0}

    # ---------- 2) 재귀 렌더링 ---------- #
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

            # ---- 후속 질문 생성 ---- #
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

                                        # live 탭에서 실행 중이면 run_tab_state 에도 반영
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
                                            qa_list = st.session_state["run_tab_state"][
                                                "qa_history"
                                            ]
                                        else:
                                            qa_list = state.get("qa_history", [])
                                            qa_list.append(new_turn)

                                        state["qa_history"] = qa_list
                                        st.success("후속 질문이 이 질문 아래에 추가되었습니다.")
                                        st.rerun()
                                except Exception as e:
                                    st.error(
                                        f"후속 질문 생성 중 오류가 발생했습니다: {e}"
                                    )

                with col_f2:
                    st.caption("※ 후속 질문은 이 질문 아래에 트리 구조로 표시됩니다.")

            # ---- 재평가용 데이터 축적 ---- #
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

    # 루트부터 렌더링
    for root in roots:
        render_node(root, level=0)

    total = len(updated_qa)
    ratio = answered_count / total if total > 0 else 0
    progress_placeholder.progress(ratio, text=f"답변 완료 {answered_count}/{total}")

    # 재평가 버튼
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
