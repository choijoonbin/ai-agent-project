# app/components/history_panel.py

import os
import json
from typing import Any, Dict, List

import html
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9898/api/v1")


# ---------- API 유틸 ---------- #

def fetch_interview_list(limit: int = 20) -> List[Dict[str, Any]]:
    """면접 이력 목록 조회"""
    url = f"{API_BASE_URL}/interviews/?limit={limit}"
    try:
        response = requests.get(url, timeout=30)
    except Exception as e:
        st.error(f"면접 이력 조회 실패: {e}")
        return []

    if response.status_code != 200:
        st.error(f"면접 이력 조회 실패: {response.status_code}")
        return []
    return response.json()


def fetch_interview_detail(interview_id: int) -> Dict[str, Any] | None:
    """특정 면접 이력 상세 조회"""
    url = f"{API_BASE_URL}/interviews/{interview_id}"
    try:
        response = requests.get(url, timeout=30)
    except Exception as e:
        st.error(f"면접 이력 상세 조회 실패: {e}")
        return None

    if response.status_code != 200:
        st.error(f"면접 이력 상세 조회 실패: {response.status_code}")
        return None
    return response.json()


# ---------- 메인 렌더링 ---------- #

def render_history_tab() -> None:
    """면접 이력 조회 탭 (네비게이션에서 'History' 선택 시 사용)."""

    st.title("📚 Interview History")

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

    # ---------- 상단 검색/필터/정렬 UI ---------- #
    with st.expander("🔍 검색 및 필터", expanded=True):
        search_keyword = st.text_input(
            "제목/지원자 이름 검색",
            key="history_search_keyword",
            placeholder="예: 백엔드 / 홍길동",
        )

        # 상태 목록 (예: DONE, RUNNING, FAILED 등)
        statuses = sorted({item.get("status", "") for item in interviews if item.get("status")})
        status_filter = st.multiselect(
            "상태 필터",
            options=statuses,
            default=statuses,
            key="history_status_filter",
        )

        sort_option = st.selectbox(
            "정렬 기준",
            options=["최신순", "오래된순", "제목 오름차순", "지원자 이름 오름차순"],
            key="history_sort_option",
        )

    # ---------- 검색/필터 적용 ---------- #
    def _matches(item: Dict[str, Any]) -> bool:
        # 상태 필터
        if status_filter:
            if item.get("status") not in status_filter:
                return False

        # 키워드 검색 (job_title, candidate_name)
        if search_keyword:
            kw = search_keyword.lower()
            title = (item.get("job_title") or "").lower()
            name = (item.get("candidate_name") or "").lower()
            if kw not in title and kw not in name:
                return False

        return True

    filtered = [item for item in interviews if _matches(item)]

    # ---------- 정렬 적용 ---------- #
    def _sort_key(item: Dict[str, Any]) -> Any:
        if sort_option == "최신순":
            return item.get("created_at", ""),  # 나중에 reverse=True
        if sort_option == "오래된순":
            return item.get("created_at", "")
        if sort_option == "제목 오름차순":
            return (item.get("job_title") or "").lower()
        if sort_option == "지원자 이름 오름차순":
            return (item.get("candidate_name") or "").lower()
        return item.get("created_at", "")

    reverse = sort_option == "최신순"
    filtered.sort(key=_sort_key, reverse=reverse)

    if not filtered:
        st.info("검색/필터 조건에 해당하는 이력이 없습니다.")
        return

    selected_id = st.session_state.get("history_selected_id")

    # ---------- 이력 카드 목록 렌더 ---------- #
    for item in filtered:
        interview_id = item["id"]
        title = item.get("job_title") or "(제목 없음)"
        name = item.get("candidate_name") or "(이름 없음)"
        created_at = item.get("created_at", "")
        total_questions = item.get("total_questions", "-")
        status = item.get("status", "-")

        cache_key = f"history_state_{interview_id}"

        with st.container(border=True):
            # --- 카드 헤더 영역 --- #
            st.markdown(f"#### {title} - {name}")
            st.caption(
                f"🗓 {created_at} | 질문 수(초기): {total_questions} | 상태: {status}"
            )

            col_a, col_b = st.columns([3, 1])

            # ----- JD 영역: 펼치기 / 접기 토글 ----- #
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

            # ----- 이력 상세 열기 / 닫기 버튼 ----- #
            with col_b:
                is_open = selected_id == interview_id
                btn_label = "✖ 닫기" if is_open else "👀 이력 보기"

                if st.button(
                    btn_label,
                    key=f"toggle_{interview_id}",
                    use_container_width=True,
                ):
                    if is_open:
                        # 접기: 선택 해제 + 캐시 삭제
                        st.session_state["history_selected_id"] = None
                        if cache_key in st.session_state:
                            del st.session_state[cache_key]
                    else:
                        # 새로 열기: 이전 선택/캐시 정리 후 선택
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

                        # candidate_form 의 렌더러를 재사용하기 위해 import
                        from .candidate_form import render_evaluation, render_questions

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
