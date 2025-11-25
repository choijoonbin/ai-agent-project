# app/components/history_panel.py

from __future__ import annotations

import os
import json
from typing import Any, Dict, List

import streamlit as st

from components.candidate_form import render_evaluation, render_questions
from utils.time_utils import format_to_kst

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9898/api/v1")


# ---------- 공통 API ---------- #

def fetch_interview_list(limit: int = 20, status: str | None = None) -> List[Dict[str, Any]]:
    """면접 이력 목록 조회"""
    url = f"{API_BASE_URL}/interviews/?limit={limit}"
    if status:
        url += f"&status={status}"
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

AGENT_LABELS = {
    "JD_ANALYZER_AGENT": "JD 분석 에이전트",
    "RESUME_ANALYZER_AGENT": "이력서 분석 에이전트",
    "INTERVIEWER_AGENT": "면접관 에이전트",
    "JUDGE_AGENT": "평가 에이전트",
}


def _render_rag_sources(state: Dict[str, Any]) -> None:
    job_role = state.get("job_role", "general")
    contexts = state.get("rag_contexts") or {}

    st.markdown(f"**직군 태그**: `{job_role}`")

    if not contexts:
        st.caption("RAG 컨텍스트 기록이 없습니다.")
        return

    for agent_key, context_text in contexts.items():
        label = AGENT_LABELS.get(agent_key, agent_key)
        st.markdown(f"- **{label}**")
        st.code(context_text.strip(), language="text")


def render_history_tab() -> None:
    """면접 이력 조회 탭"""

    st.title("📚 면접 이력")

    # 필터/정렬 상태 기본값
    if "history_filter_job" not in st.session_state:
        st.session_state["history_filter_job"] = "전체"
    if "history_filter_rec" not in st.session_state:
        st.session_state["history_filter_rec"] = "전체"
    if "history_filter_status" not in st.session_state:
        st.session_state["history_filter_status"] = "전체"
    if "history_sort" not in st.session_state:
        st.session_state["history_sort"] = "최신순"

    # ------------------------
    # 1) 전체 목록 조회 (필터 UI 표시를 위해)
    # ------------------------
    all_interviews = fetch_interview_list(limit=50, status=None)  # 전체 조회
    
    # 직군/포지션 목록 (전체 목록 기준)
    job_titles = sorted(
        {item.get("job_title", "") for item in all_interviews if item.get("job_title")}
    )
    job_options = ["전체"] + job_titles

    # ------------------------
    # 2) 필터/정렬 UI (항상 표시)
    # ------------------------
    with st.container():
        col1, col2, col3, col4, col5 = st.columns([1.2, 1.0, 1.0, 0.8, 0.5])

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
                "지원 상태",
                options=["전체", "SUBMITTED", "DOCUMENT_REVIEW", "PASSED", "REJECTED", "CANCELLED"],
                key="history_filter_status",
            )

        with col4:
            st.selectbox(
                "정렬",
                options=["최신순", "오래된순"],
                key="history_sort",
            )
        
        with col5:
            if st.button("🔄 초기화", use_container_width=True, help="모든 필터를 초기화합니다"):
                st.session_state["history_filter_job"] = "전체"
                st.session_state["history_filter_rec"] = "전체"
                st.session_state["history_filter_status"] = "전체"
                st.session_state["history_sort"] = "최신순"
                st.rerun()

    # ------------------------
    # 3) 필터 적용된 목록 조회
    # ------------------------
    status_filter = st.session_state.get("history_filter_status")
    status_param = None if status_filter == "전체" else status_filter
    interviews = fetch_interview_list(limit=50, status=status_param)
    
    if not all_interviews:
        st.info("저장된 면접 이력이 없습니다.")
        return

    # ------------------------
    # 4) 필터 적용
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
    # 5) 새로고침 버튼 / 안내
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
        st.warning(f"📋 필터 조건에 해당하는 면접 이력이 없습니다. (전체: {len(all_interviews)}건)")
        st.info("💡 다른 필터 조건을 선택하거나 '초기화' 버튼을 눌러 필터를 초기화해보세요.")
        return

    selected_id = st.session_state.get("history_selected_id")

    # 상태 배지 스타일 정의
    def _get_status_badge(status: str | None) -> str:
        """Application status에 따른 배지 HTML 반환"""
        if not status:
            return ""
        
        status_labels = {
            "SUBMITTED": "지원완료",
            "DOCUMENT_REVIEW": "서류심사",
            "PASSED": "합격",
            "REJECTED": "불합격",
            "CANCELLED": "지원취소",
        }
        status_colors = {
            "SUBMITTED": "#0ea5e9",
            "DOCUMENT_REVIEW": "#6366f1",
            "PASSED": "#10b981",
            "REJECTED": "#ef4444",
            "CANCELLED": "#94a3b8",
        }
        
        label = status_labels.get(status, status)
        color = status_colors.get(status, "#94a3b8")
        
        return (
            f"<span style='display:inline-block;padding:3px 8px;border-radius:999px;"
            f"background:{color};color:white;font-weight:600;font-size:0.7rem;margin-left:8px;vertical-align:middle;'>"
            f"{label}</span>"
        )
    
    def _get_recommendation_badge(interview_id: int) -> str:
        """면접 평가 결과(Hire/No Hire)에 따른 배지 HTML 반환"""
        rec = _get_recommendation_cached(interview_id)
        
        if not rec or rec == "기타":
            return ""
        
        # Hire/No Hire 판단
        rec_upper = rec.upper()
        if "NO HIRE" in rec_upper or "NO-HIRE" in rec_upper:
            label = "No Hire"
            color = "#ef4444"  # 빨간색
        elif "HIRE" in rec_upper:
            if "STRONG" in rec_upper:
                label = "Strong Hire"
                color = "#10b981"  # 초록색
            else:
                label = "Hire"
                color = "#10b981"  # 초록색
        else:
            return ""
        
        return (
            f"<span style='display:inline-block;padding:3px 8px;border-radius:999px;"
            f"background:{color};color:white;font-weight:600;font-size:0.7rem;margin-left:8px;vertical-align:middle;'>"
            f"{label}</span>"
        )

    # ------------------------
    # 6) 카드 렌더링
    # ------------------------
    for item in filtered:
        interview_id = item["id"]
        title = item["job_title"]
        name = item["candidate_name"]
        created_at = format_to_kst(item.get("created_at"))
        total_questions = item["total_questions"]
        status = item["status"]
        application_status = item.get("application_status")

        cache_key_state = f"history_state_{interview_id}"

        with st.container(border=True):
            top_cols = st.columns([5, 1])
            with top_cols[0]:
                status_badge = _get_status_badge(application_status)
                recommendation_badge = _get_recommendation_badge(interview_id)
                st.markdown(
                    f"#### {title} - {name}{status_badge}{recommendation_badge}",
                    unsafe_allow_html=True
                )
                st.caption(
                    f"🗓 {created_at} | 질문 수(초기): {total_questions} | 상태: {status}"
                )

            # ----- 이력 상세 열기 / 닫기 버튼 및 인터뷰 진행 버튼 (카드 우측 상단) ----- #
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
                
                # 인터뷰 진행 버튼
                if st.button(
                    "💬 인터뷰 진행",
                    key=f"interview_{interview_id}",
                    use_container_width=True,
                ):
                    # 추후 기능 구현 예정
                    st.info("인터뷰 진행 기능은 추후 구현 예정입니다.")
                    # TODO: 인터뷰 진행 기능 구현

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

                        with st.expander("🔎 직군 & RAG 참고 정보", expanded=False):
                            _render_rag_sources(state)

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
