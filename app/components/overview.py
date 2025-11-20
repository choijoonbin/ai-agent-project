# app/components/overview.py

import os
from typing import Any, Dict, List

import requests
import streamlit as st
import pandas as pd
import altair as alt

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9898/api/v1")


def fetch_interview_list(limit: int = 100) -> List[Dict[str, Any]]:
    """면접 이력 목록 조회 (Overview/History 공용)."""
    url = f"{API_BASE_URL}/interviews/?limit={limit}"
    try:
        resp = requests.get(url, timeout=30)
    except Exception as e:
        st.error(f"면접 이력 조회 실패: {e}")
        return []

    if resp.status_code != 200:
        st.error(f"면접 이력 조회 실패: {resp.status_code}")
        return []

    return resp.json()


def render_overview_page() -> None:
    """사이드바에서 'Overview' 선택 시 렌더링되는 메인 대시보드."""

    st.title("🏠 Interview Overview")
    st.caption("최근 인터뷰 현황과 간단한 통계를 한눈에 볼 수 있는 대시보드입니다.")

    interviews = fetch_interview_list(limit=200)
    if not interviews:
        st.info("아직 저장된 면접 이력이 없습니다. 먼저 Studio에서 인터뷰를 실행해 보세요.")
        return

    # ---------- 기본 통계 계산 ---------- #
    df = pd.DataFrame(interviews)

    # created_at 컬럼에서 날짜만 추출 (형식이 다르더라도 최대한 안전하게 처리)
    if "created_at" in df.columns:
        df["date"] = df["created_at"].astype(str).str.slice(0, 10)
    else:
        df["date"] = "알 수 없음"

    total_cnt = len(df)
    unique_dates = df["date"].nunique()
    status_counts = df["status"].value_counts() if "status" in df.columns else pd.Series([], dtype=int)

    done_cnt = int(status_counts.get("DONE", 0))
    failed_cnt = int(status_counts.get("FAILED", 0))

    # ---------- 상단 Metric 카드 ---------- #
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("총 인터뷰 수", f"{total_cnt}")
    with c2:
        st.metric("인터뷰 진행 날짜 수", f"{unique_dates}")
    with c3:
        st.metric("완료(DONE)", f"{done_cnt}")
    with c4:
        st.metric("실패/중단", f"{failed_cnt}")

    st.markdown("---")

    # ---------- 통계 차트 영역 ---------- #
    left, right = st.columns(2)

    # 1) 날짜별 인터뷰 수 (라인차트)
    with left:
        st.subheader("📆 날짜별 인터뷰 수")

        date_counts = (
            df.groupby("date")
            .size()
            .reset_index(name="count")
            .sort_values("date")
        )

        chart_date = (
            alt.Chart(date_counts)
            .mark_line(point=True)
            .encode(
                x=alt.X("date:N", title="날짜", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("count:Q", title="인터뷰 수"),
                tooltip=["date", "count"],
            )
            .properties(height=260)
        )

        st.altair_chart(chart_date, use_container_width=True)

    # 2) 상태별 분포 (막대차트)
    with right:
        st.subheader("⚙️ 상태별 인터뷰 분포")

        if "status" in df.columns:
            status_df = (
                df["status"]
                .value_counts()
                .rename_axis("status")
                .reset_index(name="count")
            )
            chart_status = (
                alt.Chart(status_df)
                .mark_bar()
                .encode(
                    x=alt.X("status:N", title="상태", axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("count:Q", title="개수"),
                    tooltip=["status", "count"],
                )
                .properties(height=260)
            )
            st.altair_chart(chart_status, use_container_width=True)
        else:
            st.caption("상태 정보가 없어 분포 차트를 표시할 수 없습니다.")

    st.markdown("---")

    # ---------- 최근 인터뷰 테이블 ---------- #
    st.subheader("🕒 최근 인터뷰 목록")

    # 화면에 간단히 보일 컬럼만 추려서 표시
    show_cols = []
    for col in ["id", "job_title", "candidate_name", "created_at", "status", "total_questions"]:
        if col in df.columns:
            show_cols.append(col)

    if show_cols:
        st.dataframe(
            df[show_cols].sort_values("created_at", ascending=False),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.write(df)
