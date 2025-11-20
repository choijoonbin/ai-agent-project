# app/components/insights.py

import os
from typing import Any, Dict, List

import requests
import streamlit as st
import pandas as pd
import altair as alt

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9898/api/v1")


# ---------- 공통 API ---------- #

def _get(url: str, *, timeout: int = 30) -> requests.Response:
    return requests.get(url, timeout=timeout)


def _post(url: str, payload: Dict[str, Any], *, timeout: int = 180) -> requests.Response:
    return requests.post(url, json=payload, timeout=timeout)


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


def call_insights_api(interview_id: int, use_mini: bool = True) -> Dict[str, Any]:
    url = f"{API_BASE_URL}/workflow/interview/insights"
    payload = {
        "interview_id": interview_id,
        "use_mini": use_mini,
    }
    resp = _post(url, payload, timeout=240)
    if resp.status_code != 200:
        raise RuntimeError(f"인사이트 API 오류: {resp.status_code} - {resp.text}")
    return resp.json()


# ---------- 차트 렌더링 ---------- #

def _render_contribution_chart(scores: Dict[str, Any]) -> None:
    if not scores:
        st.caption("기여도 스코어 정보가 없어 차트를 표시할 수 없습니다.")
        return

    rows = []
    for k, v in scores.items():
        try:
            val = float(v)
        except Exception:
            continue
        label = {
            "short_term_impact": "단기 기여도",
            "long_term_growth": "장기 성장성",
            "team_fit": "팀 적합도",
            "risk_level": "리스크 수준",
        }.get(k, k)
        rows.append({"항목": label, "점수": val})

    if not rows:
        st.caption("유효한 수치형 스코어가 없어 차트를 표시할 수 없습니다.")
        return

    df = pd.DataFrame(rows)
    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("항목:N", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("점수:Q", scale=alt.Scale(domain=[0, 5])),
            tooltip=["항목", "점수"],
        )
        .properties(height=260)
    )
    st.altair_chart(chart, use_container_width=True)


# ---------- 메인 페이지 ---------- #

def render_insights_page() -> None:
    st.title("📊 Candidate Insights")
    st.caption(
        "저장된 면접 결과를 기반으로, 후보자의 온보딩 전략과 조직 기여도/리스크를 요약해 줍니다."
    )

    # 최근 인터뷰 목록
    interviews = fetch_interview_list(limit=50)
    if not interviews:
        st.info("먼저 Studio에서 면접을 실행하고 저장한 후, 이 화면에서 인사이트를 확인할 수 있습니다.")
        return

    # 선택용 options 구성
    options = []
    option_labels = []
    for item in interviews:
        iid = item["id"]
        label = f"[ID {iid}] {item.get('job_title','')} - {item.get('candidate_name','')} / {item.get('created_at','')}"
        options.append(iid)
        option_labels.append(label)

    col_left, col_right = st.columns([1, 3])

    with col_left:
        st.subheader("🎯 대상 인터뷰 선택")

        # 기본값: 세션의 last_interview_id 가 있으면 그것을 우선
        last_id = st.session_state.get("last_interview_id")
        default_index = 0
        if last_id is not None:
            for i, iid in enumerate(options):
                if iid == last_id:
                    default_index = i
                    break

        selected_idx = st.selectbox(
            "인사이트를 볼 인터뷰를 선택하세요.",
            options=list(range(len(options))),
            format_func=lambda i: option_labels[i],
            index=default_index,
        )
        selected_id = options[selected_idx]

        st.markdown("---")
        st.subheader("⚙️ 옵션")

        use_mini = st.checkbox(
            "경량 모델 사용 (gpt-4o-mini)",
            value=st.session_state.get("cfg_use_mini", True),
            key="insights_use_mini",
        )

        if st.button("✨ 인사이트 생성/갱신", use_container_width=True):
            with st.spinner("LLM이 인사이트를 생성 중입니다..."):
                try:
                    resp = call_insights_api(selected_id, use_mini=use_mini)
                    insights = resp.get("insights", {})
                    st.session_state["insights_result"] = {
                        "interview_id": selected_id,
                        "insights": insights,
                    }
                    st.success("인사이트 생성이 완료되었습니다.")
                except Exception as e:
                    st.error(f"인사이트 생성 중 오류가 발생했습니다: {e}")

        st.markdown("---")
        st.caption("※ 좌측에서 인터뷰를 선택하고, '인사이트 생성/갱신' 버튼을 눌러주세요.")

    with col_right:
        st.subheader("📌 인사이트 상세")

        result = st.session_state.get("insights_result")
        if not result or result.get("interview_id") != selected_id:
            st.info("아직 이 인터뷰에 대한 인사이트가 없습니다. 좌측에서 '인사이트 생성/갱신'을 눌러주세요.")
            return

        insights = result.get("insights", {})

        soft_landing_plan = insights.get("soft_landing_plan", "")
        contribution_summary = insights.get("contribution_summary", "")
        contribution_scores = insights.get("contribution_scores", {})
        risk_factors = insights.get("risk_factors", []) or []
        growth_recommendations = insights.get("growth_recommendations", []) or []
        raw_text = insights.get("raw_text", "")

        # 상단 2열 레이아웃: 요약 + 차트
        top_left, top_right = st.columns([2, 3])

        with top_left:
            st.markdown("#### 🧭 Soft-landing 플랜 (입사 후 90일)")
            if soft_landing_plan:
                st.write(soft_landing_plan)
            else:
                st.caption("Soft-landing 플랜 정보가 없습니다.")

            st.markdown("#### 🧩 기여도 요약")
            if contribution_summary:
                st.write(contribution_summary)
            else:
                st.caption("기여도 요약 정보가 없습니다.")

        with top_right:
            st.markdown("#### 📈 기여도 & 리스크 스코어")
            _render_contribution_chart(contribution_scores)

        st.markdown("---")

        # 리스크 & 성장 추천
        col_risk, col_growth = st.columns(2)

        with col_risk:
            st.markdown("#### ⚠️ 리스크 & 주의 포인트")
            if risk_factors:
                for r in risk_factors:
                    st.markdown(f"- {r}")
            else:
                st.caption("특별히 언급된 리스크가 없습니다.")

        with col_growth:
            st.markdown("#### 🌱 성장/코칭 추천")
            if growth_recommendations:
                for g in growth_recommendations:
                    st.markdown(f"- {g}")
            else:
                st.caption("별도 성장 추천 정보가 없습니다.")

        if raw_text:
            st.markdown("---")
            with st.expander("🔍 원문 인사이트 응답 보기 (디버그용)"):
                st.write(raw_text)
