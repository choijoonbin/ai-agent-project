# app/components/history_panel.py

from __future__ import annotations

import os
import json
from typing import Any, Dict, List

import streamlit as st

from components.candidate_form import render_evaluation, render_questions

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9898/api/v1")


# ---------- 공통 API ---------- #

def fetch_interview_list(limit: int = 20) -> List[Dict[str, Any]]:
    """면접 이력 목록 조회"""
    url = f"{API_BASE_URL}/interviews/?limit={limit}"
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200:
        st.error(f"면접 이력 조회 실패: {resp.status_code}")
        return []
    return resp.json()


def fetch_interview_detail(interview_id: int) -> Dict[str, Any] | None:
    """특정 면접 이력 상세 조회"""
    url = f"{API_BASE_URL}/interviews/{interview_id}"
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200:
        st.error(f"면접 이력 상세 조회 실패: {resp.status_code}")
        return None
    return resp.json()


import requests  # 아래에서 사용


# ---------- 추천 결과 캐시 ---------- #

def _get_recommendation_cached(interview_id: int) -> str:
    """
    History 필터에서 '추천 결과' 로 필터링하기 위해,
    evaluation.recommendation 을 캐시해서 사용한다.
    """
    cache: Dict[int, str] = st.session_state.setdefault("history_rec_cache", {})

    if interview_id in cache:
        return cache[interview_id]

    detail = fetch_interview_detail(interview_id)
    if not detail:
        cache[interview_id] = "기타"
        return "기타"

    try:
        state = json.loads(detail.get("state_json", "{}"))
        evaluation = state.get("evaluation") or {}
        rec = evaluation.get("recommendation") or "기타"
    except Exception:
        rec = "기타"

    cache[interview_id] = rec
    return rec


# ---------- 메인 렌더링 ---------- #

