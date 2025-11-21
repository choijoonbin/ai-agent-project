# app/components/overview.py

import os
from typing import Any, Dict, List

import requests
import streamlit as st
import pandas as pd
import altair as alt

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9898/api/v1")


def _get(url: str, *, timeout: int = 30) -> requests.Response:
    return requests.get(url, timeout=timeout)


def fetch_interview_list(limit: int = 50) -> List[Dict[str, Any]]:
    url = f"{API_BASE_URL}/interviews/?limit={limit}"
    try:
        resp = _get(url, timeout=30)
    except Exception as e:
        st.error(f"면접 이력 목록 조회 실패: {e}")
        return []
    if resp.status_code != 200:
        st.error(f"면접 이력 목록 조회 실패: {resp.status_code}")
        return []
    return resp.json()


def render_overview_page() -> None:
    st.title("🏠 Overview")
    st.caption("최근 AI 면접 실행 현황과 인터뷰 요약을 한 눈에 확인할 수 있는 화면입니다.")

    interviews = fetch_interview_list(limit=50)
    total = len(interviews)

    if total == 0:
        st.info("아직 저장된 면접 이력이 없습니다. 왼쪽 메뉴에서 **Studio** 로 이동해 첫 면접을 실행해 보세요.")
        return

    # 최신 인터뷰 한 건
    latest = interviews[0]  # API가 최신순으로 내려온다고 가정
    latest_title = latest.get("job_title", "") or "-"
    latest_name = latest.get("candidate_name", "") or "-"
    latest_created = latest.get("created_at", "") or "-"
    latest_status = latest.get("status", "") or "-"

    # ----- 상단 메트릭 카드 3개 ----- #
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("저장된 면접 수", f"{total} 건")

    with col2:
        st.metric("최근 면접 포지션", latest_title, help="가장 최근에 실행된 면접의 포지션명입니다.")

    with col3:
        st.metric("최근 후보자", latest_name, help="가장 최근에 실행된 면접의 지원자 이름입니다.")

    st.markdown("")

    # ----- 상태별(STATUS) 분포 차트 ----- #
    status_rows = []
    for item in interviews:
        status = item.get("status") or "UNKNOWN"
        status_rows.append({"status": status})

    df_status = pd.DataFrame(status_rows)
    status_counts = df_status.value_counts("status").reset_index(name="count")

    with st.container():
        st.markdown("### 📊 면접 상태 분포")

        chart = (
            alt.Chart(status_counts)
            .mark_bar()
            .encode(
                x=alt.X("status:N", title="상태", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("count:Q", title="건수"),
                tooltip=["status", "count"],
            )
            .properties(height=260)
        )

        st.altair_chart(chart, use_container_width=True)

    st.markdown("---")

    # ----- 최근 N건 테이블 ----- #
    st.markdown("### 🕒 최근 인터뷰 목록")

    # 표시에 쓸 필드만 추리기
    table_rows = []
    for item in interviews[:10]:
        table_rows.append(
            {
                "ID": item.get("id"),
                "포지션": item.get("job_title", ""),
                "지원자": item.get("candidate_name", ""),
                "생성일시": item.get("created_at", ""),
                "질문수(초기)": item.get("total_questions", ""),
                "상태": item.get("status", ""),
            }
        )

    df_table = pd.DataFrame(table_rows)

    st.dataframe(
        df_table,
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("")
    st.caption(
        "※ 상세 질문/답변 및 재평가, 후속질문 트리는 **History** 메뉴에서 확인할 수 있습니다."
    )