def render_history_tab() -> None:
    """면접 이력 조회 탭"""

    st.title("📚 면접 이력")

    # 필터/정렬 상태 기본값
    if "history_filter_job" not in st.session_state:
        st.session_state["history_filter_job"] = "전체"
    if "history_filter_rec" not in st.session_state:
        st.session_state["history_filter_rec"] = "전체"
    if "history_sort" not in st.session_state:
        st.session_state["history_sort"] = "최신순"

    # ------------------------
    # 1) 목록 조회
    # ------------------------
    interviews = fetch_interview_list(limit=50)
    if not interviews:
        st.info("저장된 면접 이력이 없습니다.")
        return

    # 직군/포지션 목록
    job_titles = sorted(
        {item.get("job_title", "") for item in interviews if item.get("job_title")}
    )
    job_options = ["전체"] + job_titles

    # ------------------------
    # 2) 필터/정렬 UI
    # ------------------------
    with st.container():
        col1, col2, col3 = st.columns([1.4, 1.0, 1.0])

        with col1:
            st.selectbox(
                "직군 / 포지션",
                options=job_options,
                key="history_filter_job",
            )

        with col2:
            st.selectbox(
                "추천 결과",
                options=["전체", "Hire", "No Hire", "기타"],
                key="history_filter_rec",
            )

        with col3:
            st.selectbox(
                "정렬",
                options=["최신순", "오래된순"],
                key="history_sort",
            )

    # ------------------------
    # 3) 필터 적용
    # ------------------------
    filtered = list(interviews)

    # 직군 필터
    job_filter = st.session_state["history_filter_job"]
    if job_filter != "전체":
        filtered = [it for it in filtered if it.get("job_title") == job_filter]

    # 추천 결과 필터
    rec_filter = st.session_state["history_filter_rec"]
    if rec_filter != "전체":
        tmp: List[Dict[str, Any]] = []
        for it in filtered:
            rid = it["id"]
            rec = _get_recommendation_cached(rid)
            # 추천 결과 문자열 안에 "Hire"/"No Hire" 가 들어있는 경우를 포함해서 필터
            if rec_filter == "기타":
                if ("Hire" not in rec) and ("hire" not in rec.lower()):
                    tmp.append(it)
            elif rec_filter == "Hire":
                if "Hire" in rec and "No Hire" not in rec:
                    tmp.append(it)
            elif rec_filter == "No Hire":
                if "No Hire" in rec:
                    tmp.append(it)
        filtered = tmp

    # 정렬
    sort_opt = st.session_state["history_sort"]
    def _key_created(it: Dict[str, Any]) -> str:
        # created_at 이 ISO 문자열이라고 가정하고 단순 문자열 정렬
        return it.get("created_at", "")

    reverse = sort_opt == "최신순"
    filtered.sort(key=_key_created, reverse=reverse)

    # ------------------------
    # 4) 새로고침 버튼 / 안내
    # ------------------------
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🔄 이력 새로고침", use_container_width=True):
            # 캐시 및 선택 상태 초기화
            st.session_state["history_selected_id"] = None
            st.session_state["history_rec_cache"] = {}
            st.rerun()

    with col2:
        st.caption("※ 최대 50건 이력을 조회합니다.")

    if not filtered:
        st.info("필터 조건에 해당하는 면접 이력이 없습니다.")
        return

    selected_id = st.session_state.get("history_selected_id")

    # ------------------------
    # 5) 카드 렌더링
    # ------------------------
    for item in filtered:
        interview_id = item["id"]
        title = item["job_title"]
        name = item["candidate_name"]
        created_at = item["created_at"]
        total_questions = item["total_questions"]
        status = item["status"]

        cache_key_state = f"history_state_{interview_id}"

        with st.container(border=True):
            top_cols = st.columns([5, 1])
            with top_cols[0]:
                st.markdown(f"#### {title} - {name}")
                st.caption(
                    f"🗓 {created_at} | 질문 수(초기): {total_questions} | 상태: {status}"
                )

            # ----- 이력 상세 열기 / 닫기 버튼 (카드 우측 상단) ----- #
            with top_cols[1]:
                st.write("")  # align button to top
                is_open = selected_id == interview_id
                btn_label = "✖ 닫기" if is_open else "👀 이력 보기"

                if st.button(
                    btn_label,
                    key=f"toggle_{interview_id}",
                    use_container_width=True,
                ):
                    if is_open:
                        st.session_state["history_selected_id"] = None
                        if cache_key_state in st.session_state:
                            del st.session_state[cache_key_state]
                    else:
                        prev_id = st.session_state.get("history_selected_id")
                        if prev_id is not None and prev_id != interview_id:
                            prev_cache_key = f"history_state_{prev_id}"
                            if prev_cache_key in st.session_state:
                                del st.session_state[prev_cache_key]
                        st.session_state["history_selected_id"] = interview_id
                    st.rerun()

            # --- 선택된 카드라면, 바로 아래에 상세 패널 렌더 --- #
            if selected_id == interview_id:
                detail = fetch_interview_detail(interview_id)
                if not detail:
                    st.error("선택한 이력 정보를 불러오지 못했습니다.")
                else:
                    if cache_key_state in st.session_state:
                        state = st.session_state[cache_key_state]
                    else:
                        try:
                            state = json.loads(detail.get("state_json", "{}"))
                        except json.JSONDecodeError:
                            st.error("저장된 state_json을 파싱할 수 없습니다.")
                            state = {}
                        st.session_state[cache_key_state] = state

                    st.markdown("---")

                    with st.container(border=True):
                        header_col_left, header_col_right = st.columns([4, 2])

                        with header_col_left:
                            st.markdown(
                                f"##### 📄 선택한 이력 상세 (ID: {interview_id})  \n"
                                f"**{detail.get('job_title', '')} - {detail.get('candidate_name', '')}**"
                            )

                        with header_col_right:
                            # 이력 상세 닫기
                            col_close, col_insight = st.columns(2)
                            with col_close:
                                if st.button(
                                    "✖ 이력 상세 닫기",
                                    key=f"close_detail_{interview_id}",
                                    use_container_width=True,
                                ):
                                    st.session_state["history_selected_id"] = None
                                    if cache_key_state in st.session_state:
                                        del st.session_state[cache_key_state]
                                    st.rerun()

                            # 인사이트로 이동
                            with col_insight:
                                if st.button(
                                    "📊 이 후보 인사이트 보기",
                                    key=f"goto_insights_{interview_id}",
                                    use_container_width=True,
                                ):
                                    # 인사이트 탭에서 기본 선택 ID로 사용
                                    st.session_state["insights_selected_interview_id"] = interview_id
                                    st.session_state["nav_selected_code"] = "insights"
                                    # 사이드바 선택 상태 초기화 후 재렌더링
                                    if "sidebar_nav_menu" in st.session_state:
                                        del st.session_state["sidebar_nav_menu"]
                                    if "sidebar_nav_menu_logout" in st.session_state:
                                        del st.session_state["sidebar_nav_menu_logout"]
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
